import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/pose_frame.dart';
import '../models/skeleton_topology.dart';

/// Connection lifecycle states surfaced to the UI.
enum SocketStatus {
  idle('Not connected'),
  connecting('Connecting…'),
  connected('Live'),
  reconnecting('Reconnecting…'),
  failed('Connection failed');

  const SocketStatus(this.label);
  final String label;

  bool get isLive => this == SocketStatus.connected;
}

/// ============================================================================
/// POSE SOCKET
/// ============================================================================
/// Transport to the Python inference server.
///
/// Design notes
/// ------------
/// * **Latest-frame-wins.** [sendFrame] refuses to queue when too many frames
///   are already unacknowledged. Buffering video on a Wi-Fi socket only converts
///   dropped frames into growing latency, which is far worse for a live
///   movement assessment — a clinician needs *now*, not a complete history.
/// * **Auto-reconnect with backoff.** Phones sleep radios and roam between APs;
///   a physio session should survive that without the user re-typing an IP.
/// * **Binary frames, text control.** Keeps the video path allocation-free and
///   makes control messages trivially debuggable.
/// ============================================================================
class PoseSocket {
  PoseSocket({this.maxFramesInFlight = 1});

  /// How many sent-but-unanswered frames are tolerated before we start skipping.
  ///
  /// ONE, not two. A second in-flight frame does not raise throughput — the
  /// server processes strictly one at a time — it only guarantees that the frame
  /// being analysed is already a full round trip old. With a single frame in
  /// flight the pipeline always works on the freshest pixels available, which is
  /// what keeps the skeleton on the body instead of behind it.
  final int maxFramesInFlight;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;

  final _frames = StreamController<PoseFrame>.broadcast();
  final _status = StreamController<SocketStatus>.broadcast();
  final _errors = StreamController<String>.broadcast();

  /// Decoded inference results, one per processed frame.
  Stream<PoseFrame> get frames => _frames.stream;

  /// Connection state changes.
  Stream<SocketStatus> get status => _status.stream;

  /// Human-readable problems worth showing in a snackbar.
  Stream<String> get errors => _errors.stream;

  SocketStatus _currentStatus = SocketStatus.idle;
  SocketStatus get currentStatus => _currentStatus;

  String? _url;
  int _seq = 0;
  int _inFlight = 0;
  bool _disposed = false;
  bool _manualClose = false;

  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;

  /// Round-trip latency of the last frame, measured phone-to-phone.
  Duration? lastRoundTrip;
  final Map<int, DateTime> _sentAt = <int, DateTime>{};

  /// Reported by the server in its `hello` message.
  String? serverVersion;

  // --------------------------------------------------------------------------
  // CONNECT / DISCONNECT
  // --------------------------------------------------------------------------

  /// Opens the socket. [url] may be `ws://host:port/ws`, `host:port` or `host`;
  /// missing pieces are filled in by [normaliseUrl].
  Future<void> connect(String url) async {
    if (_disposed) return;

    _manualClose = false;
    _url = normaliseUrl(url);
    await _open();
  }

  Future<void> _open() async {
    final url = _url;
    if (url == null || _disposed) return;

    _emitStatus(_reconnectAttempt == 0 ? SocketStatus.connecting : SocketStatus.reconnecting);

    await _teardownChannel();

    try {
      final channel = WebSocketChannel.connect(Uri.parse(url));
      _channel = channel;

      // `ready` throws on a refused connection, which lets us report a clear
      // failure instead of silently waiting for a stream that never emits.
      await channel.ready;

      _inFlight = 0;
      _sentAt.clear();
      _timedOut = 0;
      _reconnectAttempt = 0;
      _emitStatus(SocketStatus.connected);

      _subscription = channel.stream.listen(
        _onMessage,
        onError: (Object error) {
          _errors.add('Socket error: $error');
          _scheduleReconnect();
        },
        onDone: _scheduleReconnect,
        cancelOnError: false,
      );
    } catch (error) {
      _errors.add(_friendlyError(error, url));
      _emitStatus(SocketStatus.failed);
      _scheduleReconnect();
    }
  }

  /// Closes the socket and stops reconnecting.
  Future<void> disconnect() async {
    _manualClose = true;
    _reconnectTimer?.cancel();
    _reconnectAttempt = 0;
    await _teardownChannel();
    _emitStatus(SocketStatus.idle);
  }

  Future<void> _teardownChannel() async {
    await _subscription?.cancel();
    _subscription = null;
    try {
      await _channel?.sink.close();
    } catch (_) {
      // Already gone — nothing to do.
    }
    _channel = null;
  }

  void _scheduleReconnect() {
    if (_disposed || _manualClose) return;
    if (_reconnectTimer?.isActive ?? false) return;

    _reconnectAttempt++;
    _emitStatus(SocketStatus.reconnecting);

    // Capped exponential backoff: 0.5s, 1s, 2s, 4s, then every 5s. Fast enough
    // to feel instant after a brief Wi-Fi blip, slow enough not to spam a PC
    // that is genuinely switched off.
    final delayMs = switch (_reconnectAttempt) {
      1 => 500,
      2 => 1000,
      3 => 2000,
      4 => 4000,
      _ => 5000,
    };

    _reconnectTimer = Timer(Duration(milliseconds: delayMs), _open);
  }

  // --------------------------------------------------------------------------
  // OUTBOUND
  // --------------------------------------------------------------------------

  /// How long to wait for a reply before assuming it is never coming.
  ///
  /// With [maxFramesInFlight] at 1, a single unanswered frame closes the gate
  /// completely. That is the desired behaviour for backpressure — but only if a
  /// reply is guaranteed. It is not: the server can drop a frame it fails to
  /// process, and when it did, the client sent exactly one frame and then went
  /// silent forever, showing 0 fps behind a healthy green socket.
  ///
  /// 1500 ms is far longer than any legitimate round trip (measured at 118–207 ms)
  /// so this never fires during normal operation, but short enough that a lost
  /// reply costs a beat rather than the session.
  static const Duration replyTimeout = Duration(milliseconds: 1500);

  /// Number of replies that never arrived. Non-zero means the server is dropping
  /// frames; worth surfacing rather than silently absorbing.
  int _timedOut = 0;
  int get timedOutFrames => _timedOut;

  /// True when a new video frame would actually be transmitted. The frame pump
  /// checks this before doing any pixel work, so a saturated link costs nothing.
  bool get canSendFrame {
    if (!_currentStatus.isLive || _channel == null) return false;
    if (_inFlight < maxFramesInFlight) return true;

    // Gate is closed. Before honouring it, check the outstanding frames are
    // actually outstanding and not simply lost.
    _releaseTimedOutFrames();
    return _inFlight < maxFramesInFlight;
  }

  /// Reopens the in-flight gate for frames whose replies are overdue.
  void _releaseTimedOutFrames() {
    if (_sentAt.isEmpty) {
      // Nothing is genuinely outstanding, so the counter is stale. This is the
      // belt-and-braces case: it cannot drift without a bug elsewhere, but if it
      // does, the session recovers instead of stalling permanently.
      if (_inFlight > 0) _inFlight = 0;
      return;
    }

    final cutoff = DateTime.now().subtract(replyTimeout);
    final overdue = _sentAt.entries
        .where((e) => e.value.isBefore(cutoff))
        .map((e) => e.key)
        .toList(growable: false);
    if (overdue.isEmpty) return;

    for (final seq in overdue) {
      _sentAt.remove(seq);
      _inFlight = _inFlight > 0 ? _inFlight - 1 : 0;
      _timedOut++;
    }
  }

  /// Sends one video frame.
  ///
  /// Framing: `[uint32 LE header length][UTF-8 JSON header][pixel payload]`.
  /// A JSON header rather than a packed struct keeps the protocol extensible
  /// without versioning pain — the server ignores fields it does not know.
  bool sendFrame({
    required Uint8List payload,
    required int width,
    required int height,
    required String format,
    required int rotation,
    required bool mirror,
    required BodyMode mode,
  }) {
    if (!canSendFrame) return false;

    final seq = _seq++;
    final header = utf8.encode(jsonEncode(<String, dynamic>{
      'w': width,
      'h': height,
      'fmt': format,
      'rot': rotation,
      'mirror': mirror,
      'mode': mode.wire,
      'seq': seq,
    }));

    final message = Uint8List(4 + header.length + payload.length);
    final view = ByteData.view(message.buffer);
    view.setUint32(0, header.length, Endian.little);
    message.setRange(4, 4 + header.length, header);
    message.setRange(4 + header.length, message.length, payload);

    try {
      _channel!.sink.add(message);
    } catch (error) {
      _errors.add('Send failed: $error');
      _scheduleReconnect();
      return false;
    }

    _inFlight++;
    _sentAt[seq] = DateTime.now();

    // Bound the map. Unanswered sends are already capped by the in-flight gate,
    // so this only trims entries left behind by out-of-order or duplicate acks.
    if (_sentAt.length > 64) {
      final cutoff = DateTime.now().subtract(const Duration(seconds: 5));
      _sentAt.removeWhere((_, sent) => sent.isBefore(cutoff));
    }

    return true;
  }

  void setMode(BodyMode mode) =>
      _sendControl(<String, dynamic>{'type': 'set_mode', 'mode': mode.wire});

  void setFilter(String filterType) =>
      _sendControl(<String, dynamic>{'type': 'set_filter', 'filter': filterType});

  /// Turns hand tracking off ON THE SERVER, not just in the overlay.
  ///
  /// This matters for throughput: MediaPipe Hands is the most expensive stage in
  /// the graph, so hiding the drawing while the server keeps computing it would
  /// waste the entire cost for no visible benefit.
  void setHands({required bool on}) =>
      _sendControl(<String, dynamic>{'type': 'set_hands', 'on': on});

  /// Switches the pose model between fast (0) and balanced (1).
  void setComplexity(int complexity) =>
      _sendControl(<String, dynamic>{'type': 'set_complexity', 'complexity': complexity});

  void resetRom() => _sendControl(<String, dynamic>{'type': 'reset_rom'});

  void requestScreenshot() => _sendControl(<String, dynamic>{'type': 'screenshot'});

  void setRecording({required bool on}) =>
      _sendControl(<String, dynamic>{'type': 'record', 'on': on});

  void _sendControl(Map<String, dynamic> payload) {
    if (!_currentStatus.isLive || _channel == null) return;
    try {
      _channel!.sink.add(jsonEncode(payload));
    } catch (error) {
      _errors.add('Control send failed: $error');
    }
  }

  // --------------------------------------------------------------------------
  // INBOUND
  // --------------------------------------------------------------------------

  void _onMessage(dynamic raw) {
    if (raw is! String) return;

    Map<String, dynamic> json;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      json = Map<String, dynamic>.from(decoded);
    } catch (_) {
      return;
    }

    switch (json['type']) {
      case 'pose':
        _inFlight = _inFlight > 0 ? _inFlight - 1 : 0;

        final seq = (json['seq'] as num?)?.toInt();
        if (seq != null) {
          final sent = _sentAt.remove(seq);
          if (sent != null) lastRoundTrip = DateTime.now().difference(sent);
        }

        if (!_frames.isClosed) _frames.add(PoseFrame.fromJson(json));

      case 'error':
        {
          // The server failed on a frame it will therefore never answer. Free
          // the in-flight slot — otherwise one server-side fault silences the
          // client permanently — and show the reason rather than leaving a
          // blank skeleton and no explanation.
          _inFlight = _inFlight > 0 ? _inFlight - 1 : 0;
          _sentAt.clear();
          final detail = json['message'] as String?;
          final stage = json['stage'] as String? ?? 'server';
          if (!_errors.isClosed) {
            _errors.add('Server $stage error: ${detail ?? 'unknown'}');
          }
        }

      case 'hello':
        serverVersion = json['version'] as String?;

      case 'ack':
      case 'pong':
        break;
    }
  }

  void _emitStatus(SocketStatus next) {
    if (_currentStatus == next) return;
    _currentStatus = next;
    if (!_status.isClosed) _status.add(next);
  }

  Future<void> dispose() async {
    _disposed = true;
    _manualClose = true;
    _reconnectTimer?.cancel();
    await _teardownChannel();
    await _frames.close();
    await _status.close();
    await _errors.close();
  }

  // --------------------------------------------------------------------------
  // HELPERS
  // --------------------------------------------------------------------------

  /// Accepts what a user would realistically type and produces a valid ws URL.
  ///
  ///   "192.168.1.7"            -> ws://192.168.1.7:8765/ws
  ///   "192.168.1.7:8765"       -> ws://192.168.1.7:8765/ws
  ///   "ws://192.168.1.7:8765"  -> ws://192.168.1.7:8765/ws
  static String normaliseUrl(String input, {int defaultPort = 8765}) {
    var value = input.trim();
    if (value.isEmpty) return 'ws://127.0.0.1:$defaultPort/ws';

    if (!value.contains('://')) value = 'ws://$value';
    value = value.replaceFirst(RegExp(r'^http://'), 'ws://');
    value = value.replaceFirst(RegExp(r'^https://'), 'wss://');

    var uri = Uri.parse(value);
    if (!uri.hasPort) uri = uri.replace(port: defaultPort);
    if (uri.path.isEmpty || uri.path == '/') uri = uri.replace(path: '/ws');

    return uri.toString();
  }

  /// The matching `http://host:port/health` URL, for the pre-flight check.
  static String healthUrl(String input, {int defaultPort = 8765}) {
    final ws = Uri.parse(normaliseUrl(input, defaultPort: defaultPort));
    return ws.replace(scheme: ws.scheme == 'wss' ? 'https' : 'http', path: '/health').toString();
  }

  String _friendlyError(Object error, String url) {
    final text = error.toString();
    final host = Uri.tryParse(url)?.host ?? url;

    if (text.contains('refused') || text.contains('ECONNREFUSED')) {
      return 'Nothing is listening on $host. Is ws_server.py running?';
    }
    if (text.contains('timed out') || text.contains('ETIMEDOUT')) {
      return 'No response from $host. Check both devices are on the same Wi-Fi '
          'and that Windows Firewall allows Python on private networks.';
    }
    if (text.contains('Failed host lookup')) {
      return 'Could not resolve $host. Enter the PC\'s LAN IP address.';
    }
    return 'Could not connect to $host: $text';
  }
}

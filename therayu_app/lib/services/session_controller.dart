import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../models/pose_frame.dart';
import '../models/skeleton_topology.dart';
import 'camera_streamer.dart';
import 'pose_interpolator.dart';
import 'pose_socket.dart';

/// ============================================================================
/// SESSION CONTROLLER
/// ============================================================================
/// The one object the UI listens to. It owns the socket and the camera, keeps
/// the latest [PoseFrame], and persists the server address and body mode so a
/// returning user is one tap from a live session.
///
/// Kept as a plain [ChangeNotifier] rather than pulling in a state-management
/// package: there is exactly one screen and one stream of truth, so anything
/// heavier would be ceremony.
/// ============================================================================
class SessionController extends ChangeNotifier {
  SessionController() {
    _socket = PoseSocket();
    _camera = CameraStreamer(socket: _socket);

    _frameSub = _socket.frames.listen(_onPoseFrame);
    _statusSub = _socket.status.listen(_onSocketStatus);
    _errorSub = _socket.errors.listen(_onSocketError);

    _camera.addListener(notifyListeners);

    _supervisor = Timer.periodic(const Duration(seconds: 1), (_) => _reconcile());
  }

  /// Brings the camera into line with what the session needs.
  void _reconcile() {
    if (!_status.isLive) return;
    if (!_camera.isReady) return;

    if (!_camera.isStreaming) {
      // Either the first start() lost the race with camera initialisation, or
      // streaming stopped unexpectedly. Either way, ask again.
      _camera.start();
    }
  }

  static const _prefServerKey = 'server_url';
  static const _prefModeKey = 'body_mode';
  static const _prefMirrorKey = 'mirror_selfie';
  static const _prefQualityKey = 'capture_quality';

  late final PoseSocket _socket;
  late final CameraStreamer _camera;

  StreamSubscription<PoseFrame>? _frameSub;
  StreamSubscription<SocketStatus>? _statusSub;
  StreamSubscription<String>? _errorSub;

  /// Reconciles "should be streaming" against "is streaming", once a second.
  ///
  /// Event-driven start-up alone proved fragile: whichever of the socket and the
  /// camera became ready second, the other's one-shot callback had already run
  /// and done nothing. A cheap periodic check makes the pipeline self-healing
  /// regardless of ordering, and also recovers from a camera that drops out
  /// mid-session.
  Timer? _supervisor;

  /// When the socket most recently went live, used to give startup a grace
  /// period before declaring capture stalled.
  DateTime? _liveSince;

  CameraStreamer get camera => _camera;
  PoseSocket get socket => _socket;

  /// Smooths the ~10 fps landmark stream up to display rate. See
  /// [PoseInterpolator] for why angles are deliberately left alone.
  final PoseInterpolator poseInterpolator = PoseInterpolator();

  // --------------------------------------------------------------------------
  // STATE
  // --------------------------------------------------------------------------

  PoseFrame _frame = const PoseFrame.empty();
  PoseFrame get frame => _frame;

  SocketStatus _status = SocketStatus.idle;
  SocketStatus get status => _status;

  BodyMode _bodyMode = BodyMode.fullBody;
  BodyMode get bodyMode => _bodyMode;

  String _serverUrl = '';
  String get serverUrl => _serverUrl;

  String? _message;
  String? get message => _message;

  /// Hand tracking defaults OFF on web.
  ///
  /// MediaPipe Hands is the most expensive stage in the graph, and the browser
  /// capture path already has less headroom than Android. Starting without it
  /// gives a responsive skeleton by default; it can be enabled from Controls
  /// when finger tracking is actually the point.
  bool _showHands = !kIsWeb;
  bool _showBones = true;
  bool _showJoints = true;
  bool _showArcs = true;
  bool _showAngleCards = true;
  bool _showConfidenceBadge = true;

  bool get showHands => _showHands;
  bool get showBones => _showBones;
  bool get showJoints => _showJoints;
  bool get showArcs => _showArcs;
  bool get showAngleCards => _showAngleCards;
  bool get showConfidenceBadge => _showConfidenceBadge;

  bool _isRecording = false;
  bool get isRecording => _isRecording;

  DateTime? _sessionStart;

  /// Wall-clock length of the current session, for the header timer.
  Duration get sessionDuration =>
      _sessionStart == null ? Duration.zero : DateTime.now().difference(_sessionStart!);

  /// Phone-to-phone round trip of the last frame, which includes Wi-Fi latency
  /// and is therefore the number that actually reflects what the user perceives.
  Duration? get roundTrip => _socket.lastRoundTrip;

  /// Frames per second the phone is managing to push through the whole loop.
  double get pipelineFps => _camera.sendFps;

  /// True when the socket is live but no frames are actually reaching it.
  ///
  /// This state used to be invisible: a green connection dot, no error, and the
  /// only clue a frame counter stuck at zero. It is called out explicitly now
  /// because "connected but sending nothing" and "working" looked identical.
  bool get captureStalled {
    if (!_status.isLive) return false;
    if (_camera.framesSent > 0) return false;

    // Deliberately NOT gated on isStreaming. The very failure this is meant to
    // report — streaming never having started — would have made that condition
    // false and suppressed the warning entirely, which is exactly what happened.
    final since = _liveSince;
    if (since == null) return false;
    return DateTime.now().difference(since) > const Duration(seconds: 4);
  }

  /// Why capture is producing nothing, when it is.
  String? get captureDiagnosis {
    if (!_camera.isReady) return 'Camera not ready yet.';
    if (!_camera.isStreaming) return 'Camera stream not started — retrying.';
    return _camera.captureNote ?? _camera.captureFailure;
  }

  // --------------------------------------------------------------------------
  // BOOTSTRAP
  // --------------------------------------------------------------------------

  Future<void> loadPreferences() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _serverUrl = prefs.getString(_prefServerKey) ?? '';

      // In Chrome the app and the server are on the same machine, so there is
      // exactly one correct address. Prefilling it removes the single most
      // error-prone step of setup.
      if (_serverUrl.isEmpty && kIsWeb) _serverUrl = 'localhost:8765';
      _bodyMode = BodyMode.fromWire(prefs.getString(_prefModeKey));
      _camera
        ..bodyMode = _bodyMode
        ..setMirror(mirror: prefs.getBool(_prefMirrorKey) ?? true);

      final qualityName = prefs.getString(_prefQualityKey);
      if (qualityName != null) {
        final match = CaptureQuality.values
            .where((q) => q.name == qualityName)
            .firstOrNull;
        if (match != null) await _camera.setQuality(match);
      }
    } catch (_) {
      // A prefs failure must never block the app from starting.
    }
    notifyListeners();
  }

  Future<void> _persist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefServerKey, _serverUrl);
      await prefs.setString(_prefModeKey, _bodyMode.wire);
      await prefs.setBool(_prefMirrorKey, _camera.mirrorSelfie);
      await prefs.setString(_prefQualityKey, _camera.quality.name);
    } catch (_) {
      // Non-fatal.
    }
  }

  Future<void> initialiseCamera() => _camera.initialise();

  // --------------------------------------------------------------------------
  // CONNECTION
  // --------------------------------------------------------------------------

  /// Pre-flight HTTP check. Distinguishes "wrong address / firewall" from
  /// "address is right but the WebSocket handshake failed", which is by far the
  /// most common setup confusion.
  Future<({bool ok, String detail})> testConnection(String url) async {
    final target = PoseSocket.healthUrl(url);
    try {
      final response = await http
          .get(Uri.parse(target))
          .timeout(const Duration(seconds: 4));

      if (response.statusCode == 200) {
        return (ok: true, detail: 'Server reachable at $target');
      }
      return (ok: false, detail: 'Server replied ${response.statusCode}.');
    } on TimeoutException {
      return (
        ok: false,
        detail: 'Timed out. Same Wi-Fi? Windows Firewall allowing Python on '
            'private networks?'
      );
    } catch (e) {
      return (ok: false, detail: 'Unreachable: $e');
    }
  }

  Future<void> connect(String url) async {
    _serverUrl = url.trim();
    _message = null;
    notifyListeners();

    await _socket.connect(_serverUrl);
    await _persist();
  }

  Future<void> disconnect() async {
    await _camera.stop();
    await _socket.disconnect();
    _isRecording = false;
    _sessionStart = null;
    _liveSince = null;
    _frame = const PoseFrame.empty();
    poseInterpolator.reset();
    await WakelockPlus.disable();
    notifyListeners();
  }

  void _onSocketStatus(SocketStatus status) {
    _status = status;

    if (status.isLive) {
      _sessionStart ??= DateTime.now();
      _liveSince ??= DateTime.now();
      // Push the persisted mode immediately so the server does not spend the
      // first frames in the wrong profile.
      _socket.setMode(_bodyMode);
      _socket.setHands(on: _showHands);
      _camera.start();
      WakelockPlus.enable();
    } else {
      if (status == SocketStatus.idle || status == SocketStatus.failed) {
        WakelockPlus.disable();
      }
    }

    notifyListeners();
  }

  void _onSocketError(String error) {
    _message = error;
    notifyListeners();
  }

  void _onPoseFrame(PoseFrame frame) {
    _frame = frame;
    _isRecording = frame.isRecording;

    // Landmarks go to the interpolator, which the painter samples at display
    // rate. The frame itself still drives the numeric readouts directly.
    poseInterpolator.push(frame.landmarks, at: DateTime.now());

    notifyListeners();
  }

  void clearMessage() {
    if (_message == null) return;
    _message = null;
    notifyListeners();
  }

  // --------------------------------------------------------------------------
  // SESSION CONTROLS
  // --------------------------------------------------------------------------

  void setBodyMode(BodyMode mode) {
    if (mode == _bodyMode) return;
    _bodyMode = mode;
    _camera.bodyMode = mode;
    _socket.setMode(mode);
    _persist();
    notifyListeners();
  }

  void setFilter(String filterType) {
    _socket.setFilter(filterType);
    notifyListeners();
  }

  /// Fast mode drops MediaPipe pose complexity from 1 to 0.
  void setFastMode({required bool fast}) {
    _socket.setComplexity(fast ? 0 : 1);
    _message = fast
        ? 'Fast pose model — lower latency, slightly less precise landmarks.'
        : 'Balanced pose model.';
    notifyListeners();
  }

  void resetRom() {
    _socket.resetRom();
    _sessionStart = DateTime.now();
    _message = 'Range-of-motion history reset.';
    notifyListeners();
  }

  void captureScreenshot() {
    _socket.requestScreenshot();
    _message = 'Screenshot saved on the PC (output/screenshots).';
    notifyListeners();
  }

  void toggleRecording() {
    final next = !_isRecording;
    _socket.setRecording(on: next);
    _isRecording = next;
    _message = next
        ? 'Recording to output/recordings on the PC.'
        : 'Recording stopped and saved.';
    notifyListeners();
  }

  Future<void> switchCamera() async {
    await _camera.switchCamera();
    await _persist();
    notifyListeners();
  }

  Future<void> setQuality(CaptureQuality quality) async {
    await _camera.setQuality(quality);
    await _persist();
    notifyListeners();
  }

  void setMirror({required bool mirror}) {
    _camera.setMirror(mirror: mirror);
    _persist();
    notifyListeners();
  }

  void toggleOverlay({
    bool? hands,
    bool? bones,
    bool? joints,
    bool? arcs,
    bool? angleCards,
    bool? confidenceBadge,
  }) {
    // Hiding hands also stops the server computing them, which is where the
    // cost actually is. Without this the toggle would be cosmetic and the frame
    // rate would not improve at all.
    if (hands != null && hands != _showHands) {
      _showHands = hands;
      _socket.setHands(on: hands);
    }
    _showBones = bones ?? _showBones;
    _showJoints = joints ?? _showJoints;
    _showArcs = arcs ?? _showArcs;
    _showAngleCards = angleCards ?? _showAngleCards;
    _showConfidenceBadge = confidenceBadge ?? _showConfidenceBadge;
    notifyListeners();
  }

  // --------------------------------------------------------------------------
  // APP LIFECYCLE
  // --------------------------------------------------------------------------

  /// Releases the camera when the app is backgrounded — Android will revoke it
  /// anyway, and holding it produces a black preview on resume.
  Future<void> handlePause() async {
    await _camera.stop();
    await WakelockPlus.disable();
  }

  Future<void> handleResume() async {
    if (_status.isLive) {
      await _camera.start();
      await WakelockPlus.enable();
    }
  }

  @override
  void dispose() {
    // Synchronous signature to match ChangeNotifier. Subscriptions are detached
    // first so nothing can call notifyListeners() after super.dispose(), then the
    // async transport teardown runs unawaited.
    _supervisor?.cancel();
    _frameSub?.cancel();
    _statusSub?.cancel();
    _errorSub?.cancel();
    _camera.removeListener(notifyListeners);
    poseInterpolator.dispose();
    _camera.dispose();
    _socket.dispose();
    WakelockPlus.disable();
    super.dispose();
  }
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../models/pose_frame.dart';
import '../models/records.dart';
import '../models/skeleton_topology.dart';
import 'camera_streamer.dart';
import 'records_api.dart';
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
    _recordsSub = _socket.records.listen(_onRecordsMessage);

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
  StreamSubscription<Map<String, dynamic>>? _recordsSub;

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

  /// REST client for patient administration. Shares the address the user typed
  /// for the socket, so the two can never point at different machines.
  final RecordsApi api = RecordsApi();

  // --------------------------------------------------------------------------
  // PATIENT RECORDS STATE
  // --------------------------------------------------------------------------

  /// Whether the connected server actually has the records API. An older build
  /// of the server still runs the live view perfectly; the patient features are
  /// simply hidden rather than throwing when tapped.
  bool _recordsAvailable = false;
  bool get recordsAvailable => _recordsAvailable;

  Patient? _patient;
  Patient? get patient => _patient;

  TodaysPlan? _plan;
  TodaysPlan? get plan => _plan;

  int? _recordsSessionId;
  int? get recordsSessionId => _recordsSessionId;
  bool get inPatientSession => _recordsSessionId != null;

  int _dayIndex = 1;
  int get dayIndex => _dayIndex;

  /// The exercise currently being recorded, if any.
  PlannedExercise? _activeExercise;
  PlannedExercise? get activeExercise => _activeExercise;
  bool get exerciseRunning => _activeExercise != null;

  /// Codes of exercises already completed this session, so the plan list can
  /// tick them off and the runner knows what is left.
  final Set<int> _completedExerciseIds = <int>{};
  Set<int> get completedExerciseIds => Set.unmodifiable(_completedExerciseIds);

  /// The result of the exercise that just finished, shown in a sheet.
  ExerciseResult? _lastResult;
  ExerciseResult? get lastResult => _lastResult;
  void clearLastResult() {
    _lastResult = null;
    notifyListeners();
  }

  /// Populated when the whole session is closed out.
  Map<String, dynamic>? _sessionSummary;
  Map<String, dynamic>? get sessionSummary => _sessionSummary;
  void clearSessionSummary() {
    _sessionSummary = null;
    notifyListeners();
  }

  String? _recordsError;
  String? get recordsError => _recordsError;

  /// Live value of the joint this exercise is scored on, straight from the
  /// current frame. Null when nothing is being measured.
  double? get activeJointValue {
    final ex = _activeExercise;
    if (ex == null) return null;
    final v = _frame.angles[ex.primaryJoint];
    return v is num && v > 0 ? v.toDouble() : null;
  }

  /// Reps the server has counted in the current exercise.
  int get activeReps => _frame.exerciseReps;

  /// How far through the prescribed work the patient is, 0..1.
  double get exerciseProgress {
    final ex = _activeExercise;
    if (ex == null) return 0;
    if (ex.isHold) {
      final target = ex.targetHoldSec;
      if (target == null || target <= 0) return 0;
      return (_holdSeconds / target).clamp(0.0, 1.0);
    }
    final target = ex.targetReps;
    if (target == null || target <= 0) return 0;
    return (activeReps / target).clamp(0.0, 1.0);
  }

  /// Seconds the patient has been inside the target band on a HOLD exercise.
  /// Tracked here only for the on-screen ring; the authoritative figure is
  /// computed server-side and stored with the result.
  double _holdSeconds = 0;
  double get holdSeconds => _holdSeconds;
  DateTime? _lastHoldTick;

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

  /// Records the address without opening the socket.
  ///
  /// The patient screens talk REST, not WebSocket, so they need the address
  /// resolved before any video starts — a clinician browsing the caseload has
  /// no reason to have the camera streaming.
  void setServerUrl(String url) {
    _serverUrl = url.trim();
    api.configureFromSocketUrl(_serverUrl);
    _persist();
    notifyListeners();
  }

  Future<void> connect(String url) async {
    _serverUrl = url.trim();
    api.configureFromSocketUrl(_serverUrl);
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
    _recordsSessionId = null;
    _activeExercise = null;
    _frame = const PoseFrame.empty();
    poseInterpolator.reset();
    await WakelockPlus.disable();
    notifyListeners();
  }

  /// Advances the on-screen hold timer while the patient is inside the band.
  ///
  /// Driven by frame arrival rather than a wall clock so it cannot keep counting
  /// when tracking has dropped out — a hold only counts while the joint is
  /// actually being measured.
  void _tickHold(PoseFrame frame) {
    final ex = _activeExercise;
    if (ex == null || !ex.isHold) {
      _lastHoldTick = null;
      return;
    }

    final value = frame.angles[ex.primaryJoint];
    final now = DateTime.now();
    final inBand = value is num &&
        value > 0 &&
        (ex.bandMinDeg == null || value >= ex.bandMinDeg!) &&
        (ex.bandMaxDeg == null || value <= ex.bandMaxDeg!);

    if (inBand && frame.telemetry.isReady) {
      final last = _lastHoldTick;
      if (last != null) {
        final dt = now.difference(last).inMilliseconds / 1000.0;
        if (dt > 0 && dt < 1.0) _holdSeconds += dt;
      }
      _lastHoldTick = now;
    } else {
      _lastHoldTick = null;
    }
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

  // --------------------------------------------------------------------------
  // PATIENT RECORDS ACTIONS
  // --------------------------------------------------------------------------

  /// Checks whether this server can store records, and points the REST client
  /// at the same host as the socket.
  Future<void> refreshRecordsAvailability() async {
    api.configureFromSocketUrl(_serverUrl);
    _recordsAvailable = await api.isAvailable();
    notifyListeners();
  }

  /// Loads a patient and their prescription without starting anything.
  Future<void> selectPatient(Patient patient) async {
    _patient = patient;
    _recordsError = null;
    notifyListeners();
    try {
      final plan = await api.todaysPlan(patient.id);
      _plan = plan;
      _dayIndex = plan.dayIndex;
    } on RecordsApiException catch (e) {
      _recordsError = e.message;
    }
    notifyListeners();
  }

  void clearPatient() {
    _patient = null;
    _plan = null;
    _recordsSessionId = null;
    _activeExercise = null;
    _completedExerciseIds.clear();
    notifyListeners();
  }

  /// Opens a records session on the server. Must be live: the recorder attaches
  /// to the same PhysioSession that is processing this client's video.
  void beginPatientSession() {
    final patient = _patient;
    if (patient == null || !_status.isLive) return;
    _completedExerciseIds.clear();
    _socket.startRecordsSession(patient.id);
  }

  void startExercise(PlannedExercise exercise) {
    if (!_status.isLive || !inPatientSession) return;
    _holdSeconds = 0;
    _lastHoldTick = null;
    _socket.startExercise(exercise.exerciseId, sequence: exercise.sequence);
  }

  void stopExercise({bool aborted = false}) {
    if (_activeExercise == null) return;
    _socket.stopExercise(aborted: aborted);
  }

  void endPatientSession({String? notes}) {
    if (!inPatientSession) return;
    _socket.endRecordsSession(notes: notes);
  }

  /// Records how the exercise felt. Optional, and deliberately non-blocking:
  /// a failed save must not stand between the patient and the next movement.
  Future<void> submitPainScore(int resultId, int pain) async {
    try {
      await api.saveReported(resultId, painScore: pain);
    } on RecordsApiException catch (e) {
      _recordsError = e.message;
      notifyListeners();
    }
  }

  void _onRecordsMessage(Map<String, dynamic> msg) {
    switch (msg['type']) {
      case 'session_started':
        _recordsSessionId = (msg['session_id'] as num?)?.toInt();
        _dayIndex = (msg['day_index'] as num?)?.toInt() ?? 1;
        _recordsError = null;
        final list = (msg['exercises'] as List?) ?? const [];
        if (list.isNotEmpty) {
          _plan = TodaysPlan(
            patient: _patient!,
            exercises: list
                .map((e) => PlannedExercise.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList(),
            conditionName: msg['condition'] as String?,
            dayIndex: _dayIndex,
          );
        }

      case 'exercise_started':
        _activeExercise = PlannedExercise.fromJson(Map<String, dynamic>.from(msg));
        _holdSeconds = 0;
        _lastHoldTick = null;
        _recordsError = null;

        // Keep the pose profile aligned with what the exercise measures — the
        // server switched its own mode, and the client must follow or the
        // skeleton and the guidance will describe different body regions.
        final mode = BodyMode.fromWire(msg['body_mode'] as String?);
        if (mode != _bodyMode) {
          _bodyMode = mode;
          _camera.bodyMode = mode;
        }

      case 'exercise_saved':
        final finished = _activeExercise;
        _activeExercise = null;
        _holdSeconds = 0;
        if (finished != null) {
          _completedExerciseIds.add(finished.exerciseId);
        }
        _lastResult = ExerciseResult.fromSaved(
          Map<String, dynamic>.from(msg),
          finished?.name ?? 'Exercise',
        );

      case 'session_ended':
        _sessionSummary = Map<String, dynamic>.from(msg);
        _recordsSessionId = null;
        _activeExercise = null;

      case 'records_error':
        _recordsError = msg['message']?.toString() ?? 'Records error';
        _activeExercise = null;
    }
    notifyListeners();
  }

  void _onSocketError(String error) {
    _message = error;
    notifyListeners();
  }

  void _onPoseFrame(PoseFrame frame) {
    _frame = frame;
    _tickHold(frame);
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
    _recordsSub?.cancel();
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

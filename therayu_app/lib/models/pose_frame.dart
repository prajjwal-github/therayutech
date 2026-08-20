import 'skeleton_topology.dart';

/// ============================================================================
/// WIRE MODELS
/// ============================================================================
/// Typed views over the JSON the Python server sends. Parsing is defensive on
/// purpose: the clinical engine intentionally emits three different "no value"
/// states and the UI must be able to tell them apart.
///
///   null            -> low confidence, render "TRACKING..."
///   "SIDE VIEW REQ" -> sagittal shoulder flexion needs a side view
///   0.0 with        -> framing invalid; the pipeline zeroes every angle rather
///   is_ready=false     than report a number it cannot stand behind
/// ============================================================================

/// A single landmark in normalised frame coordinates (0..1, already upright and
/// already mirrored by the server).
class Landmark {
  const Landmark({
    required this.x,
    required this.y,
    required this.z,
    required this.visibility,
  });

  factory Landmark.fromJson(Map<String, dynamic> json) => Landmark(
        x: _toDouble(json['x']) ?? 0,
        y: _toDouble(json['y']) ?? 0,
        z: _toDouble(json['z']) ?? 0,
        visibility: _toDouble(json['v']) ?? 0,
      );

  final double x;
  final double y;
  final double z;
  final double visibility;
}

/// Camera framing / performance telemetry — the `telemetry` dict from
/// `RealTimeInferencePipeline.process_frame`.
class Telemetry {
  const Telemetry({
    required this.personDetected,
    required this.isReady,
    required this.guidanceMessage,
    required this.statusBadge,
    required this.overallConfidence,
    required this.latencyMs,
    required this.serverFps,
    required this.filterType,
    required this.handsDetected,
    required this.inferMs,
    required this.analysisMs,
    required this.handsOn,
    required this.complexity,
  });

  factory Telemetry.fromJson(Map<String, dynamic> json) => Telemetry(
        personDetected: json['person_detected'] == true,
        isReady: json['is_ready'] == true,
        guidanceMessage:
            (json['guidance_message'] as String?) ?? 'Waiting for full body detection...',
        statusBadge: (json['status_badge'] as String?) ?? 'No Person Detected',
        overallConfidence: _toDouble(json['overall_confidence']) ?? 0,
        latencyMs: _toDouble(json['latency_ms']) ?? 0,
        serverFps: _toDouble(json['fps']) ?? 0,
        filterType: (json['filter_type'] as String?) ?? 'one_euro',
        handsDetected: json['hands_detected'] == true,
        inferMs: _toDouble(json['infer_ms']) ?? 0,
        analysisMs: _toDouble(json['analysis_ms']) ?? 0,
        handsOn: json['hands_on'] != false,
        complexity: (json['complexity'] as num?)?.toInt() ?? 1,
      );

  const Telemetry.empty()
      : personDetected = false,
        isReady = false,
        guidanceMessage = 'Waiting for full body detection...',
        statusBadge = 'No Person Detected',
        overallConfidence = 0,
        latencyMs = 0,
        serverFps = 0,
        filterType = 'one_euro',
        handsDetected = false,
        inferMs = 0,
        analysisMs = 0,
        handsOn = true,
        complexity = 1;

  final bool personDetected;

  /// True only when every landmark the active profile requires is visible and
  /// inside the 2%–98% frame margin. Drives the "no fake angles" gate.
  final bool isReady;

  final String guidanceMessage;
  final String statusBadge;
  final double overallConfidence;
  final double latencyMs;
  final double serverFps;
  final String filterType;
  final bool handsDetected;

  /// Milliseconds spent inside the MediaPipe pipeline for this frame — the
  /// dominant term in end-to-end latency, and the one worth attacking first.
  final double inferMs;

  /// Milliseconds spent in the ROM / quality analysis stage.
  final double analysisMs;

  /// Whether hand tracking is running on the server.
  final bool handsOn;

  /// MediaPipe pose model complexity currently in use (0 fast, 1 balanced).
  final int complexity;

  /// Strips the emoji the Python side prefixes onto badge strings, since the
  /// Flutter UI shows a coloured dot instead.
  String get cleanStatusBadge =>
      statusBadge.replaceAll(RegExp(r'[✅⚠️]'), '').trim();
}

/// Clinical assessment output — the `physio_telemetry` dict from
/// `PhysiotherapyAnalysisEngine.analyze_frame`.
class PhysioAssessment {
  const PhysioAssessment({
    required this.movementQualityPct,
    required this.clinicalFeedback,
    required this.symmetryStatus,
    required this.cogShiftStatus,
    required this.romSummary,
  });

  factory PhysioAssessment.fromJson(Map<String, dynamic> json) {
    final romRaw = json['rom_summary'];
    final rom = <String, RomRecord>{};
    if (romRaw is Map) {
      romRaw.forEach((key, value) {
        if (value is Map) {
          rom['$key'] = RomRecord.fromJson(Map<String, dynamic>.from(value));
        }
      });
    }

    final feedbackRaw = json['clinical_feedback'];
    final feedback = <String>[
      if (feedbackRaw is List)
        for (final item in feedbackRaw)
          if (item is String && item.trim().isNotEmpty) item,
    ];

    return PhysioAssessment(
      movementQualityPct: _toDouble(json['movement_quality_pct']) ?? 0,
      clinicalFeedback: feedback,
      symmetryStatus: (json['symmetry_status'] as String?) ?? 'WAITING',
      cogShiftStatus: (json['cog_shift_status'] as String?) ?? 'WAITING',
      romSummary: rom,
    );
  }

  const PhysioAssessment.empty()
      : movementQualityPct = 0,
        clinicalFeedback = const <String>[],
        symmetryStatus = 'WAITING',
        cogShiftStatus = 'WAITING',
        romSummary = const <String, RomRecord>{};

  final double movementQualityPct;
  final List<String> clinicalFeedback;
  final String symmetryStatus;
  final String cogShiftStatus;
  final Map<String, RomRecord> romSummary;

  bool get isSymmetric => symmetryStatus == 'NORMAL';
  bool get isBalanced => cogShiftStatus == 'BALANCED';
}

/// Per-joint range-of-motion record accumulated over the session.
class RomRecord {
  const RomRecord({required this.min, required this.max, required this.current});

  factory RomRecord.fromJson(Map<String, dynamic> json) => RomRecord(
        min: _toDouble(json['min']) ?? 0,
        max: _toDouble(json['max']) ?? 0,
        current: _toDouble(json['current']) ?? 0,
      );

  final double min;
  final double max;
  final double current;

  double get sweep => (max - min).clamp(0, 360).toDouble();
  bool get hasData => max > 0;
}

/// One fully-parsed inference result.
class PoseFrame {
  const PoseFrame({
    required this.seq,
    required this.landmarks,
    required this.angles,
    required this.telemetry,
    required this.physio,
    required this.trackId,
    required this.bodyMode,
    required this.isRecording,
    required this.frameWidth,
    required this.frameHeight,
  });

  factory PoseFrame.fromJson(Map<String, dynamic> json) {
    final lmRaw = json['landmarks'];
    final landmarks = <String, Landmark>{};
    if (lmRaw is Map) {
      lmRaw.forEach((key, value) {
        if (value is Map) {
          landmarks['$key'] = Landmark.fromJson(Map<String, dynamic>.from(value));
        }
      });
    }

    final anglesRaw = json['angles'];
    final angles = <String, dynamic>{};
    if (anglesRaw is Map) {
      anglesRaw.forEach((key, value) => angles['$key'] = value);
    }

    return PoseFrame(
      seq: (json['seq'] as num?)?.toInt() ?? -1,
      landmarks: landmarks,
      angles: angles,
      telemetry: Telemetry.fromJson(
        json['telemetry'] is Map
            ? Map<String, dynamic>.from(json['telemetry'] as Map)
            : const <String, dynamic>{},
      ),
      physio: PhysioAssessment.fromJson(
        json['physio'] is Map
            ? Map<String, dynamic>.from(json['physio'] as Map)
            : const <String, dynamic>{},
      ),
      trackId: (json['track_id'] as num?)?.toInt() ?? 1,
      bodyMode: BodyMode.fromWire(json['body_mode'] as String?),
      isRecording: json['is_recording'] == true,
      frameWidth: (json['frame_w'] as num?)?.toInt() ?? 0,
      frameHeight: (json['frame_h'] as num?)?.toInt() ?? 0,
    );
  }

  const PoseFrame.empty()
      : seq = -1,
        landmarks = const <String, Landmark>{},
        angles = const <String, dynamic>{},
        telemetry = const Telemetry.empty(),
        physio = const PhysioAssessment.empty(),
        trackId = 1,
        bodyMode = BodyMode.fullBody,
        isRecording = false,
        frameWidth = 0,
        frameHeight = 0;

  final int seq;
  final Map<String, Landmark> landmarks;

  /// Raw angle map. Values are `double`, `null` or `String` — read it through
  /// [angleState] rather than casting.
  final Map<String, dynamic> angles;

  final Telemetry telemetry;
  final PhysioAssessment physio;
  final int trackId;
  final BodyMode bodyMode;
  final bool isRecording;

  /// Dimensions of the upright, already-mirrored frame the landmarks were
  /// normalised against. The overlay uses this aspect ratio so the skeleton
  /// lines up with the camera preview to the pixel.
  final int frameWidth;
  final int frameHeight;

  /// Aspect ratio of the inference frame, or null before the first reply.
  double? get frameAspect =>
      (frameWidth > 0 && frameHeight > 0) ? frameWidth / frameHeight : null;

  bool get hasSkeleton => landmarks.isNotEmpty && telemetry.personDetected;

  /// The active movement classification, e.g. "SHOULDER ABDUCTION REHAB".
  String get detectedExercise {
    final value = angles['detected_exercise'];
    return value is String && value.isNotEmpty ? value : 'POSTURAL STABILITY';
  }

  /// Resolves one angle key into a renderable state.
  ///
  /// This is the single place the three-way null/string/number contract from the
  /// Python engine is interpreted, so no widget has to re-derive it.
  AngleState angleState(String key) {
    if (!telemetry.isReady) return const AngleState.unavailable();

    if (!angles.containsKey(key)) return const AngleState.unavailable();

    final value = angles[key];
    if (value == null) return const AngleState.tracking();
    if (value is String) return AngleState.note(value);
    if (value is num) return AngleState.degrees(value.toDouble());
    return const AngleState.unavailable();
  }
}

/// How a single angle should be presented.
sealed class AngleState {
  const AngleState();

  /// A real measurement.
  const factory AngleState.degrees(double value) = AngleDegrees;

  /// Landmark confidence below the 0.50 floor — the engine returned None.
  const factory AngleState.tracking() = AngleTracking;

  /// A textual note such as "SIDE VIEW REQ".
  const factory AngleState.note(String text) = AngleNote;

  /// Framing invalid or key absent.
  const factory AngleState.unavailable() = AngleUnavailable;

  /// Text for the HUD, matching the desktop renderer's `val_str` helper.
  String get display => switch (this) {
        AngleDegrees(:final value) => '${value.toStringAsFixed(1)}°',
        AngleTracking() => 'TRACKING…',
        AngleNote(:final text) => text,
        AngleUnavailable() => 'N/A',
      };

  /// Numeric value when there is one.
  double? get value => switch (this) {
        AngleDegrees(:final value) => value,
        _ => null,
      };

  bool get isMeasured => this is AngleDegrees;
}

class AngleDegrees extends AngleState {
  const AngleDegrees(this.value);
  @override
  final double value;
}

class AngleTracking extends AngleState {
  const AngleTracking();
}

class AngleNote extends AngleState {
  const AngleNote(this.text);
  final String text;
}

class AngleUnavailable extends AngleState {
  const AngleUnavailable();
}

/// Tolerant numeric parse — the server may legitimately send `null` for a
/// low-confidence joint, and JSON gives us `int` where we expect `double`.
double? _toDouble(Object? value) {
  if (value == null) return null;
  if (value is num) {
    final d = value.toDouble();
    return d.isFinite ? d : null;
  }
  if (value is String) return double.tryParse(value);
  return null;
}

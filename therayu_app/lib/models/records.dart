import 'package:flutter/foundation.dart';

/// ============================================================================
/// RECORDS MODELS
/// ============================================================================
/// Typed mirrors of what `upper_body_ai/records/` returns over `/api`.
///
/// Every field is parsed defensively. SQLite hands back nulls for anything not
/// yet measured — a patient with no sessions has no first_value, a HOLD exercise
/// has no rep target — and a rehab screen must render that as "—" rather than
/// crashing on a null cast.
/// ============================================================================

double? _d(dynamic v) => v == null ? null : (v as num).toDouble();
int? _i(dynamic v) => v == null ? null : (v as num).toInt();
String? _s(dynamic v) => v?.toString();

/// A person under treatment.
@immutable
class Patient {
  const Patient({
    required this.id,
    required this.code,
    required this.fullName,
    this.dateOfBirth,
    this.sex,
    this.phone,
    this.notes,
    this.sessionCount = 0,
    this.lastSessionAt,
    this.activeCondition,
  });

  final int id;
  final String code;
  final String fullName;
  final String? dateOfBirth;
  final String? sex;
  final String? phone;
  final String? notes;

  /// Present on the list endpoint, absent when fetched singly.
  final int sessionCount;
  final String? lastSessionAt;
  final String? activeCondition;

  factory Patient.fromJson(Map<String, dynamic> j) => Patient(
        id: (j['id'] as num).toInt(),
        code: j['code']?.toString() ?? '',
        fullName: j['full_name']?.toString() ?? 'Unnamed',
        dateOfBirth: _s(j['date_of_birth']),
        sex: _s(j['sex']),
        phone: _s(j['phone']),
        notes: _s(j['notes']),
        sessionCount: _i(j['session_count']) ?? 0,
        lastSessionAt: _s(j['last_session_at']),
        activeCondition: _s(j['active_condition']),
      );

  /// Two-letter monogram for the avatar, e.g. "Anjali Sharma" -> "AS".
  String get initials {
    final parts = fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }
}

/// A treatable condition with a prescribed exercise protocol behind it.
@immutable
class Condition {
  const Condition({
    required this.id,
    required this.code,
    required this.name,
    required this.bodyRegion,
    this.description,
    this.exerciseCount = 0,
  });

  final int id;
  final String code;
  final String name;
  final String bodyRegion;
  final String? description;
  final int exerciseCount;

  factory Condition.fromJson(Map<String, dynamic> j) => Condition(
        id: (j['id'] as num).toInt(),
        code: j['code']?.toString() ?? '',
        name: j['name']?.toString() ?? '',
        bodyRegion: j['body_region']?.toString() ?? 'FULL',
        description: _s(j['description']),
        exerciseCount: _i(j['exercise_count']) ?? 0,
      );
}

/// One prescribed movement, with the targets resolved from the protocol.
@immutable
class PlannedExercise {
  const PlannedExercise({
    required this.exerciseId,
    required this.code,
    required this.name,
    required this.bodyMode,
    required this.primaryJoint,
    required this.movementType,
    required this.goal,
    this.sequence = 1,
    this.mirrorJoint,
    this.instructions,
    this.targetRomDeg,
    this.targetReps,
    this.targetHoldSec,
    this.bandMinDeg,
    this.bandMaxDeg,
  });

  final int exerciseId;
  final String code;
  final String name;
  final String bodyMode;
  final String primaryJoint;
  final String? mirrorJoint;

  /// REP or HOLD. Decides whether the runner shows a rep count or a timer.
  final String movementType;

  /// INCREASE or REDUCE. A bigger trunk lean is worse, not better.
  final String goal;

  final int sequence;
  final String? instructions;
  final double? targetRomDeg;
  final int? targetReps;
  final int? targetHoldSec;
  final double? bandMinDeg;
  final double? bandMaxDeg;

  bool get isHold => movementType == 'HOLD';
  bool get lowerIsBetter => goal == 'REDUCE';

  /// What the patient is working towards, phrased for a person not a database.
  String get targetLabel {
    if (isHold) {
      final secs = targetHoldSec;
      final band = bandMaxDeg;
      if (secs != null && band != null && lowerIsBetter) {
        return 'Hold ${secs}s under ${band.toStringAsFixed(0)}°';
      }
      if (secs != null && bandMinDeg != null && bandMaxDeg != null) {
        return 'Hold ${secs}s at '
            '${bandMinDeg!.toStringAsFixed(0)}–${bandMaxDeg!.toStringAsFixed(0)}°';
      }
      if (secs != null) return 'Hold ${secs}s';
      return 'Hold steady';
    }
    final reps = targetReps;
    final rom = targetRomDeg;
    if (reps != null && rom != null) {
      return '$reps reps · ${rom.toStringAsFixed(0)}° range';
    }
    if (reps != null) return '$reps reps';
    if (rom != null) return '${rom.toStringAsFixed(0)}° range';
    return 'As tolerated';
  }

  factory PlannedExercise.fromJson(Map<String, dynamic> j) => PlannedExercise(
        // The plan endpoint calls it exercise_id; exercise_started calls it the
        // same, but a bare exercise row calls it id. Accept either.
        exerciseId: (_i(j['exercise_id']) ?? _i(j['id']) ?? 0),
        code: j['code']?.toString() ?? '',
        name: j['name']?.toString() ?? '',
        bodyMode: j['body_mode']?.toString() ?? 'FULL_BODY',
        primaryJoint: j['primary_joint']?.toString() ?? '',
        mirrorJoint: _s(j['mirror_joint']),
        movementType: j['movement_type']?.toString() ?? 'REP',
        goal: j['goal']?.toString() ?? 'INCREASE',
        sequence: _i(j['sequence']) ?? 1,
        instructions: _s(j['instructions']),
        targetRomDeg: _d(j['target_rom_deg']),
        targetReps: _i(j['target_reps']),
        targetHoldSec: _i(j['target_hold_sec']),
        bandMinDeg: _d(j['band_min_deg']),
        bandMaxDeg: _d(j['band_max_deg']),
      );
}

/// Everything the patient screen needs after picking a name.
@immutable
class TodaysPlan {
  const TodaysPlan({
    required this.patient,
    required this.exercises,
    this.conditionName,
    this.conditionId,
    this.dayIndex = 1,
    this.message,
  });

  final Patient patient;
  final List<PlannedExercise> exercises;
  final String? conditionName;
  final int? conditionId;
  final int dayIndex;

  /// Set when there is nothing to do, e.g. no condition assigned yet.
  final String? message;

  bool get hasPlan => exercises.isNotEmpty;

  factory TodaysPlan.fromJson(Map<String, dynamic> j) {
    final assignment = j['assignment'] as Map<String, dynamic>?;
    return TodaysPlan(
      patient: Patient.fromJson(Map<String, dynamic>.from(j['patient'] as Map)),
      exercises: ((j['exercises'] as List?) ?? const [])
          .map((e) => PlannedExercise.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      conditionName: _s(assignment?['condition_name']),
      conditionId: _i(assignment?['condition_id']),
      dayIndex: _i(j['day_index']) ?? 1,
      message: _s(j['message']),
    );
  }
}

/// What one completed exercise produced.
@immutable
class ExerciseResult {
  const ExerciseResult({
    required this.exerciseName,
    this.resultId,
    this.romMinDeg,
    this.romMaxDeg,
    this.romRangeDeg,
    this.targetRomDeg,
    this.romPctOfTarget,
    this.repsCompleted = 0,
    this.targetReps,
    this.holdSecTotal = 0,
    this.targetHoldSec,
    this.meanQualityPct,
    this.inTargetPct,
    this.symmetryDelta,
    this.durationSec = 0,
    this.framesAnalysed = 0,
    this.painScore,
    this.previousValue,
    this.previousDay,
    this.changeDeg,
    this.improved,
  });

  final int? resultId;
  final String exerciseName;
  final double? romMinDeg;
  final double? romMaxDeg;
  final double? romRangeDeg;
  final double? targetRomDeg;
  final double? romPctOfTarget;
  final int repsCompleted;
  final int? targetReps;
  final double holdSecTotal;
  final int? targetHoldSec;
  final double? meanQualityPct;
  final double? inTargetPct;
  final double? symmetryDelta;
  final double durationSec;

  /// Frames that carried a usable measurement.
  ///
  /// ZERO IS A REAL AND IMPORTANT OUTCOME. The engine refuses to publish angles
  /// while the body is out of frame, so a patient can complete a movement the
  /// camera never saw. Without this the result sheet would show a wall of
  /// dashes and no reason for them.
  final int framesAnalysed;

  final int? painScore;

  /// True when the attempt produced no usable measurement at all.
  bool get hasNoMeasurements => framesAnalysed == 0 || romMaxDeg == null;

  /// Comparison against the previous attempt, when there was one.
  final double? previousValue;
  final int? previousDay;
  final double? changeDeg;
  final bool? improved;

  bool get hasComparison => changeDeg != null;

  factory ExerciseResult.fromSaved(Map<String, dynamic> j, String name) {
    final s = Map<String, dynamic>.from((j['summary'] as Map?) ?? const {});
    final c = j['comparison'] as Map<String, dynamic>?;
    return ExerciseResult(
      resultId: _i(j['result_id']),
      exerciseName: name,
      romMinDeg: _d(s['rom_min_deg']),
      romMaxDeg: _d(s['rom_max_deg']),
      romRangeDeg: _d(s['rom_range_deg']),
      targetRomDeg: _d(s['target_rom_deg']),
      romPctOfTarget: _d(s['rom_pct_of_target']),
      repsCompleted: _i(s['reps_completed']) ?? 0,
      targetReps: _i(s['target_reps']),
      holdSecTotal: _d(s['hold_sec_total']) ?? 0,
      targetHoldSec: _i(s['target_hold_sec']),
      meanQualityPct: _d(s['mean_quality_pct']),
      inTargetPct: _d(s['in_target_pct']),
      symmetryDelta: _d(s['symmetry_delta']),
      durationSec: _d(s['duration_sec']) ?? 0,
      framesAnalysed: _i(s['frames_analysed']) ?? 0,
      previousValue: _d(c?['previous_value']),
      previousDay: _i(c?['previous_day']),
      changeDeg: _d(c?['change_deg']),
      improved: c?['improved'] as bool?,
    );
  }

  factory ExerciseResult.fromRow(Map<String, dynamic> j) => ExerciseResult(
        resultId: _i(j['id']),
        exerciseName: j['exercise_name']?.toString() ?? '',
        romMinDeg: _d(j['rom_min_deg']),
        romMaxDeg: _d(j['rom_max_deg']),
        romRangeDeg: _d(j['rom_range_deg']),
        targetRomDeg: _d(j['target_rom_deg']),
        romPctOfTarget: _d(j['rom_pct_of_target']),
        repsCompleted: _i(j['reps_completed']) ?? 0,
        targetReps: _i(j['target_reps']),
        holdSecTotal: _d(j['hold_sec_total']) ?? 0,
        targetHoldSec: _i(j['target_hold_sec']),
        meanQualityPct: _d(j['mean_quality_pct']),
        inTargetPct: _d(j['in_target_pct']),
        symmetryDelta: _d(j['symmetry_delta']),
        durationSec: _d(j['duration_sec']) ?? 0,
        framesAnalysed: _i(j['frames_analysed']) ?? 0,
        painScore: _i(j['pain_score']),
      );
}

/// One visit.
@immutable
class SessionRecord {
  const SessionRecord({
    required this.id,
    required this.dayIndex,
    required this.startedAt,
    this.endedAt,
    this.conditionName,
    this.exerciseCount = 0,
    this.notes,
  });

  final int id;
  final int dayIndex;
  final String startedAt;
  final String? endedAt;
  final String? conditionName;
  final int exerciseCount;
  final String? notes;

  factory SessionRecord.fromJson(Map<String, dynamic> j) => SessionRecord(
        id: (j['id'] as num).toInt(),
        dayIndex: _i(j['day_index']) ?? 1,
        startedAt: j['started_at']?.toString() ?? '',
        endedAt: _s(j['ended_at']),
        conditionName: _s(j['condition_name']),
        exerciseCount: _i(j['exercise_count']) ?? 0,
        notes: _s(j['notes']),
      );

  DateTime? get startedDate => DateTime.tryParse(startedAt)?.toLocal();
}

/// One point on a trend line.
@immutable
class TrendPoint {
  const TrendPoint({required this.dayIndex, this.value, this.reps, this.quality});

  final int dayIndex;
  final double? value;
  final int? reps;
  final double? quality;

  factory TrendPoint.fromJson(Map<String, dynamic> j) => TrendPoint(
        dayIndex: _i(j['day_index']) ?? 1,
        value: _d(j['value']),
        reps: _i(j['reps']),
        quality: _d(j['quality']),
      );
}

/// First versus latest for one prescribed movement.
@immutable
class ProgressItem {
  const ProgressItem({
    required this.exerciseId,
    required this.code,
    required this.name,
    required this.goal,
    required this.movementType,
    required this.primaryJoint,
    required this.trend,
    this.sessions = 0,
    this.firstDay = 1,
    this.latestDay = 1,
    this.firstValue,
    this.latestValue,
    this.bestValue,
    this.changeDeg,
    this.changePct,
    this.improved,
    this.targetRomDeg,
    this.romPctOfTarget,
  });

  final int exerciseId;
  final String code;
  final String name;
  final String goal;
  final String movementType;
  final String primaryJoint;
  final List<TrendPoint> trend;
  final int sessions;
  final int firstDay;
  final int latestDay;
  final double? firstValue;
  final double? latestValue;
  final double? bestValue;
  final double? changeDeg;
  final double? changePct;
  final bool? improved;
  final double? targetRomDeg;
  final double? romPctOfTarget;

  bool get lowerIsBetter => goal == 'REDUCE';

  factory ProgressItem.fromJson(Map<String, dynamic> j) => ProgressItem(
        exerciseId: _i(j['exercise_id']) ?? 0,
        code: j['code']?.toString() ?? '',
        name: j['name']?.toString() ?? '',
        goal: j['goal']?.toString() ?? 'INCREASE',
        movementType: j['movement_type']?.toString() ?? 'REP',
        primaryJoint: j['primary_joint']?.toString() ?? '',
        sessions: _i(j['sessions']) ?? 0,
        firstDay: _i(j['first_day']) ?? 1,
        latestDay: _i(j['latest_day']) ?? 1,
        firstValue: _d(j['first_value']),
        latestValue: _d(j['latest_value']),
        bestValue: _d(j['best_value']),
        changeDeg: _d(j['change_deg']),
        changePct: _d(j['change_pct']),
        improved: j['improved'] as bool?,
        targetRomDeg: _d(j['target_rom_deg']),
        romPctOfTarget: _d(j['rom_pct_of_target']),
        trend: ((j['trend'] as List?) ?? const [])
            .map((e) => TrendPoint.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
      );
}

/// The whole picture for one patient, as the doctor's view needs it.
@immutable
class ProgressReport {
  const ProgressReport({
    required this.patient,
    required this.exercises,
    required this.regressions,
    this.conditionName,
    this.sessionCount = 0,
    this.daysInProgramme = 0,
    this.firstSessionAt,
    this.latestSessionAt,
  });

  final Patient patient;
  final List<ProgressItem> exercises;
  final List<ProgressItem> regressions;
  final String? conditionName;
  final int sessionCount;
  final int daysInProgramme;
  final String? firstSessionAt;
  final String? latestSessionAt;

  int get improvedCount => exercises.where((e) => e.improved == true).length;

  factory ProgressReport.fromJson(Map<String, dynamic> j) {
    final assignment = j['assignment'] as Map<String, dynamic>?;
    List<ProgressItem> parse(String key) =>
        ((j[key] as List?) ?? const [])
            .map((e) => ProgressItem.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList();
    return ProgressReport(
      patient: Patient.fromJson(Map<String, dynamic>.from(j['patient'] as Map)),
      exercises: parse('exercises'),
      regressions: parse('regressions'),
      conditionName: _s(assignment?['condition_name']),
      sessionCount: _i(j['session_count']) ?? 0,
      daysInProgramme: _i(j['days_in_programme']) ?? 0,
      firstSessionAt: _s(j['first_session_at']),
      latestSessionAt: _s(j['latest_session_at']),
    );
  }
}

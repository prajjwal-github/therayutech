import 'package:flutter/material.dart';

import '../models/records.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import 'record_widgets.dart';

/// ============================================================================
/// EXERCISE RUNNER
/// ============================================================================
/// The overlay that turns the live view from a measuring instrument into a
/// guided session: which movement is being performed, what the target is, how
/// far through it the patient is, and what to do next.
///
/// Everything here reads from [SessionController]. Nothing computes an angle or
/// counts a rep — the reps on screen are the server's count, so the number the
/// patient watches climb is the same number written to their record.
/// ============================================================================

/// Bar shown while an exercise is being recorded.
class ExerciseHud extends StatelessWidget {
  const ExerciseHud({required this.session, required this.compact, super.key});

  final SessionController session;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final ex = session.activeExercise;
    if (ex == null) return const SizedBox.shrink();

    final live = session.activeJointValue;
    final reps = session.activeReps;
    final progress = session.exerciseProgress;
    final done = progress >= 1.0;

    return Positioned(
      left: AppGaps.screenEdge,
      right: AppGaps.screenEdge,
      bottom: compact ? 74 : 68,
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.all(AppGaps.md),
          decoration: BoxDecoration(
            color: AppPalette.scrim,
            borderRadius: BorderRadius.circular(AppRadii.md),
            border: Border.all(
              color: done ? AppPalette.success : AppPalette.brandCyan,
              width: 1.4,
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  ProgressRing(
                    progress: progress,
                    label: ex.isHold
                        ? '${session.holdSeconds.toStringAsFixed(0)}s'
                        : '$reps',
                    caption: ex.isHold
                        ? 'of ${ex.targetHoldSec ?? '—'}s'
                        : 'of ${ex.targetReps ?? '—'}',
                    size: compact ? 74 : 88,
                  ),
                  const SizedBox(width: AppGaps.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: AppPalette.brandGold,
                                borderRadius:
                                    BorderRadius.circular(AppRadii.sm),
                              ),
                              child: Text(
                                'RECORDING',
                                style: AppTheme.label.copyWith(
                                  fontSize: 8,
                                  color: AppPalette.textOnAccent,
                                ),
                              ),
                            ),
                            const SizedBox(width: AppGaps.sm),
                            Expanded(
                              child: Text(
                                ex.targetLabel,
                                style: AppTheme.caption,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          ex.name,
                          style: AppTheme.value.copyWith(fontSize: 15),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: AppGaps.sm),

                        // Where the joint is right now against the band it is
                        // supposed to reach. This is the single most useful
                        // thing on screen mid-movement: the patient can see
                        // whether they got there without reading a number.
                        BandGauge(
                          value: live,
                          bandMin: ex.bandMinDeg,
                          bandMax: ex.bandMaxDeg,
                          lowerIsBetter: ex.lowerIsBetter,
                        ),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              live == null
                                  ? 'TRACKING…'
                                  : '${live.toStringAsFixed(1)}°',
                              style: AppTheme.value.copyWith(
                                fontSize: 13,
                                color: live == null
                                    ? AppPalette.textMuted
                                    : AppPalette.brandCyanLight,
                              ),
                            ),
                            if (ex.bandMinDeg != null || ex.bandMaxDeg != null)
                              Text(
                                'band '
                                '${ex.bandMinDeg?.toStringAsFixed(0) ?? '0'}–'
                                '${ex.bandMaxDeg?.toStringAsFixed(0) ?? '∞'}°',
                                style: AppTheme.caption.copyWith(fontSize: 10),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppGaps.md),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 42,
                      child: FilledButton.icon(
                        onPressed: () => session.stopExercise(),
                        style: FilledButton.styleFrom(
                          backgroundColor:
                              done ? AppPalette.success : AppPalette.brandGold,
                          foregroundColor: AppPalette.textOnAccent,
                        ),
                        icon: const Icon(Icons.stop_rounded, size: 20),
                        label: Text(done ? 'Finish — target met' : 'Finish'),
                      ),
                    ),
                  ),
                  const SizedBox(width: AppGaps.sm),
                  SizedBox(
                    height: 42,
                    child: OutlinedButton(
                      onPressed: () => _confirmDiscard(context, session),
                      child: const Text('Discard'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmDiscard(
      BuildContext context, SessionController session) async {
    // A discarded attempt is still written, flagged aborted, so it never enters
    // a trend line but the fact it happened is not silently erased.
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppPalette.surface,
        title: const Text('Discard this attempt?', style: AppTheme.title),
        content: Text(
          'It will be recorded as abandoned and left out of the progress '
          'trend. Use this if the patient stopped early or the tracking was '
          'wrong.',
          style: AppTheme.body,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep going'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text('Discard',
                style: AppTheme.body.copyWith(color: AppPalette.danger)),
          ),
        ],
      ),
    );
    if (ok == true) session.stopExercise(aborted: true);
  }
}

/// Panel shown between exercises: what is left, and a button to begin the next.
class ExercisePicker extends StatelessWidget {
  const ExercisePicker({required this.session, required this.compact, super.key});

  final SessionController session;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final plan = session.plan;
    if (plan == null || !plan.hasPlan) return const SizedBox.shrink();

    final done = session.completedExerciseIds;
    final remaining =
        plan.exercises.where((e) => !done.contains(e.exerciseId)).toList();
    final allDone = remaining.isEmpty;

    return Positioned(
      left: AppGaps.screenEdge,
      right: AppGaps.screenEdge,
      bottom: compact ? 74 : 68,
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.all(AppGaps.md),
          decoration: BoxDecoration(
            color: AppPalette.scrim,
            borderRadius: BorderRadius.circular(AppRadii.md),
            border: Border.all(
                color: allDone ? AppPalette.success : AppPalette.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      session.patient == null
                          ? 'No patient selected'
                          : '${session.patient!.fullName}  ·  day ${session.dayIndex}',
                      style: AppTheme.value.copyWith(fontSize: 13),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text('${done.length}/${plan.exercises.length} done',
                      style: AppTheme.caption),
                ],
              ),
              const SizedBox(height: AppGaps.sm),

              if (allDone) ...[
                Row(
                  children: [
                    const Icon(Icons.check_circle,
                        color: AppPalette.success, size: 18),
                    const SizedBox(width: AppGaps.sm),
                    Expanded(
                      child: Text('Every prescribed exercise is complete.',
                          style: AppTheme.body),
                    ),
                  ],
                ),
                const SizedBox(height: AppGaps.md),
                SizedBox(
                  width: double.infinity,
                  height: 44,
                  child: FilledButton.icon(
                    onPressed: () => session.endPatientSession(),
                    style: FilledButton.styleFrom(
                      backgroundColor: AppPalette.success,
                      foregroundColor: AppPalette.textOnAccent,
                    ),
                    icon: const Icon(Icons.done_all_rounded, size: 20),
                    label: const Text('Finish session and save'),
                  ),
                ),
              ] else ...[
                SizedBox(
                  height: compact ? 84 : 92,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: remaining.length,
                    separatorBuilder: (_, __) => const SizedBox(width: AppGaps.sm),
                    itemBuilder: (context, i) => _NextExerciseChip(
                      exercise: remaining[i],
                      isNext: i == 0,
                      onStart: () => session.startExercise(remaining[i]),
                    ),
                  ),
                ),
                const SizedBox(height: AppGaps.sm),
                SizedBox(
                  width: double.infinity,
                  height: 38,
                  child: OutlinedButton.icon(
                    onPressed: () => session.endPatientSession(),
                    icon: const Icon(Icons.stop_circle_outlined, size: 18),
                    label: Text(
                      done.isEmpty
                          ? 'End session without recording'
                          : 'End session early (${done.length} saved)',
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _NextExerciseChip extends StatelessWidget {
  const _NextExerciseChip({
    required this.exercise,
    required this.isNext,
    required this.onStart,
  });

  final PlannedExercise exercise;
  final bool isNext;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 210,
      child: Material(
        color: AppPalette.transparent,
        child: InkWell(
          onTap: onStart,
          borderRadius: BorderRadius.circular(AppRadii.md),
          child: Container(
            padding: const EdgeInsets.all(AppGaps.sm),
            decoration: BoxDecoration(
              color: isNext ? AppPalette.surfaceRaised : AppPalette.surface,
              borderRadius: BorderRadius.circular(AppRadii.md),
              border: Border.all(
                color: isNext ? AppPalette.brandCyan : AppPalette.border,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    if (isNext)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 5, vertical: 1),
                        decoration: BoxDecoration(
                          color: AppPalette.brandCyan,
                          borderRadius: BorderRadius.circular(AppRadii.sm),
                        ),
                        child: Text('NEXT',
                            style: AppTheme.label.copyWith(
                                fontSize: 7, color: AppPalette.textOnAccent)),
                      ),
                    if (isNext) const SizedBox(width: 5),
                    Text(exercise.isHold ? 'HOLD' : 'REPS',
                        style: AppTheme.label.copyWith(fontSize: 7)),
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  exercise.name,
                  style: AppTheme.value.copyWith(fontSize: 12),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const Spacer(),
                Row(
                  children: [
                    Expanded(
                      child: Text(exercise.targetLabel,
                          style: AppTheme.caption.copyWith(fontSize: 10),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                    ),
                    const Icon(Icons.play_circle_fill,
                        color: AppPalette.brandCyanLight, size: 20),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Sheet shown the moment an exercise is saved: what was achieved, and whether
/// it beat last time.
class ExerciseResultSheet extends StatefulWidget {
  const ExerciseResultSheet({
    required this.result,
    required this.session,
    super.key,
  });

  final ExerciseResult result;
  final SessionController session;

  static Future<void> show(
      BuildContext context, ExerciseResult result, SessionController session) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      backgroundColor: AppPalette.transparent,
      builder: (_) => ExerciseResultSheet(result: result, session: session),
    );
  }

  @override
  State<ExerciseResultSheet> createState() => _ExerciseResultSheetState();
}

class _ExerciseResultSheetState extends State<ExerciseResultSheet> {
  int? _pain;

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    final improved = r.improved;

    return Container(
      decoration: const BoxDecoration(
        color: AppPalette.background,
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.lg)),
      ),
      padding: const EdgeInsets.all(AppGaps.lg),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 38,
                height: 4,
                decoration: BoxDecoration(
                  color: AppPalette.border,
                  borderRadius: BorderRadius.circular(AppRadii.pill),
                ),
              ),
            ),
            const SizedBox(height: AppGaps.lg),

            Row(
              children: [
                Icon(
                  improved == true
                      ? Icons.trending_up
                      : improved == false
                          ? Icons.trending_down
                          : Icons.check_circle_outline,
                  color: improved == true
                      ? AppPalette.success
                      : improved == false
                          ? AppPalette.danger
                          : AppPalette.brandCyan,
                  size: 26,
                ),
                const SizedBox(width: AppGaps.sm),
                Expanded(
                  child: Text(r.exerciseName, style: AppTheme.title),
                ),
              ],
            ),
            const SizedBox(height: AppGaps.lg),

            if (r.hasNoMeasurements) ...[
              RecordCard(
                accent: AppPalette.brandGold,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.videocam_off_outlined,
                            color: AppPalette.brandGold, size: 20),
                        const SizedBox(width: AppGaps.sm),
                        Expanded(
                          child: Text('Nothing was measured',
                              style: AppTheme.value.copyWith(fontSize: 14)),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppGaps.sm),
                    Text(
                      'The body was never correctly framed, so no angle could be '
                      'recorded. Nothing is stored against the target for this '
                      'attempt. Check the guidance banner, step back so the whole '
                      'region is in shot, and try again.',
                      style: AppTheme.body,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppGaps.md),
            ],

            RecordCard(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  StatTile(
                    label: 'Range',
                    value: r.romRangeDeg?.toStringAsFixed(1) ?? '—',
                    suffix: r.romRangeDeg == null ? null : '°',
                  ),
                  StatTile(
                    label: 'Peak',
                    value: r.romMaxDeg?.toStringAsFixed(1) ?? '—',
                    suffix: r.romMaxDeg == null ? null : '°',
                  ),
                  StatTile(
                    label: 'Reps',
                    value: r.targetReps != null
                        ? '${r.repsCompleted}/${r.targetReps}'
                        : '${r.repsCompleted}',
                    tone: (r.targetReps != null &&
                            r.repsCompleted >= r.targetReps!)
                        ? AppPalette.success
                        : null,
                  ),
                  StatTile(
                    label: 'Quality',
                    value: r.meanQualityPct?.toStringAsFixed(0) ?? '—',
                    suffix: r.meanQualityPct == null ? null : '%',
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppGaps.sm),
            RecordCard(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  StatTile(
                    label: 'Of target',
                    value: r.romPctOfTarget?.toStringAsFixed(0) ?? '—',
                    suffix: r.romPctOfTarget == null ? null : '%',
                    tone: (r.romPctOfTarget ?? 0) >= 100
                        ? AppPalette.success
                        : null,
                  ),
                  StatTile(
                    label: 'In band',
                    value: r.inTargetPct?.toStringAsFixed(0) ?? '—',
                    suffix: r.inTargetPct == null ? null : '%',
                  ),
                  StatTile(
                    label: 'L/R gap',
                    value: r.symmetryDelta?.toStringAsFixed(1) ?? '—',
                    suffix: r.symmetryDelta == null ? null : '°',
                  ),
                  StatTile(
                    label: 'Duration',
                    value: r.durationSec.toStringAsFixed(0),
                    suffix: 's',
                  ),
                ],
              ),
            ),

            if (r.hasComparison) ...[
              const SizedBox(height: AppGaps.md),
              RecordCard(
                accent: improved == true
                    ? AppPalette.success
                    : improved == false
                        ? AppPalette.danger
                        : AppPalette.border,
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text('COMPARED WITH DAY ${r.previousDay}',
                              style: AppTheme.label),
                          const SizedBox(height: 3),
                          Text(
                            improved == true
                                ? 'Better than last time'
                                : improved == false
                                    ? 'Down on last time'
                                    : 'No change',
                            style: AppTheme.value.copyWith(fontSize: 14),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${r.previousValue?.toStringAsFixed(1) ?? '—'}° → '
                            '${(r.romRangeDeg ?? r.romMaxDeg)?.toStringAsFixed(1) ?? '—'}°',
                            style: AppTheme.caption,
                          ),
                        ],
                      ),
                    ),
                    ChangeChip(changeDeg: r.changeDeg, improved: improved),
                  ],
                ),
              ),
            ],

            const SizedBox(height: AppGaps.lg),
            Text('HOW DID THAT FEEL?', style: AppTheme.label),
            const SizedBox(height: AppGaps.xs),
            Text(
              'Optional. Pain right now, 0 (none) to 10 (worst imaginable).',
              style: AppTheme.caption,
            ),
            const SizedBox(height: AppGaps.sm),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (var i = 0; i <= 10; i++)
                  _PainChip(
                    score: i,
                    selected: _pain == i,
                    onTap: () => setState(() => _pain = i),
                  ),
              ],
            ),

            const SizedBox(height: AppGaps.lg),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: FilledButton(
                onPressed: () {
                  final id = r.resultId;
                  if (id != null && _pain != null) {
                    widget.session.submitPainScore(id, _pain!);
                  }
                  widget.session.clearLastResult();
                  Navigator.of(context).pop();
                },
                child: const Text('Continue'),
              ),
            ),
            const SizedBox(height: AppGaps.sm),
          ],
        ),
      ),
    );
  }
}

class _PainChip extends StatelessWidget {
  const _PainChip({
    required this.score,
    required this.selected,
    required this.onTap,
  });

  final int score;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // Green through gold to red as the score climbs, so the scale reads at a
    // glance without needing the numbers.
    final tone = score <= 3
        ? AppPalette.success
        : score <= 6
            ? AppPalette.brandGold
            : AppPalette.danger;
    return Material(
      color: AppPalette.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Container(
          width: 34,
          height: 34,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? tone : AppPalette.surface,
            borderRadius: BorderRadius.circular(AppRadii.sm),
            border: Border.all(
                color: selected ? tone : AppPalette.border,
                width: selected ? 1.6 : 1),
          ),
          child: Text(
            '$score',
            style: AppTheme.value.copyWith(
              fontSize: 13,
              color: selected ? AppPalette.textOnAccent : AppPalette.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

/// End-of-session summary.
class SessionSummarySheet extends StatelessWidget {
  const SessionSummarySheet({
    required this.summary,
    required this.session,
    super.key,
  });

  final Map<String, dynamic> summary;
  final SessionController session;

  static Future<void> show(BuildContext context, Map<String, dynamic> summary,
      SessionController session) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      backgroundColor: AppPalette.transparent,
      builder: (_) => SessionSummarySheet(summary: summary, session: session),
    );
  }

  @override
  Widget build(BuildContext context) {
    final results = ((summary['results'] as List?) ?? const [])
        .map((e) => ExerciseResult.fromRow(Map<String, dynamic>.from(e as Map)))
        .toList();
    final day = summary['day_index'];
    final completed = summary['exercises_completed'] ?? results.length;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.85,
      ),
      decoration: const BoxDecoration(
        color: AppPalette.background,
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.lg)),
      ),
      padding: const EdgeInsets.all(AppGaps.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: AppPalette.border,
                borderRadius: BorderRadius.circular(AppRadii.pill),
              ),
            ),
          ),
          const SizedBox(height: AppGaps.lg),
          Row(
            children: [
              const Icon(Icons.verified, color: AppPalette.success, size: 26),
              const SizedBox(width: AppGaps.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Session saved', style: AppTheme.title),
                    Text(
                      'Day $day  ·  $completed exercise'
                      '${completed == 1 ? '' : 's'} recorded',
                      style: AppTheme.caption,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppGaps.lg),

          if (results.isEmpty)
            Text(
              'Nothing was recorded in this session, so no history was written.',
              style: AppTheme.body,
            )
          else
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: results.length,
                separatorBuilder: (_, __) => const SizedBox(height: AppGaps.sm),
                itemBuilder: (context, i) {
                  final r = results[i];
                  return RecordCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(r.exerciseName,
                            style: AppTheme.value.copyWith(fontSize: 13)),
                        const SizedBox(height: AppGaps.sm),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            StatTile(
                              label: 'Range',
                              value: r.romRangeDeg?.toStringAsFixed(1) ?? '—',
                              suffix: r.romRangeDeg == null ? null : '°',
                            ),
                            StatTile(
                              label: 'Peak',
                              value: r.romMaxDeg?.toStringAsFixed(1) ?? '—',
                              suffix: r.romMaxDeg == null ? null : '°',
                            ),
                            StatTile(
                              label: 'Reps',
                              value: '${r.repsCompleted}',
                            ),
                            StatTile(
                              label: 'Of target',
                              value:
                                  r.romPctOfTarget?.toStringAsFixed(0) ?? '—',
                              suffix: r.romPctOfTarget == null ? null : '%',
                            ),
                          ],
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),

          const SizedBox(height: AppGaps.lg),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton.icon(
              onPressed: () {
                session.clearSessionSummary();
                Navigator.of(context).pop();      // close the sheet
                Navigator.of(context).maybePop(); // leave the live view
              },
              icon: const Icon(Icons.insights),
              label: const Text('View progress'),
            ),
          ),
          const SizedBox(height: AppGaps.sm),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../models/records.dart';
import '../services/records_api.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/record_widgets.dart';
import 'live_session_screen.dart';

/// ============================================================================
/// PATIENT DETAIL
/// ============================================================================
/// Three tabs over one person: today's prescription, their history, and the
/// progress the doctor cares about.
///
/// The "Start session" button lives here rather than on the connect screen,
/// because starting a session without a patient attached is how records end up
/// orphaned.
/// ============================================================================
class PatientDetailScreen extends StatefulWidget {
  const PatientDetailScreen({
    required this.session,
    required this.patient,
    super.key,
  });

  final SessionController session;
  final Patient patient;

  @override
  State<PatientDetailScreen> createState() => _PatientDetailScreenState();
}

class _PatientDetailScreenState extends State<PatientDetailScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 3, vsync: this);

  TodaysPlan? _plan;
  List<SessionRecord> _sessions = const [];
  ProgressReport? _progress;

  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = widget.session.api;
      // Fetched together so the three tabs are never showing state from
      // different moments — a patient who just finished a session should see the
      // new figures on every tab at once.
      final results = await Future.wait([
        api.todaysPlan(widget.patient.id),
        api.listSessions(widget.patient.id),
        api.progress(widget.patient.id),
      ]);
      if (!mounted) return;
      setState(() {
        _plan = results[0] as TodaysPlan;
        _sessions = results[1] as List<SessionRecord>;
        _progress = results[2] as ProgressReport;
        _loading = false;
      });
    } on RecordsApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _assignCondition() async {
    final chosen = await showModalBottomSheet<Condition>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppPalette.transparent,
      builder: (_) => _ConditionPicker(api: widget.session.api),
    );
    if (chosen == null || !mounted) return;
    try {
      await widget.session.api.assignCondition(widget.patient.id, chosen.id);
      await _loadAll();
      if (!mounted) return;
      _toast('Assigned: ${chosen.name}');
    } on RecordsApiException catch (e) {
      if (mounted) _toast(e.message, error: true);
    }
  }

  Future<void> _startSession() async {
    final plan = _plan;
    if (plan == null || !plan.hasPlan) {
      _toast('Assign a condition before starting a session.', error: true);
      return;
    }

    final session = widget.session;
    await session.selectPatient(widget.patient);

    if (!session.status.isLive) {
      await session.connect(session.serverUrl);
    }
    if (!mounted) return;

    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => LiveSessionScreen(session: session),
      ),
    );

    // Back from the live view: refresh so today's work appears immediately.
    if (!mounted) return;
    await _loadAll();
  }

  Future<void> _exportReport() async {
    _toast('Generating report…');
    try {
      final path = await widget.session.api.buildReport(widget.patient.id);
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          backgroundColor: AppPalette.surface,
          title: const Text('Report ready', style: AppTheme.title),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Saved on the server PC at:', style: AppTheme.body),
              const SizedBox(height: AppGaps.sm),
              SelectableText(path, style: AppTheme.telemetry),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    } on RecordsApiException catch (e) {
      if (mounted) _toast(e.message, error: true);
    }
  }

  void _toast(String message, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? AppPalette.danger : AppPalette.surfaceRaised,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.patient.fullName, style: AppTheme.title),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loadAll,
            icon: const Icon(Icons.refresh),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: AppPalette.brandCyanLight,
          unselectedLabelColor: AppPalette.textMuted,
          indicatorColor: AppPalette.brandGold,
          tabs: const [
            Tab(text: 'TODAY'),
            Tab(text: 'HISTORY'),
            Tab(text: 'PROGRESS'),
          ],
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppPalette.brandCyan))
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(AppGaps.xxl),
                    child: Text(_error!,
                        style: AppTheme.body.copyWith(color: AppPalette.danger),
                        textAlign: TextAlign.center),
                  ),
                )
              : TabBarView(
                  controller: _tabs,
                  children: [_todayTab(), _historyTab(), _progressTab()],
                ),
    );
  }

  // ------------------------------------------------------------------ today --

  Widget _todayTab() {
    final plan = _plan;
    final hasPlan = plan?.hasPlan ?? false;

    return ListView(
      padding: const EdgeInsets.all(AppGaps.lg),
      children: [
        RecordCard(
          accent: hasPlan ? AppPalette.border : AppPalette.brandGold,
          child: Row(
            children: [
              PatientAvatar(patient: widget.patient, size: 52),
              const SizedBox(width: AppGaps.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(widget.patient.code, style: AppTheme.label),
                    const SizedBox(height: 2),
                    Text(
                      plan?.conditionName ?? 'No condition assigned',
                      style: AppTheme.value.copyWith(fontSize: 14),
                    ),
                    const SizedBox(height: 2),
                    Text('Day ${plan?.dayIndex ?? 1} of the programme',
                        style: AppTheme.caption),
                  ],
                ),
              ),
              TextButton(
                onPressed: _assignCondition,
                child: Text(hasPlan ? 'Change' : 'Assign'),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppGaps.lg),

        if (!hasPlan)
          RecordCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.assignment_late_outlined,
                    color: AppPalette.brandGold),
                const SizedBox(height: AppGaps.sm),
                Text(plan?.message ?? 'No condition assigned yet.',
                    style: AppTheme.body),
                const SizedBox(height: AppGaps.xs),
                Text(
                  'A clinician assigns the condition; the exercise list then '
                  'follows from it automatically.',
                  style: AppTheme.caption,
                ),
              ],
            ),
          )
        else ...[
          SectionHeading(
            title: "Today's exercises",
            trailing: Text('${plan!.exercises.length} prescribed',
                style: AppTheme.caption),
          ),
          for (final ex in plan.exercises) ...[
            _ExerciseRow(exercise: ex),
            const SizedBox(height: AppGaps.sm),
          ],
          const SizedBox(height: AppGaps.md),
          SizedBox(
            height: 52,
            child: FilledButton.icon(
              onPressed: _startSession,
              icon: const Icon(Icons.play_arrow_rounded),
              label: Text('Start day ${plan.dayIndex} session'),
            ),
          ),
        ],
        const SizedBox(height: AppGaps.xxl),
      ],
    );
  }

  // ---------------------------------------------------------------- history --

  Widget _historyTab() {
    if (_sessions.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppGaps.xxl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.history, size: 46, color: AppPalette.textMuted),
              const SizedBox(height: AppGaps.md),
              const Text('No sessions recorded yet', style: AppTheme.value),
              const SizedBox(height: AppGaps.xs),
              Text('Finish a session and it will appear here.',
                  style: AppTheme.caption, textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }

    // Newest first: the last visit is what a clinician opens this for.
    final ordered = _sessions.reversed.toList();
    return ListView.separated(
      padding: const EdgeInsets.all(AppGaps.lg),
      itemCount: ordered.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppGaps.sm),
      itemBuilder: (context, i) => _SessionRow(
        record: ordered[i],
        api: widget.session.api,
      ),
    );
  }

  // --------------------------------------------------------------- progress --

  Widget _progressTab() {
    final report = _progress;
    if (report == null || report.exercises.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppGaps.xxl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.show_chart, size: 46, color: AppPalette.textMuted),
              const SizedBox(height: AppGaps.md),
              const Text('Nothing to compare yet', style: AppTheme.value),
              const SizedBox(height: AppGaps.xs),
              Text(
                'Progress appears once the patient has completed at least one '
                'exercise. Two sessions gives a trend.',
                style: AppTheme.caption,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(AppGaps.lg),
      children: [
        RecordCard(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              StatTile(label: 'Sessions', value: '${report.sessionCount}'),
              StatTile(label: 'Days', value: '${report.daysInProgramme}'),
              StatTile(
                label: 'Improved',
                value: '${report.improvedCount}/${report.exercises.length}',
                tone: AppPalette.success,
              ),
              StatTile(
                label: 'Flagged',
                value: '${report.regressions.length}',
                tone: report.regressions.isEmpty
                    ? AppPalette.textPrimary
                    : AppPalette.danger,
              ),
            ],
          ),
        ),
        const SizedBox(height: AppGaps.lg),

        if (report.regressions.isNotEmpty) ...[
          const SectionHeading(title: 'Flagged for review'),
          for (final item in report.regressions) ...[
            RecordCard(
              accent: AppPalette.danger,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(item.name,
                            style: AppTheme.value.copyWith(fontSize: 14)),
                      ),
                      ChangeChip(
                          changeDeg: item.changeDeg, improved: item.improved),
                    ],
                  ),
                  const SizedBox(height: AppGaps.xs),
                  Text(
                    item.lowerIsBetter
                        ? 'Deviation from neutral has increased.'
                        : 'Range of motion has decreased.',
                    style: AppTheme.caption.copyWith(color: AppPalette.danger),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppGaps.sm),
          ],
          const SizedBox(height: AppGaps.md),
        ],

        const SectionHeading(title: 'Movement trends'),
        for (final item in report.exercises) ...[
          _ProgressCard(item: item),
          const SizedBox(height: AppGaps.sm),
        ],

        const SizedBox(height: AppGaps.md),
        SizedBox(
          height: 48,
          child: OutlinedButton.icon(
            onPressed: _exportReport,
            icon: const Icon(Icons.picture_as_pdf_outlined),
            label: const Text('Export doctor report (PDF)'),
          ),
        ),
        const SizedBox(height: AppGaps.xxl),
      ],
    );
  }
}

// ============================================================== sub-widgets ==

class _ExerciseRow extends StatelessWidget {
  const _ExerciseRow({required this.exercise});

  final PlannedExercise exercise;

  @override
  Widget build(BuildContext context) {
    return RecordCard(
      padding: const EdgeInsets.all(AppGaps.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 26, height: 26,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppPalette.surfaceRaised,
              borderRadius: BorderRadius.circular(AppRadii.sm),
            ),
            child: Text('${exercise.sequence}',
                style: AppTheme.value.copyWith(fontSize: 12)),
          ),
          const SizedBox(width: AppGaps.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(exercise.name, style: AppTheme.value.copyWith(fontSize: 14)),
                const SizedBox(height: 3),
                Text(exercise.targetLabel, style: AppTheme.caption),
                if (exercise.instructions != null &&
                    exercise.instructions!.isNotEmpty) ...[
                  const SizedBox(height: AppGaps.xs),
                  Text(exercise.instructions!,
                      style: AppTheme.caption.copyWith(
                          color: AppPalette.textMuted, height: 1.35)),
                ],
              ],
            ),
          ),
          const SizedBox(width: AppGaps.sm),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
            decoration: BoxDecoration(
              color: AppPalette.surfaceRaised,
              borderRadius: BorderRadius.circular(AppRadii.sm),
            ),
            child: Text(
              exercise.isHold ? 'HOLD' : 'REPS',
              style: AppTheme.label.copyWith(fontSize: 8),
            ),
          ),
        ],
      ),
    );
  }
}

class _SessionRow extends StatefulWidget {
  const _SessionRow({required this.record, required this.api});

  final SessionRecord record;
  final RecordsApi api;

  @override
  State<_SessionRow> createState() => _SessionRowState();
}

class _SessionRowState extends State<_SessionRow> {
  bool _open = false;
  List<ExerciseResult>? _results;
  bool _loading = false;

  Future<void> _toggle() async {
    setState(() => _open = !_open);
    if (_open && _results == null && !_loading) {
      setState(() => _loading = true);
      try {
        final rows = await widget.api.sessionResults(widget.record.id);
        if (!mounted) return;
        setState(() {
          _results = rows;
          _loading = false;
        });
      } on RecordsApiException {
        if (!mounted) return;
        setState(() {
          _results = const [];
          _loading = false;
        });
      }
    }
  }

  String get _dateLabel {
    final d = widget.record.startedDate;
    if (d == null) return '—';
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    final hh = d.hour.toString().padLeft(2, '0');
    final mm = d.minute.toString().padLeft(2, '0');
    return '${d.day} ${months[d.month - 1]} ${d.year}  ·  $hh:$mm';
  }

  @override
  Widget build(BuildContext context) {
    return RecordCard(
      onTap: _toggle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40, height: 40,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppPalette.surfaceRaised,
                  borderRadius: BorderRadius.circular(AppRadii.sm),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text('DAY', style: AppTheme.label.copyWith(fontSize: 7)),
                    Text('${widget.record.dayIndex}',
                        style: AppTheme.value.copyWith(fontSize: 14)),
                  ],
                ),
              ),
              const SizedBox(width: AppGaps.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_dateLabel, style: AppTheme.value.copyWith(fontSize: 13)),
                    const SizedBox(height: 2),
                    Text(
                      '${widget.record.exerciseCount} exercise'
                      '${widget.record.exerciseCount == 1 ? '' : 's'}'
                      '${widget.record.conditionName != null ? ' · ${widget.record.conditionName}' : ''}',
                      style: AppTheme.caption,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Icon(_open ? Icons.expand_less : Icons.expand_more,
                  color: AppPalette.textMuted),
            ],
          ),
          if (_open) ...[
            const SizedBox(height: AppGaps.md),
            if (_loading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(AppGaps.md),
                  child: SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: AppPalette.brandCyan),
                  ),
                ),
              )
            else if ((_results ?? const []).isEmpty)
              Text('No exercises were completed in this session.',
                  style: AppTheme.caption)
            else
              for (final r in _results!) ...[
                Container(
                  margin: const EdgeInsets.only(bottom: AppGaps.sm),
                  padding: const EdgeInsets.all(AppGaps.sm),
                  decoration: BoxDecoration(
                    color: AppPalette.background,
                    borderRadius: BorderRadius.circular(AppRadii.sm),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(r.exerciseName,
                          style: AppTheme.value.copyWith(fontSize: 12)),
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
                            value: r.targetReps != null
                                ? '${r.repsCompleted}/${r.targetReps}'
                                : '${r.repsCompleted}',
                          ),
                          StatTile(
                            label: 'Quality',
                            value: r.meanQualityPct?.toStringAsFixed(0) ?? '—',
                            suffix: r.meanQualityPct == null ? null : '%',
                          ),
                          StatTile(
                            label: 'Pain',
                            value: r.painScore?.toString() ?? '—',
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
          ],
        ],
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  const _ProgressCard({required this.item});

  final ProgressItem item;

  @override
  Widget build(BuildContext context) {
    return RecordCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(item.name, style: AppTheme.value.copyWith(fontSize: 14)),
                    const SizedBox(height: 2),
                    Text(
                      item.lowerIsBetter ? 'Lower is better' : 'Higher is better',
                      style: AppTheme.caption,
                    ),
                  ],
                ),
              ),
              ChangeChip(changeDeg: item.changeDeg, improved: item.improved),
            ],
          ),
          const SizedBox(height: AppGaps.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              StatTile(
                label: 'Day ${item.firstDay}',
                value: item.firstValue?.toStringAsFixed(1) ?? '—',
                suffix: item.firstValue == null ? null : '°',
              ),
              StatTile(
                label: 'Day ${item.latestDay}',
                value: item.latestValue?.toStringAsFixed(1) ?? '—',
                suffix: item.latestValue == null ? null : '°',
                tone: item.improved == true
                    ? AppPalette.success
                    : item.improved == false
                        ? AppPalette.danger
                        : null,
              ),
              StatTile(
                label: 'Best',
                value: item.bestValue?.toStringAsFixed(1) ?? '—',
                suffix: item.bestValue == null ? null : '°',
              ),
              StatTile(label: 'Sessions', value: '${item.sessions}'),
            ],
          ),
          const SizedBox(height: AppGaps.md),
          TrendSparkline(
            points: item.trend,
            target: item.targetRomDeg,
            lowerIsBetter: item.lowerIsBetter,
          ),
        ],
      ),
    );
  }
}

/// Bottom sheet listing every seeded condition, grouped by body region.
class _ConditionPicker extends StatefulWidget {
  const _ConditionPicker({required this.api});

  final RecordsApi api;

  @override
  State<_ConditionPicker> createState() => _ConditionPickerState();
}

class _ConditionPickerState extends State<_ConditionPicker> {
  List<Condition> _conditions = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final list = await widget.api.listConditions();
      if (!mounted) return;
      setState(() {
        _conditions = list;
        _loading = false;
      });
    } on RecordsApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final regions = <String, List<Condition>>{};
    for (final c in _conditions) {
      regions.putIfAbsent(c.bodyRegion, () => []).add(c);
    }

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.82,
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
              width: 38, height: 4,
              decoration: BoxDecoration(
                color: AppPalette.border,
                borderRadius: BorderRadius.circular(AppRadii.pill),
              ),
            ),
          ),
          const SizedBox(height: AppGaps.lg),
          const Text('Assign a condition', style: AppTheme.title),
          const SizedBox(height: AppGaps.xs),
          Text(
            'The exercise protocol follows from the condition. Targets can be '
            'tuned in protocols_seed.yaml.',
            style: AppTheme.caption,
          ),
          const SizedBox(height: AppGaps.lg),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(AppGaps.xl),
              child: Center(
                  child: CircularProgressIndicator(color: AppPalette.brandCyan)),
            )
          else if (_error != null)
            Text(_error!, style: AppTheme.body.copyWith(color: AppPalette.danger))
          else
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final entry in regions.entries) ...[
                    Padding(
                      padding: const EdgeInsets.only(
                          top: AppGaps.sm, bottom: AppGaps.sm),
                      child: Text('${entry.key} BODY', style: AppTheme.label),
                    ),
                    for (final c in entry.value) ...[
                      RecordCard(
                        onTap: () => Navigator.of(context).pop(c),
                        padding: const EdgeInsets.all(AppGaps.md),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(c.name,
                                      style:
                                          AppTheme.value.copyWith(fontSize: 14)),
                                  const SizedBox(height: 2),
                                  Text('${c.exerciseCount} exercises',
                                      style: AppTheme.caption),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right,
                                color: AppPalette.textMuted),
                          ],
                        ),
                      ),
                      const SizedBox(height: AppGaps.sm),
                    ],
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

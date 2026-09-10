import 'dart:async';

import 'package:flutter/material.dart';

import '../models/records.dart';
import '../services/records_api.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/brand.dart';
import '../widgets/record_widgets.dart';
import 'patient_detail_screen.dart';

/// ============================================================================
/// PATIENTS
/// ============================================================================
/// The clinic's caseload. Search, open, or add.
///
/// This is the entry point to everything records-related; the live session is
/// reached THROUGH a patient rather than alongside them, so a recorded session
/// can never end up without someone attached to it.
/// ============================================================================
class PatientsScreen extends StatefulWidget {
  const PatientsScreen({required this.session, super.key});

  final SessionController session;

  @override
  State<PatientsScreen> createState() => _PatientsScreenState();
}

class _PatientsScreenState extends State<PatientsScreen> {
  final _searchController = TextEditingController();

  List<Patient> _patients = const [];
  bool _loading = true;
  String? _error;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load({String? search}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await widget.session.api.listPatients(search: search);
      if (!mounted) return;
      setState(() {
        _patients = list;
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

  void _onSearchChanged(String value) {
    // Debounced so typing a name does not fire a request per keystroke.
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300),
        () => _load(search: value.trim()));
  }

  Future<void> _openNewPatientSheet() async {
    final created = await showModalBottomSheet<Patient>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppPalette.transparent,
      builder: (_) => _NewPatientSheet(api: widget.session.api),
    );
    if (created != null && mounted) {
      await _load();
      if (!mounted) return;
      _open(created);
    }
  }

  void _open(Patient patient) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => PatientDetailScreen(
          session: widget.session,
          patient: patient,
        ),
      ),
    ).then((_) => _load(search: _searchController.text.trim()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNewPatientSheet,
        backgroundColor: AppPalette.brandGold,
        foregroundColor: AppPalette.textOnAccent,
        icon: const Icon(Icons.person_add_alt_1),
        label: const Text('New patient'),
      ),
      body: Column(
        children: [
          const BrandHeader(
            height: 132,
            child: Padding(
              padding: EdgeInsets.only(top: AppGaps.xl),
              child: Wordmark(fontSize: 26),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppGaps.lg, AppGaps.lg, AppGaps.lg, AppGaps.sm),
            child: TextField(
              controller: _searchController,
              onChanged: _onSearchChanged,
              style: AppTheme.body,
              decoration: InputDecoration(
                hintText: 'Search by name or patient ID',
                prefixIcon: const Icon(Icons.search, color: AppPalette.textMuted),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close, color: AppPalette.textMuted),
                        onPressed: () {
                          _searchController.clear();
                          _load();
                        },
                      ),
              ),
            ),
          ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: AppPalette.brandCyan),
      );
    }
    if (_error != null) {
      return _ErrorState(message: _error!, onRetry: _load);
    }
    if (_patients.isEmpty) {
      return _EmptyState(
        icon: Icons.groups_outlined,
        title: _searchController.text.isEmpty
            ? 'No patients yet'
            : 'No match for "${_searchController.text}"',
        body: _searchController.text.isEmpty
            ? 'Add the first patient to start keeping records.'
            : 'Try a different name or patient ID.',
      );
    }

    return RefreshIndicator(
      color: AppPalette.brandCyan,
      backgroundColor: AppPalette.surface,
      onRefresh: () => _load(search: _searchController.text.trim()),
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(
            AppGaps.lg, AppGaps.sm, AppGaps.lg, 96),
        itemCount: _patients.length,
        separatorBuilder: (_, __) => const SizedBox(height: AppGaps.sm),
        itemBuilder: (context, i) => _PatientRow(
          patient: _patients[i],
          onTap: () => _open(_patients[i]),
        ),
      ),
    );
  }
}

class _PatientRow extends StatelessWidget {
  const _PatientRow({required this.patient, required this.onTap});

  final Patient patient;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final unassigned = patient.activeCondition == null;
    return RecordCard(
      onTap: onTap,
      child: Row(
        children: [
          PatientAvatar(patient: patient),
          const SizedBox(width: AppGaps.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(patient.fullName,
                    style: AppTheme.value.copyWith(fontSize: 15)),
                const SizedBox(height: 2),
                Text(
                  patient.activeCondition ?? 'No condition assigned',
                  style: AppTheme.caption.copyWith(
                    color: unassigned
                        ? AppPalette.brandGold
                        : AppPalette.textSecondary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: AppGaps.sm),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(patient.code, style: AppTheme.label),
              const SizedBox(height: 3),
              Text(
                patient.sessionCount == 1
                    ? '1 session'
                    : '${patient.sessionCount} sessions',
                style: AppTheme.caption,
              ),
            ],
          ),
          const Icon(Icons.chevron_right, color: AppPalette.textMuted),
        ],
      ),
    );
  }
}

/// Bottom sheet for adding a patient. Only the name is required — a clinic
/// registering someone mid-appointment should not be blocked on a date of birth.
class _NewPatientSheet extends StatefulWidget {
  const _NewPatientSheet({required this.api});

  final RecordsApi api;

  @override
  State<_NewPatientSheet> createState() => _NewPatientSheetState();
}

class _NewPatientSheetState extends State<_NewPatientSheet> {
  final _name = TextEditingController();
  final _dob = TextEditingController();
  final _phone = TextEditingController();
  String? _sex;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _dob.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'A name is required.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final created = await widget.api.createPatient(
        fullName: _name.text.trim(),
        dateOfBirth: _dob.text.trim().isEmpty ? null : _dob.text.trim(),
        sex: _sex,
        phone: _phone.text.trim().isEmpty ? null : _phone.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(created);
    } on RecordsApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
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
                  width: 38, height: 4,
                  decoration: BoxDecoration(
                    color: AppPalette.border,
                    borderRadius: BorderRadius.circular(AppRadii.pill),
                  ),
                ),
              ),
              const SizedBox(height: AppGaps.lg),
              const Text('New patient', style: AppTheme.title),
              const SizedBox(height: AppGaps.xs),
              Text('A patient ID is generated automatically.',
                  style: AppTheme.caption),
              const SizedBox(height: AppGaps.lg),

              TextField(
                controller: _name,
                autofocus: true,
                textCapitalization: TextCapitalization.words,
                style: AppTheme.body,
                decoration: const InputDecoration(labelText: 'Full name'),
              ),
              const SizedBox(height: AppGaps.md),
              TextField(
                controller: _dob,
                style: AppTheme.body,
                decoration: const InputDecoration(
                  labelText: 'Date of birth (optional)',
                  hintText: 'YYYY-MM-DD',
                ),
              ),
              const SizedBox(height: AppGaps.md),
              // Chips rather than a DropdownButtonFormField on purpose: the
              // dropdown's `initialValue` parameter only exists on very recent
              // Flutter, and `value` is deprecated on it, so either spelling
              // breaks on some SDK the clinic might have. Three buttons have no
              // version surface at all and take one tap instead of two.
              Text('SEX', style: AppTheme.label),
              const SizedBox(height: AppGaps.sm),
              Row(
                children: [
                  for (final option in const [
                    ('F', 'Female'),
                    ('M', 'Male'),
                    ('Other', 'Other'),
                  ]) ...[
                    _ChoiceChipButton(
                      label: option.$2,
                      selected: _sex == option.$1,
                      onTap: () => setState(
                          () => _sex = _sex == option.$1 ? null : option.$1),
                    ),
                    const SizedBox(width: AppGaps.sm),
                  ],
                ],
              ),
              const SizedBox(height: AppGaps.md),
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                style: AppTheme.body,
                decoration: const InputDecoration(labelText: 'Phone (optional)'),
              ),

              if (_error != null) ...[
                const SizedBox(height: AppGaps.md),
                Text(_error!,
                    style: AppTheme.body.copyWith(color: AppPalette.danger)),
              ],

              const SizedBox(height: AppGaps.lg),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: FilledButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: 18, height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: AppPalette.textOnAccent),
                        )
                      : const Text('Save patient'),
                ),
              ),
              const SizedBox(height: AppGaps.sm),
            ],
          ),
        ),
      ),
    );
  }
}

/// Small selectable pill, used where a dropdown would be overkill.
class _ChoiceChipButton extends StatelessWidget {
  const _ChoiceChipButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppPalette.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppGaps.md, vertical: AppGaps.sm),
          decoration: BoxDecoration(
            color: selected ? AppPalette.brandCyan : AppPalette.surface,
            borderRadius: BorderRadius.circular(AppRadii.sm),
            border: Border.all(
              color: selected ? AppPalette.brandCyan : AppPalette.border,
            ),
          ),
          child: Text(
            label,
            style: AppTheme.body.copyWith(
              fontSize: 13,
              color: selected
                  ? AppPalette.textOnAccent
                  : AppPalette.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.title, required this.body});

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppGaps.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 46, color: AppPalette.textMuted),
            const SizedBox(height: AppGaps.md),
            Text(title, style: AppTheme.value, textAlign: TextAlign.center),
            const SizedBox(height: AppGaps.xs),
            Text(body, style: AppTheme.caption, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppGaps.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 46, color: AppPalette.danger),
            const SizedBox(height: AppGaps.md),
            Text('Records unavailable',
                style: AppTheme.value, textAlign: TextAlign.center),
            const SizedBox(height: AppGaps.xs),
            Text(message, style: AppTheme.caption, textAlign: TextAlign.center),
            const SizedBox(height: AppGaps.lg),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ],
        ),
      ),
    );
  }
}

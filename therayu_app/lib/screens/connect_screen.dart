import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/skeleton_topology.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/brand.dart';
import 'live_session_screen.dart';

/// ============================================================================
/// CONNECT SCREEN
/// ============================================================================
/// Built on the Figma login composition: the teal brand header with its gold
/// wave, then content below on the app ground.
///
/// Functionally it does three things — pick a body profile, point the app at the
/// PC, go live. The pre-flight health check earns its place by separating "wrong
/// IP" from "firewall blocked", which is the single most common setup dead-end
/// and otherwise looks identical to the user.
/// ============================================================================
class ConnectScreen extends StatefulWidget {
  const ConnectScreen({required this.session, super.key});

  final SessionController session;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late final TextEditingController _urlController =
      TextEditingController(text: widget.session.serverUrl);

  bool _testing = false;
  String? _testResult;
  bool _testOk = false;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _testResult = null;
    });

    final result = await widget.session.testConnection(_urlController.text);

    if (!mounted) return;
    setState(() {
      _testing = false;
      _testOk = result.ok;
      _testResult = result.detail;
    });
  }

  Future<void> _start() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) {
      setState(() {
        _testOk = false;
        _testResult = 'Enter the PC\'s LAN address first.';
      });
      return;
    }

    await widget.session.connect(url);
    if (!mounted) return;

    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => LiveSessionScreen(session: widget.session),
      ),
    );

    // Returning here means the session ended; make sure nothing is left running.
    await widget.session.disconnect();
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;

    return Scaffold(
      body: AnimatedBuilder(
        animation: session,
        builder: (context, _) {
          return CustomScrollView(
            slivers: [
              // The brand header runs edge to edge behind the status bar, which
              // is how the Figma frames present it.
              const SliverToBoxAdapter(
                child: BrandHeader(
                  height: 210,
                  child: Padding(
                    padding: EdgeInsets.only(top: AppGaps.xxl),
                    child: Wordmark(fontSize: 36),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppGaps.xl,
                    AppGaps.lg,
                    AppGaps.xl,
                    AppGaps.xxl,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Center(
                        child: Column(
                          children: [
                            Text('Welcome to Therayu', style: AppTheme.title),
                            SizedBox(height: AppGaps.sm),
                            GoldRule(),
                            SizedBox(height: AppGaps.sm),
                            Text(
                              'Live pose tracking, clinical goniometry and '
                              'rehabilitation assessment.',
                              textAlign: TextAlign.center,
                              style: AppTheme.caption,
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: AppGaps.xxl),

                      // ---------------- body mode ----------------
                      const _SectionLabel('BODY TRACKING PROFILE'),
                      const SizedBox(height: AppGaps.md),
                      for (final mode in BodyMode.values)
                        _ModeOption(
                          mode: mode,
                          selected: session.bodyMode == mode,
                          onTap: () => session.setBodyMode(mode),
                        ),

                      const SizedBox(height: AppGaps.xl),

                      // ---------------- server ----------------
                      const _SectionLabel('INFERENCE SERVER'),
                      const SizedBox(height: AppGaps.sm),
                      const Text(
                        'Run ws_server.py on your PC and enter the address it '
                        'prints. Both devices must be on the same Wi-Fi.',
                        style: AppTheme.caption,
                      ),
                      const SizedBox(height: AppGaps.md),
                      TextField(
                        controller: _urlController,
                        keyboardType: TextInputType.url,
                        autocorrect: false,
                        style: AppTheme.value.copyWith(fontSize: 15),
                        inputFormatters: [
                          FilteringTextInputFormatter.deny(RegExp(r'\s')),
                        ],
                        decoration: const InputDecoration(
                          hintText: '192.168.1.7:8765',
                          prefixIcon: Icon(
                            Icons.lan_outlined,
                            size: 18,
                            color: AppPalette.brandCyan,
                          ),
                        ),
                        onChanged: (_) => setState(() => _testResult = null),
                      ),

                      if (_testResult != null) ...[
                        const SizedBox(height: AppGaps.md),
                        _ResultBanner(ok: _testOk, message: _testResult!),
                      ],

                      const SizedBox(height: AppGaps.lg),
                      OutlinedButton.icon(
                        onPressed: _testing ? null : _test,
                        icon: _testing
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.wifi_tethering_rounded, size: 18),
                        label: Text(_testing ? 'Testing…' : 'Test connection'),
                      ),
                      const SizedBox(height: AppGaps.md),
                      FilledButton.icon(
                        onPressed: _start,
                        icon: const Icon(Icons.play_arrow_rounded),
                        label: const Text('Start live session'),
                      ),

                      if (session.camera.error != null) ...[
                        const SizedBox(height: AppGaps.lg),
                        _ResultBanner(ok: false, message: session.camera.error!),
                      ],

                      const SizedBox(height: AppGaps.xxl),
                      const _SetupHint(),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 3,
          height: 12,
          decoration: BoxDecoration(
            gradient: AppPalette.goldWave,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: AppGaps.sm),
        Text(text, style: AppTheme.cardHeader),
      ],
    );
  }
}

class _ResultBanner extends StatelessWidget {
  const _ResultBanner({required this.ok, required this.message});

  final bool ok;
  final String message;

  @override
  Widget build(BuildContext context) {
    final tint = ok ? AppPalette.success : AppPalette.danger;

    return Container(
      padding: const EdgeInsets.all(AppGaps.md),
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.1),
        borderRadius: AppRadii.mdAll,
        border: Border.all(color: tint.withValues(alpha: 0.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            ok
                ? Icons.check_circle_outline_rounded
                : Icons.error_outline_rounded,
            size: 16,
            color: tint,
          ),
          const SizedBox(width: AppGaps.sm),
          Expanded(
            child: Text(
              message,
              style: AppTheme.caption.copyWith(color: AppPalette.textPrimary),
            ),
          ),
        ],
      ),
    );
  }
}

class _ModeOption extends StatelessWidget {
  const _ModeOption({
    required this.mode,
    required this.selected,
    required this.onTap,
  });

  final BodyMode mode;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final icon = switch (mode) {
      BodyMode.upperBody => Icons.airline_seat_recline_normal_rounded,
      BodyMode.lowerBody => Icons.directions_walk_rounded,
      BodyMode.fullBody => Icons.accessibility_new_rounded,
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: AppGaps.sm),
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          padding: const EdgeInsets.all(AppGaps.md + 2),
          decoration: BoxDecoration(
            color: selected
                ? AppPalette.brandCyan.withValues(alpha: 0.12)
                : AppPalette.surface,
            borderRadius: AppRadii.mdAll,
            border: Border.all(
              color: selected ? AppPalette.brandCyan : AppPalette.border,
              width: selected ? 1.6 : 1,
            ),
          ),
          child: Row(
            children: [
              Icon(
                icon,
                size: 22,
                color: selected ? AppPalette.brandCyan : AppPalette.textSecondary,
              ),
              const SizedBox(width: AppGaps.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '${mode.shortLabel} body',
                      style: AppTheme.body.copyWith(
                        fontWeight: FontWeight.w700,
                        color: selected
                            ? AppPalette.brandCyan
                            : AppPalette.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(mode.subtitle, style: AppTheme.caption),
                  ],
                ),
              ),
              if (selected)
                const Icon(
                  Icons.check_circle_rounded,
                  size: 18,
                  color: AppPalette.brandCyan,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SetupHint extends StatelessWidget {
  const _SetupHint();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppGaps.lg),
      decoration: BoxDecoration(
        color: AppPalette.surface.withValues(alpha: 0.6),
        borderRadius: AppRadii.mdAll,
        border: Border.all(color: AppPalette.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionLabel('ON THE PC'),
          const SizedBox(height: AppGaps.md),
          Text(
            'cd upper_body_ai\n'
            'pip install -r server/requirements-server.txt\n'
            'python -m server.ws_server',
            style: AppTheme.value.copyWith(
              fontSize: 11.5,
              color: AppPalette.brandCyanLight,
              height: 1.7,
            ),
          ),
          const SizedBox(height: AppGaps.md),
          const Text(
            'The server prints every LAN address it is reachable on. If the test '
            'above times out, allow Python through Windows Firewall on private '
            'networks.',
            style: AppTheme.caption,
          ),
        ],
      ),
    );
  }
}

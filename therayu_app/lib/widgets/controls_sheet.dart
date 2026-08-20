import 'package:flutter/material.dart';

import '../services/camera_streamer.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';

/// Bottom sheet replacing the desktop app's keyboard hotkeys (H/C/A/B/J,
/// 1/2/3 for filters, R, S, D). Everything reachable from the terminal is
/// reachable here with a thumb.
class ControlsSheet extends StatelessWidget {
  const ControlsSheet({required this.session, super.key});

  final SessionController session;

  static Future<void> show(BuildContext context, SessionController session) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ControlsSheet(session: session),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: session,
      builder: (context, _) {
        return DraggableScrollableSheet(
          initialChildSize: 0.72,
          minChildSize: 0.4,
          maxChildSize: 0.94,
          expand: false,
          builder: (context, scrollController) {
            return Container(
              decoration: const BoxDecoration(
                color: AppPalette.surface,
                border: Border(top: BorderSide(color: AppPalette.border)),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppRadii.lg),
                ),
              ),
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(
                  AppGaps.lg,
                  AppGaps.md,
                  AppGaps.lg,
                  AppGaps.xl,
                ),
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppPalette.border,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: AppGaps.lg),
                  const Text('Session controls', style: AppTheme.title),
                  const SizedBox(height: AppGaps.xl),

                  // ---------------- capture ----------------
                  const _SectionLabel('Capture'),
                  _ActionTile(
                    icon: Icons.photo_camera_outlined,
                    title: 'Save annotated screenshot',
                    subtitle: 'Written to output/screenshots on the PC',
                    onTap: () {
                      session.captureScreenshot();
                      Navigator.of(context).pop();
                    },
                  ),
                  _ActionTile(
                    icon: session.isRecording
                        ? Icons.stop_circle_outlined
                        : Icons.fiber_manual_record_outlined,
                    title: session.isRecording
                        ? 'Stop recording'
                        : 'Record annotated video',
                    subtitle: 'Written to output/recordings on the PC',
                    tint: session.isRecording ? AppPalette.danger : null,
                    onTap: () {
                      session.toggleRecording();
                      Navigator.of(context).pop();
                    },
                  ),
                  _ActionTile(
                    icon: Icons.flip_camera_android_outlined,
                    title: 'Switch camera',
                    subtitle: session.camera.isFrontCamera
                        ? 'Currently front-facing'
                        : 'Currently rear-facing',
                    enabled: session.camera.hasMultipleCameras,
                    onTap: () => session.switchCamera(),
                  ),
                  _ActionTile(
                    icon: Icons.restart_alt_rounded,
                    title: 'Reset range-of-motion history',
                    subtitle: 'Clears every joint\'s session min / max / peak',
                    onTap: () {
                      session.resetRom();
                      Navigator.of(context).pop();
                    },
                  ),

                  const SizedBox(height: AppGaps.xl),

                  // ---------------- overlay ----------------
                  const _SectionLabel('Skeleton overlay'),
                  _SwitchTile(
                    label: 'Bones',
                    value: session.showBones,
                    onChanged: (v) => session.toggleOverlay(bones: v),
                  ),
                  _SwitchTile(
                    label: 'Joint nodes',
                    value: session.showJoints,
                    onChanged: (v) => session.toggleOverlay(joints: v),
                  ),
                  _SwitchTile(
                    label: 'Hand & finger skeleton',
                    subtitle: '21 joints per hand. Turning this OFF roughly '
                        'doubles the frame rate — it is the most expensive '
                        'stage in the pipeline.',
                    value: session.showHands,
                    onChanged: (v) => session.toggleOverlay(hands: v),
                  ),
                  _SwitchTile(
                    label: 'Goniometric arcs',
                    subtitle: 'Angle sweeps drawn at each joint pivot',
                    value: session.showArcs,
                    onChanged: (v) => session.toggleOverlay(arcs: v),
                  ),
                  _SwitchTile(
                    label: 'Angle cards',
                    value: session.showAngleCards,
                    onChanged: (v) => session.toggleOverlay(angleCards: v),
                  ),
                  _SwitchTile(
                    label: 'Tracking badge',
                    subtitle: 'Track ID and landmark confidence',
                    value: session.showConfidenceBadge,
                    onChanged: (v) => session.toggleOverlay(confidenceBadge: v),
                  ),

                  const SizedBox(height: AppGaps.xl),

                  // ---------------- speed ----------------
                  const _SectionLabel('Responsiveness'),
                  _SwitchTile(
                    label: 'Fast pose model',
                    subtitle: 'Drops MediaPipe complexity from 1 to 0 — roughly '
                        'twice as fast, with slightly less precise landmarks. '
                        'Use it when the skeleton trails the body.',
                    value: session.frame.telemetry.complexity == 0,
                    onChanged: (v) => session.setFastMode(fast: v),
                  ),

                  const SizedBox(height: AppGaps.xl),

                  // ---------------- smoothing ----------------
                  const _SectionLabel('Temporal filter'),
                  const Padding(
                    padding: EdgeInsets.only(bottom: AppGaps.sm),
                    child: Text(
                      'Zero-jitter smoothing applied to landmarks and angles on '
                      'the server. One-Euro adapts to movement speed; Kalman is '
                      'steadier but lags; EMA is the simplest.',
                      style: AppTheme.caption,
                    ),
                  ),
                  _ChoiceRow(
                    options: const <String, String>{
                      'one_euro': 'One-Euro',
                      'kalman': 'Kalman',
                      'ema': 'EMA',
                      'none': 'Off',
                    },
                    selected: session.frame.telemetry.filterType,
                    onSelected: session.setFilter,
                  ),

                  const SizedBox(height: AppGaps.xl),

                  // ---------------- stream ----------------
                  const _SectionLabel('Stream quality'),
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppGaps.sm),
                    child: Text(
                      'Frames are sent uncompressed, so bandwidth scales with '
                      'resolution: roughly 18 / 55 / 165 Mbps. '
                      '${session.camera.quality.hint}. '
                      'Drop this first if the frame rate is unstable.',
                      style: AppTheme.caption,
                    ),
                  ),
                  _ChoiceRow(
                    options: <String, String>{
                      for (final q in CaptureQuality.values) q.name: q.label,
                    },
                    selected: session.camera.quality.name,
                    onSelected: (name) {
                      final match = CaptureQuality.values
                          .firstWhere((q) => q.name == name);
                      session.setQuality(match);
                    },
                  ),

                  const SizedBox(height: AppGaps.lg),
                  _SwitchTile(
                    label: 'Mirror view',
                    subtitle: 'Patient sees themselves as in a mirror. Turning '
                        'this off makes left/right joint labels anatomically '
                        'literal.',
                    value: session.camera.mirrorSelfie,
                    onChanged: (v) => session.setMirror(mirror: v),
                  ),

                  const SizedBox(height: AppGaps.xl),
                  Text(
                    'Server: ${session.serverUrl}',
                    style: AppTheme.caption.copyWith(color: AppPalette.textMuted),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppGaps.sm),
      child: Text(text.toUpperCase(), style: AppTheme.cardHeader),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.icon,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.tint,
    this.enabled = true,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;
  final Color? tint;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final color = enabled
        ? (tint ?? AppPalette.textPrimary)
        : AppPalette.textMuted;

    return Opacity(
      opacity: enabled ? 1 : 0.45,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: AppRadii.mdAll,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppGaps.md - 2),
          child: Row(
            children: [
              Icon(icon, size: 20, color: color),
              const SizedBox(width: AppGaps.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(title, style: AppTheme.body.copyWith(color: color)),
                    if (subtitle != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(subtitle!, style: AppTheme.caption),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SwitchTile extends StatelessWidget {
  const _SwitchTile({
    required this.label,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });

  final String label;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppGaps.xs),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(label, style: AppTheme.body),
                if (subtitle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(subtitle!, style: AppTheme.caption),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppGaps.md),
          Switch.adaptive(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _ChoiceRow extends StatelessWidget {
  const _ChoiceRow({
    required this.options,
    required this.selected,
    required this.onSelected,
  });

  final Map<String, String> options;
  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppGaps.sm,
      runSpacing: AppGaps.sm,
      children: [
        for (final entry in options.entries)
          GestureDetector(
            onTap: () => onSelected(entry.key),
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppGaps.lg,
                vertical: AppGaps.sm + 1,
              ),
              decoration: BoxDecoration(
                color: entry.key == selected
                    ? AppPalette.accent.withValues(alpha: 0.16)
                    : AppPalette.surfaceRaised,
                borderRadius: AppRadii.mdAll,
                border: Border.all(
                  color: entry.key == selected
                      ? AppPalette.accent
                      : AppPalette.border,
                ),
              ),
              child: Text(
                entry.value,
                style: AppTheme.body.copyWith(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: entry.key == selected
                      ? AppPalette.accent
                      : AppPalette.textSecondary,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

import 'package:flutter/material.dart';

import '../models/pose_frame.dart';
import '../models/skeleton_topology.dart';
import '../services/pose_socket.dart';
import '../theme/app_theme.dart';
import 'skeleton_painter.dart';

/// ============================================================================
/// TELEMETRY BAR
/// ============================================================================
/// Ports `_draw_telemetry_bar`: brand, throughput, latency, active mode and the
/// recording indicator in one thin strip along the top.
class TelemetryBar extends StatelessWidget {
  const TelemetryBar({
    required this.status,
    required this.frame,
    required this.pipelineFps,
    required this.roundTrip,
    required this.isRecording,
    required this.sessionDuration,
    required this.hudVisible,
    required this.onToggleHud,
    required this.onOpenControls,
    required this.onDisconnect,
    super.key,
  });

  final SocketStatus status;
  final PoseFrame frame;
  final double pipelineFps;
  final Duration? roundTrip;
  final bool isRecording;
  final Duration sessionDuration;
  final bool hudVisible;
  final VoidCallback onToggleHud;
  final VoidCallback onOpenControls;
  final VoidCallback onDisconnect;

  @override
  Widget build(BuildContext context) {
    // Round-trip is the honest latency figure: it includes the network in both
    // directions, not just the server's inference time.
    final latencyMs = roundTrip?.inMilliseconds ?? frame.telemetry.latencyMs.round();

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppGaps.md,
        vertical: AppGaps.sm,
      ),
      decoration: BoxDecoration(
        // Translucent because it now sits over live video rather than above it.
        // A gradient rather than a flat fill so the bar fades into the picture
        // instead of cutting a hard band across the top of the frame.
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            AppPalette.brandTealDeep.withValues(alpha: 0.92),
            AppPalette.brandTealDeep.withValues(alpha: 0.55),
            Colors.transparent,
          ],
          stops: const <double>[0, 0.7, 1],
        ),
      ),
      child: Row(
        children: [
          _ConnectionDot(status: status),
          const SizedBox(width: AppGaps.sm),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const Text('THERAYU', style: AppTheme.cardHeader),
                  const SizedBox(width: AppGaps.sm),
                  Text(
                    _formatDuration(sessionDuration),
                    style: AppTheme.telemetry.copyWith(
                      color: AppPalette.textMuted,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              Text(
                // Round trip first, then the inference share of it. Seeing the
                // split makes it obvious whether latency is the network or the
                // model, instead of leaving it to guesswork.
                '${pipelineFps.toStringAsFixed(0)} fps  ·  $latencyMs ms  '
                '(model ${frame.telemetry.inferMs.toStringAsFixed(0)})',
                style: AppTheme.telemetry,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
          const SizedBox(width: AppGaps.md),

          // Framing status lives here rather than as a separate floating chip,
          // which would be one more thing covering the patient.
          Flexible(child: _FramingChip(frame: frame, status: status)),

          const Spacer(),

          if (isRecording) ...[
            const _RecordingPip(),
            const SizedBox(width: AppGaps.sm),
          ],
          IconButton(
            onPressed: onToggleHud,
            icon: Icon(
              hudVisible
                  ? Icons.visibility_off_outlined
                  : Icons.visibility_outlined,
            ),
            iconSize: 20,
            visualDensity: VisualDensity.compact,
            tooltip: hudVisible ? 'Hide readouts' : 'Show readouts',
          ),
          IconButton(
            onPressed: onOpenControls,
            icon: const Icon(Icons.tune_rounded),
            iconSize: 20,
            visualDensity: VisualDensity.compact,
            tooltip: 'Session controls',
          ),
          IconButton(
            onPressed: onDisconnect,
            icon: const Icon(Icons.close_rounded, color: AppPalette.textSecondary),
            iconSize: 20,
            visualDensity: VisualDensity.compact,
            tooltip: 'End session',
          ),
        ],
      ),
    );
  }

  static String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}

/// Compact framing / detection status.
class _FramingChip extends StatelessWidget {
  const _FramingChip({required this.frame, required this.status});

  final PoseFrame frame;
  final SocketStatus status;

  @override
  Widget build(BuildContext context) {
    if (!status.isLive) {
      return StatusPill(
        label: switch (status) {
          SocketStatus.idle => 'SERVER OFFLINE',
          SocketStatus.connecting => 'CONNECTING…',
          SocketStatus.reconnecting => 'SERVER OFFLINE · RETRYING',
          SocketStatus.failed => 'SERVER OFFLINE',
          SocketStatus.connected => 'LIVE',
        },
        tint: status == SocketStatus.connecting
            ? AppPalette.warning
            : AppPalette.danger,
        icon: Icons.cloud_off_rounded,
      );
    }

    final telemetry = frame.telemetry;

    if (!telemetry.personDetected) {
      return const StatusPill(
        label: 'NO PERSON',
        tint: AppPalette.warning,
        icon: Icons.person_search_rounded,
      );
    }

    final ready = telemetry.isReady;
    return StatusPill(
      label: ready
          ? 'READY  ·  ${telemetry.overallConfidence.toStringAsFixed(0)}%'
          : 'POSITIONING',
      tint: ready ? AppPalette.success : AppPalette.warning,
      icon: ready ? Icons.check_rounded : Icons.center_focus_weak_rounded,
    );
  }
}

class _ConnectionDot extends StatelessWidget {
  const _ConnectionDot({required this.status});

  final SocketStatus status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      SocketStatus.connected => AppPalette.success,
      SocketStatus.connecting || SocketStatus.reconnecting => AppPalette.warning,
      SocketStatus.failed => AppPalette.danger,
      SocketStatus.idle => AppPalette.textMuted,
    };

    return Container(
      width: 9,
      height: 9,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(color: color.withValues(alpha: 0.6), blurRadius: 7),
        ],
      ),
    );
  }
}

class _RecordingPip extends StatefulWidget {
  const _RecordingPip();

  @override
  State<_RecordingPip> createState() => _RecordingPipState();
}

class _RecordingPipState extends State<_RecordingPip>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.35, end: 1).animate(_pulse),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: AppPalette.danger,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 5),
          Text(
            'REC',
            style: AppTheme.telemetry.copyWith(color: AppPalette.danger),
          ),
        ],
      ),
    );
  }
}

/// ============================================================================
/// GUIDANCE BANNER
/// ============================================================================
/// Ports `_draw_guidance_overlay`. Shown only while framing is invalid, which is
/// exactly when the engine is refusing to report angles — so the banner explains
/// the blank readouts instead of leaving the user guessing.
class GuidanceBanner extends StatelessWidget {
  const GuidanceBanner({
    required this.message,
    this.kind = GuidanceKind.framing,
    super.key,
  });

  final String message;
  final GuidanceKind kind;

  @override
  Widget build(BuildContext context) {
    final tint = kind == GuidanceKind.framing
        ? AppPalette.warning
        : AppPalette.danger;

    return Center(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: AppGaps.xl),
        padding: const EdgeInsets.symmetric(
          horizontal: AppGaps.lg,
          vertical: AppGaps.md,
        ),
        constraints: const BoxConstraints(maxWidth: 460),
        decoration: BoxDecoration(
          color: AppPalette.scrim,
          borderRadius: AppRadii.mdAll,
          border: Border.all(color: tint, width: 1.4),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(kind.icon, size: 14, color: tint),
                const SizedBox(width: AppGaps.xs + 2),
                Text(
                  kind.title,
                  style: AppTheme.cardHeader.copyWith(color: tint),
                ),
              ],
            ),
            const SizedBox(height: AppGaps.sm),
            Text(message, style: AppTheme.body, textAlign: TextAlign.center),

            // An offline server and a badly framed body both leave the readouts
            // blank, but the fixes are completely unrelated. Spelling out the
            // remedy here stops "Reconnecting…" from being read as a camera
            // fault, which is exactly how it was being misread.
            if (kind == GuidanceKind.captureStalled) ...[
              const SizedBox(height: AppGaps.md),
              Container(
                padding: const EdgeInsets.all(AppGaps.sm),
                decoration: BoxDecoration(
                  color: AppPalette.brandTealDeep.withValues(alpha: 0.7),
                  borderRadius: AppRadii.smAll,
                ),
                child: Text(
                  'The server is connected and the camera is on, but the '
                  'browser is not producing frames. Reload the page (Ctrl+R). '
                  'If it persists, open Controls and lower Stream quality.',
                  style: AppTheme.caption.copyWith(
                    color: AppPalette.brandCyanLight,
                    height: 1.5,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
            if (kind == GuidanceKind.offline) ...[
              const SizedBox(height: AppGaps.md),
              Container(
                padding: const EdgeInsets.all(AppGaps.sm),
                decoration: BoxDecoration(
                  color: AppPalette.brandTealDeep.withValues(alpha: 0.7),
                  borderRadius: AppRadii.smAll,
                ),
                child: Text(
                  'The camera is fine — the Python engine is not answering.\n'
                  'Start it on your PC:  run.bat  (or  start_server.bat )',
                  style: AppTheme.caption.copyWith(
                    fontFamily: AppTheme.monoFamily,
                    color: AppPalette.brandCyanLight,
                    height: 1.6,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Why the readouts are blank. The two causes look identical on screen but have
/// nothing to do with each other, so they get different colours and copy.
enum GuidanceKind {
  /// Socket is down — the inference server is not running or not reachable.
  offline('INFERENCE SERVER OFFLINE', Icons.cloud_off_rounded),

  /// Socket is up but no frames are leaving the browser. Distinct from both of
  /// the others: the server is fine and the body may be perfectly framed, but
  /// nothing is being sent for it to look at.
  captureStalled('CAMERA FRAMES NOT REACHING SERVER', Icons.videocam_off_rounded),

  /// Socket is fine; the body is not fully inside the frame.
  framing('CAMERA POSITIONING', Icons.center_focus_strong_rounded);

  const GuidanceKind(this.title, this.icon);

  final String title;
  final IconData icon;
}

/// ============================================================================
/// ASSESSMENT PANEL
/// ============================================================================
/// Ports `_draw_physio_assessment_overlay`: movement-quality score, the active
/// movement classification, and symmetry / centre-of-gravity status.
class AssessmentPanel extends StatelessWidget {
  const AssessmentPanel({
    required this.frame,
    required this.mode,
    super.key,
  });

  final PoseFrame frame;
  final BodyMode mode;

  @override
  Widget build(BuildContext context) {
    final physio = frame.physio;
    final pct = physio.movementQualityPct;
    final tint = qualityColor(pct);

    return Container(
      padding: const EdgeInsets.all(AppGaps.md),
      decoration: AppTheme.hudCard,
      child: Row(
        children: [
          SizedBox(
            width: 54,
            height: 54,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CustomPaint(
                  size: const Size.square(54),
                  painter: QualityRingPainter(pct: pct, color: tint),
                ),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      pct.toStringAsFixed(0),
                      style: AppTheme.metricLarge.copyWith(
                        fontSize: 18,
                        color: tint,
                      ),
                    ),
                    Text(
                      '%',
                      style: AppTheme.caption.copyWith(
                        fontSize: 8,
                        color: AppPalette.textMuted,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: AppGaps.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('MOVEMENT QUALITY', style: AppTheme.cardHeader),
                const SizedBox(height: 3),
                Text(
                  frame.detectedExercise,
                  style: AppTheme.body.copyWith(
                    fontWeight: FontWeight.w700,
                    fontSize: 12.5,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: AppGaps.sm),
                Wrap(
                  spacing: AppGaps.xs + 2,
                  runSpacing: AppGaps.xs,
                  children: [
                    if (mode != BodyMode.upperBody) ...[
                      StatusPill(
                        label: physio.symmetryStatus,
                        tint: physio.isSymmetric
                            ? AppPalette.success
                            : AppPalette.warning,
                      ),
                      StatusPill(
                        label: 'COG ${physio.cogShiftStatus}',
                        tint: physio.isBalanced
                            ? AppPalette.success
                            : AppPalette.warning,
                      ),
                    ] else
                      const StatusPill(
                        label: 'UPPER POSTURE',
                        tint: AppPalette.success,
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Small tinted capsule used for statuses and badges.
class StatusPill extends StatelessWidget {
  const StatusPill({required this.label, required this.tint, this.icon, super.key});

  final String label;
  final Color tint;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppGaps.sm, vertical: 3),
      decoration: AppTheme.statusPill(tint),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 10, color: tint),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: AppTheme.cardHeader.copyWith(color: tint, fontSize: 9.5),
          ),
        ],
      ),
    );
  }
}

/// ============================================================================
/// CLINICAL FEEDBACK BAR
/// ============================================================================
/// Ports the "CLINICAL FEEDBACK" card. Cues are corrective instructions the
/// patient acts on immediately, so they get the widest, most legible strip.
class ClinicalFeedbackBar extends StatelessWidget {
  const ClinicalFeedbackBar({required this.messages, super.key});

  final List<String> messages;

  @override
  Widget build(BuildContext context) {
    if (messages.isEmpty) return const SizedBox.shrink();

    final primary = messages.first;
    final isPositive = primary.toLowerCase().contains('optimal');
    final tint = isPositive ? AppPalette.success : AppPalette.warning;

    // AnimatedSize keeps the strip from snapping between one and two lines as
    // the engine swaps cues, which happens several times a second in practice.
    return AnimatedSize(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOutCubic,
      alignment: Alignment.bottomCenter,
      child: Container(
        key: ValueKey(primary),
        width: double.infinity,
        padding: const EdgeInsets.symmetric(
          horizontal: AppGaps.md,
          vertical: AppGaps.sm + 2,
        ),
        decoration: BoxDecoration(
          color: AppPalette.surface.withValues(alpha: 0.9),
          borderRadius: AppRadii.mdAll,
          border: Border.all(color: tint.withValues(alpha: 0.5)),
        ),
        child: Row(
          children: [
            Icon(
              isPositive
                  ? Icons.check_circle_outline_rounded
                  : Icons.info_outline_rounded,
              size: 16,
              color: tint,
            ),
            const SizedBox(width: AppGaps.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(primary, style: AppTheme.body.copyWith(fontSize: 12.5)),
                  if (messages.length > 1)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        messages[1],
                        style: AppTheme.caption.copyWith(fontSize: 10.5),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// ============================================================================
/// BODY MODE SWITCHER
/// ============================================================================
/// Replaces the desktop app's terminal prompt and 1/2/3 hotkeys with a segmented
/// control. The mode also rides along on every frame header, so switching takes
/// effect on the very next frame rather than whenever a control message lands.
class BodyModeSwitcher extends StatelessWidget {
  const BodyModeSwitcher({
    required this.active,
    required this.onChanged,
    super.key,
  });

  final BodyMode active;
  final ValueChanged<BodyMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppPalette.surface.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(AppRadii.pill),
        border: Border.all(color: AppPalette.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final mode in BodyMode.values)
            _ModeChip(
              mode: mode,
              selected: mode == active,
              onTap: () => onChanged(mode),
            ),
        ],
      ),
    );
  }
}

class _ModeChip extends StatelessWidget {
  const _ModeChip({
    required this.mode,
    required this.selected,
    required this.onTap,
  });

  final BodyMode mode;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(
          horizontal: AppGaps.md + 2,
          vertical: AppGaps.sm - 1,
        ),
        decoration: BoxDecoration(
          color: selected ? AppPalette.accent : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadii.pill),
        ),
        child: Text(
          mode.shortLabel,
          style: AppTheme.cardHeader.copyWith(
            fontSize: 11,
            color: selected ? AppPalette.background : AppPalette.textSecondary,
          ),
        ),
      ),
    );
  }
}

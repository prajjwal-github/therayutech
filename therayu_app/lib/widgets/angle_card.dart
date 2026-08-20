import 'package:flutter/material.dart';

import '../models/pose_frame.dart';
import '../models/skeleton_topology.dart';
import '../theme/app_theme.dart';

/// A frosted HUD card listing the clinical angles for one body region.
///
/// Ports `_draw_selective_angles_hud` / `_draw_hud_card_box`: an accent-tinted
/// header strip over a translucent body, with label-left / value-right rows.
class AngleCard extends StatelessWidget {
  const AngleCard({
    required this.group,
    required this.frame,
    this.showRom = true,
    super.key,
  });

  final HudGroup group;
  final PoseFrame frame;

  /// Appends the session peak from `rom_summary`, which is the number a physio
  /// actually records — a live angle is transient, end-range is the outcome.
  final bool showRom;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: AppTheme.hudCard,
      clipBehavior: Clip.antiAlias,
      // mainAxisSize.min is load-bearing, not tidiness. These cards are placed
      // with Align inside a Stack, which hands the child the full stack height
      // as its maximum. An earlier version used Flexible + ListView here, so
      // each card expanded to the entire screen height and the bottom card drew
      // straight over the top one — which looked like the top card had vanished.
      // Sizing to content keeps every card exactly as tall as its rows.
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Header(title: group.title, tint: group.tint),
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppGaps.sm,
              vertical: AppGaps.xs + 2,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final row in group.rows)
                  _AngleRowTile(
                    row: row,
                    frame: frame,
                    showRom: showRom,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.title, required this.tint});

  final String title;
  final Color tint;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppGaps.sm, vertical: 5),
      decoration: BoxDecoration(
        color: AppPalette.surfaceRaised.withValues(alpha: 0.95),
        border: Border(bottom: BorderSide(color: tint.withValues(alpha: 0.45))),
      ),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 10,
            decoration: BoxDecoration(
              color: tint,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: AppGaps.xs + 2),
          Expanded(
            child: Text(
              title,
              style: AppTheme.cardHeader.copyWith(color: tint),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _AngleRowTile extends StatelessWidget {
  const _AngleRowTile({
    required this.row,
    required this.frame,
    required this.showRom,
  });

  final AngleRow row;
  final PoseFrame frame;
  final bool showRom;

  @override
  Widget build(BuildContext context) {
    final state = frame.angleState(row.key);
    final rom = frame.physio.romSummary[row.key];

    final Color valueColor;
    if (state case AngleDegrees(:final value) when row.normalMax != null) {
      valueColor = statusColorForRatio(value / row.normalMax!);
    } else if (state.isMeasured) {
      valueColor = AppPalette.textPrimary;
    } else if (state is AngleNote) {
      valueColor = AppPalette.textSecondary;
    } else {
      valueColor = AppPalette.textMuted;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Text(
              row.label,
              style: AppTheme.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: AppGaps.xs),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                state.display,
                style: AppTheme.value.copyWith(color: valueColor),
              ),
              if (showRom && rom != null && rom.hasData)
                Text(
                  'peak ${rom.max.toStringAsFixed(0)}°',
                  style: AppTheme.caption.copyWith(
                    fontFamily: AppTheme.monoFamily,
                    fontSize: 9,
                    color: AppPalette.textMuted,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

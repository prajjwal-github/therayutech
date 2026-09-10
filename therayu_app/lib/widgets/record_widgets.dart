import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/records.dart';
import '../theme/app_theme.dart';

/// ============================================================================
/// SHARED RECORD WIDGETS
/// ============================================================================
/// Small pieces used across the patient, plan and history screens. Every colour
/// comes from [AppPalette]; there are no literals here, so a theme change is a
/// one-file edit.
/// ============================================================================

/// Circular monogram for a patient.
class PatientAvatar extends StatelessWidget {
  const PatientAvatar({required this.patient, this.size = 44, super.key});

  final Patient patient;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppPalette.surfaceRaised,
        border: Border.all(color: AppPalette.border),
      ),
      child: Text(
        patient.initials,
        style: AppTheme.value.copyWith(
          fontSize: size * 0.36,
          color: AppPalette.brandCyanLight,
        ),
      ),
    );
  }
}

/// A labelled statistic, used in rows across the result and history views.
class StatTile extends StatelessWidget {
  const StatTile({
    required this.label,
    required this.value,
    this.suffix,
    this.tone,
    super.key,
  });

  final String label;
  final String value;
  final String? suffix;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label.toUpperCase(), style: AppTheme.label),
        const SizedBox(height: 2),
        RichText(
          text: TextSpan(
            text: value,
            style: AppTheme.value.copyWith(
              fontSize: 17,
              color: tone ?? AppPalette.textPrimary,
            ),
            children: [
              if (suffix != null)
                TextSpan(
                  text: ' $suffix',
                  style: AppTheme.caption.copyWith(fontSize: 10),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Section heading with an optional trailing action.
class SectionHeading extends StatelessWidget {
  const SectionHeading({required this.title, this.trailing, super.key});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppGaps.sm),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 14,
            decoration: BoxDecoration(
              color: AppPalette.brandGold,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: AppGaps.sm),
          Expanded(child: Text(title.toUpperCase(), style: AppTheme.cardHeader)),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// Standard panel used for every card on the record screens.
class RecordCard extends StatelessWidget {
  const RecordCard({
    required this.child,
    this.padding = const EdgeInsets.all(AppGaps.md),
    this.accent,
    this.onTap,
    super.key,
  });

  final Widget child;
  final EdgeInsets padding;
  final Color? accent;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final card = Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: AppPalette.surface,
        borderRadius: BorderRadius.circular(AppRadii.md),
        border: Border.all(color: accent ?? AppPalette.border),
      ),
      child: child,
    );
    if (onTap == null) return card;
    return Material(
      color: AppPalette.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadii.md),
        child: card,
      ),
    );
  }
}

/// Coloured pill for a change value, respecting the direction of improvement.
class ChangeChip extends StatelessWidget {
  const ChangeChip({required this.changeDeg, required this.improved, super.key});

  final double? changeDeg;
  final bool? improved;

  @override
  Widget build(BuildContext context) {
    if (changeDeg == null) {
      return Text('—', style: AppTheme.caption);
    }
    // Colour follows `improved`, NOT the sign. A rising trunk lean is a positive
    // number and a worse outcome; colouring by sign would congratulate the
    // patient for deteriorating.
    final tone = improved == true
        ? AppPalette.success
        : improved == false
            ? AppPalette.danger
            : AppPalette.textSecondary;
    final sign = changeDeg! >= 0 ? '+' : '';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(AppRadii.pill),
        border: Border.all(color: tone.withValues(alpha: 0.5)),
      ),
      child: Text(
        '$sign${changeDeg!.toStringAsFixed(1)}°',
        style: AppTheme.value.copyWith(fontSize: 12, color: tone),
      ),
    );
  }
}

/// Sparkline of one exercise's values across sessions.
class TrendSparkline extends StatelessWidget {
  const TrendSparkline({
    required this.points,
    this.target,
    this.lowerIsBetter = false,
    this.height = 64,
    super.key,
  });

  final List<TrendPoint> points;
  final double? target;
  final bool lowerIsBetter;
  final double height;

  @override
  Widget build(BuildContext context) {
    final valid = points.where((p) => p.value != null).toList();
    if (valid.length < 2) {
      return SizedBox(
        height: height,
        child: Center(
          child: Text(
            valid.isEmpty
                ? 'No sessions yet'
                : 'One session so far — a trend needs at least two',
            style: AppTheme.caption,
          ),
        ),
      );
    }
    return SizedBox(
      height: height,
      width: double.infinity,
      child: CustomPaint(
        painter: _SparkPainter(valid, target, lowerIsBetter),
      ),
    );
  }
}

class _SparkPainter extends CustomPainter {
  _SparkPainter(this.points, this.target, this.lowerIsBetter);

  final List<TrendPoint> points;
  final double? target;
  final bool lowerIsBetter;

  @override
  void paint(Canvas canvas, Size size) {
    final values = points.map((p) => p.value!).toList();
    final candidates = <double>[...values, if (target != null) target!];
    var vMax = candidates.reduce(math.max) * 1.12;
    var vMin = math.min(candidates.reduce(math.min) * 0.88, 0);
    if (vMax - vMin < 1) vMax = vMin + 1;

    const padBottom = 14.0;
    final plotH = size.height - padBottom;

    double x(int i) =>
        points.length == 1 ? size.width / 2 : size.width * i / (points.length - 1);
    double y(double v) => plotH - plotH * (v - vMin) / (vMax - vMin);

    // baseline
    canvas.drawLine(
      Offset(0, plotH),
      Offset(size.width, plotH),
      Paint()
        ..color = AppPalette.border
        ..strokeWidth = 1,
    );

    // target reference
    if (target != null) {
      final ty = y(target!);
      final dash = Paint()
        ..color = AppPalette.brandGold.withValues(alpha: 0.75)
        ..strokeWidth = 1.2;
      const dashW = 5.0;
      for (double dx = 0; dx < size.width; dx += dashW * 2) {
        canvas.drawLine(Offset(dx, ty), Offset(dx + dashW, ty), dash);
      }

      // Say what the line MEANS. For a range-of-motion exercise it is a floor
      // to climb towards; for a deviation it is a ceiling to stay under. The
      // same dashed line with no label would read as "target" in both cases and
      // mislead in one of them.
      final tp = TextPainter(
        text: TextSpan(
          text: lowerIsBetter ? 'stay under' : 'target',
          style: AppTheme.caption
              .copyWith(fontSize: 8, color: AppPalette.brandGold),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(size.width - tp.width, ty - tp.height - 1));
    }

    // filled area under the line, for readability at a glance
    final path = Path()..moveTo(x(0), y(values.first));
    for (var i = 1; i < points.length; i++) {
      path.lineTo(x(i), y(values[i]));
    }
    final fill = Path.from(path)
      ..lineTo(x(points.length - 1), plotH)
      ..lineTo(x(0), plotH)
      ..close();
    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppPalette.brandCyan.withValues(alpha: 0.30),
            AppPalette.brandCyan.withValues(alpha: 0.02),
          ],
        ).createShader(Rect.fromLTWH(0, 0, size.width, plotH)),
    );

    canvas.drawPath(
      path,
      Paint()
        ..color = AppPalette.brandCyan
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke
        ..strokeJoin = StrokeJoin.round,
    );

    // endpoints emphasised — first and latest are the numbers people read
    for (final i in [0, points.length - 1]) {
      canvas.drawCircle(
        Offset(x(i), y(values[i])),
        3.2,
        Paint()..color = AppPalette.jointCore,
      );
    }

    // day labels at the ends only, to avoid crowding
    for (final i in [0, points.length - 1]) {
      final tp = TextPainter(
        text: TextSpan(
          text: 'd${points[i].dayIndex}',
          style: AppTheme.caption.copyWith(fontSize: 9),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final dx = (x(i) - tp.width / 2).clamp(0.0, size.width - tp.width);
      tp.paint(canvas, Offset(dx, plotH + 2));
    }
  }

  @override
  bool shouldRepaint(covariant _SparkPainter old) =>
      old.points != points || old.target != target;
}

/// Ring showing progress towards a rep or hold target.
class ProgressRing extends StatelessWidget {
  const ProgressRing({
    required this.progress,
    required this.label,
    required this.caption,
    this.size = 92,
    super.key,
  });

  final double progress;
  final String label;
  final String caption;
  final double size;

  @override
  Widget build(BuildContext context) {
    final done = progress >= 1.0;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox.expand(
            child: CustomPaint(
              painter: _RingPainter(
                progress.clamp(0.0, 1.0),
                done ? AppPalette.success : AppPalette.brandCyan,
              ),
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: AppTheme.metricLarge.copyWith(
                  fontSize: size * 0.27,
                  color: done ? AppPalette.success : AppPalette.textPrimary,
                ),
              ),
              Text(caption, style: AppTheme.label.copyWith(fontSize: 8)),
            ],
          ),
        ],
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.progress, this.colour);

  final double progress;
  final Color colour;

  @override
  void paint(Canvas canvas, Size size) {
    const stroke = 7.0;
    final rect = Offset(stroke / 2, stroke / 2) &
        Size(size.width - stroke, size.height - stroke);

    canvas.drawArc(
      rect, 0, math.pi * 2, false,
      Paint()
        ..color = AppPalette.border
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke,
    );

    if (progress <= 0) return;
    canvas.drawArc(
      rect, -math.pi / 2, math.pi * 2 * progress, false,
      Paint()
        ..color = colour
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) =>
      old.progress != progress || old.colour != colour;
}

/// Horizontal bar showing where a live angle sits inside its prescribed band.
class BandGauge extends StatelessWidget {
  const BandGauge({
    required this.value,
    required this.bandMin,
    required this.bandMax,
    this.lowerIsBetter = false,
    super.key,
  });

  final double? value;
  final double? bandMin;
  final double? bandMax;
  final bool lowerIsBetter;

  @override
  Widget build(BuildContext context) {
    // Scale runs to a sensible ceiling so the bar does not rescale every frame,
    // which would make the marker appear to move when the patient is still.
    final ceiling = math.max(bandMax ?? 120, (value ?? 0) + 20);
    final v = value;
    final inBand = v != null &&
        (bandMin == null || v >= bandMin!) &&
        (bandMax == null || v <= bandMax!);

    return LayoutBuilder(
      builder: (context, box) {
        final w = box.maxWidth;
        double at(double deg) => (deg / ceiling).clamp(0.0, 1.0) * w;

        return SizedBox(
          height: 30,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Positioned(
                left: 0, right: 0, top: 11,
                child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: AppPalette.surfaceRaised,
                    borderRadius: BorderRadius.circular(AppRadii.pill),
                  ),
                ),
              ),
              if (bandMin != null || bandMax != null)
                Positioned(
                  left: at(bandMin ?? 0),
                  width: math.max(2, at(bandMax ?? ceiling) - at(bandMin ?? 0)),
                  top: 11,
                  child: Container(
                    height: 8,
                    decoration: BoxDecoration(
                      color: AppPalette.success.withValues(alpha: 0.32),
                      borderRadius: BorderRadius.circular(AppRadii.pill),
                      border: Border.all(
                        color: AppPalette.success.withValues(alpha: 0.55),
                      ),
                    ),
                  ),
                ),
              if (v != null)
                Positioned(
                  left: (at(v) - 2).clamp(0.0, w - 4),
                  top: 4,
                  child: Container(
                    width: 4,
                    height: 22,
                    decoration: BoxDecoration(
                      color: inBand ? AppPalette.success : AppPalette.brandGold,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

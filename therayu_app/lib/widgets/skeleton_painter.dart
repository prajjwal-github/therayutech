import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../models/pose_frame.dart';
import '../models/skeleton_topology.dart';
import '../services/pose_interpolator.dart';
import '../theme/app_theme.dart';

/// ============================================================================
/// SKELETON PAINTER
/// ============================================================================
/// A faithful GPU-drawn port of `MedicalGUIRenderer`'s skeleton layer:
/// bones, glowing joint nodes, 21-joint finger chains, goniometric arcs with
/// floating angle badges, and the tracking/confidence badge.
///
/// Everything is drawn in the painter's own coordinate space, and the caller
/// sizes that space to exactly the rect the camera preview occupies — so
/// alignment is structural rather than something that needs fudge factors.
///
/// The visibility floors (0.2 for bones/joints, 0.35 for arcs) are the same
/// constants the OpenCV renderer used, so the phone shows and hides precisely
/// what the desktop app showed and hid.
/// ============================================================================
class SkeletonPainter extends CustomPainter {
  SkeletonPainter({
    required this.frame,
    required this.mode,
    required this.showBones,
    required this.showJoints,
    required this.showHands,
    required this.showArcs,
    required this.showBadge,
    required this.interpolator,
    required Listenable repaint,
  }) : super(repaint: repaint);

  /// Positions are sampled from here at paint time rather than read off
  /// [frame], so the skeleton glides between server updates instead of
  /// stepping. Angles still come from [frame] — they are measurements, not
  /// something to smooth.
  final PoseInterpolator interpolator;

  final PoseFrame frame;
  final BodyMode mode;
  final bool showBones;
  final bool showJoints;
  final bool showHands;
  final bool showArcs;
  final bool showBadge;

  /// Cached so a value that has not changed does not rebuild its TextPainter.
  static final Map<String, TextPainter> _labelCache = <String, TextPainter>{};

  /// Positions for this paint pass, resolved once so every helper below sees a
  /// consistent snapshot rather than re-sampling mid-frame.
  Map<String, Landmark> _pose = const <String, Landmark>{};

  @override
  void paint(Canvas canvas, Size size) {
    if (!frame.telemetry.personDetected) return;

    _pose = interpolator.sample(DateTime.now());
    if (_pose.isEmpty) return;

    final isReady = frame.telemetry.isReady;

    // One scale factor derived from the viewport keeps stroke weights and badge
    // sizes proportionate across a 5" phone and a 12" tablet.
    final scale = (size.shortestSide / 400).clamp(0.75, 2.4).toDouble();

    if (showBones) _paintBones(canvas, size, scale, isReady);
    if (showHands && mode != BodyMode.lowerBody) _paintHands(canvas, size, scale);
    if (showJoints) _paintJoints(canvas, size, scale, isReady);
    if (showArcs && isReady) _paintArcs(canvas, size, scale);
    if (showBadge) _paintTrackingBadge(canvas, size, scale, isReady);
  }

  // --------------------------------------------------------------------------
  // GEOMETRY
  // --------------------------------------------------------------------------

  Offset? _point(String name, Size size, {double floor = 0}) {
    final lm = _pose[name];
    if (lm == null || lm.visibility < floor) return null;
    return Offset(lm.x * size.width, lm.y * size.height);
  }

  // --------------------------------------------------------------------------
  // BONES
  // --------------------------------------------------------------------------

  void _paintBones(Canvas canvas, Size size, double scale, bool isReady) {
    // The dark casing drawn first is what keeps a mint-green bone readable
    // against a white t-shirt or a bright window behind the patient.
    final casing = Paint()
      ..color = AppPalette.boneCasing
      ..strokeWidth = AppStrokes.boneOutline * scale
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true;

    final bone = Paint()
      ..strokeWidth = AppStrokes.bone * scale
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true;

    for (final b in SkeletonTopology.bonesFor(mode)) {
      final p1 = _point(b.from, size, floor: SkeletonTopology.boneVisibilityFloor);
      final p2 = _point(b.to, size, floor: SkeletonTopology.boneVisibilityFloor);
      if (p1 == null || p2 == null) continue;

      canvas.drawLine(p1, p2, casing);
      bone.color = isReady ? b.color : AppPalette.inactive;
      canvas.drawLine(p1, p2, bone);
    }
  }

  // --------------------------------------------------------------------------
  // HANDS
  // --------------------------------------------------------------------------

  void _paintHands(Canvas canvas, Size size, double scale) {
    const hands = <(String, String, Color)>[
      ('LEFT_HAND_', 'LEFT_WRIST', AppPalette.handLeft),
      ('RIGHT_HAND_', 'RIGHT_WRIST', AppPalette.handRight),
    ];

    final bone = Paint()
      ..strokeWidth = AppStrokes.fingerBone * scale
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true;

    final tip = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;

    for (final (prefix, bodyWrist, color) in hands) {
      bone.color = color;

      // Only draw a hand whose wrist is confidently tracked. Below that floor
      // the finger points are extrapolation, and rendering them produces a
      // scribble that reads as a bug rather than as tracking.
      final bw = _point(bodyWrist, size,
          floor: SkeletonTopology.handVisibilityFloor);
      if (bw == null) continue;

      // Bridge the body wrist to the hand-model wrist so the arm and the hand
      // read as one limb rather than two floating pieces.
      final hw = _point('${prefix}WRIST', size);
      if (hw != null) canvas.drawLine(bw, hw, bone);

      for (final chain in SkeletonTopology.handFingerChains) {
        for (var i = 0; i < chain.length - 1; i++) {
          final a = _point('$prefix${chain[i]}', size);
          final b = _point('$prefix${chain[i + 1]}', size);
          if (a == null || b == null) continue;

          canvas.drawLine(a, b, bone);
          canvas.drawCircle(b, 1.6 * scale, tip);
        }
      }
    }
  }

  // --------------------------------------------------------------------------
  // JOINT NODES
  // --------------------------------------------------------------------------

  void _paintJoints(Canvas canvas, Size size, double scale, bool isReady) {
    final allowed = SkeletonTopology.jointNodesFor(mode);

    final halo = Paint()
      ..style = PaintingStyle.fill
      ..isAntiAlias = true
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, 3.5 * scale);

    final core = Paint()
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;

    final pip = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;

    halo.color = (isReady ? AppPalette.jointGlow : AppPalette.inactive)
        .withValues(alpha: 0.55);
    core.color = isReady ? AppPalette.jointCore : AppPalette.inactive;

    _pose.forEach((name, lm) {
      if (name.contains('HAND_')) return;
      if (!allowed.contains(name)) return;
      if (lm.visibility < SkeletonTopology.boneVisibilityFloor) return;

      final p = Offset(lm.x * size.width, lm.y * size.height);
      canvas.drawCircle(p, AppStrokes.jointGlowRadius * scale, halo);
      canvas.drawCircle(p, AppStrokes.jointCoreRadius * scale, core);
      canvas.drawCircle(p, 1.1 * scale, pip);
    });
  }

  // --------------------------------------------------------------------------
  // GONIOMETRIC ARCS + FLOATING BADGES
  // --------------------------------------------------------------------------

  void _paintArcs(Canvas canvas, Size size, double scale) {
    final radius = (size.shortestSide * 0.068).clamp(16.0, 38.0).toDouble();

    final casing = Paint()
      ..color = AppPalette.arcCasing
      ..strokeWidth = (AppStrokes.arc + 2.2) * scale
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true;

    final arc = Paint()
      ..strokeWidth = AppStrokes.arc * scale
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true;

    for (final def in SkeletonTopology.jointArcs) {
      // Region gating mirrors `_draw_goniometer_arcs_and_badges`.
      if (mode == BodyMode.upperBody &&
          !SkeletonTopology.upperPivots.contains(def.pivot)) {
        continue;
      }
      if (mode == BodyMode.lowerBody &&
          !SkeletonTopology.lowerPivots.contains(def.pivot)) {
        continue;
      }

      const floor = SkeletonTopology.arcVisibilityFloor;
      final b = _point(def.pivot, size, floor: floor);
      final a = _point(def.armA, size, floor: floor);
      final c = _point(def.armB, size, floor: floor);
      if (a == null || b == null || c == null) continue;

      final state = frame.angleState(def.angleKey);
      final value = state.value;
      if (value == null) continue;

      // Reproduces the desktop arc-span selection exactly: take both bone
      // bearings, then pick the sweep that is <= 180 deg so the arc always hugs
      // the interior of the joint instead of wrapping the long way round.
      final angA = _degrees(math.atan2(a.dy - b.dy, a.dx - b.dx)) % 360;
      final angC = _degrees(math.atan2(c.dy - b.dy, c.dx - b.dx)) % 360;

      var start = math.min(angA, angC);
      var end = math.max(angA, angC);
      if (end - start > 180) {
        final swap = start;
        start = end;
        end = swap + 360;
      }

      final rect = Rect.fromCircle(center: b, radius: radius * scale * 0.85);
      final startRad = _radians(start);
      final sweepRad = _radians(end - start);

      canvas.drawArc(rect, startRad, sweepRad, false, casing);
      arc.color = def.color;
      canvas.drawArc(rect, startRad, sweepRad, false, arc);

      // Badge sits on the arc's bisector, pushed just outside the sweep.
      final midRad = _radians((start + end) / 2);
      final distance = radius * scale * 0.85 + 20 * scale;
      final anchor = Offset(
        b.dx + distance * math.cos(midRad),
        b.dy + distance * math.sin(midRad),
      );

      _paintValueBadge(
        canvas,
        size,
        anchor,
        '${value.toStringAsFixed(1)}°',
        def.color,
        scale,
      );
    }
  }

  void _paintValueBadge(
    Canvas canvas,
    Size size,
    Offset anchor,
    String text,
    Color tint,
    double scale,
  ) {
    final painter = _label(text, AppTheme.jointBadge.copyWith(fontSize: 10.5 * scale));

    final padH = 5.0 * scale;
    final padV = 2.5 * scale;
    final w = painter.width + padH * 2;
    final h = painter.height + padV * 2;

    // Keep the badge fully on screen — a value clipped by the bezel is useless.
    final left =
        (anchor.dx - w / 2).clamp(2.0, math.max(2.0, size.width - w - 2)).toDouble();
    final top =
        (anchor.dy - h / 2).clamp(2.0, math.max(2.0, size.height - h - 2)).toDouble();
    final rect = Rect.fromLTWH(left, top, w, h);
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(5 * scale));

    canvas.drawRRect(
      rrect,
      Paint()..color = AppPalette.surface.withValues(alpha: 0.92),
    );
    canvas.drawRRect(
      rrect,
      Paint()
        ..color = tint.withValues(alpha: 0.9)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.1 * scale
        ..isAntiAlias = true,
    );

    painter.paint(canvas, Offset(rect.left + padH, rect.top + padV));
  }

  // --------------------------------------------------------------------------
  // TRACKING / CONFIDENCE BADGE
  // --------------------------------------------------------------------------

  void _paintTrackingBadge(Canvas canvas, Size size, double scale, bool isReady) {
    final nose = _point('NOSE', size);
    if (nose == null) return;

    final telemetry = frame.telemetry;
    final text = 'ID ${frame.trackId}  ·  '
        '${telemetry.overallConfidence.toStringAsFixed(0)}%';

    final painter = _label(text, AppTheme.jointBadge.copyWith(fontSize: 10 * scale));

    final padH = 8.0 * scale;
    final padV = 4.0 * scale;
    final w = painter.width + padH * 2;
    final h = painter.height + padV * 2;

    final left =
        (nose.dx - w / 2).clamp(2.0, math.max(2.0, size.width - w - 2)).toDouble();
    final top =
        (nose.dy - 62 * scale).clamp(2.0, math.max(2.0, size.height - h - 2)).toDouble();
    final rect = Rect.fromLTWH(left, top, w, h);
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(AppRadii.sm * scale));

    final tint = isReady ? AppPalette.success : AppPalette.warning;

    canvas.drawRRect(
      rrect,
      Paint()..color = AppPalette.surface.withValues(alpha: 0.9),
    );
    canvas.drawRRect(
      rrect,
      Paint()
        ..color = tint
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2 * scale
        ..isAntiAlias = true,
    );

    painter.paint(canvas, Offset(rect.left + padH, rect.top + padV));
  }

  // --------------------------------------------------------------------------
  // TEXT CACHE
  // --------------------------------------------------------------------------

  TextPainter _label(String text, TextStyle style) {
    final key = '$text|${style.fontSize}|${style.color}';
    final cached = _labelCache[key];
    if (cached != null) return cached;

    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
    )..layout();

    // Angle values churn constantly; an unbounded cache would leak steadily
    // across a long session, so clear it wholesale once it grows.
    if (_labelCache.length > 240) _labelCache.clear();
    _labelCache[key] = painter;
    return painter;
  }

  static double _degrees(double radians) => radians * 180 / math.pi;
  static double _radians(double degrees) => degrees * math.pi / 180;

  @override
  bool shouldRepaint(SkeletonPainter oldDelegate) =>
      // The ticker passed to super(repaint:) drives per-frame redraws; this only
      // needs to catch configuration changes that arrive without a tick.
      oldDelegate.frame != frame ||
      oldDelegate.interpolator != interpolator ||
      oldDelegate.mode != mode ||
      oldDelegate.showBones != showBones ||
      oldDelegate.showJoints != showJoints ||
      oldDelegate.showHands != showHands ||
      oldDelegate.showArcs != showArcs ||
      oldDelegate.showBadge != showBadge;

  @override
  bool shouldRebuildSemantics(SkeletonPainter oldDelegate) => false;
}

/// Faint corner brackets marking the usable capture area.
///
/// The Python `CameraValidator` rejects any required landmark outside a 2%–98%
/// margin, which is invisible to the patient. Drawing that boundary turns
/// "Please step back" from a mystery into something self-correcting.
class FramingGuidePainter extends CustomPainter {
  const FramingGuidePainter({required this.isReady, this.marginPct = 0.02});

  final bool isReady;
  final double marginPct;

  @override
  void paint(Canvas canvas, Size size) {
    final inset = Rect.fromLTRB(
      size.width * marginPct,
      size.height * marginPct,
      size.width * (1 - marginPct),
      size.height * (1 - marginPct),
    );

    final paint = Paint()
      ..color = (isReady ? AppPalette.success : AppPalette.warning)
          .withValues(alpha: isReady ? 0.28 : 0.6)
      ..strokeWidth = 2.4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true;

    final arm = size.shortestSide * 0.07;

    void bracket(Offset corner, double dx, double dy) {
      canvas.drawLine(corner, corner.translate(arm * dx, 0), paint);
      canvas.drawLine(corner, corner.translate(0, arm * dy), paint);
    }

    bracket(inset.topLeft, 1, 1);
    bracket(inset.topRight, -1, 1);
    bracket(inset.bottomLeft, 1, -1);
    bracket(inset.bottomRight, -1, -1);
  }

  @override
  bool shouldRepaint(FramingGuidePainter oldDelegate) =>
      oldDelegate.isReady != isReady || oldDelegate.marginPct != marginPct;
}

/// Circular progress arc used for the movement-quality score.
class QualityRingPainter extends CustomPainter {
  const QualityRingPainter({
    required this.pct,
    required this.color,
    this.strokeWidth = 6,
  });

  final double pct;
  final Color color;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTWH(
      strokeWidth / 2,
      strokeWidth / 2,
      size.width - strokeWidth,
      size.height - strokeWidth,
    );

    canvas.drawArc(
      rect,
      -math.pi / 2,
      math.pi * 2,
      false,
      Paint()
        ..color = AppPalette.border
        ..strokeWidth = strokeWidth
        ..style = PaintingStyle.stroke
        ..isAntiAlias = true,
    );

    final sweep = (pct.clamp(0, 100) / 100) * math.pi * 2;
    canvas.drawArc(
      rect,
      -math.pi / 2,
      sweep,
      false,
      Paint()
        ..shader = ui.Gradient.sweep(
          rect.center,
          <Color>[color.withValues(alpha: 0.55), color],
          <double>[0, 1],
        )
        ..strokeWidth = strokeWidth
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke
        ..isAntiAlias = true,
    );
  }

  @override
  bool shouldRepaint(QualityRingPainter oldDelegate) =>
      oldDelegate.pct != pct || oldDelegate.color != color || oldDelegate.strokeWidth != strokeWidth;
}

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// ============================================================================
/// BRAND ELEMENTS
/// ============================================================================
/// The Therayu identity from the Figma frames, rebuilt as widgets:
///
///   [BrandHeader]   deep teal block with the gold wave along its bottom edge —
///                   the composition on the login / OTP screens.
///   [BrandBackdrop] full-bleed teal with the gold wave sweeping a corner —
///                   the splash / Profile Screen frame.
///   [Wordmark]      the "therayu" lockup with its Meditech Solutions tagline.
///   [BrandMarkTile] the rounded logo tile.
///
/// Everything is drawn with paths and gradients rather than shipped as raster
/// assets, so it stays crisp at any density and recolours instantly when the
/// palette changes. Swap in the real exported SVG/PNG later if you want the
/// exact letterforms — see [Wordmark] for where.
/// ============================================================================

/// How the wave curve bends. The Figma set uses a shallow S along a bottom edge
/// for the login headers and a deep vertical sweep for the animated splash.
enum WaveStyle {
  /// Shallow S-curve across a horizontal edge (login header).
  edge,

  /// Deep sweep filling a corner (splash).
  sweep,
}

/// ============================================================================
/// WAVE GEOMETRY
/// ============================================================================
/// Top-level so the painter and the clipper are guaranteed to describe the same
/// curve. If these ever diverged, the teal fill and its clip would disagree by a
/// pixel or two and leave a visible seam along the wave.

/// Shallow S across the bottom edge: dips low on the left, rises through the
/// middle, settles right. Matches the curve under the login-screen headers.
///
/// Control points are fractions of the box's height, so the curve keeps its
/// proportions whatever height the header ends up being.
Path buildEdgeWavePath(
  Size size, {
  double verticalBias = 0,
  double amplitude = 1,
}) {
  final w = size.width;
  final h = size.height;
  final bias = h * verticalBias;

  double y(double fraction) => (h * fraction * amplitude) + bias;

  return Path()
    ..moveTo(0, 0)
    ..lineTo(0, y(0.62))
    ..cubicTo(
      w * 0.18, y(0.98),
      w * 0.52, y(0.52),
      w * 0.74, y(0.70),
    )
    ..cubicTo(
      w * 0.87, y(0.79),
      w * 0.95, y(0.86),
      w, y(0.80),
    )
    ..lineTo(w, 0)
    ..close();
}

/// Deep sweep filling the lower-left through to the right edge, as in the splash
/// frame where the gold occupies a whole corner.
Path buildSweepWavePath(Size size, {double verticalBias = 0}) {
  final w = size.width;
  final h = size.height;
  final bias = h * verticalBias;

  double y(double fraction) => (h * fraction) + bias;

  return Path()
    ..moveTo(0, y(0.58))
    ..cubicTo(
      w * 0.30, y(0.44),
      w * 0.42, y(0.86),
      w, y(0.66),
    )
    ..lineTo(w, h + bias)
    ..lineTo(0, h + bias)
    ..close();
}

/// ============================================================================
/// WAVE PAINTER
/// ============================================================================
class _WavePainter extends CustomPainter {
  const _WavePainter({
    required this.style,
    required this.gradient,
    this.verticalBias = 0,
  });

  final WaveStyle style;
  final Gradient gradient;

  /// Shifts the whole curve down as a fraction of height. Drawing the gold layer
  /// with a small positive bias and the teal layer at zero is what produces the
  /// gold sliver peeking out from under the teal — the actual signature of the
  /// brand, rather than a separate band.
  final double verticalBias;

  @override
  void paint(Canvas canvas, Size size) {
    final path = style == WaveStyle.edge
        ? buildEdgeWavePath(size, verticalBias: verticalBias)
        : buildSweepWavePath(size, verticalBias: verticalBias);

    canvas.drawPath(
      path,
      Paint()
        ..shader = gradient.createShader(Offset.zero & size)
        ..isAntiAlias = true,
    );
  }

  @override
  bool shouldRepaint(_WavePainter oldDelegate) =>
      oldDelegate.style != style ||
      oldDelegate.gradient != gradient ||
      oldDelegate.verticalBias != verticalBias;
}

/// Faint repeating watermark visible on the teal ground in the source frames.
class _WatermarkPainter extends CustomPainter {
  const _WatermarkPainter();

  static const double opacity = 0.035;
  static const double spacing = 46;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppPalette.brandCyanLight.withValues(alpha: opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.1
      ..isAntiAlias = true;

    // A sparse diagonal lattice of small arcs. Cheap to draw, and at 3.5% alpha
    // it reads as texture rather than pattern — which is what the frames do.
    for (double y = -spacing; y < size.height + spacing; y += spacing) {
      for (double x = -spacing; x < size.width + spacing; x += spacing) {
        final offset = ((y / spacing).floor().isEven) ? spacing / 2 : 0.0;
        final center = Offset(x + offset, y);
        canvas.drawArc(
          Rect.fromCircle(center: center, radius: spacing * 0.22),
          math.pi * 0.85,
          math.pi * 1.3,
          false,
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_WatermarkPainter oldDelegate) => false;
}

/// ============================================================================
/// BRAND HEADER — the login-screen composition
/// ============================================================================
/// Deep teal block, watermarked, with the gold wave running along its bottom
/// edge and [child] centred inside.
class BrandHeader extends StatelessWidget {
  const BrandHeader({
    required this.child,
    this.height = 190,
    super.key,
  });

  final Widget child;
  final double height;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Gold first, biased downward so its crest shows below the teal.
          const CustomPaint(
            painter: _WavePainter(
              style: WaveStyle.edge,
              gradient: AppPalette.goldWave,
              verticalBias: 0.055,
            ),
          ),

          // Teal on top, clipped to the same curve.
          const ClipPath(
            clipper: _EdgeWaveClipper(),
            child: Stack(
              fit: StackFit.expand,
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(gradient: AppPalette.tealGround),
                ),
                CustomPaint(painter: _WatermarkPainter()),
              ],
            ),
          ),

          // Content sits above both layers, lifted clear of the curve.
          Positioned.fill(
            bottom: height * 0.24,
            child: Center(child: child),
          ),
        ],
      ),
    );
  }
}

/// Clips a box to the same S-curve [_WavePainter] draws in [WaveStyle.edge].
class _EdgeWaveClipper extends CustomClipper<Path> {
  const _EdgeWaveClipper();

  @override
  Path getClip(Size size) => buildEdgeWavePath(size);

  @override
  bool shouldReclip(CustomClipper<Path> oldClipper) => false;
}

/// ============================================================================
/// BRAND BACKDROP — the splash composition
/// ============================================================================
/// Full-bleed watermarked teal with the gold wave sweeping the bottom corner.
class BrandBackdrop extends StatelessWidget {
  const BrandBackdrop({required this.child, this.waveHeightFactor = 0.34, super.key});

  final Widget child;

  /// Share of the screen height the gold sweep occupies.
  final double waveHeightFactor;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(gradient: AppPalette.tealGround),
      child: Stack(
        fit: StackFit.expand,
        children: [
          const CustomPaint(painter: _WatermarkPainter()),
          Align(
            alignment: Alignment.bottomCenter,
            child: FractionallySizedBox(
              heightFactor: waveHeightFactor,
              child: const CustomPaint(
                painter: _WavePainter(
                  style: WaveStyle.sweep,
                  gradient: AppPalette.goldWave,
                ),
              ),
            ),
          ),
          child,
        ],
      ),
    );
  }
}

/// ============================================================================
/// WORDMARK
/// ============================================================================
/// The "therayu" lockup.
///
/// TO USE THE REAL LOGO: drop the export at assets/images/therayu_wordmark.png,
/// declare it under `assets:` in pubspec.yaml, and replace the Text below with
/// `Image.asset('assets/images/therayu_wordmark.png', height: fontSize * 1.4)`.
/// The tagline and spacing here already match the Figma lockup, so nothing else
/// needs to change.
class Wordmark extends StatelessWidget {
  const Wordmark({
    this.fontSize = 34,
    this.showTagline = true,
    super.key,
  });

  final double fontSize;
  final bool showTagline;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // The descender of the "y" is gold in the source lockup, so the wordmark
        // is split into runs rather than being one flat-coloured string.
        Text.rich(
          TextSpan(
            style: AppTheme.wordmark.copyWith(fontSize: fontSize),
            children: const <TextSpan>[
              TextSpan(text: 'thera'),
              TextSpan(text: 'y', style: TextStyle(color: AppPalette.brandGold)),
              TextSpan(text: 'u'),
            ],
          ),
        ),
        if (showTagline) ...[
          SizedBox(height: fontSize * 0.08),
          Text(
            'MEDITECH SOLUTIONS',
            style: AppTheme.wordmarkTag.copyWith(fontSize: fontSize * 0.235),
          ),
        ],
      ],
    );
  }
}

/// The rounded logo tile: a gold-to-cyan gradient behind a stylised "t".
class BrandMarkTile extends StatelessWidget {
  const BrandMarkTile({this.size = 64, super.key});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: AppPalette.brandMark,
        borderRadius: BorderRadius.circular(size * 0.28),
        boxShadow: [
          BoxShadow(
            color: AppPalette.brandCyan.withValues(alpha: 0.3),
            blurRadius: size * 0.3,
            offset: Offset(0, size * 0.08),
          ),
        ],
      ),
      child: Center(
        child: Text(
          't',
          style: TextStyle(
            fontFamily: AppTheme.fontFamily,
            fontSize: size * 0.62,
            fontWeight: FontWeight.w700,
            color: AppPalette.brandTealDeep,
            height: 1.1,
          ),
        ),
      ),
    );
  }
}

/// A slim gold rule, used to separate brand areas from content.
class GoldRule extends StatelessWidget {
  const GoldRule({this.width = 56, this.thickness = 3, super.key});

  final double width;
  final double thickness;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: thickness,
      decoration: BoxDecoration(
        gradient: AppPalette.goldWave,
        borderRadius: BorderRadius.circular(thickness),
      ),
    );
  }
}

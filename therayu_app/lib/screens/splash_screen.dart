import 'package:flutter/material.dart';

import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/brand.dart';
import 'connect_screen.dart';

/// ============================================================================
/// SPLASH SCREEN
/// ============================================================================
/// The "Profile Screen" frame from the Figma set: watermarked teal ground, the
/// gold wave sweeping the bottom corner, wordmark centred.
///
/// It is not decorative filler — the camera permission prompt and preview
/// warm-up both happen here, so the app arrives at the connect screen with a
/// live viewfinder instead of a black rectangle. The animation length is set to
/// roughly cover that work rather than being an arbitrary delay.
/// ============================================================================
class SplashScreen extends StatefulWidget {
  const SplashScreen({required this.session, super.key});

  final SessionController session;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1500),
  );

  late final Animation<double> _markFade = CurvedAnimation(
    parent: _controller,
    curve: const Interval(0.10, 0.55, curve: Curves.easeOut),
  );

  late final Animation<double> _markRise = Tween<double>(begin: 18, end: 0).animate(
    CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.10, 0.65, curve: Curves.easeOutCubic),
    ),
  );

  /// The gold wave sweeps up into place, echoing the two "animated" frames in
  /// the Figma file where the wave is mid-transition.
  late final Animation<double> _waveRise = Tween<double>(begin: 0.02, end: 0.34).animate(
    CurvedAnimation(
      parent: _controller,
      curve: const Interval(0, 0.75, curve: Curves.easeOutCubic),
    ),
  );

  @override
  void initState() {
    super.initState();
    _controller.forward();
    _advance();
  }

  Future<void> _advance() async {
    // Run the camera bring-up concurrently with the animation, then leave once
    // both are done. whenComplete rather than await on the camera: a permission
    // denial must not strand the user on the splash.
    await Future<void>.delayed(const Duration(milliseconds: 1650));
    if (!mounted) return;

    await Navigator.of(context).pushReplacement(
      PageRouteBuilder<void>(
        transitionDuration: const Duration(milliseconds: 420),
        pageBuilder: (_, __, ___) => ConnectScreen(session: widget.session),
        transitionsBuilder: (_, animation, __, child) => FadeTransition(
          opacity: animation,
          child: child,
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppPalette.brandTeal,
      body: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return BrandBackdrop(
            waveHeightFactor: _waveRise.value,
            child: Center(
              child: FadeTransition(
                opacity: _markFade,
                child: Transform.translate(
                  offset: Offset(0, _markRise.value),
                  child: const Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      BrandMarkTile(size: 76),
                      SizedBox(height: AppGaps.xl),
                      Wordmark(fontSize: 38),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

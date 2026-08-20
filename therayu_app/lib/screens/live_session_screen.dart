import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../models/skeleton_topology.dart';
import '../services/pose_socket.dart';
import '../services/session_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/angle_card.dart';
import '../widgets/controls_sheet.dart';
import '../widgets/skeleton_painter.dart';
import '../widgets/status_widgets.dart';

/// ============================================================================
/// LIVE SESSION SCREEN
/// ============================================================================
/// The camera fills the window. Everything else floats on top of it.
///
/// LAYOUT REASONING
/// An earlier version split the screen 58/42 between video and a readout panel,
/// and fitted the video with BoxFit.cover. Both were wrong for this app:
///
///   * cover CROPS to fill. When the viewport's aspect differs from the camera's
///     — a wide desktop window against a 4:3 webcam — it scales to the wider
///     axis and throws away the rest, so the patient appears magnified and cut
///     off at the waist. For an assessment that depends on seeing the whole
///     body, cropping is the one thing the fit must never do. It is now
///     [BoxFit.contain]: the entire frame is always visible, letterboxed.
///
///   * Giving 42% of the screen to numbers left the video too short to show a
///     standing person. The readouts now float over the video, so the camera
///     gets the full window and the HUD can be dismissed entirely.
///
/// The HUD arranges itself by window shape: a wide window gets a right-hand
/// column (vertical space is scarce, horizontal is not); a tall window gets a
/// bottom strip.
/// ============================================================================
class LiveSessionScreen extends StatefulWidget {
  const LiveSessionScreen({required this.session, super.key});

  final SessionController session;

  @override
  State<LiveSessionScreen> createState() => _LiveSessionScreenState();
}

class _LiveSessionScreenState extends State<LiveSessionScreen>
    with WidgetsBindingObserver, SingleTickerProviderStateMixin {
  Timer? _clock;

  /// Drives the skeleton at display rate.
  ///
  /// The painter is handed this as its `repaint` listenable, so ticking it
  /// redraws ONLY the skeleton layer — the widget tree is untouched. That is
  /// what makes 60 fps rendering affordable on top of a 10 fps data stream:
  /// there is no rebuild, just a repaint of one RepaintBoundary.
  late final Ticker _ticker;
  final ValueNotifier<int> _vsync = ValueNotifier<int>(0);

  /// Lets the user clear every overlay for an unobstructed view of the body.
  bool _hudVisible = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _ticker = createTicker((_) => _vsync.value++)..start();

    // Separate, slow tick for the session clock. Rebuilding the tree once a
    // second is cheap; doing it 60 times a second would not be.
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });

    widget.session.addListener(_onSessionChanged);
  }

  @override
  void dispose() {
    _ticker.dispose();
    _vsync.dispose();
    _clock?.cancel();
    widget.session.removeListener(_onSessionChanged);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        widget.session.handlePause();
      case AppLifecycleState.resumed:
        widget.session.handleResume();
    }
  }

  void _onSessionChanged() {
    final message = widget.session.message;
    if (message == null || !mounted) return;

    widget.session.clearMessage();
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;

    return Scaffold(
      backgroundColor: Colors.black,
      body: AnimatedBuilder(
        animation: session,
        builder: (context, _) {
          final frame = session.frame;

          return LayoutBuilder(
            builder: (context, constraints) {
              // A wide window has horizontal room to spare and little vertical
              // room; a tall one is the opposite. The breakpoint is the aspect
              // ratio rather than a pixel width, so it behaves the same on a
              // resized browser window and on a tablet.
              final isWide = constraints.maxWidth / constraints.maxHeight > 1.25;

              return Stack(
                fit: StackFit.expand,
                children: [
                  // ---- the camera owns the whole window ----
                  _Viewport(session: session, vsync: _vsync),

                  // ---- top bar ----
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: SafeArea(
                      bottom: false,
                      child: TelemetryBar(
                        status: session.status,
                        frame: frame,
                        pipelineFps: session.pipelineFps,
                        roundTrip: session.roundTrip,
                        isRecording: session.isRecording,
                        sessionDuration: session.sessionDuration,
                        hudVisible: _hudVisible,
                        onToggleHud: () =>
                            setState(() => _hudVisible = !_hudVisible),
                        onOpenControls: () => ControlsSheet.show(context, session),
                        onDisconnect: () => Navigator.of(context).maybePop(),
                      ),
                    ),
                  ),

                  // ---- guidance: offline server, or body not framed ----
                  if (!session.status.isLive)
                    Positioned.fill(
                      child: IgnorePointer(
                        child: GuidanceBanner(
                          kind: GuidanceKind.offline,
                          message: session.status == SocketStatus.connecting
                              ? 'Connecting to ${session.serverUrl}…'
                              : 'No response from ${session.serverUrl}',
                        ),
                      ),
                    )
                  else if (session.captureStalled)
                    Positioned.fill(
                      child: IgnorePointer(
                        child: GuidanceBanner(
                          kind: GuidanceKind.captureStalled,
                          message: session.captureDiagnosis ??
                              'No frames captured yet.',
                        ),
                      ),
                    )
                  else if (!frame.telemetry.isReady)
                    Positioned.fill(
                      child: IgnorePointer(
                        child: GuidanceBanner(
                          message: frame.telemetry.guidanceMessage,
                        ),
                      ),
                    ),

                  // ---- floating readouts ----
                  if (_hudVisible) ...[
                    if (session.showAngleCards)
                      _CornerHud(session: session, compact: !isWide),
                    _AssessmentStrip(session: session, compact: !isWide),
                  ],

                  // ---- mode switcher ----
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    child: SafeArea(
                      top: false,
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: AppGaps.md),
                        child: Center(
                          child: BodyModeSwitcher(
                            active: session.bodyMode,
                            onChanged: session.setBodyMode,
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              );
            },
          );
        },
      ),
    );
  }
}

/// ============================================================================
/// VIEWPORT — camera preview + skeleton, guaranteed aligned
/// ============================================================================
class _Viewport extends StatelessWidget {
  const _Viewport({required this.session, required this.vsync});

  final SessionController session;
  final Listenable vsync;

  @override
  Widget build(BuildContext context) {
    final controller = session.camera.controller;
    final frame = session.frame;

    if (controller == null || !controller.value.isInitialized) {
      return _ViewportPlaceholder(
        message: session.camera.error ?? 'Starting camera…',
        isError: session.camera.error != null,
      );
    }

    final preview = controller.value.previewSize;

    // Prefer the server's frame_w/frame_h: that is literally the buffer the
    // landmarks were normalised against, so using it removes any chance of the
    // overlay and the video disagreeing about shape.
    final sourceAspect = frame.frameAspect ??
        (preview != null && preview.height > 0
            ? preview.width / preview.height
            : 4 / 3);

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final rect = fitContain(viewport, sourceAspect);

        return ClipRect(
          child: Stack(
            fit: StackFit.expand,
            children: [
              const ColoredBox(color: Colors.black),

              // ---- live video ----
              Positioned.fromRect(
                rect: rect,
                child: _MaybeMirror(
                  // NOT `mirrorSelfie`. On web the mirror is applied to the
                  // video element itself, so flipping here as well would cancel
                  // it out and leave the skeleton facing the wrong way.
                  mirror: session.camera.mirrorPreviewWidget,
                  child: FittedBox(
                    fit: BoxFit.fill,
                    child: SizedBox(
                      width: preview?.width ?? rect.width,
                      height: preview?.height ?? rect.height,
                      child: CameraPreview(controller),
                    ),
                  ),
                ),
              ),

              // ---- framing boundary ----
              Positioned.fromRect(
                rect: rect,
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: FramingGuidePainter(
                      isReady: frame.telemetry.isReady,
                    ),
                  ),
                ),
              ),

              // ---- skeleton, drawn in the same rect as the video ----
              // NOT wrapped in _MaybeMirror: the server mirrored the frame
              // before inference, so these coordinates are already in the
              // mirrored space the preview above is showing.
              Positioned.fromRect(
                rect: rect,
                child: IgnorePointer(
                  child: RepaintBoundary(
                    child: CustomPaint(
                      painter: SkeletonPainter(
                        frame: frame,
                        interpolator: session.poseInterpolator,
                        repaint: vsync,
                        mode: session.bodyMode,
                        showBones: session.showBones,
                        showJoints: session.showJoints,
                        showHands: session.showHands,
                        showArcs: session.showArcs,
                        showBadge: session.showConfidenceBadge,
                      ),
                    ),
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

/// The rect a source of [sourceAspect] occupies inside [viewport] under
/// [BoxFit.contain] — scaled to fit entirely, centred, letterboxed.
///
/// Computed here rather than delegated to a FittedBox so the skeleton painter
/// can be handed the identical rect. Alignment is then structural: the overlay
/// cannot drift from the video because both are positioned by the same maths.
///
/// Exposed (not private) so it can be unit-tested.
Rect fitContain(Size viewport, double sourceAspect) {
  if (viewport.width <= 0 || viewport.height <= 0 || sourceAspect <= 0) {
    return Rect.fromLTWH(0, 0, viewport.width, viewport.height);
  }

  final viewportAspect = viewport.width / viewport.height;

  final double width;
  final double height;

  // Contain is the mirror image of cover: constrain by whichever axis runs out
  // first, so nothing is ever cropped.
  if (sourceAspect > viewportAspect) {
    width = viewport.width;
    height = width / sourceAspect;
  } else {
    height = viewport.height;
    width = height * sourceAspect;
  }

  return Rect.fromCenter(
    center: Offset(viewport.width / 2, viewport.height / 2),
    width: width,
    height: height,
  );
}

class _MaybeMirror extends StatelessWidget {
  const _MaybeMirror({required this.mirror, required this.child});

  final bool mirror;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!mirror) return child;
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()..scaleByDouble(-1.0, 1.0, 1.0, 1.0),
      child: child,
    );
  }
}

class _ViewportPlaceholder extends StatelessWidget {
  const _ViewportPlaceholder({required this.message, required this.isError});

  final String message;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppGaps.xl),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                isError ? Icons.videocam_off_rounded : Icons.videocam_rounded,
                size: 32,
                color: isError ? AppPalette.danger : AppPalette.textMuted,
              ),
              const SizedBox(height: AppGaps.md),
              Text(
                message,
                textAlign: TextAlign.center,
                style: AppTheme.body.copyWith(
                  color: isError ? AppPalette.danger : AppPalette.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// ============================================================================
/// HUD — four corners
/// ============================================================================
/// Angle cards pinned to the corners, the way the desktop app laid them out and
/// the way a clinician reads them: left-side joints on the left, right-side on
/// the right, upper body up, lower body down. Spatial position carries the
/// meaning, so no one has to parse a label to know which limb a number belongs
/// to.
///
/// The corners are also the cheapest real estate on screen — with the video
/// letterboxed, they are largely black bars anyway.
class _CornerHud extends StatelessWidget {
  const _CornerHud({required this.session, required this.compact});

  final SessionController session;

  /// Narrow windows get smaller cards and drop the centre posture panel, which
  /// would otherwise collide with the mode switcher.
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final frame = session.frame;
    final mode = session.bodyMode;
    final width = compact ? 158.0 : 196.0;

    // Which group sits in which corner, per mode. Left-side joints go left,
    // right-side right, upper up, lower down — position carries the meaning, so
    // nobody has to read a label to know which limb a number describes.
    //
    // Single-region modes promote their own region to the TOP corners and leave
    // the bottom ones empty rather than stranding the reader with half a screen
    // of blanks.
    final (HudGroup? tl, HudGroup? tr, HudGroup? bl, HudGroup? br) =
        switch (mode) {
      BodyMode.upperBody => (
          HudLayout.leftUpper,
          HudLayout.rightUpper,
          null,
          null,
        ),
      BodyMode.lowerBody => (
          HudLayout.leftLower,
          HudLayout.rightLower,
          null,
          null,
        ),
      BodyMode.fullBody => (
          HudLayout.leftUpper,
          HudLayout.rightUpper,
          HudLayout.leftLower,
          HudLayout.rightLower,
        ),
    };

    // Posture/pelvis/balance is bilateral, so no side owns it. In full-body mode
    // all four corners are taken, so it goes centre-left — clear of the corner
    // cards and clear of the mode switcher along the bottom. With only two cards
    // on screen it can take the free bottom-left corner.
    final postureAlignment = mode == BodyMode.fullBody
        ? Alignment.centerLeft
        : Alignment.bottomLeft;

    return Positioned.fill(
      child: SafeArea(
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            AppGaps.md,
            compact ? 76 : 68,
            AppGaps.md,
            AppGaps.xxl + AppGaps.lg,
          ),
          child: Stack(
            children: [
              if (tl != null)
                Align(
                  alignment: Alignment.topLeft,
                  child: SizedBox(
                    width: width,
                    child: AngleCard(group: tl, frame: frame),
                  ),
                ),
              if (tr != null)
                Align(
                  alignment: Alignment.topRight,
                  child: SizedBox(
                    width: width,
                    child: AngleCard(group: tr, frame: frame),
                  ),
                ),
              if (bl != null)
                Align(
                  alignment: Alignment.bottomLeft,
                  child: SizedBox(
                    width: width,
                    child: AngleCard(group: bl, frame: frame),
                  ),
                ),
              if (br != null)
                Align(
                  alignment: Alignment.bottomRight,
                  child: SizedBox(
                    width: width,
                    child: AngleCard(group: br, frame: frame),
                  ),
                ),

              Align(
                alignment: postureAlignment,
                child: SizedBox(
                  width: compact ? 190 : 226,
                  child: AngleCard(
                    group: HudLayout.posture,
                    frame: frame,
                    showRom: false,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// ============================================================================
/// ASSESSMENT STRIP
/// ============================================================================
/// Movement quality and the corrective cue. Kept separate from the corner cards
/// because it is the one thing the patient — not the clinician — is meant to
/// read, so it sits under the top bar where the eye lands first.
class _AssessmentStrip extends StatelessWidget {
  const _AssessmentStrip({required this.session, required this.compact});

  final SessionController session;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final frame = session.frame;

    return Positioned(
      top: compact ? 118 : 64,
      left: 0,
      right: 0,
      child: SafeArea(
        bottom: false,
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: compact ? 320 : 430),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                AssessmentPanel(frame: frame, mode: session.bodyMode),
                const SizedBox(height: AppGaps.sm),
                ClinicalFeedbackBar(
                  messages: frame.telemetry.isReady
                      ? frame.physio.clinicalFeedback
                      : <String>[frame.telemetry.guidanceMessage],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

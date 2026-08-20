import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show DeviceOrientation;

import '../models/skeleton_topology.dart';
import 'pose_socket.dart';

// The real grabber only compiles on web; Android gets the stub. Conditional
// import keeps a single unqualified name at the call site.
import 'frame_grabber_stub.dart'
    if (dart.library.js_interop) 'frame_grabber_web.dart';

/// Capture resolution presets.
///
/// The hints are blunt about bandwidth because raw NV21 is uncompressed, and the
/// cost scales with pixel count: roughly 18 Mbps at Fast, 55 Mbps at Detailed and
/// 165 Mbps at Maximum (all at 15 fps). Ordinary 2.4 GHz Wi-Fi tops out well
/// below the middle option.
///
/// Fast is the default and is not a compromise: MediaPipe's pose graph runs its
/// detector at roughly 256x256 internally, and `PoseDetector` downsamples
/// anything wider than 640 px before inference anyway. Sending more pixels than
/// that mostly buys latency.
enum CaptureQuality {
  low('Fast', '~320x240 · works on any Wi-Fi', ResolutionPreset.low),
  medium('Detailed', '~640x480 · needs 5 GHz', ResolutionPreset.medium),
  high('Maximum', '~1280x720 · 5 GHz, may drop frames', ResolutionPreset.high);

  const CaptureQuality(this.label, this.hint, this.preset);

  final String label;
  final String hint;
  final ResolutionPreset preset;
}

/// ============================================================================
/// CAMERA STREAMER
/// ============================================================================
/// Owns the device camera and pumps frames to the inference server.
///
/// TWO CAPTURE PATHS
///
/// * **Native (Android)** — `startImageStream` hands us raw YUV420 planes, which
///   we repack to NV21: a strided memory copy, roughly 2–4 ms. OpenCV converts
///   colour on the PC with one SIMD call. Encoding JPEG in Dart instead would
///   cost 30–60 ms a frame and cap the session in the single digits, so the
///   device never touches a compression codec. See [_yuv420ToNv21].
///
/// * **Web (Chrome)** — `camera_web` has no `startImageStream`; a browser exposes
///   a `<video>` element, not sensor planes. So we poll `takePicture()` and send
///   the resulting JPEG, which the server already decodes. Slower (10–15 fps),
///   but it needs no Android toolchain and no phone. See [_startWebPump].
///
/// Both paths share the socket, the header format and the send-rate maths — only
/// the pixel acquisition differs.
/// ============================================================================
class CameraStreamer extends ChangeNotifier {
  CameraStreamer({required this.socket});

  final PoseSocket socket;

  CameraController? _controller;
  CameraController? get controller => _controller;

  List<CameraDescription> _cameras = <CameraDescription>[];
  int _cameraIndex = 0;

  /// Default capture resolution.
  ///
  /// The Fast preset exists to protect Wi-Fi bandwidth on the Android path,
  /// where frames travel uncompressed over the air. In Chrome the server is on
  /// localhost and the frames are JPEG, so neither constraint applies — and a
  /// full-window view upscaled from 320x240 looks soft. Web therefore starts at
  /// Detailed.
  CaptureQuality _quality = kIsWeb ? CaptureQuality.medium : CaptureQuality.low;
  CaptureQuality get quality => _quality;

  /// Mirrors the preview and the frame sent for inference.
  ///
  /// Defaults to true to match `config/config.yaml`'s `flip_horizontal: true`,
  /// so behaviour is identical to the validated desktop app.
  ///
  /// CLINICAL CAVEAT: a mirrored frame swaps which limb MediaPipe labels LEFT vs
  /// RIGHT, because the model reasons about the image as presented. Mirroring
  /// gives the patient an intuitive "looking in a mirror" view; turn it off when
  /// the side labels in a report must be anatomically literal.
  bool _mirrorSelfie = true;
  bool get mirrorSelfie => _mirrorSelfie;

  /// Whether the Flutter widget tree should flip the preview.
  ///
  /// FALSE ON WEB — and that is the whole fix for the inverted skeleton.
  /// `camera_web` already applies its own CSS transform to the video element,
  /// and [FrameGrabber] now overrides that transform directly. Adding a Flutter
  /// `Transform` on top would be a second flip, cancelling the first: the
  /// picture would come out unmirrored while the landmarks stayed mirrored, so
  /// the skeleton would move opposite to the body.
  ///
  /// On Android there is no CSS layer, `CameraPreview` renders the raw frame,
  /// and the widget flip is the only one — so it is applied there.
  bool get mirrorPreviewWidget => !kIsWeb && _mirrorSelfie;

  /// Upper bound on frames offered to the socket per second.
  ///
  /// 20 is chosen against the wire cost on Android: uncompressed NV21 at
  /// 320x240 is ~115 KB a frame, so 20 fps is ~18 Mbps — comfortable on 2.4 GHz.
  /// On web there is no link to saturate (the server is localhost), so the cap
  /// is raised and the real limiter becomes browser JPEG encoding.
  ///
  /// Either way the socket's in-flight gate does the actual throttling; this cap
  /// only avoids pixel work that would be dropped anyway.
  int targetFps = kIsWeb ? 30 : 20;

  bool _initialising = false;
  bool _streaming = false;

  /// Whether the session WANTS frames flowing, independent of whether they are.
  ///
  /// This distinction is the fix for a race that stopped the app dead. [start]
  /// used to be called exactly once, when the socket went live — and it returns
  /// immediately if the camera controller is not initialised yet. On web the
  /// controller waits on a permission prompt, so the socket routinely wins that
  /// race, `start()` no-oped, and nothing ever called it again. The preview
  /// rendered fine (that is the plugin's own element) while zero frames were
  /// ever captured.
  ///
  /// Recording the *intent* separately lets [_startController] and the session
  /// supervisor reconcile reality against it, rather than depending on one
  /// perfectly-timed call.
  bool _wantStreaming = false;
  bool get wantStreaming => _wantStreaming;

  String? _error;

  String? get error => _error;
  bool get isReady => _controller?.value.isInitialized ?? false;
  bool get isStreaming => _streaming;
  bool get hasMultipleCameras => _cameras.length > 1;

  BodyMode bodyMode = BodyMode.fullBody;

  DateTime _lastSent = DateTime.fromMillisecondsSinceEpoch(0);
  int _framesSent = 0;
  int _framesSkipped = 0;

  /// Web-only frame pump. See [_startWebPump] for why the web path differs.
  Timer? _webPump;
  bool _webCapturing = false;

  /// Direct canvas capture on web. Bypasses takePicture()'s JPEG + base64
  /// pipeline, which was the cause of multi-second skeleton lag.
  final FrameGrabber _grabber = FrameGrabber();

  /// Set once takePicture() has had to stand in for the canvas path, so the
  /// slow route is not retried on every single frame.
  bool _canvasUnavailable = false;

  /// When the canvas path started failing continuously, or null if healthy.
  /// Used to distinguish ordinary startup from a genuine breakage.
  DateTime? _canvasFailingSince;

  /// Human-readable note about capture health, shown in the UI. Null when fine.
  ///
  /// Without this, a stalled capture is indistinguishable from a working app:
  /// the socket stays green, no error is thrown, and the only symptom is a
  /// frame counter that never moves.
  String? captureNote;

  /// Why the last capture attempt produced nothing, if anything.
  String? get captureFailure => _grabber.lastFailure;

  /// Inference frame width on web. Small on purpose: MediaPipe's pose graph runs
  /// near 256 px internally and `PoseDetector` downsamples past 640 anyway, so
  /// extra pixels buy latency, not accuracy. The PREVIEW is unaffected — it
  /// still shows the camera's full resolution.
  int webInferenceWidth = 384;

  int get framesSent => _framesSent;
  int get framesSkipped => _framesSkipped;

  /// Frames offered to the socket per second, measured over a rolling window.
  double _sendFps = 0;
  double get sendFps => _sendFps;
  DateTime? _lastSendTick;

  CameraDescription? get _activeCamera =>
      _cameras.isEmpty ? null : _cameras[_cameraIndex % _cameras.length];

  bool get isFrontCamera =>
      _activeCamera?.lensDirection == CameraLensDirection.front;

  // --------------------------------------------------------------------------
  // LIFECYCLE
  // --------------------------------------------------------------------------

  /// Enumerates cameras and starts the front camera (a patient standing in front
  /// of a propped-up phone needs to see themselves).
  Future<void> initialise() async {
    if (_initialising) return;
    _initialising = true;
    _error = null;
    notifyListeners();

    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        _error = 'No camera found on this device.';
        return;
      }

      final frontIndex =
          _cameras.indexWhere((c) => c.lensDirection == CameraLensDirection.front);
      _cameraIndex = frontIndex >= 0 ? frontIndex : 0;

      await _startController();
    } on CameraException catch (e) {
      _error = _friendlyCameraError(e);
    } catch (e) {
      _error = 'Camera initialisation failed: $e';
    } finally {
      _initialising = false;
      notifyListeners();
    }
  }

  Future<void> _startController() async {
    final camera = _activeCamera;
    if (camera == null) return;

    await _disposeController();

    final controller = CameraController(
      camera,
      _quality.preset,
      enableAudio: false,
      // yuv420 is the only format that gives us raw planes cheaply on Android.
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    _controller = controller;
    await controller.initialize();

    // Locking to portrait keeps the rotation maths a constant rather than
    // something that changes mid-session as the patient moves. camera_web does
    // not implement this, and a browser window has no orientation to lock, so
    // the failure is expected rather than exceptional there.
    if (!kIsWeb) {
      try {
        await controller.lockCaptureOrientation(DeviceOrientation.portraitUp);
      } on CameraException catch (e) {
        debugPrint('Could not lock orientation: ${e.code}');
      }
    }

    // If the session already asked for frames while this was initialising —
    // the common case on web, where a permission prompt delays the camera long
    // past the socket connecting — honour that intent now.
    if (_wantStreaming && !_streaming) {
      await start();
    }

    notifyListeners();
  }

  Future<void> _disposeController() async {
    final controller = _controller;
    _controller = null;
    if (controller == null) return;

    try {
      if (_streaming && !kIsWeb) {
        await controller.stopImageStream();
      }
      _streaming = false;
    } catch (_) {
      // Stream may already be stopped.
    }
    await controller.dispose();
  }

  /// Begins pumping frames. Safe to call repeatedly, and safe to call BEFORE
  /// the camera is ready — the intent is remembered and acted on once it is.
  Future<void> start() async {
    _wantStreaming = true;

    final controller = _controller;
    if (controller == null || !controller.value.isInitialized || _streaming) return;

    if (kIsWeb) {
      _startWebPump();
      return;
    }

    try {
      await controller.startImageStream(_onFrame);
      _streaming = true;
      notifyListeners();
    } on CameraException catch (e) {
      _error = _friendlyCameraError(e);
      notifyListeners();
    }
  }

  Future<void> stop() async {
    _wantStreaming = false;
    _webPump?.cancel();
    _webPump = null;

    final controller = _controller;
    if (controller == null || !_streaming) {
      _streaming = false;
      return;
    }

    if (!kIsWeb) {
      try {
        await controller.stopImageStream();
      } catch (_) {
        // Ignore — we are tearing down anyway.
      }
    }

    _streaming = false;
    notifyListeners();
  }

  Future<void> switchCamera() async {
    if (_cameras.length < 2) return;

    final wasStreaming = _streaming;
    await stop();
    _cameraIndex = (_cameraIndex + 1) % _cameras.length;

    // Selfie mirroring only makes sense on a front-facing lens.
    _mirrorSelfie = isFrontCamera;

    await _startController();
    if (wasStreaming) await start();
  }

  Future<void> setQuality(CaptureQuality quality) async {
    if (quality == _quality) return;
    _quality = quality;

    final wasStreaming = _streaming;
    await stop();
    await _startController();
    if (wasStreaming) await start();
  }

  void setMirror({required bool mirror}) {
    _mirrorSelfie = mirror;
    // Push the new state to the video element now. Waiting for the next capture
    // would leave the preview and the landmark space disagreeing for a frame,
    // which reads as the skeleton jumping to the wrong side.
    if (kIsWeb) _grabber.grab(targetWidth: webInferenceWidth, mirror: mirror);
    notifyListeners();
  }

  /// Releases the camera. Kept synchronous to match [ChangeNotifier.dispose]'s
  /// signature; the teardown itself is inherently async, so it is fired and
  /// forgotten — there is no listener left to care about its completion.
  @override
  void dispose() {
    _webPump?.cancel();
    _grabber.dispose();
    _disposeController();
    super.dispose();
  }

  // --------------------------------------------------------------------------
  // FRAME PUMP
  // --------------------------------------------------------------------------

  /// ------------------------------------------------------------------------
  /// WEB FRAME PUMP
  /// ------------------------------------------------------------------------
  /// `camera_web` does not implement `startImageStream` — browsers expose a
  /// `<video>` element, not raw sensor planes — so the native NV21 path cannot
  /// run here. Instead we poll `takePicture()`, which the web plugin implements
  /// by drawing the video frame to a canvas and encoding it.
  ///
  /// That hands us a JPEG, which is the format the server's `decode_payload`
  /// already handles via `cv2.imdecode`. So the web path needs no server change
  /// at all: same socket, same header, different `fmt`.
  ///
  /// The trade-off versus Android is honest: JPEG encoding in the browser caps
  /// this around 10–15 fps rather than 20. For checking that the pipeline works
  /// and for demoing the UI that is plenty, and it costs no Android toolchain.
  void _startWebPump() {
    _webPump?.cancel();
    _streaming = true;
    notifyListeners();

    final periodMs = (1000 / targetFps).round().clamp(25, 400);

    _webPump = Timer.periodic(Duration(milliseconds: periodMs), (_) async {
      // takePicture() is async and can outlast the tick, so without this guard
      // captures would pile up and each would fight the last for the canvas.
      if (_webCapturing) return;

      if (!socket.canSendFrame) {
        _framesSkipped++;
        return;
      }

      final controller = _controller;
      if (controller == null || !controller.value.isInitialized) return;

      // ---- fast path: straight off the video element, no codec ----
      if (!_canvasUnavailable) {
        final grabbed =
            _grabber.grab(targetWidth: webInferenceWidth, mirror: _mirrorSelfie);
        if (grabbed != null) {
          _canvasFailingSince = null;
          final sent = socket.sendFrame(
            payload: grabbed.bytes,
            width: grabbed.width,
            height: grabbed.height,
            format: 'rgba',
            rotation: 0,
            // The MEASURED flip, not the requested one. If something in the DOM
            // cancelled our transform, this still matches what is on screen.
            mirror: grabbed.mirrored,
            mode: bodyMode,
          );
          if (sent) {
            _framesSent++;
            _tickSendRate(DateTime.now());
          } else {
            _framesSkipped++;
          }
          return;
        }

        // Nothing to grab yet. This is normal for the first second or so while
        // the browser loads video metadata, so it is timed rather than counted:
        // only a sustained failure downgrades to the slow path.
        //
        // The previous rule (`framesSent == 0 && skipped > 30`) was wrong twice
        // over — it could latch during ordinary startup, and once a single frame
        // had succeeded it could never fall back at all, so a capture that broke
        // mid-session simply stalled at 0 fps forever.
        _framesSkipped++;
        _canvasFailingSince ??= DateTime.now();

        final failingFor = DateTime.now().difference(_canvasFailingSince!);
        if (failingFor > const Duration(seconds: 3)) {
          _canvasUnavailable = true;
          captureNote = 'Canvas capture unavailable — using the slower '
              'takePicture() path. ${_grabber.lastFailure ?? ''}'.trim();
          debugPrint(captureNote);
        }
        return;
      }

      // ---- fallback: the plugin's own capture (JPEG + base64, much slower) ----
      _webCapturing = true;
      try {
        final shot = await controller.takePicture();
        final bytes = await shot.readAsBytes();

        final sent = socket.sendFrame(
          payload: bytes,
          width: 0,
          height: 0,
          format: 'jpeg',
          rotation: 0,
          mirror: _mirrorSelfie,
          mode: bodyMode,
        );

        if (sent) {
          _framesSent++;
          _tickSendRate(DateTime.now());
        } else {
          _framesSkipped++;
        }
      } catch (e) {
        _framesSkipped++;
        debugPrint('Web capture skipped: $e');
      } finally {
        _webCapturing = false;
      }
    });
  }

  /// Rolling send-rate estimate, shared by both capture paths.
  void _tickSendRate(DateTime now) {
    final previous = _lastSendTick;
    if (previous != null) {
      final dt = now.difference(previous).inMicroseconds / 1000000.0;
      if (dt > 0) {
        final instant = 1 / dt;
        _sendFps = _sendFps <= 0 ? instant : (0.85 * _sendFps + 0.15 * instant);
      }
    }
    _lastSendTick = now;
  }

  void _onFrame(CameraImage image) {
    // Cheapest checks first: never convert pixels we are not going to send.
    if (!socket.canSendFrame) {
      _framesSkipped++;
      return;
    }

    final now = DateTime.now();
    final minGapMs = (1000 / targetFps).floor();
    if (now.difference(_lastSent).inMilliseconds < minGapMs) {
      _framesSkipped++;
      return;
    }

    final Uint8List? payload;
    final String format;

    if (image.format.group == ImageFormatGroup.yuv420 && image.planes.length >= 3) {
      payload = _yuv420ToNv21(image);
      format = 'nv21';
    } else if (image.format.group == ImageFormatGroup.bgra8888 &&
        image.planes.isNotEmpty) {
      // iOS / emulator fallback. Four bytes per pixel is heavier on the wire but
      // needs no repacking, and this path is not the Android target anyway.
      payload = image.planes.first.bytes;
      format = 'bgra';
    } else {
      _framesSkipped++;
      return;
    }

    if (payload == null) {
      _framesSkipped++;
      return;
    }

    final sent = socket.sendFrame(
      payload: payload,
      width: image.width,
      height: image.height,
      format: format,
      rotation: _rotationDegrees(),
      mirror: _mirrorSelfie,
      mode: bodyMode,
    );

    if (!sent) {
      _framesSkipped++;
      return;
    }

    _lastSent = now;
    _framesSent++;
    _tickSendRate(now);
  }

  /// Clockwise rotation the server must apply to bring the frame upright.
  ///
  /// The app is locked to portrait, so this reduces to the sensor's mounting
  /// orientation — 90° on virtually every Android back camera, 270° on the front.
  int _rotationDegrees() => (_activeCamera?.sensorOrientation ?? 90) % 360;

  /// Repacks a 3-plane YUV420 [CameraImage] into a contiguous NV21 buffer:
  /// the full-resolution Y plane followed by half-resolution V,U interleaved.
  ///
  /// Both loops respect `bytesPerRow` and `bytesPerPixel`, because Android pads
  /// plane rows to hardware alignment and delivers chroma as either planar
  /// (stride 1) or semi-planar (stride 2) depending on the device. Ignoring
  /// those strides is the classic source of green-skewed or sheared frames.
  static Uint8List? _yuv420ToNv21(CameraImage image) {
    try {
      final int width = image.width;
      final int height = image.height;

      final Plane yPlane = image.planes[0];
      final Plane uPlane = image.planes[1];
      final Plane vPlane = image.planes[2];

      final int ySize = width * height;
      final int uvSize = ySize ~/ 2;
      final out = Uint8List(ySize + uvSize);

      // ---- luma ----
      final Uint8List yBytes = yPlane.bytes;
      final int yRowStride = yPlane.bytesPerRow;
      int offset = 0;

      if (yRowStride == width) {
        // Unpadded: one bulk copy.
        out.setRange(0, ySize, yBytes);
        offset = ySize;
      } else {
        for (int row = 0; row < height; row++) {
          final int start = row * yRowStride;
          out.setRange(offset, offset + width, yBytes, start);
          offset += width;
        }
      }

      // ---- chroma, interleaved as V,U for NV21 ----
      final Uint8List uBytes = uPlane.bytes;
      final Uint8List vBytes = vPlane.bytes;
      final int uvRowStride = uPlane.bytesPerRow;
      final int uvPixelStride = uPlane.bytesPerPixel ?? 1;

      final int chromaWidth = width ~/ 2;
      final int chromaHeight = height ~/ 2;

      for (int row = 0; row < chromaHeight; row++) {
        final int rowStart = row * uvRowStride;
        for (int col = 0; col < chromaWidth; col++) {
          final int index = rowStart + col * uvPixelStride;
          if (index >= vBytes.length || index >= uBytes.length) break;
          out[offset++] = vBytes[index];
          out[offset++] = uBytes[index];
        }
      }

      return out;
    } catch (e) {
      debugPrint('NV21 repack failed: $e');
      return null;
    }
  }

  String _friendlyCameraError(CameraException e) {
    return switch (e.code) {
      'CameraAccessDenied' || 'CameraAccessDeniedWithoutPrompt' =>
        'Camera permission denied. Enable it in Android Settings → Apps → '
            'Therayu → Permissions.',
      'CameraAccessRestricted' => 'Camera access is restricted on this device.',
      'cameraNotFound' => 'No usable camera was found.',
      _ => 'Camera error (${e.code}): ${e.description ?? 'unknown'}',
    };
  }
}

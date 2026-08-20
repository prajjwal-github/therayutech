import 'dart:js_interop';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:web/web.dart' as web;

/// One captured frame as raw, uncompressed RGBA.
class RgbaFrame {
  const RgbaFrame({
    required this.bytes,
    required this.width,
    required this.height,
    required this.mirrored,
  });

  final Uint8List bytes;
  final int width;
  final int height;

  /// The net horizontal flip of the preview when this frame was grabbed — what
  /// actually ended up on screen, not what was requested. The server applies the
  /// same flip, which is what keeps the skeleton on the body rather than
  /// mirrored across it.
  final bool mirrored;
}

/// ============================================================================
/// FRAME GRABBER — web
/// ============================================================================
/// Pulls frames straight off the `<video>` element the camera plugin created.
///
/// ---------------------------------------------------------------------------
/// FAILURE POLICY — read this before adding anything to [grab]
/// ---------------------------------------------------------------------------
/// Exactly one thing in here is allowed to fail the capture: copying the pixels.
/// Everything else — mirroring the preview, measuring the transform — is
/// optional decoration around that copy, and each is guarded on its own.
///
/// This rule exists because it was broken once, with instructive results. A
/// single try/catch wrapped the whole method, so when the mirror-detection code
/// threw, `grab` returned null. The pump treats null as "not ready yet" and
/// skips, so the app sat at 0 fps with a healthy green socket and no error
/// anywhere — a diagnostic feature had silently stopped the pipeline it was
/// meant to explain.
///
/// A helper that reports on the pipeline must never be able to halt it.
/// ---------------------------------------------------------------------------
///
/// WHY THE CANVAS AT ALL
/// `camera_web.takePicture()` draws to a canvas, JPEG-encodes, base64-encodes
/// into a data URL, wraps it in a Blob and hands back a file that must then be
/// fetched and base64-decoded — 35–90 ms per frame for pixels discarded
/// immediately. `getImageData` is 2–4 ms with no codec at all.
///
/// WHY MIRRORING LIVES HERE
/// Three places can flip the image horizontally: `camera_web`'s own CSS on the
/// video element, a Flutter `Transform` around the preview, and the server. Two
/// of those cancelling while the third stayed put is what drew the skeleton as a
/// mirror image of the body. Note that `drawImage(video, …)` copies the decoded
/// frame and ignores CSS entirely, so the canvas cannot reveal the CSS flip
/// either. This class therefore sets the transform itself AND measures the net
/// result, and reports the measurement.
/// ============================================================================
class FrameGrabber {
  web.HTMLCanvasElement? _canvas;
  web.CanvasRenderingContext2D? _ctx;

  /// Last mirror state written to the video, so the DOM is touched only on
  /// change rather than on every frame.
  bool? _appliedMirror;

  /// Why the most recent grab returned nothing. Surfaced in the UI so a stalled
  /// pipeline explains itself instead of just showing 0 fps.
  String? lastFailure;

  bool get isSupported => true;

  /// Grabs the current video frame, downscaled to [targetWidth].
  ///
  /// Returns null only when there is genuinely nothing to copy — no video
  /// element yet, no metadata yet, or no 2D context. Those are ordinary startup
  /// states, not errors, and the caller simply skips the tick.
  RgbaFrame? grab({int targetWidth = 320, bool mirror = false}) {
    final video = _tryFindVideo();
    if (video == null) {
      lastFailure = 'no <video> element in the DOM yet';
      return null;
    }

    // OPTIONAL #1 — never allowed to fail the capture.
    _tryApplyPreviewMirror(video, mirror);

    final int sourceWidth;
    final int sourceHeight;
    try {
      sourceWidth = video.videoWidth;
      sourceHeight = video.videoHeight;
    } catch (e) {
      lastFailure = 'video dimensions unreadable: $e';
      return null;
    }

    // videoWidth stays 0 until the browser has metadata. Drawing then throws,
    // so this is "not ready", not a fault.
    if (sourceWidth == 0 || sourceHeight == 0) {
      lastFailure = 'video has no dimensions yet (metadata still loading)';
      return null;
    }

    final width = targetWidth.clamp(160, sourceWidth);
    final height = (sourceHeight * width / sourceWidth).round();

    // THE ONE STEP THAT MAY FAIL THE CAPTURE: copying pixels.
    final Uint8List bytes;
    try {
      // Canvas and context are reused; recreating them would allocate a fresh
      // GPU surface 20+ times a second.
      var canvas = _canvas;
      if (canvas == null || canvas.width != width || canvas.height != height) {
        canvas = web.document.createElement('canvas') as web.HTMLCanvasElement;
        canvas.width = width;
        canvas.height = height;
        _canvas = canvas;
        _ctx = canvas.getContext('2d') as web.CanvasRenderingContext2D?;
      }

      final ctx = _ctx;
      if (ctx == null) {
        lastFailure = 'could not obtain a 2D canvas context';
        return null;
      }

      // Draws the RAW frame deliberately — no canvas flip. The server performs
      // the mirror from the header flag, so pixels are flipped in exactly one
      // place and landmarks come from exactly one space.
      ctx.drawImage(video, 0, 0, width.toDouble(), height.toDouble());

      final imageData = ctx.getImageData(0, 0, width, height);

      // asUint8List over the existing buffer — no copy of the ~400 KB payload.
      bytes = imageData.data.toDart.buffer.asUint8List();
    } catch (e) {
      lastFailure = 'canvas copy failed: $e';
      return null;
    }

    // OPTIONAL #2 — measured after the pixels are safely in hand, so a throw
    // here costs the measurement and nothing else.
    final measured = _tryNetMirrored(video) ?? mirror;

    lastFailure = null;
    return RgbaFrame(
      bytes: bytes,
      width: width,
      height: height,
      mirrored: measured,
    );
  }

  // --------------------------------------------------------------------------
  // OPTIONAL STAGES — each swallows its own errors and degrades gracefully
  // --------------------------------------------------------------------------

  /// Forces the video's mirror state, overriding whatever the plugin set.
  ///
  /// `!important` matters: `camera_web` writes its own inline transform, and
  /// without the priority flag a plugin rebuild would silently win.
  void _tryApplyPreviewMirror(web.HTMLVideoElement video, bool mirror) {
    if (_appliedMirror == mirror) return;
    try {
      video.style.setProperty(
        'transform',
        mirror ? 'scaleX(-1)' : 'scaleX(1)',
        'important',
      );
      _appliedMirror = mirror;
    } catch (e) {
      debugPrint('Could not set preview mirror (continuing): $e');
    }
  }

  /// Measures the net horizontal flip actually applied to the preview, or null
  /// if it cannot be determined — in which case the caller falls back to the
  /// value it asked for.
  ///
  /// Forcing the video's own transform is not sufficient alone: Flutter web
  /// wraps platform views in container elements, and a flip applied to a PARENT
  /// would cancel ours one level up. So the ancestor chain is walked and every
  /// computed transform inspected. A negative first term in `matrix(a, …)` is a
  /// horizontal flip; an odd count means the picture on screen is mirrored.
  bool? _tryNetMirrored(web.HTMLVideoElement video) {
    try {
      var flipped = false;
      web.Element? el = video;

      // A dozen levels is far more than the platform-view wrapper needs, and
      // bounds the cost of doing this every frame.
      for (var depth = 0; el != null && depth < 12; depth++) {
        final style = web.window.getComputedStyle(el);
        final scaleX = _matrixScaleX(style.transform);
        if (scaleX != null && scaleX < 0) flipped = !flipped;
        el = el.parentElement;
      }
      return flipped;
    } catch (e) {
      debugPrint('Mirror detection unavailable (continuing): $e');
      return null;
    }
  }

  /// Pulls the horizontal scale term out of a computed `transform`.
  ///
  /// Browsers normalise every transform to `matrix(...)` or `matrix3d(...)`, so
  /// the first component is the horizontal scale whether the author wrote
  /// `scaleX(-1)`, `scale(-1, 1)` or a raw matrix.
  double? _matrixScaleX(String transform) {
    if (transform.isEmpty || transform == 'none') return null;
    final match = RegExp(r'matrix(?:3d)?\(([^)]+)\)').firstMatch(transform);
    if (match == null) return null;
    return double.tryParse(match.group(1)!.split(',').first.trim());
  }

  /// Finds the camera's video element.
  ///
  /// Prefers one with real dimensions: Flutter web can leave a detached video
  /// behind after a hot restart, and picking that one would stall capture
  /// permanently while the live element sat right beside it.
  web.HTMLVideoElement? _tryFindVideo() {
    try {
      final videos = web.document.querySelectorAll('video');

      web.HTMLVideoElement? fallback;
      for (var i = 0; i < videos.length; i++) {
        final node = videos.item(i);
        if (node is! web.HTMLVideoElement) continue;
        fallback ??= node;
        if (node.videoWidth > 0) return node;
      }
      return fallback;
    } catch (e) {
      debugPrint('Video lookup failed: $e');
      return null;
    }
  }

  void dispose() {
    _canvas = null;
    _ctx = null;
    _appliedMirror = null;
    lastFailure = null;
  }
}

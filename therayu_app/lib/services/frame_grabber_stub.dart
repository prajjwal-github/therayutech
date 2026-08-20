import 'dart:typed_data';

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

  /// The MEASURED net horizontal flip of the preview at the moment this frame
  /// was grabbed — not what we asked for, what actually ended up on screen.
  /// The server must apply the same flip or the skeleton lands mirrored.
  final bool mirrored;
}

/// ============================================================================
/// FRAME GRABBER — non-web stub
/// ============================================================================
/// On Android the camera plugin hands us raw YUV420 planes through
/// `startImageStream`, which is already the fastest possible path, so there is
/// nothing for a grabber to improve. This stub exists purely so
/// `camera_streamer.dart` can import one name unconditionally; the real
/// implementation is selected by a conditional import and only exists on web.
/// ============================================================================
class FrameGrabber {
  bool get isSupported => false;

  /// Always null here — the native path never uses this grabber.
  String? lastFailure;

  RgbaFrame? grab({int targetWidth = 320, bool mirror = false}) => null;

  void dispose() {}
}

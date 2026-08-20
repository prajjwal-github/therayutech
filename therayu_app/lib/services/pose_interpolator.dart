import 'package:flutter/foundation.dart';

import '../models/pose_frame.dart';

/// ============================================================================
/// POSE INTERPOLATOR
/// ============================================================================
/// Turns a low-rate landmark stream into smooth motion.
///
/// THE PROBLEM
/// The server delivers roughly 10 landmark sets a second. Painting each one the
/// instant it lands means the skeleton teleports 10 times a second while the
/// display refreshes 60 — so it reads as stuttering even though the tracking
/// itself is fine. Raising the capture rate does not fix this; it just moves the
/// stutter.
///
/// THE FIX
/// Keep the previous and current landmark sets and linearly interpolate between
/// them, sampled from a display-rate ticker. The skeleton then glides between
/// known positions instead of snapping to them.
///
/// WHAT IS DELIBERATELY *NOT* INTERPOLATED
/// Joint angles. Those are clinical measurements: a physio reading 88.4° is
/// entitled to assume the engine computed 88.4° from a real frame. Inventing
/// intermediate values would be fabricating data that no camera ever saw.
/// Smoothing is applied to the *picture*, never to the numbers.
///
/// LATENCY COST
/// This renders one server interval behind live (~100 ms) because it moves
/// toward a position already received rather than predicting past it. That is
/// the right trade for an assessment tool — extrapolation would overshoot on
/// direction changes and briefly draw limbs where they never went.
/// ============================================================================
class PoseInterpolator extends ChangeNotifier {
  /// Where the current glide started.
  Map<String, Landmark> _from = const <String, Landmark>{};

  /// Where it is heading — the newest set the server sent.
  Map<String, Landmark> _to = const <String, Landmark>{};

  DateTime _segmentStart = DateTime.now();

  /// Smoothed inter-arrival time, measured rather than assumed: the effective
  /// rate swings with camera resolution, whether hand tracking is on, and how
  /// busy the PC is.
  double _intervalMs = 100;

  /// Hard ceiling on how long a glide may take.
  ///
  /// The glide is what makes motion smooth, but it is also pure latency: the
  /// skeleton is always somewhere between the last two known positions. Letting
  /// it run a full server interval means a slow stream (say 300 ms a frame)
  /// visibly drags the skeleton behind the body.
  ///
  /// Capping it decouples the two concerns — smoothing stays, latency does not
  /// grow with the interval. Past the cap the skeleton simply holds the newest
  /// known position, which is the truthful thing to draw anyway.
  static const double _maxGlideMs = 70;

  DateTime? _lastArrival;

  /// True once at least one frame has been received.
  bool get hasData => _to.isNotEmpty;

  /// Measured server frame interval, exposed for diagnostics.
  double get intervalMs => _intervalMs;

  /// Accepts a newly arrived landmark set.
  void push(Map<String, Landmark> next, {required DateTime at}) {
    if (next.isEmpty) {
      // Detection dropped out. Hold the last pose rather than collapsing the
      // skeleton to the origin, which would look like a violent glitch.
      return;
    }

    final previous = _lastArrival;
    if (previous != null) {
      final gap = at.difference(previous).inMicroseconds / 1000.0;
      // Clamp before smoothing: a paused tab or a GC pause can produce a
      // multi-second gap that would otherwise poison the average for a while.
      if (gap > 8 && gap < 1000) {
        _intervalMs = _intervalMs * 0.8 + gap * 0.2;
      }
    }
    _lastArrival = at;

    // Start the new glide from wherever we had actually drawn to, not from the
    // previous target. If the last segment had not finished, jumping to its
    // endpoint here would produce exactly the snap this class exists to remove.
    _from = _to.isEmpty ? next : sample(at);
    _to = next;
    _segmentStart = at;

    notifyListeners();
  }

  /// The landmark positions to draw at [now].
  Map<String, Landmark> sample(DateTime now) {
    if (_to.isEmpty) return const <String, Landmark>{};
    if (_from.isEmpty) return _to;

    final elapsed = now.difference(_segmentStart).inMicroseconds / 1000.0;

    // Glide over the shorter of (measured interval, cap). A fast stream keeps
    // full smoothing; a slow one reaches the true position quickly rather than
    // easing toward it for a third of a second.
    final glideMs = _intervalMs < _maxGlideMs ? _intervalMs : _maxGlideMs;
    final t = (elapsed / glideMs).clamp(0.0, 1.0);

    if (t >= 1.0) return _to;

    final out = <String, Landmark>{};
    _to.forEach((name, target) {
      final origin = _from[name];
      if (origin == null) {
        // A landmark that just appeared (a hand entering frame) has nothing to
        // glide from, so it is placed directly rather than sliding in from a
        // stale position elsewhere on screen.
        out[name] = target;
        return;
      }
      out[name] = Landmark(
        x: _lerp(origin.x, target.x, t),
        y: _lerp(origin.y, target.y, t),
        z: _lerp(origin.z, target.z, t),
        // Visibility drives show/hide thresholds, so easing it too keeps limbs
        // from popping in and out at the boundary.
        visibility: _lerp(origin.visibility, target.visibility, t),
      );
    });
    return out;
  }

  /// Clears state, e.g. when a session ends.
  void reset() {
    _from = const <String, Landmark>{};
    _to = const <String, Landmark>{};
    _lastArrival = null;
    _intervalMs = 100;
    notifyListeners();
  }

  static double _lerp(double a, double b, double t) => a + (b - a) * t;
}

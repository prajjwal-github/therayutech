import 'package:flutter_test/flutter_test.dart';

import 'package:therayu_app/models/pose_frame.dart';
import 'package:therayu_app/models/skeleton_topology.dart';
import 'package:therayu_app/services/pose_socket.dart';

void main() {
  group('AngleState', () {
    test('renders the three engine "no value" states distinctly', () {
      // The Python engine deliberately signals three different things, and the
      // UI must never collapse them into a bare 0 degrees.
      const frame = PoseFrame.empty();
      expect(frame.angleState('elbow_flexion_left').display, 'N/A');

      expect(const AngleState.tracking().display, 'TRACKING…');
      expect(const AngleState.note('SIDE VIEW REQ').display, 'SIDE VIEW REQ');
      expect(const AngleState.degrees(88.4).display, '88.4°');
    });

    test('only a real measurement exposes a numeric value', () {
      expect(const AngleState.degrees(90).value, 90);
      expect(const AngleState.tracking().value, isNull);
      expect(const AngleState.unavailable().value, isNull);
    });
  });

  group('PoseFrame parsing', () {
    test('keeps null, string and numeric angles apart', () {
      final frame = PoseFrame.fromJson(<String, dynamic>{
        'landmarks': <String, dynamic>{
          'NOSE': <String, dynamic>{'x': 0.5, 'y': 0.25, 'z': 0.0, 'v': 0.97},
        },
        'angles': <String, dynamic>{
          'elbow_flexion_left': 88.4,
          'elbow_flexion_right': null,
          'shoulder_flexion_left': 'SIDE VIEW REQ',
        },
        'telemetry': <String, dynamic>{'person_detected': true, 'is_ready': true},
        'physio': <String, dynamic>{'movement_quality_pct': 94.5},
        'frame_w': 480,
        'frame_h': 640,
      });

      expect(frame.angleState('elbow_flexion_left').display, '88.4°');
      expect(frame.angleState('elbow_flexion_right').display, 'TRACKING…');
      expect(frame.angleState('shoulder_flexion_left').display, 'SIDE VIEW REQ');
      expect(frame.frameAspect, 480 / 640);
    });

    test('zeroes every angle while framing is invalid', () {
      // Mirrors the pipeline's "no fake angles" safety policy.
      final frame = PoseFrame.fromJson(<String, dynamic>{
        'angles': <String, dynamic>{'elbow_flexion_left': 88.4},
        'telemetry': <String, dynamic>{'person_detected': true, 'is_ready': false},
      });
      expect(frame.angleState('elbow_flexion_left').display, 'N/A');
    });
  });

  group('PoseSocket.normaliseUrl', () {
    test('accepts what a user would realistically type', () {
      const want = 'ws://192.168.1.7:8765/ws';
      expect(PoseSocket.normaliseUrl('192.168.1.7'), want);
      expect(PoseSocket.normaliseUrl('192.168.1.7:8765'), want);
      expect(PoseSocket.normaliseUrl('ws://192.168.1.7:8765'), want);
      expect(PoseSocket.normaliseUrl('  192.168.1.7:8765/ws  '), want);
    });

    test('derives the matching health URL', () {
      expect(PoseSocket.healthUrl('localhost'), 'http://localhost:8765/health');
    });
  });

  group('BodyMode', () {
    test('round-trips the wire strings the Python profiles expect', () {
      for (final mode in BodyMode.values) {
        expect(BodyMode.fromWire(mode.wire), mode);
      }
      expect(BodyMode.fromWire('nonsense'), BodyMode.fullBody);
    });
  });
}

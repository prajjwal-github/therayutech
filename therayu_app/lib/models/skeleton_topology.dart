import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// ============================================================================
/// SKELETON TOPOLOGY
/// ============================================================================
/// A 1:1 port of the connection tables in `visualization/medical_gui.py`.
/// Landmark names match `src/pose_detector.py` exactly (33 body landmarks, the
/// two derived anchors C7_NECK and PELVIS_CENTER, and 21 joints per hand
/// prefixed LEFT_HAND_ / RIGHT_HAND_), so the JSON the server sends can be
/// looked up here without any translation layer.
/// ============================================================================

/// Which body regions are drawn and measured.
enum BodyMode {
  upperBody('UPPER_BODY', 'Upper', 'Shoulders · Elbows · Neck · Spine'),
  lowerBody('LOWER_BODY', 'Lower', 'Hips · Knees · Ankles · Balance'),
  fullBody('FULL_BODY', 'Full', '33 landmarks + 42 finger joints');

  const BodyMode(this.wire, this.shortLabel, this.subtitle);

  /// The exact string the Python `CameraValidator.EXERCISE_PROFILES` expects.
  final String wire;
  final String shortLabel;
  final String subtitle;

  static BodyMode fromWire(String? wire) => switch (wire?.toUpperCase()) {
        'UPPER_BODY' => BodyMode.upperBody,
        'LOWER_BODY' => BodyMode.lowerBody,
        _ => BodyMode.fullBody,
      };
}

/// One drawable bone: two landmark names and the colour of the line between them.
class Bone {
  const Bone(this.from, this.to, this.color);

  final String from;
  final String to;
  final Color color;
}

/// One goniometric arc: the sweep drawn at [pivot] between the bones running to
/// [armA] and [armB], labelled with the value of [angleKey] from the angles map.
class JointArc {
  const JointArc(this.pivot, this.armA, this.armB, this.angleKey, this.color);

  final String pivot;
  final String armA;
  final String armB;
  final String angleKey;
  final Color color;
}

class SkeletonTopology {
  const SkeletonTopology._();

  // --------------------------------------------------------------------------
  // BONES — ports MedicalGUIRenderer.UPPER_BODY_CONNECTIONS / LOWER_BODY_...
  // --------------------------------------------------------------------------

  static const List<Bone> upperBody = <Bone>[
    Bone('C7_NECK', 'PELVIS_CENTER', AppPalette.boneSpine),
    Bone('NOSE', 'C7_NECK', AppPalette.boneSpine),
    Bone('LEFT_SHOULDER', 'RIGHT_SHOULDER', AppPalette.boneTorso),
    Bone('LEFT_SHOULDER', 'LEFT_HIP', AppPalette.boneTorso),
    Bone('RIGHT_SHOULDER', 'RIGHT_HIP', AppPalette.boneTorso),
    // The pelvic girdle closes the torso. Without it, upper-body mode drew two
    // shoulder-to-hip rails hanging in space with nothing joining them at the
    // bottom, so the trunk read as an open V rather than a quadrilateral. It is
    // also the reference for pelvic tilt, which upper-body mode reports.
    Bone('LEFT_HIP', 'RIGHT_HIP', AppPalette.boneTorso),
    Bone('LEFT_SHOULDER', 'LEFT_ELBOW', AppPalette.boneLeft),
    Bone('LEFT_ELBOW', 'LEFT_WRIST', AppPalette.boneLeft),
    Bone('RIGHT_SHOULDER', 'RIGHT_ELBOW', AppPalette.boneRight),
    Bone('RIGHT_ELBOW', 'RIGHT_WRIST', AppPalette.boneRight),
  ];

  static const List<Bone> lowerBody = <Bone>[
    Bone('LEFT_HIP', 'RIGHT_HIP', AppPalette.boneTorso),
    Bone('LEFT_HIP', 'LEFT_KNEE', AppPalette.boneLeft),
    Bone('LEFT_KNEE', 'LEFT_ANKLE', AppPalette.boneLeft),
    Bone('LEFT_ANKLE', 'LEFT_HEEL', AppPalette.boneLeft),
    Bone('LEFT_ANKLE', 'LEFT_FOOT_INDEX', AppPalette.boneLeft),
    Bone('LEFT_HEEL', 'LEFT_FOOT_INDEX', AppPalette.boneLeft),
    Bone('RIGHT_HIP', 'RIGHT_KNEE', AppPalette.boneRight),
    Bone('RIGHT_KNEE', 'RIGHT_ANKLE', AppPalette.boneRight),
    Bone('RIGHT_ANKLE', 'RIGHT_HEEL', AppPalette.boneRight),
    Bone('RIGHT_ANKLE', 'RIGHT_FOOT_INDEX', AppPalette.boneRight),
    Bone('RIGHT_HEEL', 'RIGHT_FOOT_INDEX', AppPalette.boneRight),
  ];

  /// Full body, written out rather than `[...upperBody, ...lowerBody]`.
  ///
  /// Both regions legitimately own the pelvic girdle — it is the base of the
  /// trunk and the top of the legs — so concatenating them would draw that line
  /// twice, doubling its apparent stroke weight against every other bone.
  static const List<Bone> fullBody = <Bone>[
    // trunk
    Bone('C7_NECK', 'PELVIS_CENTER', AppPalette.boneSpine),
    Bone('NOSE', 'C7_NECK', AppPalette.boneSpine),
    Bone('LEFT_SHOULDER', 'RIGHT_SHOULDER', AppPalette.boneTorso),
    Bone('LEFT_SHOULDER', 'LEFT_HIP', AppPalette.boneTorso),
    Bone('RIGHT_SHOULDER', 'RIGHT_HIP', AppPalette.boneTorso),
    Bone('LEFT_HIP', 'RIGHT_HIP', AppPalette.boneTorso),
    // arms
    Bone('LEFT_SHOULDER', 'LEFT_ELBOW', AppPalette.boneLeft),
    Bone('LEFT_ELBOW', 'LEFT_WRIST', AppPalette.boneLeft),
    Bone('RIGHT_SHOULDER', 'RIGHT_ELBOW', AppPalette.boneRight),
    Bone('RIGHT_ELBOW', 'RIGHT_WRIST', AppPalette.boneRight),
    // legs
    Bone('LEFT_HIP', 'LEFT_KNEE', AppPalette.boneLeft),
    Bone('LEFT_KNEE', 'LEFT_ANKLE', AppPalette.boneLeft),
    Bone('LEFT_ANKLE', 'LEFT_HEEL', AppPalette.boneLeft),
    Bone('LEFT_ANKLE', 'LEFT_FOOT_INDEX', AppPalette.boneLeft),
    Bone('LEFT_HEEL', 'LEFT_FOOT_INDEX', AppPalette.boneLeft),
    Bone('RIGHT_HIP', 'RIGHT_KNEE', AppPalette.boneRight),
    Bone('RIGHT_KNEE', 'RIGHT_ANKLE', AppPalette.boneRight),
    Bone('RIGHT_ANKLE', 'RIGHT_HEEL', AppPalette.boneRight),
    Bone('RIGHT_ANKLE', 'RIGHT_FOOT_INDEX', AppPalette.boneRight),
    Bone('RIGHT_HEEL', 'RIGHT_FOOT_INDEX', AppPalette.boneRight),
  ];

  static List<Bone> bonesFor(BodyMode mode) => switch (mode) {
        BodyMode.upperBody => upperBody,
        BodyMode.lowerBody => lowerBody,
        BodyMode.fullBody => fullBody,
      };

  // --------------------------------------------------------------------------
  // HANDS — ports MedicalGUIRenderer.HAND_FINGER_CHAINS
  // --------------------------------------------------------------------------

  static const List<List<String>> handFingerChains = <List<String>>[
    ['WRIST', 'THUMB_CMC', 'THUMB_MCP', 'THUMB_IP', 'THUMB_TIP'],
    ['WRIST', 'INDEX_FINGER_MCP', 'INDEX_FINGER_PIP', 'INDEX_FINGER_DIP', 'INDEX_FINGER_TIP'],
    ['WRIST', 'MIDDLE_FINGER_MCP', 'MIDDLE_FINGER_PIP', 'MIDDLE_FINGER_DIP', 'MIDDLE_FINGER_TIP'],
    ['WRIST', 'RING_FINGER_MCP', 'RING_FINGER_PIP', 'RING_FINGER_DIP', 'RING_FINGER_TIP'],
    ['WRIST', 'PINKY_MCP', 'PINKY_PIP', 'PINKY_DIP', 'PINKY_TIP'],
  ];

  // --------------------------------------------------------------------------
  // GONIOMETRIC ARCS — ports MedicalGUIRenderer.JOINT_ARC_DEFINITIONS
  // --------------------------------------------------------------------------

  static const List<JointArc> jointArcs = <JointArc>[
    JointArc('LEFT_SHOULDER', 'LEFT_HIP', 'LEFT_ELBOW',
        'shoulder_abduction_left', AppPalette.arc),
    JointArc('RIGHT_SHOULDER', 'RIGHT_HIP', 'RIGHT_ELBOW',
        'shoulder_abduction_right', AppPalette.arc),
    JointArc('LEFT_ELBOW', 'LEFT_SHOULDER', 'LEFT_WRIST',
        'elbow_flexion_left', AppPalette.boneLeft),
    JointArc('RIGHT_ELBOW', 'RIGHT_SHOULDER', 'RIGHT_WRIST',
        'elbow_flexion_right', AppPalette.boneRight),
    JointArc('LEFT_HIP', 'LEFT_SHOULDER', 'LEFT_KNEE',
        'hip_flexion_left', AppPalette.boneTorso),
    JointArc('RIGHT_HIP', 'RIGHT_SHOULDER', 'RIGHT_KNEE',
        'hip_flexion_right', AppPalette.boneTorso),
    JointArc('LEFT_KNEE', 'LEFT_HIP', 'LEFT_ANKLE',
        'knee_flexion_left', AppPalette.boneLeft),
    JointArc('RIGHT_KNEE', 'RIGHT_HIP', 'RIGHT_ANKLE',
        'knee_flexion_right', AppPalette.boneRight),
    JointArc('LEFT_ANKLE', 'LEFT_KNEE', 'LEFT_FOOT_INDEX',
        'ankle_flexion_left', AppPalette.boneLeft),
    JointArc('RIGHT_ANKLE', 'RIGHT_KNEE', 'RIGHT_FOOT_INDEX',
        'ankle_flexion_right', AppPalette.boneRight),
  ];

  /// Pivots belonging to each region, used to filter arcs and joint nodes by
  /// mode. Mirrors the `upper_joints` / `lower_joints` sets in
  /// `_draw_goniometer_arcs_and_badges`.
  static const Set<String> upperPivots = <String>{
    'LEFT_SHOULDER', 'RIGHT_SHOULDER',
    'LEFT_ELBOW', 'RIGHT_ELBOW',
    'LEFT_WRIST', 'RIGHT_WRIST',
  };

  static const Set<String> lowerPivots = <String>{
    'LEFT_HIP', 'RIGHT_HIP',
    'LEFT_KNEE', 'RIGHT_KNEE',
    'LEFT_ANKLE', 'RIGHT_ANKLE',
  };

  /// Joint nodes drawn per mode. Mirrors `_draw_joints`'s name sets.
  static const Set<String> upperJointNodes = <String>{
    'NOSE', 'C7_NECK',
    'LEFT_SHOULDER', 'RIGHT_SHOULDER',
    'LEFT_ELBOW', 'RIGHT_ELBOW',
    'LEFT_WRIST', 'RIGHT_WRIST',
    'PELVIS_CENTER',
    // The shoulder-to-hip rails and the pelvic girdle terminate here, so the
    // hips need nodes; without them the trunk's lower corners were bare.
    'LEFT_HIP', 'RIGHT_HIP',
  };

  static const Set<String> lowerJointNodes = <String>{
    'PELVIS_CENTER',
    'LEFT_HIP', 'RIGHT_HIP',
    'LEFT_KNEE', 'RIGHT_KNEE',
    'LEFT_ANKLE', 'RIGHT_ANKLE',
    'LEFT_HEEL', 'RIGHT_HEEL',
    'LEFT_FOOT_INDEX', 'RIGHT_FOOT_INDEX',
  };

  /// Joints drawn in full-body mode.
  ///
  /// The union of the two regions rather than "every landmark". MediaPipe returns
  /// ten facial points — both eye triples, both ears and both mouth corners —
  /// which cluster into an unreadable blob on the face and mean nothing
  /// clinically. NOSE alone anchors the head.
  ///
  /// Written out longhand rather than as `{...upperJointNodes, ...lowerJointNodes}`
  /// because PELVIS_CENTER belongs to both regions, and a const set literal
  /// cannot contain a duplicate — spreading them fails const evaluation.
  static const Set<String> fullBodyJointNodes = <String>{
    'NOSE', 'C7_NECK',
    'LEFT_SHOULDER', 'RIGHT_SHOULDER',
    'LEFT_ELBOW', 'RIGHT_ELBOW',
    'LEFT_WRIST', 'RIGHT_WRIST',
    'PELVIS_CENTER',
    'LEFT_HIP', 'RIGHT_HIP',
    'LEFT_KNEE', 'RIGHT_KNEE',
    'LEFT_ANKLE', 'RIGHT_ANKLE',
    'LEFT_HEEL', 'RIGHT_HEEL',
    'LEFT_FOOT_INDEX', 'RIGHT_FOOT_INDEX',
  };

  static Set<String> jointNodesFor(BodyMode mode) => switch (mode) {
        BodyMode.upperBody => upperJointNodes,
        BodyMode.lowerBody => lowerJointNodes,
        BodyMode.fullBody => fullBodyJointNodes,
      };

  // --------------------------------------------------------------------------
  // VISIBILITY GATES — the same numeric floors the OpenCV renderer used, so the
  // phone shows and hides exactly what the desktop app showed and hid.
  // --------------------------------------------------------------------------

  /// `_draw_bones` / `_draw_joints` require visibility >= 0.2.
  static const double boneVisibilityFloor = 0.2;

  /// `_draw_goniometer_arcs_and_badges` requires visibility >= 0.35.
  static const double arcVisibilityFloor = 0.35;

  /// Finger joints are only drawn when the wrist anchoring them is solidly
  /// tracked. At distance MediaPipe still emits 21 hand points, but they are
  /// guesses, and drawing them produces a tangle of lines around the hand that
  /// looks like a malfunction. Requiring a confident wrist suppresses that.
  static const double handVisibilityFloor = 0.55;
}

/// The clinical rows rendered in the HUD cards, mirroring
/// `_draw_selective_angles_hud`. Kept as data so the card widget stays dumb.
class AngleRow {
  const AngleRow(this.label, this.key, {this.normalMax});

  final String label;
  final String key;

  /// Top of the joint's normal range from `PhysiotherapyAngleEngine.NORMAL_RANGES`,
  /// used to tint the value as it approaches or exceeds end-range.
  final double? normalMax;
}

class HudGroup {
  const HudGroup(this.title, this.rows, this.tint);

  final String title;
  final List<AngleRow> rows;
  final Color tint;
}

class HudLayout {
  const HudLayout._();

  static const HudGroup leftUpper = HudGroup(
    'LEFT UPPER BODY',
    <AngleRow>[
      AngleRow('L Elbow Flexion', 'elbow_flexion_left', normalMax: 150),
      AngleRow('L Shoulder Abd', 'shoulder_abduction_left', normalMax: 180),
      AngleRow('L Shoulder Flex', 'shoulder_flexion_left'),
    ],
    AppPalette.boneLeft,
  );

  static const HudGroup rightUpper = HudGroup(
    'RIGHT UPPER BODY',
    <AngleRow>[
      AngleRow('R Elbow Flexion', 'elbow_flexion_right', normalMax: 150),
      AngleRow('R Shoulder Abd', 'shoulder_abduction_right', normalMax: 180),
      AngleRow('R Shoulder Flex', 'shoulder_flexion_right'),
    ],
    AppPalette.boneRight,
  );

  static const HudGroup leftLower = HudGroup(
    'LEFT LOWER BODY',
    <AngleRow>[
      AngleRow('L Hip Flexion', 'hip_flexion_left', normalMax: 125),
      AngleRow('L Knee Flexion', 'knee_flexion_left', normalMax: 140),
      AngleRow('L Ankle Angle', 'ankle_flexion_left'),
    ],
    AppPalette.boneLeft,
  );

  static const HudGroup rightLower = HudGroup(
    'RIGHT LOWER BODY',
    <AngleRow>[
      AngleRow('R Hip Flexion', 'hip_flexion_right', normalMax: 125),
      AngleRow('R Knee Flexion', 'knee_flexion_right', normalMax: 140),
      AngleRow('R Ankle Angle', 'ankle_flexion_right'),
    ],
    AppPalette.boneRight,
  );

  static const HudGroup posture = HudGroup(
    'POSTURE · PELVIS · BALANCE',
    <AngleRow>[
      AngleRow('Spine Tilt', 'trunk_posture', normalMax: 25),
      AngleRow('Pelvic Tilt', 'pelvic_tilt', normalMax: 20),
      AngleRow('Neck Inclination', 'neck_inclination', normalMax: 35),
      AngleRow('Leg Symmetry Δ', 'leg_symmetry_delta'),
      AngleRow('Body COG Shift', 'balance_offset'),
    ],
    AppPalette.boneTorso,
  );

  /// Groups shown for a given mode, matching `_draw_selective_angles_hud`'s
  /// `if body_mode in [...]` gates.
  static List<HudGroup> groupsFor(BodyMode mode) => switch (mode) {
        BodyMode.upperBody => <HudGroup>[leftUpper, rightUpper, posture],
        BodyMode.lowerBody => <HudGroup>[leftLower, rightLower, posture],
        BodyMode.fullBody => <HudGroup>[
            leftUpper,
            rightUpper,
            leftLower,
            rightLower,
            posture,
          ],
      };
}

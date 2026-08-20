import math
import numpy as np

class PhysiotherapyAngleEngine:
    """
    Standard Clinical Goniometric Joint Angle Calculation Engine.

    COORDINATE CONVENTION — read this before touching the geometry.

    MediaPipe hands back landmarks normalised as x = px/frame_width and
    y = px/frame_height. Those two axes therefore have DIFFERENT scales on any
    non-square frame, so an angle computed directly from (x, y) is not the angle
    a goniometer would read. Every vector built here is corrected back to square
    pixels by multiplying x by the frame aspect ratio, which is passed into
    compute_physio_metrics. A uniform scale does not change angles, so there is
    no need to know the absolute resolution.

    MediaPipe's `z` is DELIBERATELY NOT USED. It is a weakly-supervised depth
    guess from a single RGB frame and is by far the least reliable channel the
    model produces. This engine previously blended 0.60*angle_3d + 0.40*angle_2d
    using that z, which was measured against the app's own rendered skeleton and
    found to inflate elbow flexion by 20-35 degrees: a visibly straight arm read
    as 38 degrees of flexion, because the 3D term alone put the elbow at 119
    degrees. Frontal-plane angles from a single camera are measured in the image
    plane; out-of-plane motion is reported as "SIDE VIEW REQ" instead of being
    guessed at.

    Implements standard clinical physiotherapy / goniometry conventions:
    - Elbow Flexion: Standard 3-point angle (Shoulder -> Elbow -> Wrist). 0 deg (extended arm) to 150 deg (full flexion).
    - Shoulder Abduction (Frontal Plane): Angle between arm vector (Shoulder -> Elbow) and torso vertical reference axis (ShoulderCenter -> HipCenter).
      0 deg (arm at side along torso) to 90 deg (horizontal) to 180 deg (overhead). Returns None ('TRACKING...') if torso/arm landmarks are missing or low-confidence (<0.50).
    - Shoulder Flexion (Sagittal Plane): True flexion requires a side view. Front view displays 'SIDE VIEW REQ'.
    - Knee Flexion: 0 deg (straight standing leg) to 140 deg (full squat)
    - Hip Flexion: 0 deg (standing) to 125 deg (knee to chest)
    - Ankle Angle: 90 deg (neutral plantigrade standing foot)
    - Trunk Spine Tilt: 0 deg (upright vertical spine relative to gravity vector)
    """

    NORMAL_RANGES = {
        "shoulder_flexion_left": (0, 180),
        "shoulder_flexion_right": (0, 180),
        "shoulder_abduction_left": (0, 180),
        "shoulder_abduction_right": (0, 180),
        "elbow_flexion_left": (0, 150),
        "elbow_flexion_right": (0, 150),
        "hip_flexion_left": (0, 125),
        "hip_flexion_right": (0, 125),
        "knee_flexion_left": (0, 140),
        "knee_flexion_right": (0, 140),
        "ankle_flexion_left": (0, 50),
        "ankle_flexion_right": (0, 50),
        "neck_inclination": (0, 35),
        "trunk_posture": (0, 25),
        "pelvic_tilt": (0, 20)
    }

    def __init__(self, min_confidence=0.50, frame_aspect=1.0):
        self.min_confidence = min_confidence

        # Fallback used only when a caller omits the per-frame aspect ratio.
        # 1.0 means "treat the normalised space as already square", which
        # reproduces the old behaviour for callers that do not know the frame
        # size (offline dataset tooling). The live pipeline always passes the
        # real value.
        self.frame_aspect = float(frame_aspect) if frame_aspect else 1.0

    def _confident(self, *pts):
        """True when every landmark exists and clears the confidence floor."""
        for pt in pts:
            if not pt:
                return False
            if pt.get("visibility", 1.0) < self.min_confidence:
                return False
        return True

    def _vec(self, pt_from, pt_to, aspect):
        """
        Displacement in square-pixel proportions.

        x is multiplied by the aspect ratio to undo MediaPipe's per-axis
        normalisation; see the class docstring. z is intentionally absent.
        """
        return np.array([
            (pt_to["x"] - pt_from["x"]) * aspect,
            (pt_to["y"] - pt_from["y"]),
        ], dtype=np.float64)

    def _angle_between(self, u, v):
        """Unsigned angle between two vectors, in degrees, or None if degenerate."""
        nu = np.linalg.norm(u)
        nv = np.linalg.norm(v)
        if nu <= 1e-9 or nv <= 1e-9:
            return None
        cos_t = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_t)))

    def _calculate_joint_angle(self, pt_a, pt_b, pt_c, aspect):
        """
        Interior goniometric angle at pivot B, between BA and BC.

        Returns a float in [0.0, 180.0], or None when any of the three
        landmarks is missing or below the confidence floor (which the caller
        surfaces as "TRACKING..." rather than inventing a number).
        """
        if not self._confident(pt_a, pt_b, pt_c):
            return None

        angle = self._angle_between(self._vec(pt_b, pt_a, aspect),
                                    self._vec(pt_b, pt_c, aspect))
        return None if angle is None else float(round(angle, 1))

    def _tilt_from_vertical(self, pt_top, pt_bottom, aspect):
        """
        Deviation of a body segment from the image vertical, in degrees.

        Aspect-corrected for the same reason as the joint angles: on a 16:9
        frame the raw normalised form understates every tilt by roughly the
        aspect ratio, so a genuine 12 degree lean was reporting as about 7.
        """
        if not self._confident(pt_top, pt_bottom):
            return None
        dx = (pt_top["x"] - pt_bottom["x"]) * aspect
        dy = (pt_top["y"] - pt_bottom["y"])
        return float(round(math.degrees(math.atan2(abs(dx), abs(dy) + 1e-9)), 1))

    def _calculate_shoulder_abduction(self, sh_pt, elb_pt, l_sh_pt, r_sh_pt,
                                      l_hip_pt, r_hip_pt, aspect):
        """
        Frontal-plane shoulder abduction, measured against the anatomical torso
        axis (shoulder centre -> hip centre) rather than the image vertical, so
        a patient who leans does not gain or lose range spuriously.

        0 deg  = arm at the side, along the torso
        90 deg = arm horizontal
        180 deg = arm overhead

        Returns None if any required landmark is missing or low-confidence.
        """
        if not self._confident(sh_pt, elb_pt, l_sh_pt, r_sh_pt, l_hip_pt, r_hip_pt):
            return None

        sh_center = {
            "x": (l_sh_pt["x"] + r_sh_pt["x"]) / 2.0,
            "y": (l_sh_pt["y"] + r_sh_pt["y"]) / 2.0,
        }
        hip_center = {
            "x": (l_hip_pt["x"] + r_hip_pt["x"]) / 2.0,
            "y": (l_hip_pt["y"] + r_hip_pt["y"]) / 2.0,
        }

        torso_vec = self._vec(sh_center, hip_center, aspect)
        arm_vec = self._vec(sh_pt, elb_pt, aspect)

        angle = self._angle_between(arm_vec, torso_vec)
        if angle is None:
            return None
        return float(round(max(0.0, min(180.0, angle)), 1))

    def compute_physio_metrics(self, landmarks_dict, frame_aspect=None):
        """
        Computes full-body clinical physiotherapy joint angles and balance indicators.

        frame_aspect is frame_width / frame_height. It is required to undo
        MediaPipe's per-axis normalisation; see the class docstring. Callers that
        genuinely do not know the frame size may omit it, at the cost of the
        aspect distortion it exists to remove.

        Returns dict of named angle metrics, normal range statuses, and active exercise assessment.
        """
        if not landmarks_dict:
            return {}

        aspect = float(frame_aspect) if frame_aspect else self.frame_aspect

        def get_pt(name):
            return landmarks_dict.get(name, None)

        angles = {}

        # 1. Elbow Flexion (Left & Right): Standard 3-point angle (Shoulder -> Elbow -> Wrist)
        raw_elb_l = self._calculate_joint_angle(get_pt("LEFT_SHOULDER"), get_pt("LEFT_ELBOW"), get_pt("LEFT_WRIST"), aspect)
        raw_elb_r = self._calculate_joint_angle(get_pt("RIGHT_SHOULDER"), get_pt("RIGHT_ELBOW"), get_pt("RIGHT_WRIST"), aspect)
        angles["elbow_flexion_left"] = float(round(abs(180.0 - raw_elb_l), 1)) if raw_elb_l is not None else None
        angles["elbow_flexion_right"] = float(round(abs(180.0 - raw_elb_r), 1)) if raw_elb_r is not None else None

        angles["left_elbow_angle"] = angles["elbow_flexion_left"]
        angles["right_elbow_angle"] = angles["elbow_flexion_right"]

        # 2. Knee Flexion (Left & Right): Standard Goniometric Flexion (0 deg = straight leg, 140 deg = squat)
        raw_kn_l = self._calculate_joint_angle(get_pt("LEFT_HIP"), get_pt("LEFT_KNEE"), get_pt("LEFT_ANKLE"), aspect)
        raw_kn_r = self._calculate_joint_angle(get_pt("RIGHT_HIP"), get_pt("RIGHT_KNEE"), get_pt("RIGHT_ANKLE"), aspect)
        angles["knee_flexion_left"] = float(round(abs(180.0 - raw_kn_l), 1)) if raw_kn_l is not None else None
        angles["knee_flexion_right"] = float(round(abs(180.0 - raw_kn_r), 1)) if raw_kn_r is not None else None

        # 3. Hip Flexion (Left & Right): Trunk-Relative Flexion
        raw_hip_l = self._calculate_joint_angle(get_pt("LEFT_SHOULDER"), get_pt("LEFT_HIP"), get_pt("LEFT_KNEE"), aspect)
        raw_hip_r = self._calculate_joint_angle(get_pt("RIGHT_SHOULDER"), get_pt("RIGHT_HIP"), get_pt("RIGHT_KNEE"), aspect)
        angles["hip_flexion_left"] = float(round(abs(180.0 - raw_hip_l), 1)) if raw_hip_l is not None else None
        angles["hip_flexion_right"] = float(round(abs(180.0 - raw_hip_r), 1)) if raw_hip_r is not None else None

        # 4. Shoulder Abduction (Left & Right): Frontal Plane Abduction relative to Torso Vertical Axis
        l_sh = get_pt("LEFT_SHOULDER")
        r_sh = get_pt("RIGHT_SHOULDER")
        l_elb = get_pt("LEFT_ELBOW")
        r_elb = get_pt("RIGHT_ELBOW")
        l_hip = get_pt("LEFT_HIP")
        r_hip = get_pt("RIGHT_HIP")

        angles["shoulder_abduction_left"] = self._calculate_shoulder_abduction(l_sh, l_elb, l_sh, r_sh, l_hip, r_hip, aspect)
        angles["shoulder_abduction_right"] = self._calculate_shoulder_abduction(r_sh, r_elb, l_sh, r_sh, l_hip, r_hip, aspect)

        # Store Torso Angle & Landmark Confidence Scores for Debug Mode
        if l_sh and r_sh and l_hip and r_hip:
            sh_center = {"x": (l_sh["x"] + r_sh["x"]) / 2.0,
                         "y": (l_sh["y"] + r_sh["y"]) / 2.0}
            hip_center = {"x": (l_hip["x"] + r_hip["x"]) / 2.0,
                          "y": (l_hip["y"] + r_hip["y"]) / 2.0}
            angles["torso_angle"] = self._tilt_from_vertical(sh_center, hip_center, aspect)
        else:
            angles["torso_angle"] = None

        angles["l_sh_conf"] = l_sh.get("visibility", 0.0) if l_sh else 0.0
        angles["r_sh_conf"] = r_sh.get("visibility", 0.0) if r_sh else 0.0
        angles["l_elb_conf"] = l_elb.get("visibility", 0.0) if l_elb else 0.0
        angles["r_elb_conf"] = r_elb.get("visibility", 0.0) if r_elb else 0.0

        # 5. Shoulder Flexion (Left & Right): Front-view Sagittal Flexion limitation
        angles["shoulder_flexion_left"] = "SIDE VIEW REQ"
        angles["shoulder_flexion_right"] = "SIDE VIEW REQ"

        angles["left_shoulder_angle"] = angles["shoulder_abduction_left"]
        angles["right_shoulder_angle"] = angles["shoulder_abduction_right"]

        # 6. Ankle Angle (Left & Right): Interior Plantigrade Angle (90 deg = neutral standing foot)
        angles["ankle_flexion_left"] = self._calculate_joint_angle(get_pt("LEFT_KNEE"), get_pt("LEFT_ANKLE"), get_pt("LEFT_FOOT_INDEX"), aspect)
        angles["ankle_flexion_right"] = self._calculate_joint_angle(get_pt("RIGHT_KNEE"), get_pt("RIGHT_ANKLE"), get_pt("RIGHT_FOOT_INDEX"), aspect)

        # 7. Trunk Spine Posture / Inclination Angle
        pelvis = get_pt("PELVIS_CENTER")
        c7 = get_pt("C7_NECK")
        trunk_angle = self._tilt_from_vertical(c7, pelvis, aspect)
        if trunk_angle is not None:
            angles["trunk_posture"] = trunk_angle
            angles["torso_tilt_angle"] = angles["trunk_posture"]
        else:
            angles["trunk_posture"] = 0.0
            angles["torso_tilt_angle"] = 0.0

        # 8. Neck Tilt Angle
        nose = get_pt("NOSE")
        neck_angle = self._tilt_from_vertical(nose, c7, aspect)
        if neck_angle is not None:
            angles["neck_inclination"] = neck_angle
        else:
            angles["neck_inclination"] = 0.0

        # 9. Pelvic Tilt & Symmetry Metrics
        if l_hip and r_hip:
            # Tilt of the hip line away from horizontal, so aspect correction is
            # applied to the horizontal span rather than the vertical one.
            dy_pelvis = abs(l_hip["y"] - r_hip["y"])
            dx_pelvis = abs(l_hip["x"] - r_hip["x"]) * aspect + 1e-9
            angles["pelvic_tilt"] = float(round(math.degrees(math.atan2(dy_pelvis, dx_pelvis)), 1))
        else:
            angles["pelvic_tilt"] = 0.0

        # Leg Symmetry Delta & Center of Gravity (COG) Offset
        l_knee = angles["knee_flexion_left"] if isinstance(angles.get("knee_flexion_left"), (int, float)) else 0.0
        r_knee = angles["knee_flexion_right"] if isinstance(angles.get("knee_flexion_right"), (int, float)) else 0.0
        angles["leg_symmetry_delta"] = float(round(abs(l_knee - r_knee), 1))

        if l_hip and r_hip and "LEFT_ANKLE" in landmarks_dict and "RIGHT_ANKLE" in landmarks_dict:
            l_ank = landmarks_dict["LEFT_ANKLE"]
            r_ank = landmarks_dict["RIGHT_ANKLE"]
            hip_mid_x = (l_hip["x"] + r_hip["x"]) / 2.0
            ank_mid_x = (l_ank["x"] + r_ank["x"]) / 2.0
            cog_offset = abs(hip_mid_x - ank_mid_x) * aspect * 100.0
            angles["balance_offset"] = float(round(cog_offset, 1))
        else:
            angles["balance_offset"] = 0.0

        # Physiotherapy Movement Type Classifier
        angles["detected_exercise"] = self._detect_physio_exercise_type(angles)

        return angles

    def _detect_physio_exercise_type(self, angles):
        """Classifies active movement into physiotherapy category."""
        k_l = angles.get("knee_flexion_left", 0.0) or 0.0
        k_r = angles.get("knee_flexion_right", 0.0) or 0.0
        s_l = angles.get("shoulder_abduction_left", 0.0) or 0.0
        s_r = angles.get("shoulder_abduction_right", 0.0) or 0.0

        if isinstance(s_l, (int, float)) and isinstance(s_r, (int, float)):
            if s_l > 60 or s_r > 60:
                return "SHOULDER ABDUCTION REHAB"
        if isinstance(k_l, (int, float)) and isinstance(k_r, (int, float)):
            if k_l > 70 and k_r > 70:
                return "SQUAT MOBILITY ASSESS"
            elif (k_l > 60 and k_r < 30) or (k_r > 60 and k_l < 30):
                return "SINGLE LEG LUNGE"
        return "POSTURAL STABILITY"

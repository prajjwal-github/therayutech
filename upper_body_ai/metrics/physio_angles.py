import math
import numpy as np

class PhysiotherapyAngleEngine:
    """
    Standard Clinical Goniometric Joint Angle Calculation Engine.
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

    def __init__(self, min_confidence=0.50):
        self.min_confidence = min_confidence

    def _calculate_vector_angle_3d(self, pt_a, pt_b, pt_c):
        """
        Calculates 3-point interior vector angle (in degrees) at pivot B between BA and BC.
        Returns float angle in [0.0, 180.0] or None if insufficient confidence (<0.50).
        """
        if not pt_a or not pt_b or not pt_c:
            return None

        vis_a = pt_a.get("visibility", 1.0)
        vis_b = pt_b.get("visibility", 1.0)
        vis_c = pt_c.get("visibility", 1.0)

        if vis_a < self.min_confidence or vis_b < self.min_confidence or vis_c < self.min_confidence:
            return None

        # 3D Spatial Vector BA & BC
        u3d = np.array([pt_a["x"] - pt_b["x"], pt_a["y"] - pt_b["y"], pt_a.get("z", 0.0) - pt_b.get("z", 0.0)], dtype=np.float64)
        v3d = np.array([pt_c["x"] - pt_b["x"], pt_c["y"] - pt_b["y"], pt_c.get("z", 0.0) - pt_b.get("z", 0.0)], dtype=np.float64)

        norm_u3d = np.linalg.norm(u3d)
        norm_v3d = np.linalg.norm(v3d)
        if norm_u3d <= 1e-6 or norm_v3d <= 1e-6:
            return None

        dot_3d = np.clip(np.dot(u3d, v3d) / (norm_u3d * norm_v3d), -1.0, 1.0)
        angle_3d = float(np.degrees(np.arccos(dot_3d)))

        # 2D Image Plane Projection Vector
        u2d = np.array([pt_a["x"] - pt_b["x"], pt_a["y"] - pt_b["y"]], dtype=np.float64)
        v2d = np.array([pt_c["x"] - pt_b["x"], pt_c["y"] - pt_b["y"]], dtype=np.float64)
        norm_u2d = np.linalg.norm(u2d)
        norm_v2d = np.linalg.norm(v2d)

        if norm_u2d > 1e-6 and norm_v2d > 1e-6:
            dot_2d = np.clip(np.dot(u2d, v2d) / (norm_u2d * norm_v2d), -1.0, 1.0)
            angle_2d = float(np.degrees(np.arccos(dot_2d)))
            return float(round(0.60 * angle_3d + 0.40 * angle_2d, 1))

        return float(round(angle_3d, 1))

    def _calculate_shoulder_abduction(self, sh_pt, elb_pt, l_sh_pt, r_sh_pt, l_hip_pt, r_hip_pt):
        """
        Calculates anatomical Shoulder Abduction in the frontal plane.
        Uses the anatomical Torso Vertical Axis (shoulder_center -> hip_center).
        Arm at side along torso = 0 deg, arm horizontal = 90 deg, arm overhead = 180 deg.
        Returns None if required landmarks are missing or low-confidence (<0.50).
        """
        if not sh_pt or not elb_pt or not l_sh_pt or not r_sh_pt or not l_hip_pt or not r_hip_pt:
            return None

        vis_sh = sh_pt.get("visibility", 1.0)
        vis_elb = elb_pt.get("visibility", 1.0)
        vis_l_sh = l_sh_pt.get("visibility", 1.0)
        vis_r_sh = r_sh_pt.get("visibility", 1.0)
        vis_l_hip = l_hip_pt.get("visibility", 1.0)
        vis_r_hip = r_hip_pt.get("visibility", 1.0)

        # Strict Confidence Floor (vis >= 0.50) across shoulders, elbow, and hips
        if (vis_sh < self.min_confidence or vis_elb < self.min_confidence or
            vis_l_sh < self.min_confidence or vis_r_sh < self.min_confidence or
            vis_l_hip < self.min_confidence or vis_r_hip < self.min_confidence):
            return None

        # Construct Torso Vertical Reference Vector (Shoulder Center -> Hip Center)
        sh_center_x = (l_sh_pt["x"] + r_sh_pt["x"]) / 2.0
        sh_center_y = (l_sh_pt["y"] + r_sh_pt["y"]) / 2.0
        sh_center_z = (l_sh_pt.get("z", 0.0) + r_sh_pt.get("z", 0.0)) / 2.0

        hip_center_x = (l_hip_pt["x"] + r_hip_pt["x"]) / 2.0
        hip_center_y = (l_hip_pt["y"] + r_hip_pt["y"]) / 2.0
        hip_center_z = (l_hip_pt.get("z", 0.0) + r_hip_pt.get("z", 0.0)) / 2.0

        torso_vec = np.array([
            hip_center_x - sh_center_x,
            hip_center_y - sh_center_y,
            hip_center_z - sh_center_z
        ], dtype=np.float64)

        # Arm Vector (Shoulder -> Elbow)
        arm_vec = np.array([
            elb_pt["x"] - sh_pt["x"],
            elb_pt["y"] - sh_pt["y"],
            elb_pt.get("z", 0.0) - sh_pt.get("z", 0.0)
        ], dtype=np.float64)

        norm_torso = np.linalg.norm(torso_vec)
        norm_arm = np.linalg.norm(arm_vec)

        if norm_torso <= 1e-6 or norm_arm <= 1e-6:
            return None

        dot_val = np.clip(np.dot(arm_vec, torso_vec) / (norm_torso * norm_arm), -1.0, 1.0)
        abduction_angle = float(np.degrees(np.arccos(dot_val)))

        # Sanity check range [0.0, 180.0]
        return float(round(max(0.0, min(180.0, abduction_angle)), 1))

    def compute_physio_metrics(self, landmarks_dict):
        """
        Computes full-body clinical physiotherapy joint angles and balance indicators.
        Returns dict of named angle metrics, normal range statuses, and active exercise assessment.
        """
        if not landmarks_dict:
            return {}

        def get_pt(name):
            return landmarks_dict.get(name, None)

        angles = {}

        # 1. Elbow Flexion (Left & Right): Standard 3-point angle (Shoulder -> Elbow -> Wrist)
        raw_elb_l = self._calculate_vector_angle_3d(get_pt("LEFT_SHOULDER"), get_pt("LEFT_ELBOW"), get_pt("LEFT_WRIST"))
        raw_elb_r = self._calculate_vector_angle_3d(get_pt("RIGHT_SHOULDER"), get_pt("RIGHT_ELBOW"), get_pt("RIGHT_WRIST"))
        angles["elbow_flexion_left"] = float(round(abs(180.0 - raw_elb_l), 1)) if raw_elb_l is not None else None
        angles["elbow_flexion_right"] = float(round(abs(180.0 - raw_elb_r), 1)) if raw_elb_r is not None else None

        angles["left_elbow_angle"] = angles["elbow_flexion_left"]
        angles["right_elbow_angle"] = angles["elbow_flexion_right"]

        # 2. Knee Flexion (Left & Right): Standard Goniometric Flexion (0 deg = straight leg, 140 deg = squat)
        raw_kn_l = self._calculate_vector_angle_3d(get_pt("LEFT_HIP"), get_pt("LEFT_KNEE"), get_pt("LEFT_ANKLE"))
        raw_kn_r = self._calculate_vector_angle_3d(get_pt("RIGHT_HIP"), get_pt("RIGHT_KNEE"), get_pt("RIGHT_ANKLE"))
        angles["knee_flexion_left"] = float(round(abs(180.0 - raw_kn_l), 1)) if raw_kn_l is not None else None
        angles["knee_flexion_right"] = float(round(abs(180.0 - raw_kn_r), 1)) if raw_kn_r is not None else None

        # 3. Hip Flexion (Left & Right): Trunk-Relative Flexion
        raw_hip_l = self._calculate_vector_angle_3d(get_pt("LEFT_SHOULDER"), get_pt("LEFT_HIP"), get_pt("LEFT_KNEE"))
        raw_hip_r = self._calculate_vector_angle_3d(get_pt("RIGHT_SHOULDER"), get_pt("RIGHT_HIP"), get_pt("RIGHT_KNEE"))
        angles["hip_flexion_left"] = float(round(abs(180.0 - raw_hip_l), 1)) if raw_hip_l is not None else None
        angles["hip_flexion_right"] = float(round(abs(180.0 - raw_hip_r), 1)) if raw_hip_r is not None else None

        # 4. Shoulder Abduction (Left & Right): Frontal Plane Abduction relative to Torso Vertical Axis
        l_sh = get_pt("LEFT_SHOULDER")
        r_sh = get_pt("RIGHT_SHOULDER")
        l_elb = get_pt("LEFT_ELBOW")
        r_elb = get_pt("RIGHT_ELBOW")
        l_hip = get_pt("LEFT_HIP")
        r_hip = get_pt("RIGHT_HIP")

        angles["shoulder_abduction_left"] = self._calculate_shoulder_abduction(l_sh, l_elb, l_sh, r_sh, l_hip, r_hip)
        angles["shoulder_abduction_right"] = self._calculate_shoulder_abduction(r_sh, r_elb, l_sh, r_sh, l_hip, r_hip)

        # Store Torso Angle & Landmark Confidence Scores for Debug Mode
        if l_sh and r_sh and l_hip and r_hip:
            sh_center_x = (l_sh["x"] + r_sh["x"]) / 2.0
            sh_center_y = (l_sh["y"] + r_sh["y"]) / 2.0
            hip_center_x = (l_hip["x"] + r_hip["x"]) / 2.0
            hip_center_y = (l_hip["y"] + r_hip["y"]) / 2.0
            dx_t = hip_center_x - sh_center_x
            dy_t = hip_center_y - sh_center_y
            angles["torso_angle"] = float(round(math.degrees(math.atan2(abs(dx_t), abs(dy_t) + 1e-6)), 1))
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
        angles["ankle_flexion_left"] = self._calculate_vector_angle_3d(get_pt("LEFT_KNEE"), get_pt("LEFT_ANKLE"), get_pt("LEFT_FOOT_INDEX"))
        angles["ankle_flexion_right"] = self._calculate_vector_angle_3d(get_pt("RIGHT_KNEE"), get_pt("RIGHT_ANKLE"), get_pt("RIGHT_FOOT_INDEX"))

        # 7. Trunk Spine Posture / Inclination Angle
        pelvis = get_pt("PELVIS_CENTER")
        c7 = get_pt("C7_NECK")
        if pelvis and c7 and pelvis.get("visibility", 1.0) >= self.min_confidence and c7.get("visibility", 1.0) >= self.min_confidence:
            dx = c7["x"] - pelvis["x"]
            dy = c7["y"] - pelvis["y"]
            trunk_angle = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))
            angles["trunk_posture"] = float(round(trunk_angle, 1))
            angles["torso_tilt_angle"] = angles["trunk_posture"]
        else:
            angles["trunk_posture"] = 0.0
            angles["torso_tilt_angle"] = 0.0

        # 8. Neck Tilt Angle
        nose = get_pt("NOSE")
        if nose and c7 and nose.get("visibility", 1.0) >= self.min_confidence and c7.get("visibility", 1.0) >= self.min_confidence:
            dx = nose["x"] - c7["x"]
            dy = nose["y"] - c7["y"]
            neck_angle = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))
            angles["neck_inclination"] = float(round(neck_angle, 1))
        else:
            angles["neck_inclination"] = 0.0

        # 9. Pelvic Tilt & Symmetry Metrics
        if l_hip and r_hip:
            dy_pelvis = abs(l_hip["y"] - r_hip["y"])
            dx_pelvis = abs(l_hip["x"] - r_hip["x"]) + 1e-6
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
            cog_offset = abs(hip_mid_x - ank_mid_x) * 100.0
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

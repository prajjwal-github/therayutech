import math
import numpy as np

class AngleCalculator:
    """
    Upper-Body Joint Angle & Geometric Feature Engine.
    Calculates 3D interior vector angles and body alignment metrics:
    - Left/Right Elbow Angle (Flexion/Extension)
    - Left/Right Shoulder Angle (Elevation/Abduction)
    - Torso Orientation & Spine Tilt Angle
    - Arm Cross-Body Distances
    - Left/Right Bilateral Symmetry Delta
    """

    def __init__(self):
        pass

    @staticmethod
    def calculate_3d_angle(a, b, c):
        """
        Calculates interior angle (in degrees) at vertex B given 3 points A, B, C in 2D or 3D.
        Angle range: [0°, 180°].
        """
        a = np.array(a, dtype=np.float64)
        b = np.array(b, dtype=np.float64)
        c = np.array(c, dtype=np.float64)

        ba = a - b
        bc = c - b

        norm_ba = np.linalg.norm(ba)
        norm_bc = np.linalg.norm(bc)

        if norm_ba <= 1e-6 or norm_bc <= 1e-6:
            return 0.0

        cosine_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
        cosine_angle = np.clip(cosine_angle, -1.0, 1.0)

        angle_rad = np.arccos(cosine_angle)
        return float(np.degrees(angle_rad))

    def compute_all_angles(self, landmarks_dict):
        """
        Computes comprehensive suite of upper body angles and geometric metrics.
        Returns dictionary of named angle metrics (in degrees or normalized ratios).
        """
        if not landmarks_dict:
            return {}

        def get_pt(name):
            if name in landmarks_dict:
                lm = landmarks_dict[name]
                return [lm["x"], lm["y"], lm.get("z", 0.0)]
            return [0.0, 0.0, 0.0]

        ls = get_pt("LEFT_SHOULDER")
        rs = get_pt("RIGHT_SHOULDER")
        le = get_pt("LEFT_ELBOW")
        re = get_pt("RIGHT_ELBOW")
        lw = get_pt("LEFT_WRIST")
        rw = get_pt("RIGHT_WRIST")
        lh = get_pt("LEFT_HIP")
        rh = get_pt("RIGHT_HIP")
        nose = get_pt("NOSE")

        # 1. Elbow Angles (Shoulder -> Elbow -> Wrist)
        left_elbow_angle = self.calculate_3d_angle(ls, le, lw)
        right_elbow_angle = self.calculate_3d_angle(rs, re, rw)

        # 2. Shoulder Elevation Angles (Elbow -> Shoulder -> Hip)
        left_shoulder_angle = self.calculate_3d_angle(le, ls, lh)
        right_shoulder_angle = self.calculate_3d_angle(re, rs, rh)

        # 3. Torso / Spine Alignment Angle
        shoulder_center = np.array([(ls[0]+rs[0])/2, (ls[1]+rs[1])/2, (ls[2]+rs[2])/2])
        hip_center = np.array([(lh[0]+rh[0])/2, (lh[1]+rh[1])/2, (lh[2]+rh[2])/2])
        spine_vector = shoulder_center - hip_center
        vertical_vector = np.array([0.0, -1.0, 0.0]) # Y points down in image coords
        
        spine_norm = np.linalg.norm(spine_vector)
        if spine_norm > 1e-6:
            cos_tilt = np.dot(spine_vector, vertical_vector) / spine_norm
            torso_tilt_angle = float(np.degrees(np.arccos(np.clip(cos_tilt, -1.0, 1.0))))
        else:
            torso_tilt_angle = 0.0

        # 4. Cross-Body Radial Distances (wrist relative to opposite shoulder)
        left_wrist_cross_dist = float(np.linalg.norm(np.array(lw) - np.array(rs)))
        right_wrist_cross_dist = float(np.linalg.norm(np.array(rw) - np.array(ls)))

        # 5. Left/Right Symmetry Delta
        elbow_symmetry_delta = abs(left_elbow_angle - right_elbow_angle)
        shoulder_symmetry_delta = abs(left_shoulder_angle - right_shoulder_angle)

        return {
            "left_elbow_angle": round(left_elbow_angle, 2),
            "right_elbow_angle": round(right_elbow_angle, 2),
            "left_shoulder_angle": round(left_shoulder_angle, 2),
            "right_shoulder_angle": round(right_shoulder_angle, 2),
            "torso_tilt_angle": round(torso_tilt_angle, 2),
            "left_wrist_cross_dist": round(left_wrist_cross_dist, 4),
            "right_wrist_cross_dist": round(right_wrist_cross_dist, 4),
            "elbow_symmetry_delta": round(elbow_symmetry_delta, 2),
            "shoulder_symmetry_delta": round(shoulder_symmetry_delta, 2)
        }

    def get_angle_feature_vector(self, landmarks_dict):
        """Returns 1D array of calculated numerical angles for ML feature vector embedding."""
        angles = self.compute_all_angles(landmarks_dict)
        if not angles:
            return np.zeros(9, dtype=np.float32)
        return np.array([
            angles["left_elbow_angle"],
            angles["right_elbow_angle"],
            angles["left_shoulder_angle"],
            angles["right_shoulder_angle"],
            angles["torso_tilt_angle"],
            angles["left_wrist_cross_dist"],
            angles["right_wrist_cross_dist"],
            angles["elbow_symmetry_delta"],
            angles["shoulder_symmetry_delta"]
        ], dtype=np.float32)

import numpy as np

class LandmarkNormalizer:
    """
    Scale and Camera-Distance Invariant Full Body Landmark Normalizer.
    Transforms raw coordinates (X, Y, Z) to body-relative coordinates:
    1. Shoulder Center Anchor: ShoulderCenter = (LeftShoulder + RightShoulder) / 2
    2. Pelvic Center Anchor: HipCenter = (LeftHip + RightHip) / 2
    3. Full Body Scale Factor S = (||ShoulderCenter - HipCenter|| + ||LeftShoulder - RightShoulder|| + ||HipCenter - AnkleCenter||) / 3.0
    4. Normalized Coordinate P_norm = (P_raw - ShoulderCenter) / S
    """

    TARGET_LANDMARKS = [
        "NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_EAR", "RIGHT_EAR",
        "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
        "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY",
        "LEFT_INDEX", "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB",
        "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
        "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL",
        "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX", "C7_NECK", "PELVIS_CENTER"
    ]

    def __init__(self, target_landmarks=None):
        if target_landmarks is not None:
            self.target_landmarks = target_landmarks
        else:
            self.target_landmarks = self.TARGET_LANDMARKS

    def compute_anchors_and_scale(self, landmarks_dict):
        """Computes ShoulderCenter, HipCenter, and Body Scale Factor S."""
        if not landmarks_dict or "LEFT_SHOULDER" not in landmarks_dict or "RIGHT_SHOULDER" not in landmarks_dict:
            return np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0]), 1.0

        ls = landmarks_dict["LEFT_SHOULDER"]
        rs = landmarks_dict["RIGHT_SHOULDER"]

        shoulder_center = np.array([
            (ls["x"] + rs["x"]) / 2.0,
            (ls["y"] + rs["y"]) / 2.0,
            (ls.get("z", 0.0) + rs.get("z", 0.0)) / 2.0
        ], dtype=np.float64)

        if "LEFT_HIP" in landmarks_dict and "RIGHT_HIP" in landmarks_dict:
            lh = landmarks_dict["LEFT_HIP"]
            rh = landmarks_dict["RIGHT_HIP"]
            hip_center = np.array([
                (lh["x"] + rh["x"]) / 2.0,
                (lh["y"] + rh["y"]) / 2.0,
                (lh.get("z", 0.0) + rh.get("z", 0.0)) / 2.0
            ], dtype=np.float64)
        else:
            hip_center = shoulder_center + np.array([0.0, 0.4, 0.0])

        shoulder_width = np.linalg.norm(
            np.array([ls["x"], ls["y"], ls.get("z", 0.0)]) - 
            np.array([rs["x"], rs["y"], rs.get("z", 0.0)])
        )

        torso_length = np.linalg.norm(shoulder_center - hip_center)

        ankle_length = 0.4
        if "LEFT_ANKLE" in landmarks_dict and "RIGHT_ANKLE" in landmarks_dict:
            la = landmarks_dict["LEFT_ANKLE"]
            ra = landmarks_dict["RIGHT_ANKLE"]
            ankle_center = np.array([(la["x"] + ra["x"])/2.0, (la["y"] + ra["y"])/2.0, (la.get("z", 0.0) + ra.get("z", 0.0))/2.0])
            ankle_length = np.linalg.norm(hip_center - ankle_center)

        scale = (torso_length + shoulder_width + ankle_length) / 3.0
        if scale <= 1e-6:
            scale = 1.0

        return shoulder_center, hip_center, float(scale)

    def normalize_landmarks(self, landmarks_dict):
        """Compatibility wrapper for annotate_image."""
        sh_center, hip_center, scale = self.compute_anchors_and_scale(landmarks_dict)
        norm_dict, _ = self.normalize(landmarks_dict)
        return norm_dict, scale, sh_center

    def normalize(self, landmarks_dict):
        """
        Normalizes landmarks_dict coordinates to body-relative coordinates.
        Returns dict of normalized landmark coordinates and flattened feature vector array.
        """
        if not landmarks_dict:
            return {}, np.zeros(len(self.target_landmarks) * 4, dtype=np.float32)

        sh_center, hip_center, scale = self.compute_anchors_and_scale(landmarks_dict)

        normalized_dict = {}
        feature_vector = []

        for name in self.target_landmarks:
            if name in landmarks_dict:
                lm = landmarks_dict[name]
                nx = (lm["x"] - sh_center[0]) / scale
                ny = (lm["y"] - sh_center[1]) / scale
                nz = (lm.get("z", 0.0) - sh_center[2]) / scale
                vis = lm.get("visibility", 1.0)

                normalized_dict[name] = {
                    "x_norm": float(nx),
                    "y_norm": float(ny),
                    "z_norm": float(nz),
                    "visibility": float(vis)
                }

                feature_vector.extend([nx, ny, nz, vis])
            else:
                normalized_dict[name] = {"x_norm": 0.0, "y_norm": 0.0, "z_norm": 0.0, "visibility": 0.0}
                feature_vector.extend([0.0, 0.0, 0.0, 0.0])

        return normalized_dict, np.array(feature_vector, dtype=np.float32)

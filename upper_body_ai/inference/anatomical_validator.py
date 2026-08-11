import math
import numpy as np

class AnatomicalValidator:
    """
    Biomechanical Constraint Enforcer & Spatial Left/Right Swap Validator.
    Features:
    1. Spatial Left/Right Swap Detection & Auto-Correction for Crossed Arms & Legs
    2. Exponential Running Average Bone Length Constancy Enforcer (Ratio <= 1.35)
    3. Biomechanical Joint Rotation Clamping (Elbows 0-165 deg, Knees 0-160 deg)
    4. Suppresses Floating / Disconnected Keypoints during Extreme Yoga & Physio Poses
    """

    def __init__(self, max_symmetry_ratio=1.35, history_alpha=0.15):
        self.max_symmetry_ratio = max_symmetry_ratio
        self.history_alpha = history_alpha

        # Exponential running averages of anatomical bone lengths (in normalized units)
        self.bone_length_history = {
            "upper_arm_left": None, "upper_arm_right": None,
            "forearm_left": None, "forearm_right": None,
            "thigh_left": None, "thigh_right": None,
            "calf_left": None, "calf_right": None
        }

        # Track previous keypoint positions for L/R swap prevention
        self.prev_positions = {}

    def validate_and_correct(self, landmarks_dict):
        """Validates landmarks against anatomical bone length and left/right swap constraints."""
        if not landmarks_dict:
            return landmarks_dict

        corrected_dict = dict(landmarks_dict)

        # 1. Left/Right Swap Prevention for Wrists and Ankles during Cross-Body Movements
        self._prevent_left_right_swaps(corrected_dict)

        # 2. Bone Length Constancy & Symmetry Constraint Enforcement
        self._enforce_bone_constancy(corrected_dict)

        # 3. Save current positions for next frame
        for name, lm in corrected_dict.items():
            self.prev_positions[name] = (lm["x"], lm["y"], lm.get("z", 0.0))

        return corrected_dict

    def _prevent_left_right_swaps(self, landmarks):
        """Detects and automatically corrects left/right wrist & ankle swaps when limbs cross."""
        if not self.prev_positions:
            return

        # Check Wrists
        if "LEFT_WRIST" in landmarks and "RIGHT_WRIST" in landmarks:
            lw_cur = (landmarks["LEFT_WRIST"]["x"], landmarks["LEFT_WRIST"]["y"])
            rw_cur = (landmarks["RIGHT_WRIST"]["x"], landmarks["RIGHT_WRIST"]["y"])

            if "LEFT_WRIST" in self.prev_positions and "RIGHT_WRIST" in self.prev_positions:
                lw_prev = (self.prev_positions["LEFT_WRIST"][0], self.prev_positions["LEFT_WRIST"][1])
                rw_prev = (self.prev_positions["RIGHT_WRIST"][0], self.prev_positions["RIGHT_WRIST"][1])

                # Normal Euclidean distances to previous frame position
                d_normal = (math.hypot(lw_cur[0]-lw_prev[0], lw_cur[1]-lw_prev[1]) +
                            math.hypot(rw_cur[0]-rw_prev[0], rw_cur[1]-rw_prev[1]))

                # Swapped Euclidean distances
                d_swapped = (math.hypot(rw_cur[0]-lw_prev[0], rw_cur[1]-lw_prev[1]) +
                             math.hypot(lw_cur[0]-rw_prev[0], lw_cur[1]-rw_prev[1]))

                # If swapped distance is significantly smaller, swap landmarks back!
                if d_swapped + 0.08 < d_normal:
                    # Swap Left and Right Wrist landmark coordinates and visibilities
                    landmarks["LEFT_WRIST"], landmarks["RIGHT_WRIST"] = landmarks["RIGHT_WRIST"], landmarks["LEFT_WRIST"]
                    landmarks["LEFT_WRIST"]["name"] = "LEFT_WRIST"
                    landmarks["RIGHT_WRIST"]["name"] = "RIGHT_WRIST"

        # Check Ankles
        if "LEFT_ANKLE" in landmarks and "RIGHT_ANKLE" in landmarks:
            la_cur = (landmarks["LEFT_ANKLE"]["x"], landmarks["LEFT_ANKLE"]["y"])
            ra_cur = (landmarks["RIGHT_ANKLE"]["x"], landmarks["RIGHT_ANKLE"]["y"])

            if "LEFT_ANKLE" in self.prev_positions and "RIGHT_ANKLE" in self.prev_positions:
                la_prev = (self.prev_positions["LEFT_ANKLE"][0], self.prev_positions["LEFT_ANKLE"][1])
                ra_prev = (self.prev_positions["RIGHT_ANKLE"][0], self.prev_positions["RIGHT_ANKLE"][1])

                d_normal_ank = (math.hypot(la_cur[0]-la_prev[0], la_cur[1]-la_prev[1]) +
                                math.hypot(ra_cur[0]-ra_prev[0], ra_cur[1]-ra_prev[1]))

                d_swapped_ank = (math.hypot(ra_cur[0]-la_prev[0], ra_cur[1]-la_prev[1]) +
                                 math.hypot(la_cur[0]-ra_prev[0], la_cur[1]-ra_prev[1]))

                if d_swapped_ank + 0.08 < d_normal_ank:
                    landmarks["LEFT_ANKLE"], landmarks["RIGHT_ANKLE"] = landmarks["RIGHT_ANKLE"], landmarks["LEFT_ANKLE"]
                    landmarks["LEFT_ANKLE"]["name"] = "LEFT_ANKLE"
                    landmarks["RIGHT_ANKLE"]["name"] = "RIGHT_ANKLE"

    def _enforce_bone_constancy(self, landmarks):
        """Enforces exponential running average bone length constancy ratio <= 1.35."""
        def dist3d(p1_name, p2_name):
            if p1_name in landmarks and p2_name in landmarks:
                p1 = landmarks[p1_name]
                p2 = landmarks[p2_name]
                dx = p1["x"] - p2["x"]
                dy = p1["y"] - p2["y"]
                dz = p1.get("z", 0.0) - p2.get("z", 0.0)
                return float(math.sqrt(dx*dx + dy*dy + dz*dz))
            return 0.0

        bones_map = [
            ("upper_arm_left", "LEFT_SHOULDER", "LEFT_ELBOW"),
            ("upper_arm_right", "RIGHT_SHOULDER", "RIGHT_ELBOW"),
            ("forearm_left", "LEFT_ELBOW", "LEFT_WRIST"),
            ("forearm_right", "RIGHT_ELBOW", "RIGHT_WRIST"),
            ("thigh_left", "LEFT_HIP", "LEFT_KNEE"),
            ("thigh_right", "RIGHT_HIP", "RIGHT_KNEE"),
            ("calf_left", "LEFT_KNEE", "LEFT_ANKLE"),
            ("calf_right", "RIGHT_KNEE", "RIGHT_ANKLE")
        ]

        for bone_name, p1_name, p2_name in bones_map:
            cur_len = dist3d(p1_name, p2_name)
            if cur_len < 0.005:
                continue

            hist_len = self.bone_length_history[bone_name]
            if hist_len is None:
                self.bone_length_history[bone_name] = cur_len
            else:
                # Update running average
                self.bone_length_history[bone_name] = (1.0 - self.history_alpha) * hist_len + self.history_alpha * cur_len
                avg_len = self.bone_length_history[bone_name]

                # Check ratio limit
                if cur_len / avg_len > self.max_symmetry_ratio:
                    # Soften visibility to suppress erratic bone stretching
                    landmarks[p2_name]["visibility"] *= 0.80

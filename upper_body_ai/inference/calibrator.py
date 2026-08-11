import math
import numpy as np

class ConfidenceCalibrator:
    """
    Multi-Factor Confidence Fusion & Temporal Velocity Predictor.
    Features:
    1. Multi-Factor Confidence Fusion (Raw Visibility 0.50 + Symmetry 0.25 + Momentum 0.25)
    2. Temporal Momentum & Velocity Extrapolation during Self-Occlusion
       (Extrapolates position during forward bends, twists, or floor poses when visibility < 0.35)
    3. Prevents confidence collapse and skeleton line disconnection
    """

    def __init__(self, occlusion_floor=0.45, max_history=10):
        self.occlusion_floor = occlusion_floor
        self.max_history = max_history

        # Keypoint position and velocity history per landmark name
        # Format: {name: deque([(x, y, z), ...])}
        self.history = {}
        self.velocities = {}

    def calibrate(self, landmarks_dict):
        """Calibrates landmark visibilities and predicts occluded keypoint positions."""
        if not landmarks_dict:
            return landmarks_dict

        calibrated_dict = {}

        for name, lm in landmarks_dict.items():
            lm_copy = dict(lm)
            raw_vis = lm_copy.get("visibility", 1.0)
            x, y, z = lm_copy["x"], lm_copy["y"], lm_copy.get("z", 0.0)

            # Update position history & velocity vector
            if name not in self.history:
                self.history[name] = [(x, y, z)]
                self.velocities[name] = (0.0, 0.0, 0.0)
            else:
                prev_x, prev_y, prev_z = self.history[name][-1]
                vx = x - prev_x
                vy = y - prev_y
                vz = z - prev_z

                # Smooth velocity vector with exponential momentum
                old_vx, old_vy, old_vz = self.velocities[name]
                smooth_vx = 0.7 * old_vx + 0.3 * vx
                smooth_vy = 0.7 * old_vy + 0.3 * vy
                smooth_vz = 0.7 * old_vz + 0.3 * vz
                self.velocities[name] = (smooth_vx, smooth_vy, smooth_vz)

                self.history[name].append((x, y, z))
                if len(self.history[name]) > self.max_history:
                    self.history[name].pop(0)

            # Temporal Occlusion Recovery Extrapolation
            if raw_vis < 0.35 and len(self.history[name]) >= 2:
                vx, vy, vz = self.velocities[name]
                # Extrapolate position using velocity vector
                ext_x = self.history[name][-2][0] + vx * 0.85
                ext_y = self.history[name][-2][1] + vy * 0.85
                ext_z = self.history[name][-2][2] + vz * 0.85

                lm_copy["x"] = float(ext_x)
                lm_copy["y"] = float(ext_y)
                lm_copy["z"] = float(ext_z)

                # Set confidence floor to prevent skeleton line collapse
                lm_copy["visibility"] = float(max(raw_vis, self.occlusion_floor))
                lm_copy["is_visible"] = True
            else:
                # Multi-Factor Confidence Fusion
                sym_score = self._compute_symmetry_score(name, raw_vis, landmarks_dict)
                momentum_score = 0.95 if math.hypot(self.velocities[name][0], self.velocities[name][1]) < 0.05 else 0.85
                fused_conf = (0.50 * raw_vis) + (0.25 * sym_score) + (0.25 * momentum_score)

                lm_copy["visibility"] = float(np.clip(fused_conf, 0.0, 1.0))
                lm_copy["is_visible"] = bool(lm_copy["visibility"] >= 0.25)

            calibrated_dict[name] = lm_copy

        return calibrated_dict

    def _compute_symmetry_score(self, name, raw_vis, landmarks):
        """Computes left/right limb symmetry confidence score."""
        opposite_map = {
            "LEFT_SHOULDER": "RIGHT_SHOULDER", "RIGHT_SHOULDER": "LEFT_SHOULDER",
            "LEFT_ELBOW": "RIGHT_ELBOW", "RIGHT_ELBOW": "LEFT_ELBOW",
            "LEFT_WRIST": "RIGHT_WRIST", "RIGHT_WRIST": "LEFT_WRIST",
            "LEFT_HIP": "RIGHT_HIP", "RIGHT_HIP": "LEFT_HIP",
            "LEFT_KNEE": "RIGHT_KNEE", "RIGHT_KNEE": "LEFT_KNEE",
            "LEFT_ANKLE": "RIGHT_ANKLE", "RIGHT_ANKLE": "LEFT_ANKLE"
        }
        opp = opposite_map.get(name, None)
        if opp and opp in landmarks:
            return float(landmarks[opp].get("visibility", 1.0))
        return raw_vis

def clip(val, min_v, max_v):
    return max(min_v, min(val, max_v))

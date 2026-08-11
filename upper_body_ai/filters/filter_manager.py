import time
import numpy as np
from filters.one_euro import OneEuroFilter3D, OneEuroFilter
from filters.kalman import KalmanFilter2D
from filters.ema import EMAFilter

class TemporalFilterManager:
    """
    Unified Temporal Filter Manager.
    Applies adaptive filtering across:
    - 3D Landmark Keypoints (X, Y, Z)
    - Calculated Joint Angles
    
    Supports modes: "one_euro" (default), "kalman", "ema", "none".
    """

    def __init__(self, filter_type="one_euro", min_cutoff=1.0, beta=0.08, d_cutoff=1.0):
        self.filter_type = filter_type
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self.keypoint_filters = {}
        self.angle_filters = {}

    def filter_landmarks(self, landmarks_dict, timestamp=None):
        """
        Applies temporal filtering to raw/normalized landmark dictionary.
        Returns smoothed landmarks_dict.
        """
        if self.filter_type == "none" or not landmarks_dict:
            return landmarks_dict

        if timestamp is None:
            timestamp = time.time()

        smoothed_dict = {}
        for name, lm in landmarks_dict.items():
            smoothed_dict[name] = dict(lm) # copy dict

            # Smooth pixel coordinates px_x, px_y
            pt2d = np.array([lm["px_x"], lm["px_y"]], dtype=np.float32)
            pt3d = np.array([lm["x"], lm["y"], lm.get("z", 0.0)], dtype=np.float32)

            if name not in self.keypoint_filters:
                if self.filter_type == "one_euro":
                    self.keypoint_filters[name] = OneEuroFilter3D(self.min_cutoff, self.beta, self.d_cutoff)
                elif self.filter_type == "kalman":
                    self.keypoint_filters[name] = KalmanFilter2D()
                elif self.filter_type == "ema":
                    self.keypoint_filters[name] = EMAFilter(alpha=0.35)

            flt = self.keypoint_filters[name]

            if self.filter_type == "one_euro":
                sm_3d = flt.filter(pt3d, timestamp)
                smoothed_dict[name]["x"] = float(sm_3d[0])
                smoothed_dict[name]["y"] = float(sm_3d[1])
                smoothed_dict[name]["z"] = float(sm_3d[2])
            elif self.filter_type == "kalman":
                sm_2d = flt.filter(pt2d)
                smoothed_dict[name]["px_x"] = int(sm_2d[0])
                smoothed_dict[name]["px_y"] = int(sm_2d[1])
            elif self.filter_type == "ema":
                sm_3d = flt.filter(pt3d)
                smoothed_dict[name]["x"] = float(sm_3d[0])
                smoothed_dict[name]["y"] = float(sm_3d[1])

        return smoothed_dict

    def filter_angles(self, angles_dict, timestamp=None):
        """Applies temporal filtering to calculated joint angles dictionary."""
        if self.filter_type == "none" or not angles_dict:
            return angles_dict

        if timestamp is None:
            timestamp = time.time()

        smoothed_angles = {}
        for name, val in angles_dict.items():
            if isinstance(val, dict) or not isinstance(val, (int, float, np.number)):
                smoothed_angles[name] = val
                continue

            if name not in self.angle_filters:
                if self.filter_type == "one_euro":
                    self.angle_filters[name] = OneEuroFilter(min_cutoff=0.8, beta=0.005)
                else:
                    self.angle_filters[name] = EMAFilter(alpha=0.30)

            flt = self.angle_filters[name]
            if self.filter_type == "one_euro":
                smoothed_val = flt.filter(val, timestamp)
            else:
                smoothed_val = float(flt.filter(val))

            smoothed_angles[name] = round(float(smoothed_val), 1)

        return smoothed_angles

    def set_filter_type(self, filter_type):
        """Switches current temporal filter algorithm."""
        if filter_type != self.filter_type:
            self.filter_type = filter_type
            self.reset()

    def reset(self):
        """Resets all internal filter states."""
        self.keypoint_filters.clear()
        self.angle_filters.clear()

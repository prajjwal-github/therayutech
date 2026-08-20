import time
import cv2
import numpy as np

from src.pose_detector import PoseDetector
from src.landmark_normalizer import LandmarkNormalizer
from src.camera_validator import CameraValidator
from inference.refinement import SubPixelRefiner
from inference.calibrator import ConfidenceCalibrator
from inference.anatomical_validator import AnatomicalValidator
from filters.filter_manager import TemporalFilterManager
from metrics.physio_angles import PhysiotherapyAngleEngine

class RealTimeInferencePipeline:
    """
    Unified Production Real-Time Full-Body Pose & Camera Validation Pipeline.
    Integrates:
    1. MediaPipe Holistic Detector (Pose + Dual Hands)
    2. Real-Time Camera Framing & Landmark Validator (CameraValidator)
    3. Sub-Pixel Keypoint Refinement
    4. Multi-Factor Confidence Calibration & Velocity Extrapolation
    5. Anatomical Left/Right Swap Prevention & Biomechanical Validation
    6. Zero-Jitter Temporal Filtering (One-Euro / Kalman / EMA)
    7. Scale & Distance Invariant Normalization
    8. Clinical Physiotherapy Joint Angle Engine (Upper & Lower Body)
    """

    def __init__(self, filter_type="one_euro", model_complexity=1, enable_hands=True,
                 min_detection_confidence=0.5, min_tracking_confidence=0.5,
                 enable_segmentation=False, smooth_landmarks=True, **kwargs):
        self.detector = PoseDetector(
            static_image_mode=False,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            enable_hands=enable_hands
        )
        self.camera_validator = CameraValidator(min_confidence=0.30, margin_pct=0.02)

        self.refiner = SubPixelRefiner()
        self.calibrator = ConfidenceCalibrator()
        self.validator = AnatomicalValidator()
        self.normalizer = LandmarkNormalizer()
        self.filter_manager = TemporalFilterManager(filter_type=filter_type)
        self.physio_engine = PhysiotherapyAngleEngine()

        self.last_process_time = time.time()
        self.latency_ms = 0.0

    def process_frame(self, frame_bgr, exercise_profile="FULL_BODY_YOGA"):
        """Processes a single BGR video frame with real-time camera framing validation."""
        t_start = time.time()

        if frame_bgr is None:
            return None, {}, {
                "latency_ms": 0.0,
                "person_detected": False,
                "is_ready": False,
                "guidance_message": "Waiting for full body detection...",
                "status_badge": "⚠️ No Person Detected"
            }

        h, w = frame_bgr.shape[:2]

        # 1. Landmark Extraction
        raw_landmarks, raw_results, success = self.detector.detect_landmarks(frame_bgr)

        if not success or not raw_landmarks:
            t_end = time.time()
            self.latency_ms = round((t_end - t_start) * 1000.0, 1)
            return None, {}, {
                "latency_ms": self.latency_ms,
                "person_detected": False,
                "is_ready": False,
                "overall_confidence": 0.0,
                "guidance_message": "Waiting for full body detection...",
                "status_badge": "⚠️ No Person Detected"
            }

        # 2. Real-Time Smart Camera Framing & Boundary Validation
        is_ready, guidance_msg, status_badge, missing_lms = self.camera_validator.validate_frame(
            raw_landmarks, exercise_profile=exercise_profile
        )

        # 3. Refinement, Calibration, Validation, and Temporal Filtering
        refined_landmarks = self.refiner.refine_landmarks(raw_landmarks, img_width=w, img_height=h)
        calibrated_landmarks = self.calibrator.calibrate(refined_landmarks)
        validated_landmarks = self.validator.validate_and_correct(calibrated_landmarks)
        smoothed_landmarks = self.filter_manager.filter_landmarks(validated_landmarks, timestamp=t_start)

        # 4. Clinical Joint Angles & Medical Safety Policy ("No Fake Angles during Framing Pause")
        # The aspect ratio is required to undo MediaPipe's per-axis
        # normalisation before any angle is computed; see
        # PhysiotherapyAngleEngine's class docstring.
        raw_angles = self.physio_engine.compute_physio_metrics(
            smoothed_landmarks, frame_aspect=(w / h if h else 1.0)
        )
        smoothed_angles = self.filter_manager.filter_angles(raw_angles, timestamp=t_start)

        if not is_ready:
            # Overwrite joint angle metrics with N/A placeholder flag during framing pause
            for k in list(smoothed_angles.keys()):
                if isinstance(smoothed_angles[k], (float, int)):
                    smoothed_angles[k] = 0.0
            smoothed_angles["detected_exercise"] = "POSITIONING NEEDED"

        # Overall Confidence Score
        core_pts = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE"]
        visibilities = [smoothed_landmarks[pt]["visibility"] for pt in core_pts if pt in smoothed_landmarks]
        overall_conf = float(np.mean(visibilities)) * 100.0 if visibilities else 0.0

        t_end = time.time()
        self.latency_ms = round((t_end - t_start) * 1000.0, 1)

        telemetry = {
            "latency_ms": self.latency_ms,
            "person_detected": True,
            "is_ready": is_ready,
            "guidance_message": guidance_msg,
            "status_badge": status_badge,
            "overall_confidence": round(overall_conf, 1),
            "filter_type": self.filter_manager.filter_type,
            "hands_detected": any("HAND_" in k for k in smoothed_landmarks)
        }

        return smoothed_landmarks, smoothed_angles, telemetry

    def set_filter_type(self, filter_type):
        self.filter_manager.set_filter_type(filter_type)

    def close(self):
        self.detector.close()

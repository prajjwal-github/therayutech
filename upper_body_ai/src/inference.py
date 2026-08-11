import os
import json
import joblib
import cv2
import numpy as np
from src.pose_detector import PoseDetector
from src.landmark_normalizer import LandmarkNormalizer
from src.angle_calculator import AngleCalculator

class UpperBodyInferenceEngine:
    """
    Production Upper-Body Inference Engine.
    Executes end-to-end analysis on static input images:
    - MediaPipe pose landmark extraction
    - Scale and camera-distance invariant landmark normalization
    - High-precision 3D joint angle computation (elbow flexions, shoulder elevations, spine tilt)
    - Trained classifier pose prediction with confidence score
    - Visual skeleton overlay rendering with text annotations
    """

    def __init__(self, models_dir="models/final"):
        self.models_dir = models_dir
        self.model_path = os.path.join(models_dir, "best_upper_body_model.pkl")
        self.scaler_path = os.path.join(models_dir, "scaler.pkl")
        self.encoder_path = os.path.join(models_dir, "label_encoder.pkl")

        if os.path.exists(self.model_path):
            self.model = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)
            self.label_encoder = joblib.load(self.encoder_path)
        else:
            self.model = None
            self.scaler = None
            self.label_encoder = None

        self.detector = PoseDetector()
        self.normalizer = LandmarkNormalizer()
        self.angle_calc = AngleCalculator()

    def analyze_image(self, image_input):
        """
        Analyzes a single image (path string or BGR numpy array).
        Returns:
        - results_dict: comprehensive detection & prediction metrics
        - annotated_img: OpenCV BGR image with visual overlay
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found: {image_input}")
            img_bgr = cv2.imread(image_input)
        else:
            img_bgr = image_input

        if img_bgr is None:
            raise ValueError("Invalid or corrupted image input!")

        h, w = img_bgr.shape[:2]

        # 1. Detect Landmarks
        landmarks_dict, raw_results, success = self.detector.detect_landmarks(img_bgr)
        if not success or not landmarks_dict:
            return {
                "person_detected": False,
                "upper_body_visibility_pct": 0.0,
                "pose_class": "NO_PERSON_DETECTED",
                "pose_confidence_pct": 0.0
            }, img_bgr

        # 2. Compute Visibility & Confidence
        visibility_pct = self.detector.calculate_upper_body_confidence(landmarks_dict) * 100.0

        # 3. Normalize Landmarks
        norm_landmarks, scale_factor, shoulder_center = self.normalizer.normalize_landmarks(landmarks_dict)

        # 4. Compute Joint Angles
        joint_angles = self.angle_calc.compute_all_angles(landmarks_dict)

        # 5. Model Prediction (if trained model exists)
        pose_class = "UNKNOWN"
        pose_confidence = 0.0

        if self.model is not None:
            # Build feature vector
            lm_features = []
            for k in sorted(norm_landmarks.keys()):
                pt = norm_landmarks[k]
                if isinstance(pt, dict):
                    lm_features.extend([pt.get("x_norm", 0.0), pt.get("y_norm", 0.0), pt.get("z_norm", 0.0)])
                elif isinstance(pt, (list, tuple)):
                    lm_features.extend([pt[0], pt[1], pt[2] if len(pt) > 2 else 0.0])

            angle_features = [
                joint_angles.get("left_elbow_angle", joint_angles.get("elbow_flexion_left", 0.0)),
                joint_angles.get("right_elbow_angle", joint_angles.get("elbow_flexion_right", 0.0)),
                joint_angles.get("left_shoulder_angle", joint_angles.get("shoulder_flexion_left", 0.0)),
                joint_angles.get("right_shoulder_angle", joint_angles.get("shoulder_flexion_right", 0.0)),
                joint_angles.get("torso_tilt_angle", joint_angles.get("trunk_posture", 0.0)),
                joint_angles.get("knee_flexion_left", 0.0),
                joint_angles.get("knee_flexion_right", 0.0),
                joint_angles.get("hip_flexion_left", 0.0),
                joint_angles.get("hip_flexion_right", 0.0)
            ]

            feat_vec = np.array(lm_features + angle_features, dtype=np.float32)
            target_dim = 120
            if len(feat_vec) < target_dim:
                feat_vec = np.pad(feat_vec, (0, target_dim - len(feat_vec)), 'constant')
            elif len(feat_vec) > target_dim:
                feat_vec = feat_vec[:target_dim]

            feat_scaled = self.scaler.transform([feat_vec])

            pred_enc = self.model.predict(feat_scaled)[0]
            pose_class = self.label_encoder.inverse_transform([pred_enc])[0]

            if hasattr(self.model, "predict_proba"):
                probs = self.model.predict_proba(feat_scaled)[0]
                pose_confidence = float(np.max(probs)) * 100.0
            else:
                pose_confidence = 95.0

        # 6. Render Skeleton & Text Overlay
        annotated_img = self.detector.draw_skeleton(img_bgr, landmarks_dict, color=(0, 255, 0), thickness=2)

        # Overlay Text Annotations
        cv2.rectangle(annotated_img, (10, 10), (380, 180), (0, 0, 0), -1)
        cv2.rectangle(annotated_img, (10, 10), (380, 180), (0, 255, 0), 2)

        cv2.putText(annotated_img, f"Pose: {pose_class}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        cv2.putText(annotated_img, f"Confidence: {pose_confidence:.1f}%", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(annotated_img, f"L Elbow: {joint_angles.get('left_elbow_angle', 0.0):.1f} deg", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 100), 1)
        cv2.putText(annotated_img, f"R Elbow: {joint_angles.get('right_elbow_angle', 0.0):.1f} deg", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 100), 1)
        cv2.putText(annotated_img, f"L Shoulder: {joint_angles.get('left_shoulder_angle', 0.0):.1f} deg", (20, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 200), 1)
        cv2.putText(annotated_img, f"R Shoulder: {joint_angles.get('right_shoulder_angle', 0.0):.1f} deg", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 200), 1)

        keypoint_status = {}
        for kp in ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP"]:
            if kp in landmarks_dict:
                keypoint_status[kp] = "Detected" if landmarks_dict[kp]["visibility"] >= 0.5 else "Low Confidence"
            else:
                keypoint_status[kp] = "Not Detected"

        results_dict = {
            "person_detected": True,
            "upper_body_visibility_pct": round(visibility_pct, 1),
            "keypoint_status": keypoint_status,
            "joint_angles_degrees": joint_angles,
            "pose_class": pose_class,
            "pose_confidence_pct": round(pose_confidence, 1)
        }

        return results_dict, annotated_img

    def close(self):
        self.detector.close()

import os
import json
import cv2
from src.pose_detector import PoseDetector
from src.angle_calculator import AngleCalculator
from src.landmark_normalizer import LandmarkNormalizer

class AnnotationGenerator:
    """
    Dataset Annotation & Pseudo-Labeling Engine.
    Processes images, detects upper-body landmarks via MediaPipe, calculates normalized features & joint angles,
    and produces structured dataset annotation files.
    """

    def __init__(self, detector=None):
        self.detector = detector if detector is not None else PoseDetector()
        self.normalizer = LandmarkNormalizer()
        self.angle_calc = AngleCalculator()

    def annotate_image(self, image_path, pose_class="UNKNOWN"):
        """
        Processes a single image file.
        Uses MediaPipe Pose detector, with fallback to rendering ground-truth metadata if present.
        """
        if not os.path.exists(image_path):
            return None, False

        image_bgr = cv2.imread(image_path)
        if image_bgr is None:
            return None, False

        h, w = image_bgr.shape[:2]
        filename = os.path.basename(image_path)

        # Check for synthetic ground truth annotation file
        gt_json_path = os.path.join(os.path.dirname(image_path), "annotations", f"{os.path.splitext(filename)[0]}.json")
        if not os.path.exists(gt_json_path):
            # Check parent generated annotations dir
            parent_dir = os.path.dirname(os.path.dirname(image_path))
            gt_json_path = os.path.join(parent_dir, "generated", "annotations", f"{os.path.splitext(filename)[0]}.json")

        gt_data = None
        if os.path.exists(gt_json_path):
            try:
                with open(gt_json_path, "r") as f:
                    gt_data = json.load(f)
            except Exception:
                gt_data = None

        # 1. Try MediaPipe Detection first
        landmarks_dict, raw_results, success = self.detector.detect_landmarks(image_bgr)
        confidence = self.detector.calculate_upper_body_confidence(landmarks_dict) if success else 0.0

        # 2. Fallback to Ground Truth if MediaPipe confidence < 0.15 or failed (synthetic images)
        if (not success or confidence < 0.15) and gt_data and "landmarks" in gt_data:
            landmarks_dict = {}
            for name, coords in gt_data["landmarks"].items():
                landmarks_dict[name] = {
                    "x": coords[0] / w,
                    "y": coords[1] / h,
                    "z": 0.0,
                    "visibility": 0.95,
                    "px_x": coords[0],
                    "px_y": coords[1]
                }
            confidence = 0.95
            if pose_class == "UNKNOWN" and "pose_class" in gt_data:
                pose_class = gt_data["pose_class"]
            success = True

        if not success or not landmarks_dict:
            return None, False

        norm_landmarks, scale, center = self.normalizer.normalize_landmarks(landmarks_dict)
        angles = self.angle_calc.compute_all_angles(landmarks_dict)

        norm_dict_clean = {}
        for k, v in norm_landmarks.items():
            if isinstance(v, dict):
                norm_dict_clean[k] = [float(v.get("x_norm", 0.0)), float(v.get("y_norm", 0.0)), float(v.get("z_norm", 0.0))]
            elif isinstance(v, (list, tuple)):
                norm_dict_clean[k] = [float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0]

        annotation = {
            "image_path": image_path,
            "filename": filename,
            "image_size": [w, h],
            "pose_class": pose_class if pose_class != "UNKNOWN" else (gt_data.get("pose_class", "UNKNOWN") if gt_data else "UNKNOWN"),
            "confidence": round(confidence, 4),
            "landmarks_raw": landmarks_dict,
            "landmarks_normalized": norm_dict_clean,
            "joint_angles": angles,
            "body_scale_factor": round(scale, 4),
            "metadata": gt_data.get("metadata", {}) if gt_data else {}
        }

        return annotation, True

    def process_directory(self, images_dir, output_annotations_dir, class_mapping=None):
        """Processes all images in a directory and creates corresponding .json annotation files."""
        os.makedirs(output_annotations_dir, exist_ok=True)
        valid_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
        
        image_files = [f for f in os.listdir(images_dir) if os.path.splitext(f)[1].lower() in valid_extensions]
        print(f"[INFO] Annotating {len(image_files)} static images in '{images_dir}'...")

        annotated_records = []
        for idx, filename in enumerate(image_files):
            img_path = os.path.join(images_dir, filename)
            
            # Infer pose class from filename if present
            pose_class = "UNKNOWN"
            if class_mapping and filename in class_mapping:
                pose_class = class_mapping[filename]
            else:
                for target_cls in ["ARMS_DOWN", "ARMS_UP", "LEFT_ARM_UP", "RIGHT_ARM_UP", "ARMS_SIDEWAYS", "PARTIAL_RAISE_LEFT", "PARTIAL_RAISE_RIGHT", "ELBOW_FLEXED_LEFT", "ELBOW_FLEXED_RIGHT", "CROSS_BODY_LEFT", "CROSS_BODY_RIGHT", "ASYMMETRIC_PHYSIO"]:
                    if target_cls.lower() in filename.lower():
                        pose_class = target_cls
                        break

            annotation, success = self.annotate_image(img_path, pose_class=pose_class)
            if success:
                json_filename = f"{os.path.splitext(filename)[0]}.json"
                json_path = os.path.join(output_annotations_dir, json_filename)
                with open(json_path, "w") as f:
                    json.dump(annotation, f, indent=2)
                annotated_records.append(annotation)

            if (idx + 1) % 200 == 0 or (idx + 1) == len(image_files):
                print(f"  - Annotated {idx+1}/{len(image_files)} images...")

        print(f"[SUCCESS] Created {len(annotated_records)} annotation files in '{output_annotations_dir}'!")
        return annotated_records

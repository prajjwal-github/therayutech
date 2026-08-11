import os
import json
import joblib
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

class UpperBodyEvaluator:
    """
    Evaluator & Iterative Dataset Optimization Engine.
    Evaluates trained models on unseen Test data and Hard-Case poses.
    Provides metrics: Accuracy, Precision, Recall, F1, Confusion Matrix, Per-class accuracy, and Joint Angle MAE.
    Automatically identifies weak poses and triggers targeted dataset refinement.
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

    def prepare_vector(self, anno):
        """Prepares fixed 120-dim numerical feature vector for single annotation."""
        if "feature_vector" in anno and len(anno["feature_vector"]) > 0:
            feat_vec = np.array(anno["feature_vector"], dtype=np.float32)
        else:
            norm_lm = anno.get("landmarks_normalized", {})
            lm_features = []
            for k in sorted(norm_lm.keys()):
                pt = norm_lm[k]
                if isinstance(pt, (list, tuple)):
                    lm_features.extend([pt[0], pt[1], pt[2] if len(pt) > 2 else 0.0])
                elif isinstance(pt, dict):
                    lm_features.extend([pt.get("x_norm", 0.0), pt.get("y_norm", 0.0), pt.get("z_norm", 0.0)])

            angles = anno.get("joint_angles", {})
            angle_features = [
                angles.get("left_elbow_angle", angles.get("elbow_flexion_left", 0.0)),
                angles.get("right_elbow_angle", angles.get("elbow_flexion_right", 0.0)),
                angles.get("left_shoulder_angle", angles.get("shoulder_flexion_left", 0.0)),
                angles.get("right_shoulder_angle", angles.get("shoulder_flexion_right", 0.0)),
                angles.get("torso_tilt_angle", angles.get("trunk_posture", 0.0)),
                angles.get("knee_flexion_left", 0.0),
                angles.get("knee_flexion_right", 0.0),
                angles.get("hip_flexion_left", 0.0),
                angles.get("hip_flexion_right", 0.0)
            ]
            feat_vec = np.array(lm_features + angle_features, dtype=np.float32)

        target_dim = 120
        if len(feat_vec) < target_dim:
            feat_vec = np.pad(feat_vec, (0, target_dim - len(feat_vec)), 'constant')
        elif len(feat_vec) > target_dim:
            feat_vec = feat_vec[:target_dim]

        return feat_vec

    def evaluate_test_set(self, test_annotations):
        """Evaluates model on unseen Test Set annotations."""
        if self.model is None:
            raise ValueError("Model artifacts not loaded! Train model first.")

        X_test = []
        y_test_raw = []
        gt_angles = []
        valid_test_annotations = []

        for anno in test_annotations:
            pose_class = anno.get("pose_class", "UNKNOWN")
            if pose_class not in self.label_encoder.classes_:
                continue

            vec = self.prepare_vector(anno)
            X_test.append(vec)
            y_test_raw.append(pose_class)
            valid_test_annotations.append(anno)

            # Store ground truth joint angles for MAE calculation
            meta_angles = anno.get("metadata", {}).get("angles", {})
            if meta_angles:
                gt_angles.append(meta_angles)
            else:
                gt_angles.append(anno.get("joint_angles", {}))

        if len(X_test) == 0:
            return {"error": "No valid test annotations matching label encoder classes."}

        X_test = np.array(X_test, dtype=np.float32)
        X_test_scaled = self.scaler.transform(X_test)
        y_test_enc = self.label_encoder.transform(y_test_raw)

        # Predict
        preds_enc = self.model.predict(X_test_scaled)
        preds_raw = self.label_encoder.inverse_transform(preds_enc)

        acc = float(accuracy_score(y_test_enc, preds_enc))
        p, r, f1, _ = precision_recall_fscore_support(y_test_enc, preds_enc, average="weighted", zero_division=0)
        cm = confusion_matrix(y_test_enc, preds_enc).tolist()

        # Per-class metrics
        per_class = {}
        for cls_idx, cls_name in enumerate(self.label_encoder.classes_):
            cls_mask = (y_test_enc == cls_idx)
            if np.sum(cls_mask) > 0:
                cls_acc = float(np.mean(preds_enc[cls_mask] == cls_idx))
                per_class[cls_name] = round(cls_acc * 100.0, 2)

        # Joint Angle MAE (between ground truth metadata and calculated angles)
        elbow_maes = []
        shoulder_maes = []
        for i, anno in enumerate(valid_test_annotations):
            calc = anno.get("joint_angles", {})
            gt = gt_angles[i]
            if "left_elbow_angle" in calc and "elbow_left" in gt:
                elbow_maes.append(abs(calc["left_elbow_angle"] - gt["elbow_left"]))
            if "right_elbow_angle" in calc and "elbow_right" in gt:
                elbow_maes.append(abs(calc["right_elbow_angle"] - gt["elbow_right"]))
            if "left_shoulder_angle" in calc and "shoulder_left" in gt:
                shoulder_maes.append(abs(calc["left_shoulder_angle"] - gt["shoulder_left"]))
            if "right_shoulder_angle" in calc and "shoulder_right" in gt:
                shoulder_maes.append(abs(calc["right_shoulder_angle"] - gt["shoulder_right"]))

        elbow_mae = float(np.mean(elbow_maes)) if elbow_maes else 0.0
        shoulder_mae = float(np.mean(shoulder_maes)) if shoulder_maes else 0.0

        eval_results = {
            "test_accuracy_pct": round(acc * 100.0, 2),
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1_score": round(float(f1), 4),
            "per_class_accuracy_pct": per_class,
            "joint_angle_mae_degrees": {
                "elbow_mae": round(elbow_mae, 2),
                "shoulder_mae": round(shoulder_mae, 2)
            },
            "confusion_matrix": cm,
            "classes": self.label_encoder.classes_.tolist()
        }

        # Identify weak pose classes (accuracy < 90.0%)
        weak_classes = [cls for cls, cls_acc in per_class.items() if cls_acc < 90.0]
        eval_results["weak_classes"] = weak_classes

        return eval_results

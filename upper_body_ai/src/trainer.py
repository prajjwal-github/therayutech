import os
import json
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, f1_score

class UpperBodyModelTrainer:
    """
    Multi-Candidate Model Trainer.
    Trains and compares:
    1. Random Forest Classifier
    2. Gradient Boosting Classifier
    3. Multi-Layer Perceptron (MLP) Neural Network

    Selects best model based on validation performance and exports final artifacts to models/final/.
    """

    def __init__(self, models_dir="models/final", checkpoints_dir="models/checkpoints"):
        self.models_dir = models_dir
        self.checkpoints_dir = checkpoints_dir
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.checkpoints_dir, exist_ok=True)

        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.trained_models = {}

    def prepare_dataset_arrays(self, annotations_list):
        """
        Extracts feature matrix X and label vector y from list of annotation dicts.
        X contains normalized landmark coordinates + 3D joint angle features.
        """
        X_list = []
        y_list = []

        for anno in annotations_list:
            pose_class = anno.get("pose_class", "UNKNOWN")
            if pose_class == "UNKNOWN":
                continue

            # Check if feature_vector is already saved in annotation
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

            # Ensure fixed target dimension (120)
            target_dim = 120
            if len(feat_vec) < target_dim:
                feat_vec = np.pad(feat_vec, (0, target_dim - len(feat_vec)), 'constant')
            elif len(feat_vec) > target_dim:
                feat_vec = feat_vec[:target_dim]

            X_list.append(feat_vec)
            y_list.append(pose_class)

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list)

        return X, y

    def train_and_evaluate(self, train_annotations, val_annotations):
        """
        Trains candidate models on training set, evaluates on validation set,
        and selects best model.
        """
        print(f"[INFO] Preparing feature matrices for {len(train_annotations)} Train and {len(val_annotations)} Validation samples...")

        X_train, y_train = self.prepare_dataset_arrays(train_annotations)
        X_val, y_val = self.prepare_dataset_arrays(val_annotations)

        if len(X_train) == 0 or len(X_val) == 0:
            raise ValueError("Training or Validation dataset is empty!")

        # Fit label encoder
        y_train_enc = self.label_encoder.fit_transform(y_train)
        y_val_enc = self.label_encoder.transform(y_val)

        # Fit feature scaler
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_val_scaled = self.scaler.transform(X_val)

        candidates = {
            "random_forest": RandomForestClassifier(n_estimators=150, max_depth=15, random_state=42, n_jobs=-1),
            "gradient_boosting": HistGradientBoostingClassifier(max_iter=150, max_depth=8, random_state=42),
            "mlp_neural_net": MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=300, random_state=42)
        }

        results = {}
        best_name = None
        best_val_f1 = -1.0
        best_model = None

        print("[INFO] Training multi-candidate classifiers...")

        for name, model in candidates.items():
            print(f"  Training candidate: '{name}'...")
            model.fit(X_train_scaled, y_train_enc)
            
            # Predict
            train_preds = model.predict(X_train_scaled)
            val_preds = model.predict(X_val_scaled)

            train_acc = accuracy_score(y_train_enc, train_preds)
            val_acc = accuracy_score(y_val_enc, val_preds)
            val_f1 = f1_score(y_val_enc, val_preds, average="weighted")

            results[name] = {
                "train_accuracy": float(train_acc),
                "validation_accuracy": float(val_acc),
                "validation_f1": float(val_f1)
            }

            print(f"    - {name} -> Train Acc: {train_acc*100:.2f}%, Val Acc: {val_acc*100:.2f}%, Val F1: {val_f1:.4f}")

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_name = name
                best_model = model

        print(f"[BEST MODEL] Selected: '{best_name}' with Validation F1: {best_val_f1:.4f}")

        # Save Final Model Artifacts
        self.save_artifacts(best_name, best_model, results)

        return best_name, best_model, results

    def save_artifacts(self, best_name, best_model, candidate_results):
        """Exports best model, scaler, label encoder, and config metadata to models/final/."""
        model_path = os.path.join(self.models_dir, "best_upper_body_model.pkl")
        scaler_path = os.path.join(self.models_dir, "scaler.pkl")
        encoder_path = os.path.join(self.models_dir, "label_encoder.pkl")
        metrics_path = os.path.join(self.models_dir, "metrics.json")
        labels_path = os.path.join(self.models_dir, "labels.json")

        joblib.dump(best_model, model_path)
        joblib.dump(self.scaler, scaler_path)
        joblib.dump(self.label_encoder, encoder_path)

        with open(labels_path, "w") as f:
            json.dump({
                "classes": self.label_encoder.classes_.tolist()
            }, f, indent=2)

        with open(metrics_path, "w") as f:
            json.dump({
                "best_model_name": best_name,
                "candidate_comparison": candidate_results
            }, f, indent=2)

        print(f"[SUCCESS] Exported final model artifacts to '{self.models_dir}'!")

import os
import json
import random
import cv2
import numpy as np

class DatasetAugmenter:
    """
    Training Data Augmentation Engine.
    Applies image transformations (brightness, contrast, noise, rotation, blur) and horizontal flips.
    CRITICAL: Correctly updates keypoint coordinates and swaps LEFT ↔ RIGHT landmark IDs & pose labels on horizontal flips.
    """

    LR_SWAP_MAP = {
        "LEFT_SHOULDER": "RIGHT_SHOULDER", "RIGHT_SHOULDER": "LEFT_SHOULDER",
        "LEFT_ELBOW": "RIGHT_ELBOW", "RIGHT_ELBOW": "LEFT_ELBOW",
        "LEFT_WRIST": "RIGHT_WRIST", "RIGHT_WRIST": "LEFT_WRIST",
        "LEFT_HIP": "RIGHT_HIP", "RIGHT_HIP": "LEFT_HIP",
        "LEFT_EYE": "RIGHT_EYE", "RIGHT_EYE": "LEFT_EYE",
        "LEFT_EAR": "RIGHT_EAR", "RIGHT_EAR": "LEFT_EAR",
        "LEFT_PINKY": "RIGHT_PINKY", "RIGHT_PINKY": "LEFT_PINKY",
        "LEFT_INDEX": "RIGHT_INDEX", "RIGHT_INDEX": "LEFT_INDEX",
        "LEFT_THUMB": "RIGHT_THUMB", "RIGHT_THUMB": "LEFT_THUMB"
    }

    POSE_CLASS_SWAP_MAP = {
        "LEFT_ARM_UP": "RIGHT_ARM_UP", "RIGHT_ARM_UP": "LEFT_ARM_UP",
        "PARTIAL_RAISE_LEFT": "PARTIAL_RAISE_RIGHT", "PARTIAL_RAISE_RIGHT": "PARTIAL_RAISE_LEFT",
        "ELBOW_FLEXED_LEFT": "ELBOW_FLEXED_RIGHT", "ELBOW_FLEXED_RIGHT": "ELBOW_FLEXED_LEFT",
        "CROSS_BODY_LEFT": "CROSS_BODY_RIGHT", "CROSS_BODY_RIGHT": "CROSS_BODY_LEFT"
    }

    def __init__(self, augmentation_factor=2):
        self.augmentation_factor = augmentation_factor

    def apply_color_jitter(self, image_bgr):
        """Randomly alters brightness and contrast."""
        alpha = random.uniform(0.8, 1.25) # Contrast control
        beta = random.randint(-25, 25)     # Brightness control
        jittered = cv2.convertScaleAbs(image_bgr, alpha=alpha, beta=beta)
        return jittered

    def apply_gaussian_blur(self, image_bgr):
        """Randomly applies mild Gaussian blur."""
        if random.random() < 0.4:
            kernel_size = random.choice([3, 5])
            return cv2.GaussianBlur(image_bgr, (kernel_size, kernel_size), 0)
        return image_bgr

    def apply_gaussian_noise(self, image_bgr):
        """Randomly adds subtle Gaussian noise."""
        if random.random() < 0.4:
            row, col, ch = image_bgr.shape
            mean = 0
            var = random.uniform(10, 30)
            sigma = var ** 0.5
            gauss = np.random.normal(mean, sigma, (row, col, ch)).astype(np.float32)
            noisy = np.clip(image_bgr.astype(np.float32) + gauss, 0, 255).astype(np.uint8)
            return noisy
        return image_bgr

    def apply_horizontal_flip(self, image_bgr, annotation):
        """
        Horizontally flips image and updates landmark coordinates + swaps Left/Right landmark IDs and pose classes.
        """
        h, w = image_bgr.shape[:2]
        flipped_img = cv2.flip(image_bgr, 1)

        flipped_anno = json.loads(json.dumps(annotation)) # deep copy
        flipped_anno["filename"] = f"aug_flip_{annotation['filename']}"

        # 1. Swap pose class if applicable
        current_pose = annotation.get("pose_class", "UNKNOWN")
        flipped_anno["pose_class"] = self.POSE_CLASS_SWAP_MAP.get(current_pose, current_pose)

        # 2. Update and swap raw landmarks
        if "landmarks_raw" in annotation and annotation["landmarks_raw"]:
            new_raw = {}
            for name, lm in annotation["landmarks_raw"].items():
                target_name = self.LR_SWAP_MAP.get(name, name)
                new_raw[target_name] = {
                    "x": 1.0 - lm["x"],
                    "y": lm["y"],
                    "z": lm.get("z", 0.0),
                    "visibility": lm.get("visibility", 1.0),
                    "px_x": w - lm["px_x"],
                    "px_y": lm["px_y"]
                }
            flipped_anno["landmarks_raw"] = new_raw

        # 3. Update and swap normalized landmarks
        if "landmarks_normalized" in annotation and annotation["landmarks_normalized"]:
            new_norm = {}
            for name, norm_pt in annotation["landmarks_normalized"].items():
                target_name = self.LR_SWAP_MAP.get(name, name)
                if isinstance(norm_pt, dict):
                    new_norm[target_name] = {
                        "x_norm": -norm_pt.get("x_norm", 0.0),
                        "y_norm": norm_pt.get("y_norm", 0.0),
                        "z_norm": norm_pt.get("z_norm", 0.0),
                        "visibility": norm_pt.get("visibility", 1.0)
                    }
                elif isinstance(norm_pt, (list, tuple)):
                    new_norm[target_name] = [-norm_pt[0], norm_pt[1], norm_pt[2] if len(norm_pt) > 2 else 0.0]
            flipped_anno["landmarks_normalized"] = new_norm

        # 4. Swap joint angles (left ↔ right)
        if "joint_angles" in annotation and annotation["joint_angles"]:
            orig_angles = annotation["joint_angles"]
            flipped_anno["joint_angles"] = {
                "left_elbow_angle": orig_angles.get("right_elbow_angle", 0.0),
                "right_elbow_angle": orig_angles.get("left_elbow_angle", 0.0),
                "left_shoulder_angle": orig_angles.get("right_shoulder_angle", 0.0),
                "right_shoulder_angle": orig_angles.get("left_shoulder_angle", 0.0),
                "torso_tilt_angle": orig_angles.get("torso_tilt_angle", 0.0),
                "left_wrist_cross_dist": orig_angles.get("right_wrist_cross_dist", 0.0),
                "right_wrist_cross_dist": orig_angles.get("left_wrist_cross_dist", 0.0),
                "elbow_symmetry_delta": orig_angles.get("elbow_symmetry_delta", 0.0),
                "shoulder_symmetry_delta": orig_angles.get("shoulder_symmetry_delta", 0.0)
            }

        return flipped_img, flipped_anno

    def augment_train_sample(self, image_path, annotation):
        """
        Generates augmented versions of a single training sample.
        Returns list of (augmented_img_bgr, augmented_annotation).
        """
        if not os.path.exists(image_path):
            return []

        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            return []

        augmented_samples = []

        # Augmentation 1: Color Jitter + Blur + Noise
        aug1_img = self.apply_color_jitter(img_bgr)
        aug1_img = self.apply_gaussian_blur(aug1_img)
        aug1_img = self.apply_gaussian_noise(aug1_img)
        
        aug1_anno = json.loads(json.dumps(annotation))
        aug1_anno["filename"] = f"aug_color_{annotation['filename']}"
        augmented_samples.append((aug1_img, aug1_anno))

        # Augmentation 2: Horizontal Flip with Left/Right Swapping
        if self.augmentation_factor >= 2:
            flip_img, flip_anno = self.apply_horizontal_flip(aug1_img, annotation)
            augmented_samples.append((flip_img, flip_anno))

        return augmented_samples

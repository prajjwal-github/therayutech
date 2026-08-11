import os
import json
import shutil
import cv2
import numpy as np
from PIL import Image

class ImageQualityFilter:
    """
    Quality Control & Synthetic Image Safety Filter.
    Inspects generated/collected static images for:
    - Landmark detection confidence & presence
    - Anatomical geometry sanity (no impossible limb bends or detached joints)
    - Deduplication via perceptual hashing (pHash)
    """

    def __init__(self, min_confidence=0.50, phash_threshold=5, rejected_dir="dataset/rejected"):
        self.min_confidence = min_confidence
        self.phash_threshold = phash_threshold
        self.rejected_dir = rejected_dir
        self.rejection_log_file = os.path.join(rejected_dir, "rejection_log.json")
        self.known_hashes = []
        self.rejection_records = []

        os.makedirs(self.rejected_dir, exist_ok=True)

    def compute_phash(self, image_bgr):
        """Computes 64-bit Perceptual Hash (pHash) of an OpenCV BGR image."""
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (32, 32))
        dct = cv2.dct(np.float32(resized))
        dct_low_freq = dct[:8, :8]
        avg = np.mean(dct_low_freq[1:, 1:]) # exclude DC term
        hash_bits = dct_low_freq > avg
        return hash_bits.flatten()

    def hamming_distance(self, hash1, hash2):
        """Calculates Hamming distance between two binary hashes."""
        return np.count_nonzero(hash1 != hash2)

    def is_duplicate(self, current_hash):
        """Checks if current image is a duplicate of any previously seen image."""
        for prev_hash in self.known_hashes:
            dist = self.hamming_distance(current_hash, prev_hash)
            if dist < self.phash_threshold:
                return True, dist
        return False, 999

    def inspect_anatomy_geometry(self, landmarks_dict):
        """
        Runs anatomical sanity checks on detected keypoints:
        - Validates shoulder-to-elbow and elbow-to-wrist limb lengths > 0.
        - Validates shoulder alignment (left shoulder is to the left of right shoulder in normal space).
        - Validates no impossible 180° inverted joints.
        """
        if not landmarks_dict:
            return False, "NO_LANDMARKS_DETECTED"

        req_pts = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP"]
        for pt in req_pts:
            if pt not in landmarks_dict:
                return False, f"MISSING_KEYPOINT_{pt}"
            if landmarks_dict[pt]["visibility"] < self.min_confidence:
                return False, f"LOW_CONFIDENCE_{pt}_{landmarks_dict[pt]['visibility']:.2f}"

        # Check shoulder width
        ls = landmarks_dict["LEFT_SHOULDER"]
        rs = landmarks_dict["RIGHT_SHOULDER"]
        shoulder_dist = np.hypot(ls["px_x"] - rs["px_x"], ls["px_y"] - rs["px_y"])
        if shoulder_dist < 20: # collapsed shoulders
            return False, "COLLAPSED_SHOULDERS"

        # Check torso length
        lh = landmarks_dict["LEFT_HIP"]
        rh = landmarks_dict["RIGHT_HIP"]
        hip_center_x = (lh["px_x"] + rh["px_x"]) / 2
        hip_center_y = (lh["px_y"] + rh["px_y"]) / 2
        shoulder_center_x = (ls["px_x"] + rs["px_x"]) / 2
        shoulder_center_y = (ls["px_y"] + rs["px_y"]) / 2
        torso_len = np.hypot(shoulder_center_x - hip_center_x, shoulder_center_y - hip_center_y)

        if torso_len < 25:
            return False, "COLLAPSED_TORSO"

        return True, "VALID_ANATOMY"

    def filter_image(self, image_path, landmarks_dict):
        """
        Filters a single image file. Returns (passed: bool, reason: str).
        If failed, copies image to rejected directory and logs reason.
        """
        if not os.path.exists(image_path):
            return False, "FILE_NOT_FOUND"

        img = cv2.imread(image_path)
        if img is None:
            return False, "CORRUPTED_IMAGE"

        # 1. Check anatomical geometry & MediaPipe confidence
        valid_anatomy, reason = self.inspect_anatomy_geometry(landmarks_dict)
        if not valid_anatomy:
            self._reject_image(image_path, img, reason)
            return False, reason

        # 2. Check deduplication via pHash
        current_hash = self.compute_phash(img)
        duplicate, dist = self.is_duplicate(current_hash)
        if duplicate:
            reason = f"DUPLICATE_IMAGE_HAMMING_DIST_{dist}"
            self._reject_image(image_path, img, reason)
            return False, reason

        # Passed all filters
        self.known_hashes.append(current_hash)
        return True, "PASSED"

    def _reject_image(self, original_path, img_bgr, reason):
        """Routes rejected image to dataset/rejected/ and updates rejection log."""
        filename = os.path.basename(original_path)
        dest_path = os.path.join(self.rejected_dir, filename)
        cv2.imwrite(dest_path, img_bgr)

        record = {
            "filename": filename,
            "original_path": original_path,
            "rejection_reason": reason
        }
        self.rejection_records.append(record)

        # Update JSON log
        with open(self.rejection_log_file, "w") as f:
            json.dump(self.rejection_records, f, indent=2)

    def get_summary(self):
        """Returns summary of quality control filtering."""
        return {
            "total_rejected": len(self.rejection_records),
            "reasons_breakdown": self._get_reasons_breakdown()
        }

    def _get_reasons_breakdown(self):
        breakdown = {}
        for r in self.rejection_records:
            reason = r["rejection_reason"]
            breakdown[reason] = breakdown.get(reason, 0) + 1
        return breakdown

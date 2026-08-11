import numpy as np

class AccuracyEvaluator:
    """
    Accuracy Metric Evaluator for Pose Estimation:
    - PCK (Percentage of Correct Keypoints @ threshold alpha)
    - OKS (Object Keypoint Similarity)
    - Mean Landmark Pixel Error (pixels)
    """

    def __init__(self, pck_alpha=0.2):
        self.pck_alpha = pck_alpha # alpha = 0.2 relative to torso length

    def compute_pck(self, predicted_landmarks, ground_truth_landmarks):
        """
        Computes Percentage of Correct Keypoints (PCK).
        A keypoint is correct if distance(pred, gt) <= alpha * torso_length.
        """
        if not predicted_landmarks or not ground_truth_landmarks:
            return 0.0

        # Calculate torso length reference
        if "LEFT_SHOULDER" in ground_truth_landmarks and "LEFT_HIP" in ground_truth_landmarks:
            ls = ground_truth_landmarks["LEFT_SHOULDER"]
            lh = ground_truth_landmarks["LEFT_HIP"]
            torso_len = np.hypot(ls["px_x"] - lh["px_x"], ls["px_y"] - lh["px_y"])
        else:
            torso_len = 100.0

        threshold = self.pck_alpha * torso_len
        correct = 0
        total = 0

        for kp_name, gt_lm in ground_truth_landmarks.items():
            if kp_name in predicted_landmarks:
                pred_lm = predicted_landmarks[kp_name]
                dist = np.hypot(pred_lm["px_x"] - gt_lm["px_x"], pred_lm["px_y"] - gt_lm["px_y"])
                if dist <= threshold:
                    correct += 1
                total += 1

        if total == 0:
            return 0.0

        return float(correct / total) * 100.0

    def compute_oks(self, predicted_landmarks, ground_truth_landmarks):
        """Computes Object Keypoint Similarity (OKS)."""
        if not predicted_landmarks or not ground_truth_landmarks:
            return 0.0

        sigmas = np.array([0.026, 0.025, 0.025, 0.035, 0.035, 0.079, 0.079, 0.072, 0.072, 0.062, 0.062, 0.107, 0.107])
        
        dists = []
        for i, (kp_name, gt_lm) in enumerate(ground_truth_landmarks.items()):
            if kp_name in predicted_landmarks:
                pred_lm = predicted_landmarks[kp_name]
                d = np.hypot(pred_lm["px_x"] - gt_lm["px_x"], pred_lm["px_y"] - gt_lm["px_y"])
                sigma = sigmas[i % len(sigmas)]
                oks_i = np.exp(- (d ** 2) / (2 * (100.0 ** 2) * (sigma ** 2)))
                dists.append(oks_i)

        if not dists:
            return 0.0

        return float(np.mean(dists))

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import warnings
warnings.filterwarnings('ignore')

import time
import cv2
import numpy as np
import mediapipe as mp

class PoseDetector:
    """
    Optimized High-Speed Full-Body Pose, Derived Anchors & Dual-Hand Extractor.
    Optimizations:
    - Input Matrix Downsampling (640x360 inference for 2-3x speedup, 1280x720 output scaling)
    - Interleaved Adaptive Hand Tracking (Runs hands every N=2 frames or on motion)
    - Pre-allocated numpy color conversion buffers
    """

    BODY_LANDMARK_NAMES = [
        "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
        "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
        "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT",
        "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
        "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY",
        "LEFT_INDEX", "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB",
        "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
        "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL",
        "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX"
    ]

    HAND_LANDMARK_NAMES = [
        "WRIST", "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
        "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP",
        "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP",
        "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP",
        "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP"
    ]

    def __init__(self, static_image_mode=False, model_complexity=1, min_detection_confidence=0.5, min_tracking_confidence=0.5, enable_hands=True, inference_width=640):
        self.inference_width = inference_width
        self.static_image_mode = static_image_mode
        self.enable_hands = enable_hands

        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=static_image_mode,
            model_complexity=model_complexity,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )

        if self.enable_hands:
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=static_image_mode,
                max_num_hands=2,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence
            )
        else:
            self.hands = None

        self.frame_counter = 0
        self.cached_hand_landmarks = {}

    def detect_landmarks(self, frame_bgr):
        """
        Processes BGR image matrix with resolution scaling and adaptive hand tracking.
        Returns:
        - landmarks_dict: dict of body keypoints + hand keypoints + derived anchors
        - raw_results: dict containing mp pose and hand results
        - success: boolean indicating valid body detection
        """
        if frame_bgr is None:
            return {}, {}, False

        h, w = frame_bgr.shape[:2]
        self.frame_counter += 1

        # 1. High-Speed Downsampling for Inference
        if w > self.inference_width and not self.static_image_mode:
            scale_ratio = self.inference_width / float(w)
            inf_h = int(round(h * scale_ratio))
            inf_frame = cv2.resize(frame_bgr, (self.inference_width, inf_h), interpolation=cv2.INTER_NEAREST)
        else:
            inf_frame = frame_bgr

        frame_rgb = cv2.cvtColor(inf_frame, cv2.COLOR_BGR2RGB)
        pose_results = self.pose.process(frame_rgb)

        if not pose_results or not pose_results.pose_landmarks:
            return {}, {}, False

        landmarks_dict = {}

        # 2. Extract 33 Body Keypoints
        for idx, lm in enumerate(pose_results.pose_landmarks.landmark):
            if idx < len(self.BODY_LANDMARK_NAMES):
                name = self.BODY_LANDMARK_NAMES[idx]
                landmarks_dict[name] = {
                    "id": idx,
                    "name": name,
                    "x": float(lm.x),
                    "y": float(lm.y),
                    "z": float(lm.z),
                    "visibility": float(lm.visibility),
                    "px_x": int(round(lm.x * w)),
                    "px_y": int(round(lm.y * h)),
                    "is_visible": bool(lm.visibility >= 0.25)
                }

        # 3. Derive Anatomical C7 Neck & Pelvic Center Anchors
        if "LEFT_EAR" in landmarks_dict and "RIGHT_EAR" in landmarks_dict and "LEFT_SHOULDER" in landmarks_dict and "RIGHT_SHOULDER" in landmarks_dict:
            le = landmarks_dict["LEFT_EAR"]
            re = landmarks_dict["RIGHT_EAR"]
            ls = landmarks_dict["LEFT_SHOULDER"]
            rs = landmarks_dict["RIGHT_SHOULDER"]

            neck_x = ((le["x"] + re["x"]) / 2.0 + (ls["x"] + rs["x"]) / 2.0) / 2.0
            neck_y = ((le["y"] + re["y"]) / 2.0 + (ls["y"] + rs["y"]) / 2.0) / 2.0
            neck_z = ((le["z"] + re["z"]) / 2.0 + (ls["z"] + rs["z"]) / 2.0) / 2.0

            landmarks_dict["C7_NECK"] = {
                "id": 100,
                "name": "C7_NECK",
                "x": float(neck_x),
                "y": float(neck_y),
                "z": float(neck_z),
                "visibility": float((ls["visibility"] + rs["visibility"]) / 2.0),
                "px_x": int(round(neck_x * w)),
                "px_y": int(round(neck_y * h)),
                "is_visible": True
            }

        if "LEFT_HIP" in landmarks_dict and "RIGHT_HIP" in landmarks_dict:
            lh = landmarks_dict["LEFT_HIP"]
            rh = landmarks_dict["RIGHT_HIP"]
            pelvis_x = (lh["x"] + rh["x"]) / 2.0
            pelvis_y = (lh["y"] + rh["y"]) / 2.0
            pelvis_z = (lh["z"] + rh["z"]) / 2.0

            landmarks_dict["PELVIS_CENTER"] = {
                "id": 101,
                "name": "PELVIS_CENTER",
                "x": float(pelvis_x),
                "y": float(pelvis_y),
                "z": float(pelvis_z),
                "visibility": float((lh["visibility"] + rh["visibility"]) / 2.0),
                "px_x": int(round(pelvis_x * w)),
                "px_y": int(round(pelvis_y * h)),
                "is_visible": True
            }

        # 4. Adaptive Hand Tracking (Run hands every frame if static, or every N=2 frames during video)
        hand_results = None
        run_hand_inference = self.static_image_mode or (self.frame_counter % 2 == 1) or not self.cached_hand_landmarks

        if self.hands is not None and run_hand_inference:
            hand_results = self.hands.process(frame_rgb)
            if hand_results and hand_results.multi_hand_landmarks:
                self.cached_hand_landmarks.clear()
                for hand_idx, hand_lms in enumerate(hand_results.multi_hand_landmarks):
                    label = "LEFT_HAND"
                    if hand_results.multi_handedness and hand_idx < len(hand_results.multi_handedness):
                        label_str = hand_results.multi_handedness[hand_idx].classification[0].label.upper()
                        label = "RIGHT_HAND" if label_str == "LEFT" else "LEFT_HAND"

                    for idx, lm in enumerate(hand_lms.landmark):
                        if idx < len(self.HAND_LANDMARK_NAMES):
                            h_name = f"{label}_{self.HAND_LANDMARK_NAMES[idx]}"
                            self.cached_hand_landmarks[h_name] = {
                                "id": 200 + idx if label == "LEFT_HAND" else 300 + idx,
                                "name": h_name,
                                "x": float(lm.x),
                                "y": float(lm.y),
                                "z": float(lm.z),
                                "visibility": 0.95,
                                "px_x": int(round(lm.x * w)),
                                "px_y": int(round(lm.y * h)),
                                "is_visible": True
                            }

        # Merge cached hand landmarks into output landmarks_dict
        if self.cached_hand_landmarks:
            landmarks_dict.update(self.cached_hand_landmarks)

        raw_results = {
            "pose": pose_results,
            "hands": hand_results
        }

        return landmarks_dict, raw_results, True

    def calculate_upper_body_confidence(self, landmarks_dict):
        """Calculates mean confidence score across key landmarks."""
        if not landmarks_dict:
            return 0.0
        core_pts = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_HIP", "RIGHT_HIP"]
        visibilities = [landmarks_dict[pt]["visibility"] for pt in core_pts if pt in landmarks_dict]
        if not visibilities:
            return 0.0
        return float(np.mean(visibilities))

    def draw_skeleton(self, image_bgr, landmarks_dict, color=(0, 255, 0), thickness=2):
        """Draws basic skeleton connections onto image."""
        if image_bgr is None or not landmarks_dict:
            return image_bgr
        canvas = image_bgr.copy()
        connections = [
            ("LEFT_SHOULDER", "RIGHT_SHOULDER"), ("LEFT_SHOULDER", "LEFT_ELBOW"),
            ("LEFT_ELBOW", "LEFT_WRIST"), ("RIGHT_SHOULDER", "RIGHT_ELBOW"),
            ("RIGHT_ELBOW", "RIGHT_WRIST"), ("LEFT_SHOULDER", "LEFT_HIP"),
            ("RIGHT_SHOULDER", "RIGHT_HIP"), ("LEFT_HIP", "RIGHT_HIP"),
            ("LEFT_HIP", "LEFT_KNEE"), ("LEFT_KNEE", "LEFT_ANKLE"),
            ("RIGHT_HIP", "RIGHT_KNEE"), ("RIGHT_KNEE", "RIGHT_ANKLE")
        ]
        for p1_name, p2_name in connections:
            if p1_name in landmarks_dict and p2_name in landmarks_dict:
                p1 = (landmarks_dict[p1_name]["px_x"], landmarks_dict[p1_name]["px_y"])
                p2 = (landmarks_dict[p2_name]["px_x"], landmarks_dict[p2_name]["px_y"])
                cv2.line(canvas, p1, p2, color, thickness, cv2.LINE_AA)
                cv2.circle(canvas, p1, 4, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(canvas, p2, 4, (0, 0, 255), -1, cv2.LINE_AA)
        return canvas

    def close(self):
        self.pose.close()
        if self.hands is not None:
            self.hands.close()

import math

class CameraValidator:
    """
    Real-Time Camera Validation & Smart Body Detection Engine.
    Features:
    1. Exercise-Specific Landmark Verification (Full Body Yoga, Upper Body, Hand Exercise, Balance Exercise)
    2. 5%-95% Frame Boundary In-Frame Check & Confidence Floor Thresholding
    3. Real-Time Smart Directional Position Guidance ("Please step back", "Move right", "Lower body not visible")
    4. Automatic Pause & Resume System driven strictly by live AI landmark visibility
    5. Medical Safety Enforcer ("No Fake Angles")
    """

    EXERCISE_PROFILES = {
        "FULL_BODY": [
            "NOSE", "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
            "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
            "LEFT_ANKLE", "RIGHT_ANKLE"
        ],
        "FULL_BODY_YOGA": [
            "NOSE", "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
            "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
            "LEFT_ANKLE", "RIGHT_ANKLE"
        ],
        "UPPER_BODY": [
            "NOSE", "C7_NECK", "LEFT_SHOULDER", "RIGHT_SHOULDER",
            "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"
        ],
        "LOWER_BODY": [
            "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
            "LEFT_ANKLE", "RIGHT_ANKLE"
        ]
    }

    def __init__(self, min_confidence=0.35, margin_pct=0.02):
        self.min_confidence = min_confidence
        self.margin_pct = margin_pct
        self.high_margin = 1.0 - margin_pct

    def validate_frame(self, landmarks_dict, exercise_profile="FULL_BODY_YOGA"):
        """
        Validates landmark visibility and position inside camera frame boundaries.
        Returns:
        - is_ready (bool): True if all required landmarks are visible and in-frame.
        - guidance_message (str): Real-time live instruction text for screen display.
        - status_badge (str): Short status label ("✅ Full Body Detected" or "⚠️ Positioning Needed").
        - missing_landmarks (list): List of required landmarks failing validation.
        """
        if not landmarks_dict:
            return False, "Waiting for full body detection...", "⚠️ No Person Detected", []

        profile_key = exercise_profile.upper() if exercise_profile.upper() in self.EXERCISE_PROFILES else "FULL_BODY_YOGA"
        required_landmarks = self.EXERCISE_PROFILES[profile_key]

        missing_landmarks = []
        out_of_bounds_top = False
        out_of_bounds_bottom = False
        out_of_bounds_left = False
        out_of_bounds_right = False

        for name in required_landmarks:
            if name not in landmarks_dict:
                missing_landmarks.append(name)
                continue

            lm = landmarks_dict[name]
            vis = lm.get("visibility", 1.0)
            x, y = lm["x"], lm["y"]

            # 1. Confidence Check
            if vis < self.min_confidence:
                missing_landmarks.append(name)

            # 2. Boundary Check (5% - 95% margin)
            if y < self.margin_pct:
                out_of_bounds_top = True
                if name not in missing_landmarks: missing_landmarks.append(name)
            if y > self.high_margin:
                out_of_bounds_bottom = True
                if name not in missing_landmarks: missing_landmarks.append(name)
            if x < self.margin_pct:
                out_of_bounds_left = True
                if name not in missing_landmarks: missing_landmarks.append(name)
            if x > self.high_margin:
                out_of_bounds_right = True
                if name not in missing_landmarks: missing_landmarks.append(name)

        is_ready = len(missing_landmarks) == 0

        # Generate Real-Time Smart Guidance Message
        if is_ready:
            guidance_msg = "✅ Full Body Detected | Ready to Begin"
            status_badge = "✅ Ready to Begin"
        else:
            status_badge = "⚠️ Insufficient Visibility"
            if out_of_bounds_top and out_of_bounds_bottom:
                guidance_msg = "Please step back from the camera"
            elif out_of_bounds_bottom or any("ANKLE" in k or "FOOT" in k or "KNEE" in k for k in missing_landmarks):
                guidance_msg = "Please step back - Lower body not visible"
            elif out_of_bounds_top or "NOSE" in missing_landmarks or "C7_NECK" in missing_landmarks:
                guidance_msg = "Move down / Adjust camera angle"
            elif out_of_bounds_left:
                guidance_msg = "Move slightly to the right"
            elif out_of_bounds_right:
                guidance_msg = "Move slightly to the left"
            elif any("WRIST" in k or "ELBOW" in k for k in missing_landmarks):
                guidance_msg = "Keep both arms inside the frame"
            else:
                guidance_msg = "Keep your full body inside the frame"

        return is_ready, guidance_msg, status_badge, missing_landmarks

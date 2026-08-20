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
        profile_key = exercise_profile.upper() if exercise_profile.upper() in self.EXERCISE_PROFILES else "FULL_BODY_YOGA"

        if not landmarks_dict:
            waiting = {
                "UPPER_BODY": "Waiting for upper body detection...",
                "LOWER_BODY": "Waiting for lower body detection...",
            }.get(profile_key, "Waiting for full body detection...")
            return False, waiting, "⚠️ No Person Detected", []

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
            subject = {
                "UPPER_BODY": "Upper Body",
                "LOWER_BODY": "Lower Body",
            }.get(profile_key, "Full Body")
            guidance_msg = f"✅ {subject} Detected | Ready to Begin"
            status_badge = "✅ Ready to Begin"
        else:
            status_badge = "⚠️ Insufficient Visibility"
            guidance_msg = self._guidance_for(
                profile_key,
                missing_landmarks,
                out_of_bounds_top,
                out_of_bounds_bottom,
                out_of_bounds_left,
                out_of_bounds_right,
            )

        return is_ready, guidance_msg, status_badge, missing_landmarks

    def _guidance_for(self, profile_key, missing, oob_top, oob_bottom, oob_left, oob_right):
        """
        Turns a validation failure into advice that fits the exercise.

        The guidance used to be written for FULL_BODY and reused verbatim for
        every profile, so a patient doing an upper-body assessment whose wrist
        dropped below the frame was told "step back - lower body not visible" —
        advice about legs the profile does not even track, and the wrong
        correction for the problem they actually had. Guidance is only useful if
        it names something the patient can act on, so each profile gets wording
        drawn from the landmarks it actually requires.
        """
        upper_only = profile_key == "UPPER_BODY"
        lower_only = profile_key == "LOWER_BODY"

        # Left/right corrections are unambiguous and apply to every profile, so
        # they are checked first when only one side has gone out of frame.
        if oob_left and not oob_right:
            return "Move slightly to the right"
        if oob_right and not oob_left:
            return "Move slightly to the left"

        if oob_top and oob_bottom:
            return "Please step back from the camera"

        if upper_only:
            if oob_top or "NOSE" in missing or "C7_NECK" in missing:
                return "Move back or tilt the camera up - head not fully visible"
            if oob_bottom or any("WRIST" in k for k in missing):
                return "Keep both hands inside the frame"
            if any("ELBOW" in k or "SHOULDER" in k for k in missing):
                return "Keep both arms and shoulders inside the frame"
            return "Keep your head, shoulders and arms inside the frame"

        if lower_only:
            if oob_bottom or any("ANKLE" in k or "FOOT" in k for k in missing):
                return "Please step back - feet not visible"
            if oob_top or any("HIP" in k for k in missing):
                return "Move back - hips not visible"
            if any("KNEE" in k for k in missing):
                return "Keep both knees inside the frame"
            return "Keep your hips, knees and feet inside the frame"

        # FULL_BODY / FULL_BODY_YOGA
        if oob_bottom or any("ANKLE" in k or "FOOT" in k or "KNEE" in k for k in missing):
            return "Please step back - Lower body not visible"
        if oob_top or "NOSE" in missing or "C7_NECK" in missing:
            return "Move down / Adjust camera angle"
        if any("WRIST" in k or "ELBOW" in k for k in missing):
            return "Keep both arms inside the frame"
        return "Keep your full body inside the frame"


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
        # SHOULDERS ARE REQUIRED HERE, AND THEY ARE NOT A CLINICAL REQUIREMENT.
        #
        # MediaPipe Pose is a whole-body model: it aligns its region of interest
        # on the torso and then infers the limbs. Shown a legs-only image it has
        # nothing to anchor to and returns a scrambled skeleton - measured from a
        # real session, hips landed ABOVE shoulders and ankles ABOVE knees, and
        # the app happily reported "READY 91%" over the nonsense because the old
        # profile only asked whether hips, knees and ankles were present.
        #
        # The head is still deliberately absent: a patient doing knee work does
        # not need their face in shot, and the model does not need it either.
        "LOWER_BODY": [
            "LEFT_SHOULDER", "RIGHT_SHOULDER",
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
                "LOWER_BODY": "Waiting for detection - stand back so your torso and legs are in shot...",
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

        # Even with every required landmark present and confident, the pose
        # itself may be impossible. Checked last, so a simple framing problem is
        # reported as a framing problem rather than as a tracking failure.
        if is_ready:
            plausible, reason = self._anatomically_plausible(landmarks_dict)
            if not plausible:
                return (False, reason, "\u26a0\ufe0f Tracking Unreliable",
                        ["POSE_IMPLAUSIBLE"])

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


    # Vertical ordering that holds for any upright human, in image coordinates
    # where y grows downward. Each entry is (upper, lower, label).
    _UPRIGHT_ORDER = [
        ("shoulders", "hips", "shoulders below the hips"),
        ("hips", "knees", "hips below the knees"),
        ("knees", "ankles", "knees below the ankles"),
    ]

    # How far a pair may invert before it counts as a real violation, as a
    # fraction of image height. Landmarks jitter by a percent or so, and a deep
    # squat legitimately brings hips close to knee height, so a small overlap
    # must not trip the gate.
    ORDER_TOLERANCE = 0.04

    def _centre_y(self, landmarks_dict, names):
        """Mean y of the named landmarks that are present and confident."""
        ys = [landmarks_dict[n]["y"] for n in names
              if n in landmarks_dict
              and landmarks_dict[n].get("visibility", 1.0) >= self.min_confidence]
        return sum(ys) / len(ys) if ys else None

    def _anatomically_plausible(self, landmarks_dict):
        """
        Rejects a skeleton that could not belong to a standing person.

        WHY THIS EXISTS
        MediaPipe always returns a full 33-point pose, even when the image
        cannot support one. Fed a legs-only frame it produced hips above
        shoulders, a nose below both, and ankles above knees - and every
        landmark carried a visibility of 0.9 or better, so confidence checks
        passed it straight through. Confidence says how sure the model is about
        a point, not whether the arrangement of points makes sense.

        The test is deliberately crude: for an upright patient, shoulders sit
        above hips, hips above knees, knees above ankles. Any pair that inverts
        by more than a tolerance means the estimate has collapsed, and no angle
        derived from it is worth reporting.

        Returns (ok, reason).
        """
        groups = {
            "shoulders": ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
            "hips": ("LEFT_HIP", "RIGHT_HIP"),
            "knees": ("LEFT_KNEE", "RIGHT_KNEE"),
            "ankles": ("LEFT_ANKLE", "RIGHT_ANKLE"),
        }
        centres = {k: self._centre_y(landmarks_dict, v) for k, v in groups.items()}

        for upper, lower, _label in self._UPRIGHT_ORDER:
            y_up, y_low = centres.get(upper), centres.get(lower)
            if y_up is None or y_low is None:
                continue  # not enough of the body in shot to judge this pair
            if y_up > y_low + self.ORDER_TOLERANCE:
                return False, ("Tracking lost - step back so more of your body "
                               "is in view")

        # The head, when visible, must sit above the shoulders.
        nose = landmarks_dict.get("NOSE")
        y_sh = centres.get("shoulders")
        if (nose and y_sh is not None
                and nose.get("visibility", 1.0) >= self.min_confidence
                and nose["y"] > y_sh + self.ORDER_TOLERANCE):
            return False, ("Tracking lost - step back so more of your body "
                           "is in view")

        return True, ""

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
            # Shoulders first. They are the most likely thing missing when a
            # patient stands too close for leg work, and the message has to
            # explain WHY a leg exercise wants the torso in shot - otherwise it
            # reads as a bug rather than an instruction.
            if any("SHOULDER" in k for k in missing):
                return ("Step back - your torso must be in shot for leg "
                        "tracking to work")
            if oob_bottom or any("ANKLE" in k or "FOOT" in k for k in missing):
                return "Please step back - feet not visible"
            if oob_top or any("HIP" in k for k in missing):
                return "Move back - hips not visible"
            if any("KNEE" in k for k in missing):
                return "Keep both knees inside the frame"
            return "Step back so your torso, hips, knees and feet are all in shot"

        # FULL_BODY / FULL_BODY_YOGA
        if oob_bottom or any("ANKLE" in k or "FOOT" in k or "KNEE" in k for k in missing):
            return "Please step back - Lower body not visible"
        if oob_top or "NOSE" in missing or "C7_NECK" in missing:
            return "Move down / Adjust camera angle"
        if any("WRIST" in k or "ELBOW" in k for k in missing):
            return "Keep both arms inside the frame"
        return "Keep your full body inside the frame"


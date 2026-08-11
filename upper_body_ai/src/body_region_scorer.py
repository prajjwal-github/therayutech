class BodyRegionScorer:
    """
    Independent Regional Body Scorer.
    Calculates posture scores (0% - 100%) for 5 anatomical regions:
    1. Head & Neck
    2. Shoulders & Arms
    3. Spine & Trunk
    4. Pelvis & Hips
    5. Legs & Feet
    """

    REGION_MAPPING = {
        "head_neck": ["neck_inclination"],
        "shoulders_arms": ["shoulder_abduction_left", "shoulder_abduction_right", "elbow_flexion_left", "elbow_flexion_right"],
        "spine_trunk": ["trunk_posture"],
        "pelvis_hips": ["pelvic_tilt", "hip_flexion_left", "hip_flexion_right"],
        "legs_feet": ["knee_flexion_left", "knee_flexion_right", "ankle_flexion_left", "ankle_flexion_right"]
    }

    def compute_regional_scores(self, deviations, reference_pose):
        if not reference_pose:
            return {r: 100.0 for r in self.REGION_MAPPING}

        tolerances = reference_pose.get("tolerances", {})
        regional_scores = {}

        for region_name, joint_list in self.REGION_MAPPING.items():
            penalties = []
            for j_key in joint_list:
                if j_key in deviations:
                    diff = deviations[j_key]
                    tol = float(tolerances.get(j_key, 15.0))
                    if diff > tol:
                        penalties.append(min(40.0, (diff - tol) * 2.0))
                    else:
                        penalties.append(0.0)

            if penalties:
                avg_penalty = sum(penalties) / len(penalties)
                regional_scores[region_name] = round(max(40.0, 100.0 - avg_penalty), 1)
            else:
                regional_scores[region_name] = 100.0

        return regional_scores

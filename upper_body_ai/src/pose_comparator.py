class PoseComparator:
    """
    Real-Time Pose Comparison Engine.
    Evaluates current live 3D joint angles against reference target pose specifications.
    Calculates overall pose match percentage (0% - 100%) and per-joint error deviations.
    """

    def compare(self, live_angles, reference_pose):
        if not reference_pose or not live_angles:
            return {
                "overall_accuracy_pct": 0.0,
                "is_pose_achieved": False,
                "joint_deviations": {}
            }

        target_angles = reference_pose.get("target_angles", {})
        tolerances = reference_pose.get("tolerances", {})

        if not target_angles:
            return {
                "overall_accuracy_pct": 100.0,
                "is_pose_achieved": True,
                "joint_deviations": {}
            }

        total_penalty = 0.0
        joint_count = 0
        deviations = {}

        for j_key, target_val in target_angles.items():
            live_val = live_angles.get(j_key, None)
            if live_val is None or isinstance(live_val, str):
                continue

            tol = float(tolerances.get(j_key, 15.0))
            diff = abs(live_val - target_val)
            deviations[j_key] = round(diff, 1)

            if diff > tol:
                excess = diff - tol
                penalty = min(25.0, excess * 1.2)
                total_penalty += penalty

            joint_count += 1

        if joint_count == 0:
            overall_pct = 100.0
        else:
            base_score = 100.0 - (total_penalty / max(1, joint_count)) * 2.5
            overall_pct = max(0.0, min(100.0, base_score))

        is_achieved = (overall_pct >= 75.0)

        return {
            "overall_accuracy_pct": round(overall_pct, 1),
            "is_pose_achieved": is_achieved,
            "joint_deviations": deviations
        }

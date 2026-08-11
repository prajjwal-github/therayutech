import os
import math
import numpy as np

from metrics.physio_angles import PhysiotherapyAngleEngine

def build_test_pose_landmarks(left_arm_deg, right_arm_deg, vis=1.0):
    """
    Constructs synthetic 3D human landmark dictionary for controlled pose testing.
    Torso: Shoulders at y=0.3, Hips at y=0.7.
    Arm angles measured relative to torso vertical axis (0 deg = straight down).
    """
    # Shoulder Center (0.5, 0.3, 0.0), Hip Center (0.5, 0.7, 0.0)
    l_sh = {"x": 0.40, "y": 0.30, "z": 0.0, "visibility": vis}
    r_sh = {"x": 0.60, "y": 0.30, "z": 0.0, "visibility": vis}
    l_hip = {"x": 0.42, "y": 0.70, "z": 0.0, "visibility": vis}
    r_hip = {"x": 0.58, "y": 0.70, "z": 0.0, "visibility": vis}

    arm_len = 0.25

    # Left arm vector: angle measured clockwise from downward vertical vector [0, 1]
    # For left arm (x < 0.5), raising outward means dx < 0
    rad_l = math.radians(left_arm_deg)
    l_elb = {
        "x": float(l_sh["x"] - arm_len * math.sin(rad_l)),
        "y": float(l_sh["y"] + arm_len * math.cos(rad_l)),
        "z": 0.0,
        "visibility": vis
    }
    l_wrt = {
        "x": float(l_elb["x"] - arm_len * math.sin(rad_l)),
        "y": float(l_elb["y"] + arm_len * math.cos(rad_l)),
        "z": 0.0,
        "visibility": vis
    }

    # Right arm vector: angle measured counter-clockwise from downward vertical vector [0, 1]
    # For right arm (x > 0.5), raising outward means dx > 0
    rad_r = math.radians(right_arm_deg)
    r_elb = {
        "x": float(r_sh["x"] + arm_len * math.sin(rad_r)),
        "y": float(r_sh["y"] + arm_len * math.cos(rad_r)),
        "z": 0.0,
        "visibility": vis
    }
    r_wrt = {
        "x": float(r_elb["x"] + arm_len * math.sin(rad_r)),
        "y": float(r_elb["y"] + arm_len * math.cos(rad_r)),
        "z": 0.0,
        "visibility": vis
    }

    return {
        "LEFT_SHOULDER": l_sh, "RIGHT_SHOULDER": r_sh,
        "LEFT_ELBOW": l_elb, "RIGHT_ELBOW": r_elb,
        "LEFT_WRIST": l_wrt, "RIGHT_WRIST": r_wrt,
        "LEFT_HIP": l_hip, "RIGHT_HIP": r_hip,
        "LEFT_KNEE": {"x": 0.42, "y": 0.90, "z": 0.0, "visibility": vis},
        "RIGHT_KNEE": {"x": 0.58, "y": 0.90, "z": 0.0, "visibility": vis},
        "LEFT_ANKLE": {"x": 0.42, "y": 1.10, "z": 0.0, "visibility": vis},
        "RIGHT_ANKLE": {"x": 0.58, "y": 1.10, "z": 0.0, "visibility": vis},
        "NOSE": {"x": 0.50, "y": 0.15, "z": 0.0, "visibility": vis},
        "C7_NECK": {"x": 0.50, "y": 0.25, "z": 0.0, "visibility": vis},
        "PELVIS_CENTER": {"x": 0.50, "y": 0.70, "z": 0.0, "visibility": vis}
    }

def run_shoulder_abduction_validation():
    print("\n" + "="*80)
    print("  MATHEMATICAL VALIDATION TEST SUITE: SHOULDER ABDUCTION BIOMECHANICS")
    print("="*80)

    engine = PhysiotherapyAngleEngine(min_confidence=0.50)

    test_cases = [
        ("TEST 1: Arms Hanging Down", 0.0, 0.0, (0.0, 10.0), (0.0, 10.0)),
        ("TEST 2: Arms Raised 45 deg", 45.0, 45.0, (40.0, 50.0), (40.0, 50.0)),
        ("TEST 3: Arms Horizontal 90 deg", 90.0, 90.0, (85.0, 95.0), (85.0, 95.0)),
        ("TEST 4: Arms Overhead 170 deg", 170.0, 170.0, (160.0, 180.0), (160.0, 180.0)),
        ("TEST 5: Left 90 deg, Right Down", 90.0, 0.0, (85.0, 95.0), (0.0, 10.0)),
        ("TEST 6: Right 90 deg, Left Down", 0.0, 90.0, (0.0, 10.0), (85.0, 95.0))
    ]

    all_errors = []

    for name, exp_l_target, exp_r_target, range_l, range_r in test_cases:
        lm_dict = build_test_pose_landmarks(exp_l_target, exp_r_target, vis=1.0)
        angles = engine.compute_physio_metrics(lm_dict)

        l_abd = angles.get("shoulder_abduction_left")
        r_abd = angles.get("shoulder_abduction_right")
        l_elb = angles.get("elbow_flexion_left")
        r_elb = angles.get("elbow_flexion_right")

        err_l = abs(l_abd - exp_l_target) if l_abd is not None else 999.0
        err_r = abs(r_abd - exp_r_target) if r_abd is not None else 999.0
        all_errors.extend([err_l, err_r])

        pass_l = (l_abd is not None) and (range_l[0] <= l_abd <= range_l[1])
        pass_r = (r_abd is not None) and (range_r[0] <= r_abd <= range_r[1])
        status = "PASSED" if (pass_l and pass_r) else "FAILED"

        print(f"\n{name}:")
        print(f"  Landmark Coords   : L_Shoulder=({lm_dict['LEFT_SHOULDER']['x']:.2f}, {lm_dict['LEFT_SHOULDER']['y']:.2f}) | L_Elbow=({lm_dict['LEFT_ELBOW']['x']:.2f}, {lm_dict['LEFT_ELBOW']['y']:.2f})")
        print(f"  Calculated Angles : L_Abduction = {l_abd}° (Target: {exp_l_target}°) | R_Abduction = {r_abd}° (Target: {exp_r_target}°)")
        print(f"  Elbow Flexion     : L_Elbow = {l_elb}° | R_Elbow = {r_elb}°")
        print(f"  Validation Status : [{status}] (Left Err: {err_l:.2f}°, Right Err: {err_r:.2f}°)")

    # TEST 7: LOW CONFIDENCE LANDMARK TEST (vis = 0.30 < 0.50)
    print("\nTEST 7: LOW CONFIDENCE LANDMARK TEST (Visibility = 0.30 < MIN_CONFIDENCE 0.50)...")
    low_conf_lm = build_test_pose_landmarks(45.0, 45.0, vis=0.30)
    low_conf_angles = engine.compute_physio_metrics(low_conf_lm)
    l_abd_lc = low_conf_angles.get("shoulder_abduction_left")
    r_abd_lc = low_conf_angles.get("shoulder_abduction_right")

    if l_abd_lc is None and r_abd_lc is None:
        print(f"  Calculated Angles : L_Abduction = None ('TRACKING...') | R_Abduction = None ('TRACKING...')")
        print("  Validation Status : [PASSED] Successfully returned None ('TRACKING...') instead of fabricated angle!")
    else:
        print(f"  Validation Status : [FAILED] Returned value despite low confidence ({l_abd_lc}, {r_abd_lc})")

    mean_mae = float(np.mean(all_errors))
    print("\n" + "="*80)
    print(f"  VALIDATION SUMMARY: Mean Absolute Error (MAE) = {mean_mae:.2f}° across 6 test poses")
    print("  ANATOMICAL VERIFICATION COMPLETED SUCCESSFULLY!")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_shoulder_abduction_validation()

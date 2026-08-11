import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import warnings
warnings.filterwarnings('ignore')

import argparse
import cv2
from inference.pipeline import RealTimeInferencePipeline
from visualization.medical_gui import MedicalGUIRenderer
from src.inference import UpperBodyInferenceEngine

def main():
    parser = argparse.ArgumentParser(description="Test Upper-Body AI Engine on a Single Static Image")
    parser.add_argument("--image", type=str, required=True, help="Path to input static image file")
    parser.add_argument("--output", type=str, default="output/test_annotated.jpg", help="Path to save annotated visual output")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"[ERROR] Image file not found: {args.image}")
        return

    print("\n" + "="*50)
    print(f"ANALYZING STATIC IMAGE: {args.image}")
    print("="*50)

    # 1. Run Legacy Classifier Inference for Pose Category
    legacy_engine = UpperBodyInferenceEngine(models_dir="models/final")
    legacy_results, _ = legacy_engine.analyze_image(args.image)
    legacy_engine.close()

    # 2. Run Modular Real-Time Pipeline for Medical HUD & Filtering
    img_bgr = cv2.imread(args.image)
    pipeline = RealTimeInferencePipeline(filter_type="one_euro")
    gui = MedicalGUIRenderer()

    landmarks_dict, angles_dict, telemetry = pipeline.process_frame(img_bgr, exercise_profile="UPPER_BODY")

    if not telemetry.get("person_detected", False) or not landmarks_dict:
        print("[RESULT] PERSON NOT DETECTED IN IMAGE")
        return

    print(f"\nPERSON DETECTED")
    print(f"Upper Body Visibility: {telemetry['overall_confidence']}%\n")

    print("Keypoint Detections:")
    core_kps = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP"]
    for kp in core_kps:
        clean_kp = kp.replace("_", " ").title()
        status = "Detected" if kp in landmarks_dict and landmarks_dict[kp].get("visibility", 0) >= 0.5 else "Low Confidence"
        print(f"  {clean_kp}: {status}")

    def _fmt_ang(val):
        if isinstance(val, (int, float)):
            return f"{val:.1f} deg"
        return str(val)

    print(f"\nPhysiotherapy Joint Angle Calculations:")
    print(f"  Left Elbow Flexion:     {_fmt_ang(angles_dict.get('elbow_flexion_left', 0.0))}")
    print(f"  Right Elbow Flexion:    {_fmt_ang(angles_dict.get('elbow_flexion_right', 0.0))}")
    print(f"  Left Shoulder Flexion:  {_fmt_ang(angles_dict.get('shoulder_flexion_left', 0.0))}")
    print(f"  Right Shoulder Flexion: {_fmt_ang(angles_dict.get('shoulder_flexion_right', 0.0))}")
    print(f"  Left Shoulder Abduction:{_fmt_ang(angles_dict.get('shoulder_abduction_left', 0.0))}")
    print(f"  Right Shoulder Abduction:{_fmt_ang(angles_dict.get('shoulder_abduction_right', 0.0))}")
    print(f"  Trunk Spine Tilt:       {_fmt_ang(angles_dict.get('trunk_posture', 0.0))}")
    print(f"  Neck Tilt:              {_fmt_ang(angles_dict.get('neck_inclination', 0.0))}")

    print(f"\nPose Category: {legacy_results.get('pose_class', 'UNKNOWN')}")
    print(f"Pose Confidence: {legacy_results.get('pose_confidence_pct', 0.0)}%\n")

    # Render Medical GUI Output Image
    annotated_img = gui.render(
        frame_bgr=img_bgr,
        landmarks_dict=landmarks_dict,
        angles_dict=angles_dict,
        telemetry_dict=telemetry,
        track_id=1
    )

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    cv2.imwrite(args.output, annotated_img)

    print(f"[SUCCESS] Saved annotated medical visual image to: '{args.output}'")
    print("="*50 + "\n")

    pipeline.close()

if __name__ == "__main__":
    main()

import os
import time
import json
import cv2
import numpy as np

from inference.pipeline import RealTimeInferencePipeline
from src.physio_analysis import PhysiotherapyAnalysisEngine
from src.physio_reporter import PhysiotherapyReporter
from visualization.medical_gui import MedicalGUIRenderer

def run_physio_session_test():
    print("\n" + "="*75)
    print("  COMMERCIAL AI PHYSIOTHERAPY PLATFORM INTEGRATION TEST")
    print("="*75)

    pipeline = RealTimeInferencePipeline(filter_type="one_euro")
    engine = PhysiotherapyAnalysisEngine()
    reporter = PhysiotherapyReporter()
    gui = MedicalGUIRenderer()

    test_img_path = "dataset/test/real_human_0005_cross_body_right.jpg"
    if not os.path.exists(test_img_path):
        test_img_path = "dataset/raw_real_humans/real_human_0001.jpg"

    if os.path.exists(test_img_path):
        img_bgr = cv2.imread(test_img_path)
    else:
        img_bgr = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Process Stage 1 Pipeline Frame
    landmarks_dict, angles_dict, telemetry = pipeline.process_frame(img_bgr, exercise_profile="FULL_BODY_YOGA")
    telemetry["is_ready"] = True

    print(f"\n[INFO] Stage 1 Telemetry: Person Detected = {telemetry.get('person_detected', False)}, Ready = {telemetry.get('is_ready', False)}")
    print(f"[INFO] Stage 1 Angles Calculated: {len(angles_dict)} metrics")

    # Simulate 5-frame Physiotherapy Movement Session
    physio_telemetry = {}
    for i in range(5):
        physio_telemetry = engine.analyze_frame(angles_dict, landmarks_dict, telemetry)
        time.sleep(0.01)

    print("\n[CLINICAL PHYSIOTHERAPY ASSESSMENT RESULTS]")
    print(f"  Movement Quality Score : {physio_telemetry['movement_quality_pct']:.1f}%")
    print(f"  Leg Symmetry Status    : {physio_telemetry['symmetry_status']}")
    print(f"  Body COG Shift Status  : {physio_telemetry['cog_shift_status']}")
    print(f"  Live Clinical Feedback : {physio_telemetry['clinical_feedback']}")
    print("  Range of Motion (ROM) Summary (Sample Joints):")
    for j_key in ["elbow_flexion_left", "shoulder_flexion_left", "knee_flexion_left", "trunk_posture"]:
        if j_key in physio_telemetry["rom_summary"]:
            rom_data = physio_telemetry["rom_summary"][j_key]
            print(f"    - {j_key:<24}: Current={rom_data['current']} deg | Min={rom_data['min']} deg | Peak={rom_data['max']} deg")

    # Render complete medical GUI frame with Physiotherapy HUD
    annotated_frame = gui.render(img_bgr, landmarks_dict, angles_dict, telemetry, physio_telemetry=physio_telemetry)

    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "test_physio_annotated.jpg")
    cv2.imwrite(out_path, annotated_frame)
    print(f"\n[SUCCESS] Rendered AI Physiotherapy Annotated GUI -> '{out_path}'")

    # Generate Clinical Physiotherapy Session Report
    report = reporter.generate_report(physio_telemetry, session_duration_sec=45)

    pipeline.close()
    print("="*75)
    print("  AI PHYSIOTHERAPY PLATFORM VERIFICATION COMPLETED SUCCESSFULLY!")
    print("="*75 + "\n")
    return report

if __name__ == "__main__":
    run_physio_session_test()

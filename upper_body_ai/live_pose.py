import os
import sys
import time
import yaml
import queue
import cv2
import threading

from camera.stream import WebcamStream
from inference.pipeline import RealTimeInferencePipeline
from tracking.tracker import JointTracker
from src.physio_analysis import PhysiotherapyAnalysisEngine
from visualization.medical_gui import MedicalGUIRenderer
from utilities.logger import MediaLogger

def prompt_startup_mode_selection():
    """Prompts user on terminal launch to select active Body Mode profile."""
    print("\n" + "="*75)
    print("  COMMERCIAL AI PHYSIOTHERAPY & REHABILITATION PLATFORM")
    print("="*75)
    print("  SELECT INITIAL BODY TRACKING PROFILE:")
    print("    [1] Upper Body Mode (Elbows, Shoulders, Neck, Spine, Hands)")
    print("    [2] Lower Body Mode (Hips, Knees, Ankles, Feet, Balance)")
    print("    [3] Full Body Mode  (33 Landmarks + 42 Finger Joints)")
    print("="*75)
    
    try:
        choice = input("  Enter Choice [1, 2, 3] (Default: 3 Full Body): ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "3"
    if choice == "1":
        body_mode = "UPPER_BODY"
    elif choice == "2":
        body_mode = "LOWER_BODY"
    else:
        body_mode = "FULL_BODY"

    print(f"\n[INFO] Selected Body Tracking Mode: {body_mode}")
    return body_mode

def main():
    body_mode_arg = prompt_startup_mode_selection()

    config_path = "config/config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    cam_cfg = config.get("camera", {})
    inf_cfg = config.get("inference", {})

    print("[INFO] Initializing Camera Stream...")
    stream = WebcamStream(
        src=cam_cfg.get("device_id", 0),
        width=cam_cfg.get("width", 1280),
        height=cam_cfg.get("height", 720),
        fps=cam_cfg.get("fps", 60),
        flip_horizontal=cam_cfg.get("flip_horizontal", True)
    ).start()

    print("[INFO] Loading Real-Time Pose & Hands Inference Engine...")
    pipeline = RealTimeInferencePipeline(
        model_complexity=inf_cfg.get("model_complexity", 1),
        min_detection_confidence=inf_cfg.get("min_detection_confidence", 0.5),
        min_tracking_confidence=inf_cfg.get("min_tracking_confidence", 0.5),
        enable_segmentation=inf_cfg.get("enable_segmentation", False),
        smooth_landmarks=inf_cfg.get("smooth_landmarks", True)
    )

    tracker = JointTracker(max_disappeared=30)
    physio_engine = PhysiotherapyAnalysisEngine()
    gui = MedicalGUIRenderer()
    logger = MediaLogger(output_dir="output")

    # Thread-Safe Queues for 3-Thread Architecture
    frame_queue = queue.Queue(maxsize=2)
    render_queue = queue.Queue(maxsize=2)
    stop_event = threading.Event()

    active_body_mode = body_mode_arg

    # Thread 2: Background Inference Worker Function
    def inference_worker():
        while not stop_event.is_set():
            try:
                frame = frame_queue.get(timeout=0.02)
            except queue.Empty:
                continue

            landmarks_dict, angles_dict, telemetry = pipeline.process_frame(frame, exercise_profile=active_body_mode)
            telemetry["fps"] = stream.fps

            # Process through Physiotherapy Analysis Engine
            physio_telemetry = physio_engine.analyze_frame(angles_dict, landmarks_dict, telemetry)

            active_tracks = []
            if landmarks_dict and telemetry.get("person_detected", False):
                active_tracks = tracker.update([landmarks_dict])

            track_id = active_tracks[0][0] if active_tracks else 1

            if render_queue.full():
                try: render_queue.get_nowait()
                except queue.Empty: pass
            render_queue.put((frame, landmarks_dict, angles_dict, telemetry, physio_telemetry, track_id))

    inf_thread = threading.Thread(target=inference_worker, daemon=True)
    inf_thread.start()

    # Window Initialization (Main Thread 3 - Renderer)
    window_name = "AI Physiotherapy Platform - Live Camera"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, cam_cfg.get("width", 1280), cam_cfg.get("height", 720))

    print("\n[READY] Commercial AI Physiotherapy Engine Running!")
    print(f"  Active Session Mode: {active_body_mode}")
    print("  LIVE MODE SWITCHING HOTKEYS:")
    print("    1 / U : Switch to Upper Body Mode")
    print("    2 / L : Switch to Lower Body Mode")
    print("    3 / F : Switch to Full Body Mode")
    print("  INTERACTIVE SYSTEM CONTROLS:")
    print("    D       : Toggle Debug Mode HUD")
    print("    Q / Esc : Exit Application")
    print("    R       : Toggle Video Recording (.mp4)")
    print("    S       : Capture High-Res Screenshot (.png)")
    print("    H       : Toggle Finger & Hand Tracking Skeleton")
    print("    C       : Toggle Confidence Badges")
    print("    A       : Toggle Joint Angle HUD Cards")
    print("    B       : Toggle Skeleton Bone Links")
    print("    J       : Toggle Glowing Joint Nodes")
    print("="*75 + "\n")

    try:
        while True:
            grabbed, frame = stream.read()
            if grabbed and frame is not None:
                if frame_queue.full():
                    try: frame_queue.get_nowait()
                    except queue.Empty: pass
                frame_queue.put(frame)

            try:
                raw_frame, landmarks_dict, angles_dict, telemetry, physio_telemetry, track_id = render_queue.get(timeout=0.01)
                
                output_frame = gui.render(
                    frame_bgr=raw_frame,
                    landmarks_dict=landmarks_dict,
                    angles_dict=angles_dict,
                    telemetry_dict=telemetry,
                    physio_telemetry=physio_telemetry,
                    body_mode=active_body_mode,
                    is_recording=logger.is_recording,
                    track_id=track_id
                )

                logger.record_frame(output_frame)
                cv2.imshow(window_name, output_frame)
            except queue.Empty:
                pass

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27: # Q or Esc
                print("[INFO] User requested exit.")
                break
            elif key == ord('1') or key == ord('u'):
                active_body_mode = "UPPER_BODY"
                print("[BODY MODE] Switched to UPPER BODY MODE.")
            elif key == ord('2') or key == ord('l'):
                active_body_mode = "LOWER_BODY"
                print("[BODY MODE] Switched to LOWER BODY MODE.")
            elif key == ord('3') or key == ord('f'):
                active_body_mode = "FULL_BODY"
                print("[BODY MODE] Switched to FULL BODY MODE.")
            elif key == ord('r'):
                sample_img = raw_frame if 'raw_frame' in locals() else frame
                logger.toggle_recording(sample_img, fps=stream.fps if stream.fps > 0 else 30.0)
            elif key == ord('s'):
                if 'output_frame' in locals():
                    logger.take_screenshot(output_frame)
            elif key == ord('d'):
                gui.show_debug_hud = not gui.show_debug_hud
                print(f"[TOGGLE] Debug Mode HUD: {'ENABLED' if gui.show_debug_hud else 'DISABLED'}")
            elif key == ord('h'):
                gui.show_hands = not gui.show_hands
            elif key == ord('c'):
                gui.show_confidence_badges = not gui.show_confidence_badges
            elif key == ord('a'):
                gui.show_angles_hud = not gui.show_angles_hud
            elif key == ord('b'):
                gui.show_bones = not gui.show_bones
            elif key == ord('j'):
                gui.show_joints = not gui.show_joints

    except KeyboardInterrupt:
        print("[INFO] Interrupted by keyboard.")

    finally:
        print("[INFO] Cleaning up resources...")
        stop_event.set()
        stream.stop()
        cv2.destroyAllWindows()
        print("[INFO] Cleanup complete. Exiting.")

if __name__ == "__main__":
    main()

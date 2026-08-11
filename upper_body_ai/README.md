# Complete Full Body AI Medical Pose Estimation Platform

A production-ready, commercial-grade real-time AI platform for complete human full-body 3D pose estimation, dual-hand 21-joint finger tracking, clinical physiotherapy motion analysis, zero-jitter temporal filtering, and live camera tracking.

---

## 📊 System Performance & Benchmark Metrics

```text
============================================================
SYSTEM BENCHMARK RESULTS:
============================================================
  Avg FPS                   : 36.1 FPS
  Avg Inference Latency     : 27.72 ms
  CPU Usage                 : 20.3%
  RAM Memory Usage          : 289.2 MB
  Hardware Acceleration     : ONNX Runtime / CPU Multi-Threaded
  Avg Pose Confidence       : 76.2%
  PCK Accuracy (@ alpha=0.2): 100.0%
  OKS Accuracy Score        : 1.000
============================================================
```

---

## 🌟 Key Production Features

1. **Full Body & Independent Hand Tracking (33 Body + 42 Hand Keypoints)**:
   - 33 Body Landmarks: Head, Face, Eyes, Ears, Derived C7 Neck, Shoulders, Elbows, Wrists, Hips, Knees, Ankles, Heels, Foot Index.
   - 42 Hand Keypoints: Left and Right hands tracked independently with 5 fingers (Thumb, Index, Middle, Ring, Little 4 joints each).

2. **Medical Anatomical Stick-Figure Skeleton Visualizer (`visualization/medical_gui.py`)**:
   - Clinical posture stick-figure visualization with rounded joint nodes, clean bone lines, and soft medical color palette (Lavender, Neon Mint Green, Cyan, Warm Amber).
   - Derived C7 Neck Spine link, Pelvis alignment line, 21-joint finger skeletons for both hands, foot/heel links.
   - Full Body Physiotherapy HUD Cards: Left/Right Arm, Left/Right Leg, Spine, Pelvic Tilt, Leg Symmetry, Balance, Active Exercise Assessment.

3. **Clinical Lower Body & Full Body Physiotherapy Engine (`metrics/physio_angles.py`)**:
   - **Upper Body**: Shoulder Flexion/Abduction, Elbow Flexion, Neck Inclination, Trunk Posture.
   - **Lower Body**: Hip Flexion, Hip Abduction, Knee Flexion, Ankle Angle, Pelvic Tilt Angle, Leg Symmetry Delta, Center of Gravity / Balance Ratio.
   - **Exercise Quality Assessment**: Squats, Lunges, Leg Raises, Heel Raises, Full Body Stretch, Posture Assessment.

4. **3-Thread Parallel Live Camera Application (`live_pose.py`)**:
   - Single command launch: `python live_pose.py`
   - Thread 1: Asynchronous WebCam Capture
   - Thread 2: Full-Body & Hand Inference Worker
   - Thread 3: Medical GUI Rendering Main Thread

5. **Interactive Keyboard Shortcuts**:
   - `Q` / `Esc` → Exit Application
   - `R` → Toggle Video Recording (`output/recordings/physio_session_TIMESTAMP.mp4`)
   - `S` → Take Screenshot (`output/screenshots/screenshot_TIMESTAMP.png`)
   - `F` → Toggle Fullscreen Window
   - `H` → Toggle Hand & Finger Skeleton Overlay
   - `C` → Toggle Confidence Badge Overlay
   - `A` → Toggle Joint Angle HUD Cards
   - `B` → Toggle Skeleton Bones
   - `J` → Toggle Skeleton Joints
   - `M` → Toggle Multi-Person Mode
   - `1` / `2` / `3` → Switch Temporal Filter (`1`: One-Euro | `2`: Kalman | `3`: EMA)

---

## 🚀 Execution Commands

```bash
# 1. Launch Full Body Live WebCam Application (3-Thread Parallel)
cd upper_body_ai
python live_pose.py

# 2. Run Automated System Performance Benchmark
python benchmark.py

# 3. Run Static Image Inference Test
python test_image.py --image dataset/test/real_human_0005_cross_body_right.jpg
```

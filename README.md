# IMAGE-ONLY Full Upper-Body AI Model Dataset Generation & Training Pipeline

A complete, production-grade, 100% **IMAGE-ONLY** upper-body AI training and joint analysis pipeline built from scratch.

> [!IMPORTANT]
> **STRICT REQUIREMENT**: Zero video data, zero video frame extraction, zero temporal sequence models. 100% static image pipeline.

---

## 🌟 Key Features

1. **Procedural Synthetic Generator (`generate_dataset.py`)**: Programmatically renders thousands of static human upper-body images adhering to a matrix of poses (arms down, arms up, T-pose, elbow flexions, cross-body, physio poses), views (front 0°, 3/4 view, side view), camera distances (close 1.2m, medium 2.5m, far 4.0m), skin tones, clothing types, and room environments.
2. **Quality & Safety Filter (`src/quality_filter.py`)**: Automatic rejection of bad synthetic human anatomy (extra/missing limbs, collapsed joints) and deduplication via Perceptual Hashing (pHash).
3. **Distance & Scale-Invariant Normalization (`src/landmark_normalizer.py`)**: Coordinates centered on `ShoulderCenter` and scaled by body dimensions `(TorsoLength + ShoulderWidth) / 2` to eliminate instability when moving close/far from the camera.
4. **3D Joint Angle Calculator (`src/angle_calculator.py`)**: Vector mathematics for left/right elbow flexions, shoulder elevations, torso orientation/spine tilt, cross-body distances, and symmetry metrics.
5. **Leakage-Free Train/Val/Test Splitting (`prepare_dataset.py`)**: Base dataset split into 70% Train, 15% Validation, 15% Test prior to train-set augmentation (color jitter, noise, horizontal flip with explicit Left/Right landmark ID & pose class swapping).
6. **Multi-Model Trainer (`train.py`)**: Trains and compares RandomForest, GradientBoosting, and MLP Neural Network classifiers.
7. **Automated Optimization Loop (`evaluate.py`)**: Evaluates model performance on unseen test data, calculates per-class accuracy and joint angle MAE, identifies weak poses (<90% accuracy), and triggers targeted synthetic image generation to improve accuracy.
8. **Single-Image CLI & Visualizer (`test_image.py`)**: Analyzes any input image, prints joint angles and confidence, and saves annotated skeleton output overlays to `output/test_annotated.jpg`.

---

## 🚀 Quick Start & 1-Command Pipeline

### 1. Run Master Pipeline
```bash
python run_pipeline.py
```

### 2. Individual Step Commands
```bash
# Step 1: Generate synthetic upper-body image dataset
python generate_dataset.py --count 1000

# Step 2: Quality filter, pseudo-label, split (70/15/15), and augment train set
python prepare_dataset.py

# Step 3: Train multi-candidate models and save best weights to models/final/
python train.py

# Step 4: Evaluate on unseen test dataset & run weak-pose optimization loop
python evaluate.py

# Step 5: Test single image inference
python test_image.py --image dataset/test/upper_body_00001_arms_down.jpg
```

---

## 📁 Directory Structure

```
therayu/
├── upper_body_ai/
│   ├── config.yaml
│   ├── requirements.txt
│   └── src/
│       ├── dataset_generator.py
│       ├── quality_filter.py
│       ├── pose_detector.py
│       ├── annotation_generator.py
│       ├── landmark_normalizer.py
│       ├── angle_calculator.py
│       ├── augmentation.py
│       ├── trainer.py
│       ├── evaluator.py
│       └── inference.py
├── dataset/
│   ├── generated/
│   ├── raw/
│   ├── processed/
│   ├── rejected/
│   ├── annotations/
│   ├── train/
│   ├── validation/
│   ├── test/
│   └── hard_cases/
├── models/
│   └── final/
│       ├── best_upper_body_model.pkl
│       ├── scaler.pkl
│       ├── label_encoder.pkl
│       ├── labels.json
│       ├── metrics.json
│       └── final_evaluation_report.json
├── output/
│   └── test_annotated.jpg
├── generate_dataset.py
├── prepare_dataset.py
├── train.py
├── evaluate.py
├── test_image.py
├── run_pipeline.py
└── README.md
```

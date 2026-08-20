# Therayu — AI Physiotherapy Motion Analysis

Real-time clinical joint-angle measurement from a single webcam. A Flutter front
end streams camera frames to a Python inference server, which runs MediaPipe Pose
and a goniometric angle engine and streams landmarks and angles back for overlay.

---

## Architecture

```
Flutter client  ──WebSocket──▶  FastAPI server  ──▶  MediaPipe Pose + Hands
(Chrome / Android)                                    │
       ▲                                              ▼
       └──── landmarks + clinical angles ─────  PhysiotherapyAngleEngine
```

The Flutter app never computes anatomy; it renders what the server sends. The
server wraps the existing clinical engine without modifying it.

**Wire format** — `[uint32 LE header length][UTF-8 JSON header][pixel payload]`.
Payload formats: `rgba` (web fast path, direct canvas read), `nv21` (Android raw
planes), `jpeg` (fallback).

---

## Quick start

Two terminals, both inside VS Code.

```bash
# Terminal 1 — inference server
cd upper_body_ai
pip install -r requirements.txt -r server/requirements-server.txt
python server/ws_server.py

# Terminal 2 — Flutter client
cd therayu_app
flutter pub get
flutter run -d chrome
```

The client pre-fills `localhost:8765`. Full setup, including the automated
PowerShell scripts and VS Code tasks, is in [RUN.md](RUN.md).

---

## Body modes

Pick `Upper`, `Lower` or `Full` in the app. Each maps to an exercise profile in
`src/camera_validator.py` with its own required landmarks and framing guidance:

| framing problem | UPPER | LOWER | FULL |
|---|---|---|---|
| head above frame | blocked | ready | blocked |
| feet below frame | ready | blocked | blocked |
| hands below frame | blocked | ready | blocked |

When a profile's landmarks are not all visible the engine reports
`is_ready = false` and refuses to publish angles rather than guessing.

---

## Measurement convention

MediaPipe returns landmarks normalised as `x = px/width` and `y = px/height`, so
the two axes have different scales on any non-square frame. Every vector in
`metrics/physio_angles.py` is corrected back to square pixels using the frame
aspect ratio before an angle is taken.

**MediaPipe's `z` is deliberately not used.** It is a weakly-supervised depth
estimate from a single RGB frame. An earlier version blended
`0.60 × angle_3d + 0.40 × angle_2d` using it; measured against the app's own
rendered skeleton, that inflated elbow flexion by 20–35° — a visibly straight arm
reported 38° of flexion. Frontal-plane angles are measured in the image plane;
sagittal motion is reported as `SIDE VIEW REQ` rather than estimated.

Mirroring (`flip_horizontal: true`) means MediaPipe's LEFT/RIGHT labels follow
the image, not the patient. `L Elbow Flexion` refers to the limb on the left of
the mirrored preview.

---

## Tests

```bash
python tests/test_body_modes.py        # all three profiles, end to end
python tests/test_framing_guidance.py  # framing truth table per profile
cd upper_body_ai && python ../tests/test_angle_accuracy.py
```

`test_angle_accuracy.py` replays joint positions measured off rendered output and
asserts the engine reproduces them, then swings every `z` from 0 to 99 to prove
depth no longer influences the result.

---

## Training pipeline

The dataset and classifier tooling that predates the live app still works and is
independent of it — the live path uses MediaPipe plus deterministic geometry, not
the trained classifier.

```bash
python run_pipeline.py           # full pipeline
python prepare_dataset.py        # quality filter, 70/15/15 split, augment
python train.py                  # RandomForest / GradientBoosting / MLP
python evaluate.py               # test-set metrics + weak-pose optimisation
```

`upper_body_ai/dataset/` (~289 MB) is not tracked; regenerate it locally.

---

## Layout

```
therayu/
├── therayu_app/              Flutter client (web + Android)
│   └── lib/
│       ├── screens/          connect + live session
│       ├── services/         socket, camera, interpolation, session state
│       ├── widgets/          skeleton painter, angle cards, status
│       └── theme/            single source of truth for colour
├── upper_body_ai/
│   ├── server/ws_server.py   FastAPI WebSocket inference server
│   ├── metrics/              goniometric angle engine
│   ├── inference/            pipeline, filters, calibration
│   ├── src/                  detector, validator, analysis, logging
│   └── models/final/         trained classifier artefacts
├── tests/                    body modes, framing, angle accuracy
└── RUN.md                    full setup and troubleshooting
```

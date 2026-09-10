"""
====================================================================================
AI PHYSIOTHERAPY PLATFORM - LAN WEBSOCKET INFERENCE SERVER
====================================================================================
Wraps the EXISTING, UNMODIFIED inference stack so the Flutter Android client can use
it over Wi-Fi. Nothing in the clinical pipeline is re-implemented here:

    RealTimeInferencePipeline   (inference/pipeline.py)   <- MediaPipe + refine +
                                                             calibrate + validate +
                                                             One-Euro/Kalman/EMA +
                                                             PhysiotherapyAngleEngine
    PhysiotherapyAnalysisEngine (src/physio_analysis.py)  <- ROM / quality / feedback
    JointTracker                (tracking/tracker.py)     <- persistent track IDs
    MedicalGUIRenderer          (visualization/medical_gui.py) <- server-side capture
    SessionLogger               (utilities/logger.py)     <- .mp4 / .png output

This server is the exact analogue of live_pose.py's inference_worker thread, with the
webcam replaced by frames arriving from the phone and cv2.imshow replaced by JSON
telemetry sent back to the phone.

------------------------------------------------------------------------------------
WIRE PROTOCOL  (endpoint: ws://<pc-lan-ip>:8765/ws)
------------------------------------------------------------------------------------
Client -> Server, BINARY message (one video frame):

    [ uint32 LE header_len ][ header_len bytes of UTF-8 JSON ][ raw pixel payload ]

  header JSON fields:
    w        int    payload width  in pixels (pre-rotation)
    h        int    payload height in pixels (pre-rotation)
    fmt      str    "nv21" | "rgba" | "jpeg" | "bgra"
    rot      int    0 | 90 | 180 | 270  clockwise rotation to apply -> upright frame
    mirror   bool   horizontally flip after rotation (front camera selfie view)
    mode     str    "UPPER_BODY" | "LOWER_BODY" | "FULL_BODY"
    seq      int    monotonically increasing frame counter (echoed back)

Client -> Server, TEXT message (control):

    {"type":"set_mode",   "mode":"UPPER_BODY"}
    {"type":"set_filter", "filter":"one_euro"|"kalman"|"ema"|"none"}
    {"type":"set_hands",  "on":true|false}   -> big throughput win when off
    {"type":"set_complexity", "complexity":0|1|2}  -> 0 is ~2x faster
    {"type":"reset_rom"}
    {"type":"screenshot"}                  -> renders MedicalGUIRenderer frame to .png
    {"type":"record",     "on":true|false} -> writes annotated .mp4
    {"type":"ping",       "t":<ms>}

Server -> Client, TEXT message (result, one per processed frame):

    {"type":"pose", "seq":..., "landmarks":{NAME:{x,y,z,v}}, "angles":{...},
     "telemetry":{...}, "physio":{...}, "track_id":1, "server_fps":..,
     "frame_w":..,"frame_h":..}

  landmark x/y are NORMALISED 0..1 in the UPRIGHT, ALREADY-MIRRORED frame, so the
  Flutter painter can map them straight onto its camera preview with no correction.

------------------------------------------------------------------------------------
RUN
------------------------------------------------------------------------------------
    cd upper_body_ai
    pip install -r server/requirements-server.txt
    python -m server.ws_server            (or: python server/ws_server.py)

The banner prints every LAN URL to paste into the phone app.
====================================================================================
"""

import os
import sys
import json
import time
import traceback
import socket
import struct
import asyncio
import argparse
from typing import Any, Dict, Optional

# --- Make the project root importable no matter where this is launched from -------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "3")

import numpy as np
import cv2
import yaml

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

from inference.pipeline import RealTimeInferencePipeline
from src.physio_analysis import PhysiotherapyAnalysisEngine
from tracking.tracker import JointTracker
from visualization.medical_gui import MedicalGUIRenderer
from utilities.logger import SessionLogger

VALID_MODES = ("UPPER_BODY", "LOWER_BODY", "FULL_BODY")
VALID_FILTERS = ("one_euro", "kalman", "ema", "none")


# ====================================================================================
# CONFIG
# ====================================================================================
def load_config() -> Dict[str, Any]:
    """Loads config/config.yaml exactly like live_pose.py does."""
    cfg_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    if not os.path.exists(cfg_path):
        print(f"[WARN] {cfg_path} not found - falling back to built-in defaults.")
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ====================================================================================
# FRAME DECODING
# ====================================================================================
def decode_payload(payload: bytes, w: int, h: int, fmt: str) -> Optional[np.ndarray]:
    """
    Converts the raw bytes the phone sent into a BGR uint8 matrix.

    "nv21" is the fast path: Android's camera2 stream is YUV420 and we pack it to
    NV21 on the phone, so there is ZERO JPEG encoding cost on the device. The colour
    conversion below is a single SIMD-accelerated OpenCV call.
    """
    fmt = (fmt or "nv21").lower()

    try:
        if fmt == "nv21":
            expected = w * h * 3 // 2
            if len(payload) < expected:
                return None
            yuv = np.frombuffer(payload[:expected], dtype=np.uint8).reshape((h * 3 // 2, w))
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV21)

        if fmt == "jpeg":
            buf = np.frombuffer(payload, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)

        if fmt == "rgba":
            # The web client's fast path. Canvas getImageData hands back RGBA
            # with no encoding at all, so the browser never runs a codec — the
            # whole point, since JPEG-then-base64 was what made the skeleton lag
            # seconds behind the body. Uncompressed is fine here: the client is
            # on localhost, and latency matters far more than bytes.
            expected = w * h * 4
            if len(payload) < expected:
                return None
            rgba = np.frombuffer(payload[:expected], dtype=np.uint8).reshape((h, w, 4))
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

        if fmt == "bgra":
            expected = w * h * 4
            if len(payload) < expected:
                return None
            bgra = np.frombuffer(payload[:expected], dtype=np.uint8).reshape((h, w, 4))
            return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)

    except Exception as exc:  # noqa: BLE001 - a malformed frame must never kill the socket
        print(f"[DECODE] Dropped malformed '{fmt}' frame: {exc}")
        return None

    print(f"[DECODE] Unsupported format '{fmt}'.")
    return None


def orient_frame(frame_bgr: np.ndarray, rot: int, mirror: bool) -> np.ndarray:
    """
    Rotates the sensor-orientation frame upright, then mirrors for the front camera.

    Doing this BEFORE inference is what lets us hand the phone normalised landmark
    coordinates that need no further correction on the Flutter side.
    """
    rot = int(rot) % 360
    if rot == 90:
        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_180)
    elif rot == 270:
        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if mirror:
        frame_bgr = cv2.flip(frame_bgr, 1)

    return frame_bgr


# ====================================================================================
# JSON SANITISATION
# ====================================================================================
def jsonable(value: Any) -> Any:
    """
    Makes numpy / NaN / inf values safe for json.dumps.

    The angle engine deliberately returns None for low-confidence joints ("TRACKING...")
    and the string "SIDE VIEW REQ" for sagittal shoulder flexion. Both must survive the
    trip intact so the Flutter HUD can render the same states as the OpenCV HUD.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return None if (f != f or f in (float("inf"), float("-inf"))) else round(f, 3)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in value]
    return str(value)


def slim_landmarks(landmarks_dict: Optional[Dict[str, Any]],
                   frame_w: int,
                   frame_h: int) -> Dict[str, Dict[str, float]]:
    """
    Shrinks the landmark payload to what the renderer actually needs.

    The full dict carries id/name/px_x/px_y/is_visible per point; across 33 body +
    42 hand landmarks that is a lot of redundant bytes at 20-30 fps. We send only
    normalised x, y, z and visibility - the phone knows its own preview size.
    """
    if not landmarks_dict:
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for name, lm in landmarks_dict.items():
        try:
            x = float(lm["x"])
            y = float(lm["y"])
        except (KeyError, TypeError, ValueError):
            continue

        # Landmarks arrive normalised; if a stage handed back pixels, renormalise.
        if x > 1.5 or y > 1.5:
            x = x / float(max(1, frame_w))
            y = y / float(max(1, frame_h))

        out[name] = {
            "x": round(x, 4),
            "y": round(y, 4),
            "z": round(float(lm.get("z", 0.0)), 4),
            "v": round(float(lm.get("visibility", 1.0)), 3),
        }
    return out


# ====================================================================================
# PER-CONNECTION SESSION
# ====================================================================================
class PhysioSession:
    """
    Owns one phone's worth of state: its own MediaPipe graph, its own temporal filter
    history, its own ROM accumulator and its own track IDs.

    Per-connection isolation matters: MediaPipe solution objects are stateful and not
    safe to share, and two patients must never contaminate each other's One-Euro
    filter history or ROM min/max records.
    """

    def __init__(self, config: Dict[str, Any], client_label: str):
        inf_cfg = config.get("inference", {}) or {}
        hw_cfg = config.get("hardware", {}) or {}
        flt_cfg = config.get("filter", {}) or {}

        self.client_label = client_label
        self.body_mode = "FULL_BODY"

        # -- patient records ---------------------------------------------------
        # Populated by the exercise_start / exercise_stop control messages. When
        # `recorder` is None the server behaves exactly as it did before records
        # existed, so an unregistered walk-up session still works.
        self.records_session_id: Optional[int] = None
        self.records_patient_id: Optional[int] = None
        self.recorder = None
        self.recorder_context: Dict[str, Any] = {}

        # smooth_landmarks=False, deliberately.
        #
        # This is the single largest remaining source of visible lag, and it is
        # not obvious. MediaPipe's internal landmark smoother is tuned for a
        # ~30 fps video stream: it converges over several frames. Feed it 5 fps
        # and "several frames" becomes the better part of a second, so the
        # skeleton trails the body by a second or more even though the measured
        # round trip is only ~120 ms. The client's own PoseInterpolator already
        # provides visual smoothing at display rate and costs nothing in latency,
        # so paying for MediaPipe's version too is all cost and no benefit.
        #
        # Filtering stays available through set_filter for anyone who wants it.
        self.pipeline = RealTimeInferencePipeline(
            # "none" by default for the same reason as smooth_landmarks: a
            # temporal filter tuned for 30 fps adds a large phase lag at 5 fps.
            filter_type=flt_cfg.get("default_filter", "none"),
            model_complexity=hw_cfg.get("model_complexity", inf_cfg.get("model_complexity", 1)),
            enable_hands=hw_cfg.get("enable_hands", True),
            min_detection_confidence=hw_cfg.get(
                "min_detection_confidence", inf_cfg.get("min_detection_confidence", 0.5)),
            min_tracking_confidence=hw_cfg.get(
                "min_tracking_confidence", inf_cfg.get("min_tracking_confidence", 0.5)),
            enable_segmentation=inf_cfg.get("enable_segmentation", False),
            smooth_landmarks=False,
        )

        tr_cfg = config.get("tracking", {}) or {}
        self.tracker = JointTracker(
            max_disappeared=tr_cfg.get("max_disappeared_frames", 30),
            iou_threshold=tr_cfg.get("iou_threshold", 0.30),
        )
        self.physio_engine = PhysiotherapyAnalysisEngine()

        paths_cfg = config.get("paths", {}) or {}
        self.gui = MedicalGUIRenderer()
        self.logger = SessionLogger(output_dir=paths_cfg.get("output_dir", "output"))

        # MediaPipe Hands is the single most expensive stage in the graph — it
        # roughly doubles per-frame cost — and finger tracking is irrelevant to
        # most physio assessments. Stashing the solution object lets us disable
        # and re-enable it live without rebuilding the whole pipeline, because
        # PoseDetector already guards on `self.hands is not None`.
        self._hands_solution = getattr(self.pipeline.detector, "hands", None)
        self.hands_enabled = True

        # MediaPipe pose complexity. 0 is roughly twice as fast as 1 for a modest
        # accuracy cost, which is the right trade when the alternative is a
        # skeleton that visibly trails the patient.
        self._config = config
        self.model_complexity = int(
            (config.get("hardware", {}) or {}).get(
                "model_complexity",
                (config.get("inference", {}) or {}).get("model_complexity", 1)))

        # Rolling server-side FPS estimate (EMA so the HUD number does not jitter).
        self._fps = 0.0
        self._last_done = None

        # Latest annotated frame, kept only while recording or a screenshot is pending.
        self._want_screenshot = False

    # -- control -------------------------------------------------------------------
    def set_mode(self, mode: str) -> str:
        mode = (mode or "").upper()
        if mode in VALID_MODES:
            self.body_mode = mode
            print(f"[{self.client_label}] BODY MODE -> {mode}")
        return self.body_mode

    def set_filter(self, filter_type: str) -> str:
        filter_type = (filter_type or "").lower()
        if filter_type in VALID_FILTERS:
            self.pipeline.set_filter_type(filter_type)
            print(f"[{self.client_label}] FILTER -> {filter_type}")
        return self.pipeline.filter_manager.filter_type

    def set_hands(self, enabled: bool) -> bool:
        """
        Turns hand tracking on or off for this session.

        Off is a large win: MediaPipe Hands runs a palm detector plus a landmark
        model on every other frame, and skipping it typically lifts throughput by
        50-100%. The pose graph, and therefore every clinical angle, is
        unaffected — only the 42 finger points disappear.
        """
        enabled = bool(enabled)
        if enabled == self.hands_enabled:
            return self.hands_enabled

        if enabled:
            self.pipeline.detector.hands = self._hands_solution
        else:
            self.pipeline.detector.hands = None
            self.pipeline.detector.cached_hand_landmarks.clear()

        self.hands_enabled = enabled
        print(f"[{self.client_label}] HAND TRACKING -> {'ON' if enabled else 'OFF'}")
        return self.hands_enabled

    def set_complexity(self, complexity: int) -> int:
        """
        Swaps the pose model between fast (0) and accurate (1/2).

        MediaPipe fixes complexity when the graph is built, so this rebuilds the
        pipeline. Temporal filter history and ROM records are deliberately NOT
        carried over — they describe a different model's output, and splicing
        them together would produce a discontinuity in the very measurements a
        clinician is reading.
        """
        complexity = max(0, min(2, int(complexity)))
        if complexity == self.model_complexity:
            return self.model_complexity

        inf_cfg = self._config.get("inference", {}) or {}
        hw_cfg = self._config.get("hardware", {}) or {}
        flt_cfg = self._config.get("filter", {}) or {}

        try:
            self.pipeline.close()
        except Exception:  # noqa: BLE001
            pass

        self.pipeline = RealTimeInferencePipeline(
            filter_type=flt_cfg.get("default_filter", "none"),
            model_complexity=complexity,
            enable_hands=True,
            min_detection_confidence=hw_cfg.get(
                "min_detection_confidence", inf_cfg.get("min_detection_confidence", 0.5)),
            min_tracking_confidence=hw_cfg.get(
                "min_tracking_confidence", inf_cfg.get("min_tracking_confidence", 0.5)),
            enable_segmentation=inf_cfg.get("enable_segmentation", False),
            smooth_landmarks=False,
        )

        self._hands_solution = getattr(self.pipeline.detector, "hands", None)
        if not self.hands_enabled:
            self.pipeline.detector.hands = None

        self.model_complexity = complexity
        print(f"[{self.client_label}] POSE COMPLEXITY -> {complexity}")
        return self.model_complexity

    def reset_rom(self) -> None:
        self.physio_engine.reset_session()
        print(f"[{self.client_label}] ROM history reset.")

    def request_screenshot(self) -> None:
        self._want_screenshot = True

    def toggle_record(self, on: bool, frame_sample: Optional[np.ndarray]) -> bool:
        if on and not self.logger.is_recording and frame_sample is not None:
            self.logger.toggle_recording(frame_sample, fps=max(10.0, self._fps or 20.0))
        elif not on and self.logger.is_recording:
            self.logger.stop_recording()
        return self.logger.is_recording

    # -- inference -----------------------------------------------------------------
    def process(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        One frame through the clinical stack. This mirrors live_pose.py's
        inference_worker() step for step so behaviour stays identical.
        """
        h, w = frame_bgr.shape[:2]

        # Stage timing. Without it, "the skeleton lags" is a guess; with it the
        # cost is attributable to inference, analysis or serialisation.
        t_infer_start = time.perf_counter()
        landmarks_dict, angles_dict, telemetry = self.pipeline.process_frame(
            frame_bgr, exercise_profile=self.body_mode
        )
        infer_ms = (time.perf_counter() - t_infer_start) * 1000.0

        # Server-side throughput, reported in place of the webcam's stream.fps.
        now = time.time()
        if self._last_done is not None:
            dt = now - self._last_done
            if dt > 1e-6:
                inst = 1.0 / dt
                self._fps = inst if self._fps <= 0 else (0.85 * self._fps + 0.15 * inst)
        self._last_done = now
        # ORDER MATTERS HERE — this block used to sit above the analysis call and
        # read `analysis_ms` before it was assigned. Python raised UnboundLocalError
        # on EVERY frame, the exception propagated out of the worker, and the client
        # got no `pose` reply at all: a green socket, 0 fps, 0 ms, and no skeleton,
        # with nothing on screen to suggest the server was the problem. The
        # measurement must therefore be taken before it is reported.
        telemetry["fps"] = round(self._fps, 1)
        telemetry["infer_ms"] = round(infer_ms, 1)
        telemetry["hands_on"] = bool(self.hands_enabled)
        telemetry["complexity"] = int(self.model_complexity)

        t_analysis = time.perf_counter()
        physio_telemetry = self.physio_engine.analyze_frame(angles_dict, landmarks_dict, telemetry)
        analysis_ms = (time.perf_counter() - t_analysis) * 1000.0
        telemetry["analysis_ms"] = round(analysis_ms, 1)

        # Records layer. A pure consumer of what the engine just produced: it is
        # handed the finished dicts and cannot feed anything back. Wrapped in
        # try/except on purpose — a bookkeeping fault must never take down the
        # live clinical view the patient is standing in front of.
        if self.recorder is not None:
            try:
                self.recorder.on_frame(angles_dict, physio_telemetry)
            except Exception as exc:  # noqa: BLE001
                print(f"[{self.client_label}] recorder error (ignored): {exc}")

        active_tracks = []
        if landmarks_dict and telemetry.get("person_detected", False):
            active_tracks = self.tracker.update([landmarks_dict])
        track_id = active_tracks[0][0] if active_tracks else 1

        # Only pay the rendering cost when a capture is actually being produced.
        if self._want_screenshot or self.logger.is_recording:
            annotated = self.gui.render(
                frame_bgr=frame_bgr,
                landmarks_dict=landmarks_dict,
                angles_dict=angles_dict,
                telemetry_dict=telemetry,
                physio_telemetry=physio_telemetry,
                body_mode=self.body_mode,
                is_recording=self.logger.is_recording,
                track_id=track_id,
            )
            if self.logger.is_recording:
                self.logger.record_frame(annotated)
            if self._want_screenshot:
                self._want_screenshot = False
                path = self.logger.take_screenshot(annotated)
                telemetry["screenshot_saved"] = os.path.basename(path) if path else None

        return {
            "type": "pose",
            "landmarks": slim_landmarks(landmarks_dict, w, h),
            "angles": jsonable(angles_dict or {}),
            "telemetry": jsonable(telemetry or {}),
            "physio": jsonable(physio_telemetry or {}),
            "track_id": int(track_id),
            "body_mode": self.body_mode,
            "is_recording": bool(self.logger.is_recording),
            "hands_enabled": bool(self.hands_enabled),
            "exercise_active": self.recorder is not None,
            "exercise_reps": (self.recorder._reps if self.recorder is not None else 0),
            "records_session_id": self.records_session_id,
            "server_fps": round(self._fps, 1),
            "frame_w": int(w),
            "frame_h": int(h),
        }

    def close(self) -> None:
        try:
            self.logger.stop_recording()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.pipeline.close()
        except Exception:  # noqa: BLE001
            pass


# ====================================================================================
# FASTAPI APP
# ====================================================================================
CONFIG = load_config()
app = FastAPI(title="AI Physiotherapy LAN Inference Server", version="1.0.0")

# ------------------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------------------
# The Flutter web build is served by Flutter's own dev server on a random
# localhost port, so its calls to /health are cross-origin and the browser
# blocks them unless we say otherwise. WebSocket upgrades are not subject to
# CORS, which is why the socket would connect while the pre-flight health check
# mysteriously failed without this.
#
# allow_origins=["*"] is appropriate here: this server binds to a private LAN,
# serves no credentials and holds no session state. It should not be exposed to
# the public internet with or without this setting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_stats = {"connections": 0, "frames": 0, "dropped": 0, "started": time.time()}


# ------------------------------------------------------------------------------
# PATIENT RECORDS API
# ------------------------------------------------------------------------------
# Mounted, not merged. Records live behind /api on the same port so the Flutter
# client needs one address, but the router is a separate module and the
# WebSocket frame path above is unchanged.
#
# Failure here is non-fatal by design: if the records package cannot load, the
# server still does what it has always done and the app simply cannot save
# sessions.
try:
    from records.api import router as records_router
    from records import get_db

    app.include_router(records_router)
    _RECORDS_DB = get_db()
    RECORDS_AVAILABLE = True
    print(f"[records] database ready: {_RECORDS_DB.path}")
except Exception as _rec_exc:  # noqa: BLE001
    RECORDS_AVAILABLE = False
    print(f"[records] DISABLED — {type(_rec_exc).__name__}: {_rec_exc}")
    print("[records] the live view is unaffected; sessions just will not be saved.")


@app.get("/health")
async def health() -> JSONResponse:
    """Used by the Flutter app's 'Test connection' button before opening the socket."""
    return JSONResponse({
        "ok": True,
        "service": "ai-physiotherapy-lan-server",
        "version": "1.0.0",
        "modes": list(VALID_MODES),
        "filters": list(VALID_FILTERS),
        "uptime_s": round(time.time() - _stats["started"], 1),
        "active_connections": _stats["connections"],
        "frames_processed": _stats["frames"],
        "frames_dropped": _stats["dropped"],
    })


@app.get("/")
async def index() -> HTMLResponse:
    urls = "".join(f"<li><code>ws://{ip}:{PORT}/ws</code></li>" for ip in lan_ips())
    return HTMLResponse(
        "<html><body style='font-family:system-ui;background:#0B1220;color:#E6EDF7;padding:32px'>"
        "<h2 style='color:#22D3EE'>AI Physiotherapy LAN Inference Server</h2>"
        "<p>Server is running. Point the Flutter Android app at one of these:</p>"
        f"<ul>{urls}</ul>"
        "<p style='color:#8FA3BF'>Phone and PC must be on the same Wi-Fi network.</p>"
        "</body></html>"
    )



# ====================================================================================
# PATIENT RECORDS — WEBSOCKET CONTROL HANDLERS
# ====================================================================================
# These sit between the live socket and the records package. They exist here, in
# the server, rather than inside `records/` because they need the live
# PhysioSession; `records/` itself stays free of any dependency on the inference
# stack so it can be tested without a camera or a model.
#
# Every handler returns a plain dict for the socket and never raises: a records
# fault must degrade to "recording unavailable", not interrupt a patient's
# session.
# ====================================================================================

def _records_repo():
    from records import get_db, Repository
    return Repository(get_db())


def _records_error(stage: str, exc: Exception) -> Dict[str, Any]:
    print(f"[records] {stage} failed: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    return {"type": "records_error", "stage": stage,
            "message": f"{type(exc).__name__}: {exc}"}


def _records_session_start(session: "PhysioSession", ctl: Dict[str, Any]) -> Dict[str, Any]:
    try:
        patient_id = int(ctl.get("patient_id"))
        repo = _records_repo()
        rec_session = repo.start_session(patient_id, notes=ctl.get("notes"))
        session.records_session_id = rec_session["id"]
        session.records_patient_id = patient_id

        # A fresh ROM accumulator per patient session, so yesterday's peaks do
        # not leak into today's numbers.
        session.reset_rom()

        plan = repo.todays_plan(patient_id)
        return {"type": "session_started",
                "session_id": rec_session["id"],
                "day_index": rec_session["day_index"],
                "patient": plan["patient"],
                "condition": (plan["assignment"] or {}).get("condition_name"),
                "exercises": plan["exercises"]}
    except Exception as exc:  # noqa: BLE001
        return _records_error("session_start", exc)


def _records_exercise_start(session: "PhysioSession", ctl: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from records import SessionRecorder

        if session.records_session_id is None:
            return {"type": "records_error", "stage": "exercise_start",
                    "message": "No records session open. Send session_start first."}

        exercise_id = int(ctl.get("exercise_id"))
        repo = _records_repo()
        rec_session = repo.get_session(session.records_session_id)
        exercise = repo.get_exercise(exercise_id)
        if not exercise:
            return {"type": "records_error", "stage": "exercise_start",
                    "message": f"unknown exercise {exercise_id}"}

        # Targets come from the protocol for the condition the patient is on.
        protocol_row: Dict[str, Any] = {}
        if rec_session and rec_session.get("condition_id"):
            for row in repo.protocol_for_condition(rec_session["condition_id"]):
                if row["exercise_id"] == exercise_id:
                    protocol_row = row
                    break

        # Switch the pose profile to whatever this exercise needs, so the patient
        # is not left in upper-body mode for a knee exercise.
        if exercise.get("body_mode"):
            session.set_mode(exercise["body_mode"])

        recorder = SessionRecorder(exercise=exercise, protocol=protocol_row)
        recorder.start()
        session.recorder = recorder
        session.recorder_context = {
            "exercise": exercise,
            "protocol": protocol_row,
            "sequence": int(ctl.get("sequence", protocol_row.get("sequence", 1))),
        }
        return {"type": "exercise_started",
                "exercise_id": exercise_id,
                "name": exercise["name"],
                "body_mode": exercise.get("body_mode"),
                "primary_joint": exercise["primary_joint"],
                "movement_type": exercise.get("movement_type"),
                "goal": exercise.get("goal"),
                "instructions": exercise.get("instructions"),
                "target_rom_deg": protocol_row.get("target_rom_deg"),
                "target_reps": protocol_row.get("target_reps"),
                "target_hold_sec": protocol_row.get("target_hold_sec"),
                "band_min_deg": protocol_row.get("band_min_deg"),
                "band_max_deg": protocol_row.get("band_max_deg")}
    except Exception as exc:  # noqa: BLE001
        return _records_error("exercise_start", exc)


def _records_exercise_stop(session: "PhysioSession", ctl: Dict[str, Any]) -> Dict[str, Any]:
    try:
        recorder = session.recorder
        if recorder is None:
            return {"type": "records_error", "stage": "exercise_stop",
                    "message": "no exercise in progress"}

        aborted = bool(ctl.get("aborted"))
        summary = recorder.abort() if aborted else recorder.finish()
        joints = recorder.joint_summaries()
        samples = recorder.samples

        ctx = session.recorder_context or {}
        exercise = ctx.get("exercise", {})
        session.recorder = None
        session.recorder_context = {}

        repo = _records_repo()

        # The previous attempt at this same exercise, so the patient sees whether
        # today beat last time without waiting for a report.
        previous = None
        if session.records_patient_id:
            history = repo.exercise_history(session.records_patient_id, exercise["id"])
            if history:
                previous = history[-1]

        saved = repo.save_exercise_result(
            session_id=session.records_session_id,
            exercise_id=exercise["id"],
            summary=summary,
            joint_summaries=joints,
            samples=samples,
            sequence=ctx.get("sequence", 1),
        )

        comparison = None
        if previous:
            metric = "rom_range_deg" if exercise.get("movement_type") == "REP" else "rom_max_deg"
            prev_v, now_v = previous.get(metric), summary.get(metric)
            if prev_v is not None and now_v is not None:
                delta = round(now_v - prev_v, 1)
                better = delta > 0 if exercise.get("goal", "INCREASE") == "INCREASE" else delta < 0
                comparison = {"previous_day": previous["day_index"],
                              "previous_value": prev_v,
                              "current_value": now_v,
                              "change_deg": delta,
                              "improved": better}

        return {"type": "exercise_saved",
                "result_id": saved["id"],
                "summary": summary,
                "joints": joints,
                "comparison": comparison}
    except Exception as exc:  # noqa: BLE001
        session.recorder = None
        return _records_error("exercise_stop", exc)


def _records_session_end(session: "PhysioSession", ctl: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if session.records_session_id is None:
            return {"type": "records_error", "stage": "session_end",
                    "message": "no records session open"}

        # An exercise still running when the session ends is saved, not lost,
        # but flagged aborted so it is excluded from trend lines.
        if session.recorder is not None:
            _records_exercise_stop(session, {"aborted": True})

        repo = _records_repo()
        ended = repo.end_session(session.records_session_id, notes=ctl.get("notes"))
        results = repo.results_for_session(session.records_session_id)
        sid = session.records_session_id
        session.records_session_id = None

        return {"type": "session_ended",
                "session_id": sid,
                "day_index": (ended or {}).get("day_index"),
                "exercises_completed": len([r for r in results if not r["aborted"]]),
                "results": results}
    except Exception as exc:  # noqa: BLE001
        return _records_error("session_end", exc)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    """
    Latest-frame-wins video socket.

    Two cooperating coroutines:
      * this receive loop  - drains the socket as fast as the phone sends, keeping only
                             the newest frame in `slot`. Never blocks on inference.
      * worker()           - runs the pipeline in a thread executor and replies.

    Dropping stale frames instead of queueing them is what keeps latency flat: it is
    the same policy as live_pose.py's queue(maxsize=2) with get_nowait() eviction.
    """
    await ws.accept()

    peer = f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"
    label = f"CLIENT {peer}"
    _stats["connections"] += 1
    print(f"[+] {label} connected.")

    loop = asyncio.get_running_loop()
    session = PhysioSession(CONFIG, label)

    slot: Dict[str, Any] = {"frame": None, "seq": -1}
    frame_ready = asyncio.Event()
    closing = asyncio.Event()
    last_frame_for_capture: Dict[str, Any] = {"frame": None}

    await ws.send_text(json.dumps({
        "type": "hello",
        "server": "ai-physiotherapy-lan-server",
        "version": "1.0.0",
        "body_mode": session.body_mode,
        "filter": session.pipeline.filter_manager.filter_type,
        "modes": list(VALID_MODES),
        "filters": list(VALID_FILTERS),
    }))

    async def worker() -> None:
        while not closing.is_set():
            try:
                await asyncio.wait_for(frame_ready.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            frame_ready.clear()
            frame = slot["frame"]
            seq = slot["seq"]
            slot["frame"] = None
            if frame is None:
                continue

            try:
                result = await loop.run_in_executor(None, session.process, frame)
            except Exception as exc:  # noqa: BLE001
                # Tell the CLIENT, not just this terminal.
                #
                # A per-frame inference failure used to be printed here and
                # swallowed. The app kept its socket open and green, so the only
                # symptom was a permanently empty skeleton — the user had no way
                # to know the server was rejecting every frame. Forwarding the
                # message makes a server-side fault visible where the user is
                # actually looking. Rate-limited to once every 2 s so a
                # persistent fault cannot flood the socket.
                print(f"[{label}] Inference error: {exc}")
                traceback.print_exc()
                now = time.time()
                if now - _stats.get("last_err_sent", 0.0) > 2.0:
                    _stats["last_err_sent"] = now
                    try:
                        await ws.send_text(json.dumps({
                            "type": "error",
                            "stage": "inference",
                            "message": f"{type(exc).__name__}: {exc}",
                        }))
                    except Exception:  # noqa: BLE001
                        closing.set()
                        return
                continue

            result["seq"] = seq
            _stats["frames"] += 1

            try:
                await ws.send_text(json.dumps(result))
            except Exception:  # noqa: BLE001
                closing.set()
                return

    worker_task = asyncio.create_task(worker())

    try:
        while True:
            msg = await ws.receive()

            if msg.get("type") == "websocket.disconnect":
                break

            # ---------------- control messages ----------------
            text = msg.get("text")
            if text:
                try:
                    ctl = json.loads(text)
                except json.JSONDecodeError:
                    continue

                kind = ctl.get("type")
                if kind == "set_mode":
                    mode = session.set_mode(ctl.get("mode"))
                    await ws.send_text(json.dumps({"type": "ack", "body_mode": mode}))
                elif kind == "set_filter":
                    flt = session.set_filter(ctl.get("filter"))
                    await ws.send_text(json.dumps({"type": "ack", "filter": flt}))
                elif kind == "set_complexity":
                    c = session.set_complexity(ctl.get("complexity", 1))
                    await ws.send_text(json.dumps({"type": "ack", "complexity": c}))
                elif kind == "set_hands":
                    on = session.set_hands(ctl.get("on", True))
                    await ws.send_text(json.dumps({"type": "ack", "hands_enabled": on}))
                elif kind == "reset_rom":
                    session.reset_rom()
                    await ws.send_text(json.dumps({"type": "ack", "reset_rom": True}))
                elif kind == "screenshot":
                    session.request_screenshot()
                    await ws.send_text(json.dumps({"type": "ack", "screenshot": "queued"}))
                elif kind == "record":
                    on = bool(ctl.get("on", not session.logger.is_recording))
                    rec = session.toggle_record(on, last_frame_for_capture["frame"])
                    await ws.send_text(json.dumps({"type": "ack", "is_recording": rec}))
                elif kind == "session_start":
                    # Patient has been identified; open a records session.
                    reply = _records_session_start(session, ctl)
                    await ws.send_text(json.dumps(reply))
                elif kind == "session_end":
                    reply = _records_session_end(session, ctl)
                    await ws.send_text(json.dumps(reply))
                elif kind == "exercise_start":
                    reply = _records_exercise_start(session, ctl)
                    await ws.send_text(json.dumps(reply))
                elif kind == "exercise_stop":
                    reply = _records_exercise_stop(session, ctl)
                    await ws.send_text(json.dumps(reply))
                elif kind == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "t": ctl.get("t")}))
                continue

            # ---------------- binary video frame ----------------
            data = msg.get("bytes")
            if not data or len(data) < 4:
                continue

            hlen = struct.unpack_from("<I", data, 0)[0]
            if hlen <= 0 or hlen > 4096 or 4 + hlen > len(data):
                _stats["dropped"] += 1
                continue

            try:
                header = json.loads(data[4:4 + hlen].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _stats["dropped"] += 1
                continue

            payload = data[4 + hlen:]

            frame = decode_payload(
                payload,
                int(header.get("w", 0)),
                int(header.get("h", 0)),
                str(header.get("fmt", "nv21")),
            )
            if frame is None:
                _stats["dropped"] += 1
                continue

            frame = orient_frame(frame, header.get("rot", 0), bool(header.get("mirror", False)))

            # A mode carried on the frame header keeps switching perfectly in sync
            # with the pixels it applies to, even if a control message is in flight.
            hdr_mode = str(header.get("mode", "")).upper()
            if hdr_mode in VALID_MODES and hdr_mode != session.body_mode:
                session.set_mode(hdr_mode)

            last_frame_for_capture["frame"] = frame

            if slot["frame"] is not None:
                _stats["dropped"] += 1  # superseded before it was ever processed
            slot["frame"] = frame
            slot["seq"] = int(header.get("seq", -1))
            frame_ready.set()

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] Socket error: {exc}")
    finally:
        closing.set()
        frame_ready.set()
        worker_task.cancel()
        session.close()
        _stats["connections"] = max(0, _stats["connections"] - 1)
        print(f"[-] {label} disconnected.")


# ====================================================================================
# LAN DISCOVERY + BANNER
# ====================================================================================
PORT = 8765


def lan_ips() -> list:
    """Best-effort list of this machine's LAN addresses, most-likely-first."""
    ips = []

    # The UDP-connect trick reveals the interface that actually routes outward,
    # which is the one the phone will be able to reach.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass

    return ips or ["127.0.0.1"]


def print_banner(host: str, port: int) -> None:
    line = "=" * 78
    print("\n" + line)
    print("  AI PHYSIOTHERAPY PLATFORM - LAN INFERENCE SERVER")
    print(line)
    print(f"  Bound to           : {host}:{port}")
    print("  Pipeline           : RealTimeInferencePipeline (unmodified)")
    print("  Clinical engine    : PhysiotherapyAngleEngine + PhysiotherapyAnalysisEngine")
    print(f"  Default filter     : {(CONFIG.get('filter') or {}).get('default_filter', 'one_euro')}")
    print(line)
    print("  ENTER ONE OF THESE IN THE ANDROID APP:")
    for ip in lan_ips():
        print(f"    ws://{ip}:{port}/ws")
    print(line)
    print("  Phone and PC MUST be on the same Wi-Fi network.")
    print("  On first run Windows will ask to allow Python through the firewall -> ALLOW,")
    print("  and make sure 'Private networks' is ticked.")
    print(f"  Health check: http://{lan_ips()[0]}:{port}/health")
    print(line + "\n")


def main() -> None:
    global PORT

    parser = argparse.ArgumentParser(description="AI Physiotherapy LAN inference server")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default: 8765)")
    args = parser.parse_args()

    PORT = args.port
    print_banner(args.host, args.port)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", ws_ping_interval=None)


if __name__ == "__main__":
    main()

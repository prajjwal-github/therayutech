"""
Turns the live telemetry stream into one stored exercise result.

READ THIS BEFORE CHANGING ANYTHING
==================================
This class is a pure consumer. It is handed the dicts the clinical engine has
already produced — `angles_dict` from PhysiotherapyAngleEngine and
`physio_telemetry` from PhysiotherapyAnalysisEngine — and it derives counts and
summaries from them. It does not compute a single anatomical angle of its own,
does not import the engine, and cannot alter what the engine reports.

That constraint is deliberate. The angle path was measured and corrected against
rendered output; anything that recomputes geometry here would be a second,
unverified source of truth for the same clinical number.

REP COUNTING
Reps are counted with a two-threshold state machine (a Schmitt trigger) rather
than a single crossing. With one threshold, a joint hovering at the boundary
produces dozens of phantom reps from a few degrees of jitter. Requiring the
angle to travel past a high mark and then back below a low mark makes the count
robust to the ±5 degrees of frame-to-frame noise the tracker actually shows.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Joints the analysis engine tracks. Mirrored here so this module never has to
# import the engine; if the engine's list grows, unknown joints are simply
# carried through by name.
_FALLBACK_JOINTS = [
    "elbow_flexion_left", "elbow_flexion_right",
    "shoulder_abduction_left", "shoulder_abduction_right",
    "hip_flexion_left", "hip_flexion_right",
    "knee_flexion_left", "knee_flexion_right",
    "ankle_flexion_left", "ankle_flexion_right",
    "trunk_posture", "pelvic_tilt", "neck_inclination",
]

# How often the trace is written out for the progress charts. The live stream is
# 8-30 fps; storing all of it would bloat the database for no visual gain.
SAMPLE_HZ = 2.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionRecorder:
    """
    One instance per exercise attempt.

        rec = SessionRecorder(exercise=..., protocol=...)
        rec.start()
        ... rec.on_frame(angles, physio_telemetry) for each server frame ...
        summary = rec.finish()
    """

    def __init__(self, exercise: Dict[str, Any],
                 protocol: Optional[Dict[str, Any]] = None,
                 sample_hz: float = SAMPLE_HZ):
        self.exercise = exercise
        self.protocol = protocol or {}

        self.primary_joint: str = exercise["primary_joint"]
        self.mirror_joint: Optional[str] = exercise.get("mirror_joint")
        self.goal: str = exercise.get("goal", "INCREASE")
        self.movement_type: str = exercise.get("movement_type", "REP")

        self.target_rom: Optional[float] = self.protocol.get("target_rom_deg")
        self.target_reps: Optional[int] = self.protocol.get("target_reps")
        self.target_hold: Optional[int] = self.protocol.get("target_hold_sec")
        self.band_min: Optional[float] = self.protocol.get("band_min_deg")
        self.band_max: Optional[float] = self.protocol.get("band_max_deg")

        self._sample_interval = 1.0 / max(0.2, sample_hz)

        # -- accumulators -----------------------------------------------------
        self.started_at: Optional[str] = None
        self.ended_at: Optional[str] = None
        self._t0: Optional[float] = None
        self._last_t: Optional[float] = None
        self._last_sample_t: float = -1e9

        self.frames: int = 0
        self.aborted: bool = False

        self._joint_acc: Dict[str, Dict[str, float]] = {}
        self._quality_sum: float = 0.0
        self._quality_n: int = 0

        self._in_target_sec: float = 0.0
        self._elapsed_sec: float = 0.0
        self._hold_sec: float = 0.0

        self._reps: int = 0
        self._armed: bool = False       # True once the high threshold was crossed
        self._sym_sum: float = 0.0
        self._sym_n: int = 0

        self.samples: List[Dict[str, Any]] = []

    # -- rep thresholds -------------------------------------------------------

    @property
    def _high_threshold(self) -> Optional[float]:
        """
        Angle the patient must reach for the movement to count as performed.

        This is `band_min` — the floor of the prescribed band — because entering
        the band IS doing the repetition.

        An earlier version put this at 65 percent of the way UP the band, which
        conflated two different things: the band is the range a rep is allowed
        to occupy, not the range the limb travels through. For frozen shoulder
        (band 60-170) that put the bar at 131 degrees, so a patient sweeping a
        perfectly good 15-120 degrees scored zero reps.
        """
        if self.band_min is not None:
            return self.band_min
        if self.target_rom:
            return 0.7 * self.target_rom
        return None

    @property
    def _low_threshold(self) -> Optional[float]:
        """
        Angle the limb must return below before the next rep can be counted.

        Set one hysteresis gap beneath the high threshold. Without the gap, a
        limb held at the boundary would tick the counter on every frame of
        tracker jitter; the tracker moves about 5 degrees frame to frame, so the
        gap is never allowed below 10.
        """
        hi = self._high_threshold
        if hi is None:
            return None
        if self.band_min is not None and self.band_max is not None:
            gap = max(10.0, 0.15 * (self.band_max - self.band_min))
        elif self.target_rom:
            gap = max(10.0, 0.15 * self.target_rom)
        else:
            gap = 10.0
        return max(0.0, hi - gap)

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        self.started_at = _utc()
        self._t0 = time.monotonic()
        self._last_t = self._t0

    def on_frame(self, angles: Optional[Dict[str, Any]],
                 physio: Optional[Dict[str, Any]] = None,
                 now: Optional[float] = None) -> None:
        """
        Feed one server reply in. Safe to call with junk: frames where the
        patient is out of position carry zeroed angles and are skipped rather
        than dragging the session's minimum down to zero.
        """
        if self._t0 is None:
            self.start()

        now = now if now is not None else time.monotonic()
        dt = max(0.0, min(1.0, now - (self._last_t or now)))
        self._last_t = now
        self._elapsed_sec += dt

        if not angles:
            return

        # The engine zeroes every angle while framing is invalid and sets
        # is_ready False. Those frames are real elapsed time but not real
        # measurements, so they count towards duration and nothing else.
        if physio is not None and physio.get("rom_summary") == {}:
            return

        self.frames += 1

        # -- every numeric joint, for compensation analysis --------------------
        for key, val in angles.items():
            if not isinstance(val, (int, float)):
                continue
            if key not in _FALLBACK_JOINTS and not key.endswith(
                    ("_left", "_right", "_posture", "_tilt", "_inclination")):
                continue
            if val <= 0.0:
                continue
            acc = self._joint_acc.setdefault(
                key, {"min": float("inf"), "max": 0.0, "sum": 0.0, "n": 0.0})
            acc["min"] = min(acc["min"], float(val))
            acc["max"] = max(acc["max"], float(val))
            acc["sum"] += float(val)
            acc["n"] += 1.0

        primary = angles.get(self.primary_joint)
        if not isinstance(primary, (int, float)) or primary <= 0.0:
            return

        # -- quality -----------------------------------------------------------
        if physio:
            q = physio.get("movement_quality_pct")
            if isinstance(q, (int, float)) and q > 0:
                self._quality_sum += float(q)
                self._quality_n += 1

        # -- symmetry ----------------------------------------------------------
        if self.mirror_joint:
            mirror = angles.get(self.mirror_joint)
            if isinstance(mirror, (int, float)) and mirror > 0.0:
                self._sym_sum += abs(float(primary) - float(mirror))
                self._sym_n += 1

        # -- time inside the prescribed band -----------------------------------
        if self._within_band(float(primary)):
            self._in_target_sec += dt
            if self.movement_type == "HOLD":
                self._hold_sec += dt

        # -- rep state machine --------------------------------------------------
        if self.movement_type == "REP":
            hi, lo = self._high_threshold, self._low_threshold
            if hi is not None and lo is not None:
                if not self._armed and primary >= hi:
                    self._armed = True
                elif self._armed and primary <= lo:
                    self._armed = False
                    self._reps += 1

        # -- downsampled trace --------------------------------------------------
        if now - self._last_sample_t >= self._sample_interval:
            self._last_sample_t = now
            t_ms = int((now - self._t0) * 1000)
            self.samples.append({"t_ms": t_ms,
                                 "joint_key": self.primary_joint,
                                 "value_deg": round(float(primary), 1)})
            if self.mirror_joint:
                m = angles.get(self.mirror_joint)
                if isinstance(m, (int, float)) and m > 0:
                    self.samples.append({"t_ms": t_ms,
                                         "joint_key": self.mirror_joint,
                                         "value_deg": round(float(m), 1)})

    def _within_band(self, value: float) -> bool:
        if self.band_min is not None and value < self.band_min:
            return False
        if self.band_max is not None and value > self.band_max:
            return False
        return self.band_min is not None or self.band_max is not None

    def abort(self) -> Dict[str, Any]:
        self.aborted = True
        return self.finish()

    def finish(self) -> Dict[str, Any]:
        self.ended_at = _utc()
        primary = self._joint_acc.get(self.primary_joint)

        rom_min = rom_max = rom_range = None
        if primary and primary["n"] > 0:
            rom_min = round(primary["min"], 1)
            rom_max = round(primary["max"], 1)
            rom_range = round(rom_max - rom_min, 1)

        # Percent of target respects the direction of improvement: for a REDUCE
        # goal, staying BELOW the target is 100 percent, not zero.
        pct_target = None
        if self.target_rom:
            if self.goal == "INCREASE" and rom_range is not None:
                pct_target = round(min(150.0, rom_range / self.target_rom * 100.0), 1)
            elif self.goal == "REDUCE" and rom_max is not None:
                pct_target = round(min(150.0, self.target_rom / max(rom_max, 0.1) * 100.0), 1)

        return {
            "exercise_id": self.exercise.get("id") or self.exercise.get("exercise_id"),
            "exercise_code": self.exercise.get("code"),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_sec": round(self._elapsed_sec, 1),
            "rom_min_deg": rom_min,
            "rom_max_deg": rom_max,
            "rom_range_deg": rom_range,
            "target_rom_deg": self.target_rom,
            "rom_pct_of_target": pct_target,
            "reps_completed": self._reps,
            "target_reps": self.target_reps,
            "hold_sec_total": round(self._hold_sec, 1),
            "target_hold_sec": self.target_hold,
            "mean_quality_pct": (round(self._quality_sum / self._quality_n, 1)
                                 if self._quality_n else None),
            "in_target_pct": (round(self._in_target_sec / self._elapsed_sec * 100.0, 1)
                              if self._elapsed_sec > 0 else None),
            "symmetry_delta": (round(self._sym_sum / self._sym_n, 1)
                               if self._sym_n else None),
            "frames_analysed": self.frames,
            "aborted": self.aborted,
        }

    def joint_summaries(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for key, acc in self._joint_acc.items():
            if acc["n"] <= 0:
                continue
            out[key] = {
                "min": round(acc["min"], 1),
                "max": round(acc["max"], 1),
                "mean": round(acc["sum"] / acc["n"], 1),
                "range": round(acc["max"] - acc["min"], 1),
            }
        return out

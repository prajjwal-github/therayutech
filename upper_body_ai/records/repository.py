"""
Every query the records layer needs, in one place.

Nothing here imports MediaPipe, OpenCV or any part of the inference stack. The
records layer is downstream of the clinical engine and must stay that way: it
reads the numbers the engine already produces and never influences them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .db import Database, utc_now


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # =========================================================== patients ====

    def next_patient_code(self) -> str:
        row = self.db.query_one("SELECT COUNT(*) AS c FROM patients")
        return f"THR-{(row['c'] or 0) + 1:04d}"

    def create_patient(self, full_name: str, date_of_birth: Optional[str] = None,
                       sex: Optional[str] = None, phone: Optional[str] = None,
                       notes: Optional[str] = None,
                       code: Optional[str] = None) -> Dict[str, Any]:
        if not (full_name or "").strip():
            raise ValueError("patient name is required")
        code = code or self.next_patient_code()
        pid = self.db.execute(
            """INSERT INTO patients (code, full_name, date_of_birth, sex, phone,
                                     notes, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (code, full_name.strip(), date_of_birth, sex, phone, notes, utc_now()),
        )
        return self.get_patient(pid)

    def get_patient(self, patient_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one("SELECT * FROM patients WHERE id = ?", (patient_id,))

    def find_patient_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        return self.db.query_one("SELECT * FROM patients WHERE code = ?", (code,))

    def list_patients(self, search: Optional[str] = None,
                      include_archived: bool = False) -> List[Dict[str, Any]]:
        sql = """
            SELECT p.*,
                   (SELECT COUNT(*) FROM sessions s WHERE s.patient_id = p.id)
                       AS session_count,
                   (SELECT MAX(s.started_at) FROM sessions s WHERE s.patient_id = p.id)
                       AS last_session_at,
                   (SELECT c.name FROM assignments a
                      JOIN conditions c ON c.id = a.condition_id
                     WHERE a.patient_id = p.id AND a.active = 1
                     ORDER BY a.assigned_at DESC LIMIT 1) AS active_condition
              FROM patients p
             WHERE (? = 1 OR p.archived = 0)
        """
        params: List[Any] = [1 if include_archived else 0]
        if search:
            sql += " AND (p.full_name LIKE ? OR p.code LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY p.full_name COLLATE NOCASE"
        return self.db.query(sql, params)

    def update_patient(self, patient_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {"full_name", "date_of_birth", "sex", "phone", "notes", "archived"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if sets:
            clause = ", ".join(f"{k} = ?" for k in sets)
            self.db.execute(f"UPDATE patients SET {clause} WHERE id = ?",
                            list(sets.values()) + [patient_id])
        return self.get_patient(patient_id)

    # ========================================================== catalogue ====

    def list_conditions(self) -> List[Dict[str, Any]]:
        return self.db.query(
            """SELECT c.*,
                      (SELECT COUNT(*) FROM protocols p WHERE p.condition_id = c.id)
                          AS exercise_count
                 FROM conditions c ORDER BY c.body_region, c.name"""
        )

    def get_condition(self, condition_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one("SELECT * FROM conditions WHERE id = ?", (condition_id,))

    def protocol_for_condition(self, condition_id: int) -> List[Dict[str, Any]]:
        """The prescribed exercise list, in order, with targets resolved."""
        return self.db.query(
            """
            SELECT p.id            AS protocol_id,
                   p.sequence,
                   p.target_rom_deg, p.target_reps, p.target_hold_sec,
                   p.band_min_deg,  p.band_max_deg,
                   e.id            AS exercise_id,
                   e.code, e.name, e.body_mode, e.primary_joint, e.mirror_joint,
                   e.movement_type, e.goal, e.instructions
              FROM protocols p
              JOIN exercises e ON e.id = p.exercise_id
             WHERE p.condition_id = ?
             ORDER BY p.sequence
            """,
            (condition_id,),
        )

    def get_exercise(self, exercise_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one("SELECT * FROM exercises WHERE id = ?", (exercise_id,))

    # ======================================================== assignments ====

    def assign_condition(self, patient_id: int, condition_id: int,
                         clinician_id: Optional[int] = None,
                         notes: Optional[str] = None) -> Dict[str, Any]:
        """
        A clinician puts a patient on a condition's protocol.

        Previous assignments are deactivated rather than deleted, so the record
        of what a patient was being treated for at the time of any past session
        survives a change of plan.
        """
        self.db.execute(
            "UPDATE assignments SET active = 0 WHERE patient_id = ? AND active = 1",
            (patient_id,),
        )
        aid = self.db.execute(
            """INSERT INTO assignments
                   (patient_id, condition_id, clinician_id, assigned_at, active, notes)
               VALUES (?,?,?,?,1,?)""",
            (patient_id, condition_id, clinician_id, utc_now(), notes),
        )
        return self.db.query_one("SELECT * FROM assignments WHERE id = ?", (aid,))

    def active_assignment(self, patient_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one(
            """SELECT a.*, c.code AS condition_code, c.name AS condition_name,
                      c.body_region
                 FROM assignments a
                 JOIN conditions c ON c.id = a.condition_id
                WHERE a.patient_id = ? AND a.active = 1
                ORDER BY a.assigned_at DESC LIMIT 1""",
            (patient_id,),
        )

    def todays_plan(self, patient_id: int) -> Dict[str, Any]:
        """
        Everything the patient screen needs after picking their name: who they
        are, what they are being treated for, and the exercise list in order.
        """
        patient = self.get_patient(patient_id)
        if not patient:
            raise ValueError(f"no patient {patient_id}")
        assignment = self.active_assignment(patient_id)
        if not assignment:
            return {"patient": patient, "assignment": None, "exercises": [],
                    "message": "No condition assigned yet. Ask your clinician."}
        return {
            "patient": patient,
            "assignment": assignment,
            "exercises": self.protocol_for_condition(assignment["condition_id"]),
            "day_index": self._next_day_index(patient_id),
        }

    # ============================================================ sessions ====

    def _next_day_index(self, patient_id: int) -> int:
        """
        Days elapsed since the patient's first ever session, 1-based.

        Calendar days, not session count: a patient who trains twice on Tuesday
        is still on day 2, which is what "day 1 versus day 10" means clinically.
        """
        first = self.db.query_one(
            "SELECT MIN(started_at) AS first_at FROM sessions WHERE patient_id = ?",
            (patient_id,),
        )
        first_at = _parse(first["first_at"] if first else None)
        if not first_at:
            return 1
        now = datetime.now(timezone.utc)
        return int((now.date() - first_at.date()).days) + 1

    def start_session(self, patient_id: int,
                      notes: Optional[str] = None) -> Dict[str, Any]:
        assignment = self.active_assignment(patient_id)
        sid = self.db.execute(
            """INSERT INTO sessions
                   (patient_id, assignment_id, condition_id, started_at, day_index, notes)
               VALUES (?,?,?,?,?,?)""",
            (patient_id,
             assignment["id"] if assignment else None,
             assignment["condition_id"] if assignment else None,
             utc_now(), self._next_day_index(patient_id), notes),
        )
        return self.get_session(sid)

    def end_session(self, session_id: int,
                    notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if notes is None:
            self.db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?",
                            (utc_now(), session_id))
        else:
            self.db.execute(
                "UPDATE sessions SET ended_at = ?, notes = ? WHERE id = ?",
                (utc_now(), notes, session_id))
        return self.get_session(session_id)

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one(
            """SELECT s.*, p.full_name, p.code AS patient_code,
                      c.name AS condition_name
                 FROM sessions s
                 JOIN patients p   ON p.id = s.patient_id
            LEFT JOIN conditions c ON c.id = s.condition_id
                WHERE s.id = ?""",
            (session_id,),
        )

    def list_sessions(self, patient_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """SELECT s.*, c.name AS condition_name,
                      (SELECT COUNT(*) FROM exercise_results r WHERE r.session_id = s.id)
                          AS exercise_count
                 FROM sessions s
            LEFT JOIN conditions c ON c.id = s.condition_id
                WHERE s.patient_id = ?
                ORDER BY s.started_at""",
            (patient_id,),
        )

    # ==================================================== exercise results ====

    def save_exercise_result(self, session_id: int, exercise_id: int,
                             summary: Dict[str, Any],
                             joint_summaries: Optional[Dict[str, Dict[str, float]]] = None,
                             samples: Optional[List[Dict[str, Any]]] = None,
                             sequence: int = 1) -> Dict[str, Any]:
        """
        Persists one completed exercise. `summary` is what SessionRecorder.finish()
        returns; the split into three tables happens here so the recorder stays a
        pure calculator with no database knowledge.
        """
        rid = self.db.execute(
            """
            INSERT INTO exercise_results
                (session_id, exercise_id, sequence, started_at, ended_at, duration_sec,
                 rom_min_deg, rom_max_deg, rom_range_deg, target_rom_deg,
                 rom_pct_of_target, reps_completed, target_reps, hold_sec_total,
                 target_hold_sec, mean_quality_pct, in_target_pct, symmetry_delta,
                 frames_analysed, aborted)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (session_id, exercise_id, sequence,
             summary.get("started_at") or utc_now(),
             summary.get("ended_at") or utc_now(),
             summary.get("duration_sec", 0.0),
             summary.get("rom_min_deg"), summary.get("rom_max_deg"),
             summary.get("rom_range_deg"), summary.get("target_rom_deg"),
             summary.get("rom_pct_of_target"),
             summary.get("reps_completed", 0), summary.get("target_reps"),
             summary.get("hold_sec_total", 0.0), summary.get("target_hold_sec"),
             summary.get("mean_quality_pct"), summary.get("in_target_pct"),
             summary.get("symmetry_delta"),
             summary.get("frames_analysed", 0),
             1 if summary.get("aborted") else 0),
        )

        for joint, vals in (joint_summaries or {}).items():
            self.db.execute(
                """INSERT OR REPLACE INTO joint_summaries
                       (exercise_result_id, joint_key, min_deg, max_deg, mean_deg, range_deg)
                   VALUES (?,?,?,?,?,?)""",
                (rid, joint, vals.get("min"), vals.get("max"),
                 vals.get("mean"), vals.get("range")),
            )

        if samples:
            self.db.execute_many(
                """INSERT INTO angle_samples (exercise_result_id, t_ms, joint_key, value_deg)
                   VALUES (?,?,?,?)""",
                [(rid, s["t_ms"], s["joint_key"], s["value_deg"]) for s in samples],
            )

        return self.db.query_one("SELECT * FROM exercise_results WHERE id = ?", (rid,))

    def save_patient_reported(self, exercise_result_id: int,
                              pain_score: Optional[int] = None,
                              exertion_score: Optional[int] = None,
                              comment: Optional[str] = None) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO patient_reported
                   (exercise_result_id, pain_score, exertion_score, comment)
               VALUES (?,?,?,?)""",
            (exercise_result_id, pain_score, exertion_score, comment),
        )

    def results_for_session(self, session_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """SELECT r.*, e.code AS exercise_code, e.name AS exercise_name,
                      e.primary_joint, e.goal, e.movement_type,
                      pr.pain_score, pr.exertion_score
                 FROM exercise_results r
                 JOIN exercises e ON e.id = r.exercise_id
            LEFT JOIN patient_reported pr ON pr.exercise_result_id = r.id
                WHERE r.session_id = ?
                ORDER BY r.sequence, r.id""",
            (session_id,),
        )

    # ============================================================ progress ====

    def exercise_history(self, patient_id: int, exercise_id: int) -> List[Dict[str, Any]]:
        """Every attempt at one exercise, oldest first — the trend line."""
        return self.db.query(
            """SELECT s.day_index, s.started_at, r.*
                 FROM exercise_results r
                 JOIN sessions s ON s.id = r.session_id
                WHERE s.patient_id = ? AND r.exercise_id = ? AND r.aborted = 0
                ORDER BY s.started_at""",
            (patient_id, exercise_id),
        )

    def progress_summary(self, patient_id: int) -> Dict[str, Any]:
        """
        First versus latest, per exercise, with the direction of improvement
        respected.

        `goal` matters here. For a range-of-motion exercise a bigger number is
        better; for a deviation like trunk lean a SMALLER number is better.
        Reporting both as "change in degrees" without regard to direction would
        show a patient whose posture is deteriorating as improving.
        """
        patient = self.get_patient(patient_id)
        if not patient:
            raise ValueError(f"no patient {patient_id}")

        rows = self.db.query(
            """SELECT e.id AS exercise_id, e.code, e.name, e.goal, e.movement_type,
                      e.primary_joint
                 FROM exercise_results r
                 JOIN exercises e ON e.id = r.exercise_id
                 JOIN sessions  s ON s.id = r.session_id
                WHERE s.patient_id = ? AND r.aborted = 0
                GROUP BY e.id
                ORDER BY e.name""",
            (patient_id,),
        )

        items: List[Dict[str, Any]] = []
        for ex in rows:
            history = self.exercise_history(patient_id, ex["exercise_id"])
            if not history:
                continue
            first, latest = history[0], history[-1]
            metric = "rom_range_deg" if ex["movement_type"] == "REP" else "rom_max_deg"

            # For a REDUCE goal the meaningful number is how far from neutral the
            # patient got, so the peak deviation is what we track down.
            if ex["goal"] == "REDUCE":
                metric = "rom_max_deg"

            f_val = first.get(metric)
            l_val = latest.get(metric)
            change = None
            pct = None
            improved = None
            if f_val is not None and l_val is not None:
                change = round(l_val - f_val, 1)
                improved = (change > 0) if ex["goal"] == "INCREASE" else (change < 0)
                if f_val:
                    pct = round((l_val - f_val) / abs(f_val) * 100.0, 1)

            items.append({
                "exercise_id": ex["exercise_id"],
                "code": ex["code"],
                "name": ex["name"],
                "goal": ex["goal"],
                "movement_type": ex["movement_type"],
                "primary_joint": ex["primary_joint"],
                "metric": metric,
                "sessions": len(history),
                "first_day": first["day_index"],
                "latest_day": latest["day_index"],
                "first_value": f_val,
                "latest_value": l_val,
                "best_value": (max(h[metric] for h in history if h.get(metric) is not None)
                               if ex["goal"] == "INCREASE"
                               else min(h[metric] for h in history if h.get(metric) is not None))
                              if any(h.get(metric) is not None for h in history) else None,
                "change_deg": change,
                "change_pct": pct,
                "improved": improved,
                "target_rom_deg": latest.get("target_rom_deg"),
                "rom_pct_of_target": latest.get("rom_pct_of_target"),
                "trend": [
                    {"day_index": h["day_index"], "started_at": h["started_at"],
                     "value": h.get(metric), "reps": h.get("reps_completed"),
                     "quality": h.get("mean_quality_pct")}
                    for h in history
                ],
            })

        sessions = self.list_sessions(patient_id)
        return {
            "patient": patient,
            "assignment": self.active_assignment(patient_id),
            "session_count": len(sessions),
            "first_session_at": sessions[0]["started_at"] if sessions else None,
            "latest_session_at": sessions[-1]["started_at"] if sessions else None,
            "days_in_programme": sessions[-1]["day_index"] if sessions else 0,
            "exercises": items,
            "regressions": [i for i in items if i["improved"] is False],
        }

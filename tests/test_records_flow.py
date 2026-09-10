# Run from upper_body_ai/:  python ../tests/test_records_flow.py
"""
End-to-end test of the patient records layer.

Simulates a full course of treatment — a patient assigned a condition, returning
across ten days, gradually regaining range on one side while a second movement
quietly regresses — then checks that the stored record says what actually
happened, and renders the doctor's PDF.

The regressing movement is deliberate. A progress report that only ever reports
improvement is worthless; the test exists to prove a decline is detected and
flagged rather than averaged away.
"""

import math
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath("."))

from records import Repository, SessionRecorder, get_db, reset_db_singleton, seed
from records.report import build_progress_report

random.seed(42)

FAIL = []


def check(label, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    if not condition:
        FAIL.append(label)
    print(f"  [{status}] {label}" + (f"   {detail}" if detail else ""))


def simulate(recorder, peak, reps=6, secs=8.0, hz=10, noise=2.5):
    """Drive a recorder with a plausible sinusoidal movement."""
    recorder.start()
    t = 0.0
    for _ in range(int(reps * secs * hz)):
        t += 1.0 / hz
        phase = (t % secs) / secs
        val = 12 + (peak - 12) * math.sin(math.pi * phase) + random.uniform(-noise, noise)
        recorder.on_frame(
            {recorder.primary_joint: max(0.1, val),
             (recorder.mirror_joint or "trunk_posture"): max(0.1, val - random.uniform(0, 8)),
             "trunk_posture": random.uniform(2, 6)},
            {"movement_quality_pct": random.uniform(86, 97), "rom_summary": {"x": 1}},
            now=t,
        )
    return recorder


def simulate_hold(recorder, deviation, secs=30.0, hz=10):
    """Drive a REDUCE-goal hold, e.g. trunk lean held near neutral."""
    recorder.start()
    t = 0.0
    for _ in range(int(secs * hz)):
        t += 1.0 / hz
        recorder.on_frame(
            {recorder.primary_joint: max(0.1, deviation + random.uniform(-1.5, 1.5))},
            {"movement_quality_pct": random.uniform(88, 96), "rom_summary": {"x": 1}},
            now=t,
        )
    return recorder


def main():
    tmp = tempfile.mkdtemp()
    db = get_db(os.path.join(tmp, "records_test.db"))
    seed(db, verbose=False)
    repo = Repository(db)

    print("\n1. CATALOGUE")
    conditions = repo.list_conditions()
    check("conditions seeded", len(conditions) >= 9, f"{len(conditions)} conditions")
    check("every condition has exercises",
          all(c["exercise_count"] > 0 for c in conditions))

    print("\n2. PATIENT AND PRESCRIPTION")
    patient = repo.create_patient("Anjali Sharma", sex="F", date_of_birth="1979-04-11")
    check("patient created", patient["code"] == "THR-0001", patient["code"])

    cond = next(c for c in conditions if c["code"] == "ADHESIVE_CAPSULITIS")
    repo.assign_condition(patient["id"], cond["id"])
    plan = repo.todays_plan(patient["id"])
    check("condition assigned", plan["assignment"]["condition_code"] == "ADHESIVE_CAPSULITIS")
    check("protocol resolved", len(plan["exercises"]) == 4, f"{len(plan['exercises'])} exercises")
    check("day index starts at 1", plan["day_index"] == 1)

    abduction_l = next(e for e in plan["exercises"] if e["code"] == "SH_ABD_L")
    trunk = next(e for e in plan["exercises"] if e["code"] == "TRUNK_UPRIGHT")

    print("\n3. TEN-DAY COURSE")
    print("     abduction improves 62 -> 128 deg; trunk lean WORSENS 4 -> 11 deg")
    peaks = [62, 68, 73, 79, 86, 94, 103, 112, 120, 128]
    leans = [4.0, 4.4, 5.0, 5.6, 6.3, 7.1, 8.0, 9.0, 10.0, 11.0]

    base = datetime.now(timezone.utc) - timedelta(days=9)
    for day, (peak, lean) in enumerate(zip(peaks, leans)):
        sess = repo.start_session(patient["id"])
        # Backdate so day_index reflects a real ten-day course rather than ten
        # sessions crammed into one afternoon.
        stamp = (base + timedelta(days=day)).isoformat(timespec="seconds")
        db.execute("UPDATE sessions SET started_at = ?, day_index = ? WHERE id = ?",
                   (stamp, day + 1, sess["id"]))

        rec = simulate(SessionRecorder({**abduction_l, "id": abduction_l["exercise_id"]},
                                       abduction_l), peak)
        s = rec.finish()
        saved = repo.save_exercise_result(sess["id"], abduction_l["exercise_id"], s,
                                          rec.joint_summaries(), rec.samples, sequence=1)
        repo.save_patient_reported(saved["id"], pain_score=max(1, 7 - day // 2))

        rec2 = simulate_hold(SessionRecorder({**trunk, "id": trunk["exercise_id"]}, trunk), lean)
        s2 = rec2.finish()
        repo.save_exercise_result(sess["id"], trunk["exercise_id"], s2,
                                  rec2.joint_summaries(), rec2.samples, sequence=2)
        repo.end_session(sess["id"])

    sessions = repo.list_sessions(patient["id"])
    check("ten sessions stored", len(sessions) == 10, f"{len(sessions)}")
    check("day index spans 1..10",
          sessions[0]["day_index"] == 1 and sessions[-1]["day_index"] == 10)

    print("\n4. PROGRESS MATHS")
    prog = repo.progress_summary(patient["id"])
    by_code = {i["code"]: i for i in prog["exercises"]}

    abd = by_code["SH_ABD_L"]
    print(f"     abduction ROM  day 1 {abd['first_value']:.1f} deg  ->  "
          f"day 10 {abd['latest_value']:.1f} deg   ({abd['change_deg']:+.1f})")
    check("abduction recognised as improved", abd["improved"] is True)
    check("abduction change is positive", abd["change_deg"] > 40,
          f"{abd['change_deg']:+.1f} deg")
    check("abduction goal is INCREASE", abd["goal"] == "INCREASE")

    tru = by_code["TRUNK_UPRIGHT"]
    print(f"     trunk lean     day 1 {tru['first_value']:.1f} deg  ->  "
          f"day 10 {tru['latest_value']:.1f} deg   ({tru['change_deg']:+.1f})")
    check("trunk goal is REDUCE", tru["goal"] == "REDUCE")
    check("RISING trunk lean is flagged as NOT improved", tru["improved"] is False,
          "a bigger deviation must never read as progress")
    check("regression list contains the trunk hold",
          any(r["code"] == "TRUNK_UPRIGHT" for r in prog["regressions"]))
    check("regression list excludes the abduction",
          not any(r["code"] == "SH_ABD_L" for r in prog["regressions"]))

    check("trend has one point per session", len(abd["trend"]) == 10)
    check("trend is chronological",
          [p["day_index"] for p in abd["trend"]] == list(range(1, 11)))
    check("best value recorded", abd["best_value"] >= abd["latest_value"] - 0.1)

    print("\n5. REPS AND BANDS")
    history = repo.exercise_history(patient["id"], abduction_l["exercise_id"])
    day1, day10 = history[0], history[-1]
    check("reps counted on day 10", day10["reps_completed"] == 6,
          f"{day10['reps_completed']} of 6 simulated")
    check("day 1 shallow reps counted too", day1["reps_completed"] == 6,
          f"{day1['reps_completed']}")
    check("percent of target rose", day10["rom_pct_of_target"] > day1["rom_pct_of_target"],
          f"{day1['rom_pct_of_target']:.0f}% -> {day10['rom_pct_of_target']:.0f}%")
    check("pain score stored", day10["id"] is not None)

    print("\n6. COMPENSATION CAPTURE")
    joints = db.query(
        "SELECT joint_key FROM joint_summaries WHERE exercise_result_id = ?",
        (day10["id"],))
    keys = {j["joint_key"] for j in joints}
    check("non-prescribed joints also summarised", "trunk_posture" in keys,
          f"stored: {sorted(keys)}")

    print("\n7. TRACE SAMPLES")
    n = db.query_one("SELECT COUNT(*) AS c FROM angle_samples WHERE exercise_result_id = ?",
                     (day10["id"],))["c"]
    check("downsampled trace stored", 50 < n < 400, f"{n} samples for a 48 s exercise")

    print("\n8. DOCTOR PDF")
    out = os.path.join(tmp, "reports")
    pdf = build_progress_report(repo, patient["id"], output_dir=out)
    size = os.path.getsize(pdf)
    check("PDF written", os.path.exists(pdf) and size > 5000, f"{size:,} bytes")
    print(f"     {pdf}")

    print("\n9. ISOLATION FROM THE CLINICAL ENGINE")
    import records, records.repository, records.session_recorder, records.report
    banned = ("metrics", "inference", "src.pose_detector", "mediapipe", "cv2")
    leaked = []
    for mod in (records, records.repository, records.session_recorder,
                records.report, records.db):
        src = open(mod.__file__, encoding="utf-8").read()
        for b in banned:
            if f"import {b}" in src or f"from {b}" in src:
                leaked.append((mod.__name__, b))
    check("records package imports nothing from the engine", not leaked, str(leaked))

    print("\n" + "=" * 70)
    if FAIL:
        print(f"RESULT: {len(FAIL)} FAILURE(S)")
        for f in FAIL:
            print(f"   - {f}")
    else:
        print("RESULT: ALL CHECKS PASS")
    print("=" * 70)
    reset_db_singleton()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

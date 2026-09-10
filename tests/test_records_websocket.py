# Run from upper_body_ai/:  python ../tests/test_records_websocket.py
# Needs test frames containing a person; see tests/README in the repo.
"""
Drives the LIVE server over a real WebSocket, exactly as the Flutter client does.

This is the check that the contract test cannot make: that the messages actually
round-trip through a running FastAPI process with a real MediaPipe pipeline
attached, and that a recorder gets fitted to the same session that is processing
the video.
"""
import asyncio, json, os, struct, sys, tempfile, threading, time
import numpy as np, cv2, uvicorn, websockets

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("THERAYU_TEST", "1")

import server.ws_server as W
from records import get_db, Repository, seed

PORT = 8799
FAIL = []

def check(label, ok, detail=""):
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))
    if not ok: FAIL.append(label)

def frame_bytes(img, seq, mode="UPPER_BODY"):
    ok, buf = cv2.imencode(".jpg", img)
    payload = buf.tobytes()
    header = json.dumps({"w": img.shape[1], "h": img.shape[0], "fmt": "jpeg",
                         "rot": 0, "mirror": False, "mode": mode,
                         "seq": seq}).encode()
    return struct.pack("<I", len(header)) + header + payload

async def recv_until(ws, want, timeout=25):
    """Reads until a message of the wanted type arrives, ignoring pose frames."""
    end = time.time() + timeout
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
        msg = json.loads(raw)
        if msg.get("type") == want:
            return msg
        if msg.get("type") == "records_error":
            return msg
    raise TimeoutError(f"never saw {want}")

async def main():
    # --- patient set up through the repository, as the REST API would ---
    # A THROWAWAY database, always.
    #
    # An earlier run of this test used the default path and wrote two dummy
    # patients into the real clinic database. A test must never be able to touch
    # live patient records, so the path is a fresh temp file every time and is
    # never the default.
    tmp_db = os.path.join(tempfile.mkdtemp(prefix="therayu_wstest_"), "test.db")
    db = get_db(tmp_db); seed(db, verbose=False)
    print(f"test database: {tmp_db}")
    repo = Repository(db)
    patient = repo.create_patient("WS Test Patient")
    cond = next(c for c in repo.list_conditions() if c["code"] == "ADHESIVE_CAPSULITIS")
    repo.assign_condition(patient["id"], cond["id"])
    plan = repo.todays_plan(patient["id"])
    exercise = plan["exercises"][0]

    frames = sorted(__import__("glob").glob("/tmp/tf_*.png"))
    imgs = [cv2.imread(f) for f in frames if cv2.imread(f) is not None]
    if not imgs:
        imgs = [np.full((480, 640, 3), 40, np.uint8)]
    print(f"\ndriving with {len(imgs)} real frames\n")

    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", max_size=None) as ws:
        hello = json.loads(await ws.recv())
        check("server says hello", hello.get("type") == "hello")

        print("\n1. SESSION START")
        await ws.send(json.dumps({"type": "session_start", "patient_id": patient["id"]}))
        m = await recv_until(ws, "session_started")
        check("session_started returned", m.get("type") == "session_started", str(m)[:90])
        check("carries a session id", m.get("session_id") is not None)
        check("carries day_index", m.get("day_index") == 1)
        check("carries the exercise list", len(m.get("exercises") or []) == 4,
              f"{len(m.get('exercises') or [])} exercises")
        check("carries the condition name", bool(m.get("condition")))

        print("\n2. EXERCISE START")
        await ws.send(json.dumps({"type": "exercise_start",
                                  "exercise_id": exercise["exercise_id"]}))
        m = await recv_until(ws, "exercise_started")
        check("exercise_started returned", m.get("type") == "exercise_started", str(m)[:90])
        for key in ("name", "primary_joint", "movement_type", "goal",
                    "target_rom_deg", "target_reps", "band_min_deg", "band_max_deg"):
            check(f"  field {key}", key in m, repr(m.get(key)))
        check("server switched body mode", m.get("body_mode") == "UPPER_BODY")

        print("\n3. STREAMING FRAMES WHILE RECORDING")
        poses = 0
        active_seen = False
        for i in range(24):
            await ws.send(frame_bytes(imgs[i % len(imgs)], i))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=25))
            if msg.get("type") == "pose":
                poses += 1
                if msg.get("exercise_active"):
                    active_seen = True
        check("pose replies received", poses >= 20, f"{poses}/24")
        check("pose reply reports exercise_active", active_seen)
        check("pose reply carries exercise_reps",
              "exercise_reps" in msg and "records_session_id" in msg)

        print("\n4. EXERCISE STOP")
        await ws.send(json.dumps({"type": "exercise_stop"}))
        m = await recv_until(ws, "exercise_saved")
        check("exercise_saved returned", m.get("type") == "exercise_saved", str(m)[:120])
        check("has a result id", m.get("result_id") is not None)
        s = m.get("summary") or {}
        check("summary has duration", s.get("duration_sec", 0) > 0, f"{s.get('duration_sec')}s")
        check("summary has frames_analysed", s.get("frames_analysed", 0) > 0,
              str(s.get("frames_analysed")))
        check("joint summaries returned", len(m.get("joints") or {}) > 0,
              str(sorted((m.get('joints') or {}).keys())))

        print("\n5. SESSION END")
        await ws.send(json.dumps({"type": "session_end"}))
        m = await recv_until(ws, "session_ended")
        check("session_ended returned", m.get("type") == "session_ended", str(m)[:90])
        check("reports exercises_completed", m.get("exercises_completed") == 1,
              str(m.get("exercises_completed")))
        check("returns the result rows", len(m.get("results") or []) == 1)
        row = (m.get("results") or [{}])[0]
        check("result row names the exercise", bool(row.get("exercise_name")),
              str(row.get("exercise_name")))

    print("\n6. PERSISTED TO DISK")
    sessions = repo.list_sessions(patient["id"])
    check("session written", len(sessions) == 1)
    check("session was closed", sessions[0]["ended_at"] is not None)
    results = repo.results_for_session(sessions[0]["id"])
    check("exercise result written", len(results) == 1)
    prog = repo.progress_summary(patient["id"])
    check("progress summary builds", len(prog["exercises"]) == 1,
          f"{len(prog['exercises'])} tracked")

    print("\n" + "=" * 72)
    print(f"RESULT: {'ALL WEBSOCKET CHECKS PASS' if not FAIL else f'{len(FAIL)} FAILURE(S)'}")
    for f in FAIL: print("   -", f)
    return 1 if FAIL else 0

def serve():
    uvicorn.run(W.app, host="127.0.0.1", port=PORT, log_level="error")

t = threading.Thread(target=serve, daemon=True)
t.start()
time.sleep(6)
sys.exit(asyncio.run(main()))

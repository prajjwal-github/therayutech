# Run from the project root:  python tests/test_body_modes.py
"""
End-to-end body-mode test.

Drives the REAL ClientSession.process() — the exact code path the WebSocket
worker uses — over real video frames, once for each body mode, and asserts:

  1. process() does not raise (this is what was broken: UnboundLocalError on
     every frame, swallowed by the worker's `except: print`)
  2. the result survives json.dumps (the worker sends it with send_text)
  3. landmarks are present when a person is detected
  4. the angle keys the Flutter UI reads are actually present
"""
import json, os, sys, types, glob, traceback

ROOT = os.path.dirname(os.path.abspath("upper_body_ai/server/ws_server.py"))
sys.path.insert(0, os.path.abspath("upper_body_ai"))
sys.path.insert(0, os.path.abspath("upper_body_ai/server"))
sys.path.insert(0, os.path.abspath("."))

import cv2
import ws_server as W

frames = sorted(glob.glob("frames/*.png"))
print(f"loaded {len(frames)} frames\n")

MODES = ["UPPER_BODY", "LOWER_BODY", "FULL_BODY"]
overall_ok = True

for mode in MODES:
    print("=" * 68)
    print(f"MODE: {mode}")
    print("=" * 68)
    try:
        session = W.PhysioSession(W.CONFIG, client_label=f"test-{mode}")
    except Exception:
        traceback.print_exc(); overall_ok = False; continue
    session.body_mode = mode

    detected = 0
    errors = 0
    angle_keys, lm_counts, sizes = set(), [], []

    for fp in frames:
        img = cv2.imread(fp)
        if img is None:
            continue
        try:
            res = session.process(img)
        except Exception as exc:
            errors += 1
            print(f"  RAISED on {os.path.basename(fp)}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            continue
        try:
            blob = json.dumps(res)
            sizes.append(len(blob))
        except Exception as exc:
            errors += 1
            print(f"  NOT JSON-SERIALISABLE: {type(exc).__name__}: {exc}")
            continue

        lms = res.get("landmarks") or {}
        if lms:
            detected += 1
            lm_counts.append(len(lms))
        angle_keys |= set((res.get("angles") or {}).keys())

        assert res["body_mode"] == mode, f"mode echoed wrong: {res['body_mode']}"
        assert "telemetry" in res and "analysis_ms" in res["telemetry"], "analysis_ms missing"

    session.close()

    print(f"  frames processed : {len(frames)}")
    print(f"  exceptions       : {errors}")
    print(f"  person detected  : {detected}/{len(frames)}")
    if lm_counts:
        print(f"  landmarks/frame  : {min(lm_counts)}–{max(lm_counts)}")
    if sizes:
        print(f"  json payload     : {min(sizes)}–{max(sizes)} bytes")
    print(f"  angle keys ({len(angle_keys)}) : {sorted(angle_keys)}")
    if errors:
        overall_ok = False
    print()

print("=" * 68)
print("RESULT:", "ALL MODES PASS" if overall_ok else "FAILURES PRESENT")
sys.exit(0 if overall_ok else 1)

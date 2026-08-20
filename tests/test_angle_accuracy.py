# Run from upper_body_ai/:  python ../tests/test_angle_accuracy.py
"""
Replays the joint positions measured off the app's own rendered skeleton through
the REPAIRED angle engine, and checks the output against the angles measured
independently in square-pixel space.

Each landmark is given a deliberately absurd z. If any of it still leaked into
the result, these assertions would fail.
"""
import sys, os, math, random
sys.path.insert(0, os.path.abspath("."))
from metrics.physio_angles import PhysiotherapyAngleEngine

random.seed(7)

SHOTS = [
 ("T-POSE (arms straight out)", 1366, 900, dict(
    LEFT_SHOULDER=(504,254), LEFT_ELBOW=(283,243), LEFT_WRIST=(42,218),
    RIGHT_SHOULDER=(845,255), RIGHT_ELBOW=(1065,274), RIGHT_WRIST=(1303,257),
    LEFT_HIP=(586,802), RIGHT_HIP=(793,798)),
    {"elbow_flexion_left":3.1, "elbow_flexion_right":9.0,
     "shoulder_abduction_left":94.4, "shoulder_abduction_right":83.5},
    {"elbow_flexion_left":38.4, "elbow_flexion_right":38.5,
     "shoulder_abduction_left":91.7, "shoulder_abduction_right":77.3}),
 ("ARMS DOWN at sides", 1140, 750, dict(
    LEFT_SHOULDER=(428,242), LEFT_ELBOW=(382,467), LEFT_WRIST=(351,655),
    RIGHT_SHOULDER=(706,232), RIGHT_ELBOW=(777,432), RIGHT_WRIST=(777,620),
    LEFT_HIP=(490,681), RIGHT_HIP=(663,679)),
    {"elbow_flexion_left":2.2, "elbow_flexion_right":19.5,
     "shoulder_abduction_left":12.8, "shoulder_abduction_right":18.3},
    {"elbow_flexion_left":22.6, "elbow_flexion_right":31.8,
     "shoulder_abduction_left":10.8, "shoulder_abduction_right":17.1}),
 ("ONE ELBOW BENT (~90 deg)", 1366, 900, dict(
    LEFT_SHOULDER=(553,335), LEFT_ELBOW=(487,578), LEFT_WRIST=(281,566),
    RIGHT_SHOULDER=(867,275), RIGHT_ELBOW=(964,530), RIGHT_WRIST=(1049,726),
    LEFT_HIP=(595,839), RIGHT_HIP=(807,835)),
    {"elbow_flexion_left":78.1, "elbow_flexion_right":2.6,
     "shoulder_abduction_left":14.2, "shoulder_abduction_right":21.8},
    {"elbow_flexion_left":99.3, "elbow_flexion_right":33.4,
     "shoulder_abduction_left":37.2, "shoulder_abduction_right":15.0}),
]

engine = PhysiotherapyAngleEngine()
print(f"{'pose / metric':<44}{'expected':>10}{'engine':>9}{'was':>8}{'delta':>8}")
print("-" * 79)
fails = 0
for title, W, H, pts, expected, old in SHOTS:
    lm = {name: {"x": x / W, "y": y / H,
                 # absurd depth on purpose: nothing may read this
                 "z": random.uniform(-5.0, 5.0),
                 "visibility": 0.95}
          for name, (x, y) in pts.items()}
    got = engine.compute_physio_metrics(lm, frame_aspect=W / H)
    print(f"\n{title}   (aspect {W/H:.3f})")
    for key, want in expected.items():
        val = got[key]
        d = val - want
        ok = abs(d) <= 0.6
        fails += 0 if ok else 1
        print(f"  {key:<42}{want:>10.1f}{val:>9.1f}{old[key]:>8.1f}{d:>+8.1f}"
              + ("" if ok else "   <-- MISMATCH"))

print("\n" + "=" * 79)
# z-independence, proved twice over
lm_a = {n: {"x": x/1366, "y": y/900, "z": 0.0, "visibility": 0.95}
        for n, (x, y) in SHOTS[0][3-1].items()} if False else None
base = {n: {"x": x/1366, "y": y/900, "z": 0.0, "visibility": 0.95}
        for n, (x, y) in SHOTS[0][3].items()} if False else None
pts = SHOTS[0][3]
a = engine.compute_physio_metrics(
    {n: {"x": x/1366, "y": y/900, "z": 0.0, "visibility": 0.95} for n, (x, y) in pts.items()},
    frame_aspect=1366/900)
b = engine.compute_physio_metrics(
    {n: {"x": x/1366, "y": y/900, "z": 99.0, "visibility": 0.95} for n, (x, y) in pts.items()},
    frame_aspect=1366/900)
numeric = [k for k in a if isinstance(a[k], float)]
zdiff = max(abs(a[k] - b[k]) for k in numeric)
print(f"max change when every z is swung from 0.0 to 99.0 : {zdiff:.4f} deg")

# confidence floor still refuses to invent numbers
low = {n: {"x": x/1366, "y": y/900, "z": 0.0, "visibility": 0.10} for n, (x, y) in pts.items()}
res_low = engine.compute_physio_metrics(low, frame_aspect=1366/900)
assert res_low["elbow_flexion_left"] is None, "confidence floor stopped working"
assert res_low["shoulder_abduction_left"] is None, "confidence floor stopped working"
print("low-confidence landmarks still return None (no fake angles)  : OK")

print(f"\nRESULT: {'PASS' if fails == 0 and zdiff == 0 else 'FAIL'}  ({fails} mismatches)")
sys.exit(0 if fails == 0 and zdiff == 0 else 1)

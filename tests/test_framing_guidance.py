# Run from the project root:  python tests/test_framing_guidance.py
import sys, os
sys.path.insert(0, os.path.abspath("upper_body_ai"))
from src.camera_validator import CameraValidator

V = CameraValidator()
ALL = ["NOSE","C7_NECK","LEFT_SHOULDER","RIGHT_SHOULDER","LEFT_ELBOW","RIGHT_ELBOW",
       "LEFT_WRIST","RIGHT_WRIST","LEFT_HIP","RIGHT_HIP","LEFT_KNEE","RIGHT_KNEE",
       "LEFT_ANKLE","RIGHT_ANKLE"]

def body(**over):
    d = {n: {"x": 0.5, "y": 0.5, "visibility": 0.9} for n in ALL}
    for k, v in over.items():
        d[k] = {**d[k], **v}
    return d

CASES = [
    ("everything visible",           body()),
    ("head above frame",             body(NOSE={"y":0.01}, C7_NECK={"y":0.015})),
    ("feet below frame",             body(LEFT_ANKLE={"y":0.99}, RIGHT_ANKLE={"y":0.99})),
    ("legs out of shot entirely",    {k:v for k,v in body().items() if "KNEE" not in k and "ANKLE" not in k}),
    ("hands dropped below frame",    body(LEFT_WRIST={"y":0.99}, RIGHT_WRIST={"y":0.99})),
    ("stood too far left",           body(**{n:{"x":0.01} for n in ALL})),
    ("stood too far right",          body(**{n:{"x":0.99} for n in ALL})),
    ("no person",                    {}),
]

print(f"{'case':<28}", "".join(f"{m:<14}" for m in ["UPPER_BODY","LOWER_BODY","FULL_BODY"]))
print("-"*70)
for name, lms in CASES:
    row = []
    for mode in ["UPPER_BODY","LOWER_BODY","FULL_BODY"]:
        ready, msg, badge, missing = V.validate_frame(lms, mode)
        row.append("READY" if ready else "blocked")
    print(f"{name:<28}", "".join(f"{r:<14}" for r in row))

print("\nGUIDANCE TEXT PER MODE")
print("="*70)
for name, lms in CASES:
    print(f"\n{name}")
    for mode in ["UPPER_BODY","LOWER_BODY","FULL_BODY"]:
        ready, msg, badge, missing = V.validate_frame(lms, mode)
        print(f"  {mode:<12} {msg}")

# regressions that must hold
r,_,_,_ = V.validate_frame(body(LEFT_ANKLE={"y":0.99}, RIGHT_ANKLE={"y":0.99}), "UPPER_BODY")
assert r, "upper body must not care about ankles"
r,_,_,_ = V.validate_frame(body(NOSE={"y":0.01}), "LOWER_BODY")
assert r, "lower body must not care about the head"
_,m,_,_ = V.validate_frame(body(LEFT_WRIST={"y":0.99}), "UPPER_BODY")
assert "Lower body" not in m, f"upper body gave lower-body advice: {m}"
print("\nassertions: PASS")

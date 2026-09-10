# Run from upper_body_ai/:  python ../tests/test_lower_body.py
"""
Regression test for the lower-body collapse.

Case 1 replays the EXACT landmark geometry MediaPipe produced from a real
legs-only frame. Before the fix the app reported "READY 91%" over it and drew a
skeleton with the hips above the shoulders.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
from src.camera_validator import CameraValidator
from metrics.physio_angles import PhysiotherapyAngleEngine

V = CameraValidator()
E = PhysiotherapyAngleEngine()
FAIL = []

def check(label, ok, detail=""):
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))
    if not ok: FAIL.append(label)

def lm(**pts):
    return {n: {"x": x, "y": y, "visibility": v} for n, (x, y, v) in pts.items()}

print("\n1. THE ACTUAL SCRAMBLED POSE FROM A LEGS-ONLY FRAME")
print("     hips ABOVE shoulders, nose BELOW shoulders, ankles ABOVE knees")
scrambled = lm(
    LEFT_SHOULDER=(0.354, 0.552, 0.98), RIGHT_SHOULDER=(0.301, 0.569, 0.98),
    LEFT_HIP=(0.462, 0.251, 0.99),      RIGHT_HIP=(0.414, 0.275, 0.99),
    LEFT_KNEE=(0.587, 0.337, 0.75),     RIGHT_KNEE=(0.497, 0.353, 0.55),
    LEFT_ANKLE=(0.688, 0.313, 0.73),    RIGHT_ANKLE=(0.621, 0.274, 0.58),
    NOSE=(0.392, 0.628, 0.98),
)
for mode in ("LOWER_BODY", "FULL_BODY", "UPPER_BODY"):
    ready, msg, badge, _ = V.validate_frame(scrambled, mode)
    check(f"{mode:<11} refuses it", not ready, f"{badge} | {msg}")

print("\n2. A NORMAL STANDING POSE IS STILL ACCEPTED")
standing = lm(
    NOSE=(0.50, 0.08, 0.99), C7_NECK=(0.50, 0.18, 0.98),
    LEFT_SHOULDER=(0.42, 0.22, 0.99), RIGHT_SHOULDER=(0.58, 0.22, 0.99),
    LEFT_ELBOW=(0.40, 0.38, 0.95),    RIGHT_ELBOW=(0.60, 0.38, 0.95),
    LEFT_WRIST=(0.39, 0.52, 0.92),    RIGHT_WRIST=(0.61, 0.52, 0.92),
    LEFT_HIP=(0.45, 0.52, 0.98),      RIGHT_HIP=(0.55, 0.52, 0.98),
    LEFT_KNEE=(0.45, 0.72, 0.95),     RIGHT_KNEE=(0.55, 0.72, 0.95),
    LEFT_ANKLE=(0.45, 0.92, 0.92),    RIGHT_ANKLE=(0.55, 0.92, 0.92),
)
for mode in ("UPPER_BODY", "LOWER_BODY", "FULL_BODY"):
    ready, msg, _, _ = V.validate_frame(standing, mode)
    check(f"{mode:<11} accepts it", ready, msg)

print("\n3. A DEEP SQUAT MUST NOT BE MISTAKEN FOR A COLLAPSE")
squat = dict(standing)
squat["LEFT_HIP"]  = {"x": 0.45, "y": 0.70, "visibility": 0.98}
squat["RIGHT_HIP"] = {"x": 0.55, "y": 0.70, "visibility": 0.98}
squat["LEFT_KNEE"] = {"x": 0.44, "y": 0.73, "visibility": 0.95}
squat["RIGHT_KNEE"]= {"x": 0.56, "y": 0.73, "visibility": 0.95}
ready, msg, _, _ = V.validate_frame(squat, "LOWER_BODY")
check("hips almost level with knees still accepted", ready, msg)

print("\n4. LEGS ONLY, TORSO OUT OF SHOT")
legs_only = lm(
    LEFT_HIP=(0.45, 0.15, 0.95),   RIGHT_HIP=(0.55, 0.15, 0.95),
    LEFT_KNEE=(0.45, 0.45, 0.93),  RIGHT_KNEE=(0.55, 0.45, 0.93),
    LEFT_ANKLE=(0.45, 0.85, 0.90), RIGHT_ANKLE=(0.55, 0.85, 0.90),
)
ready, msg, _, _ = V.validate_frame(legs_only, "LOWER_BODY")
check("lower body blocks when the torso is missing", not ready)
check("guidance names the torso", "torso" in msg.lower(), msg)

print("\n5. THE HEAD IS STILL NOT REQUIRED FOR LEG WORK")
no_head = {k: v for k, v in standing.items() if k not in ("NOSE", "C7_NECK")}
ready, msg, _, _ = V.validate_frame(no_head, "LOWER_BODY")
check("lower body ready without the head in shot", ready, msg)

print("\n6. EARLIER FRAMING RULES UNCHANGED")
head_up = dict(standing); head_up["NOSE"] = {"x": 0.5, "y": 0.01, "visibility": 0.99}
check("head above frame blocks UPPER", not V.validate_frame(head_up, "UPPER_BODY")[0])
check("head above frame does not block LOWER", V.validate_frame(head_up, "LOWER_BODY")[0])
feet = dict(standing)
feet["LEFT_ANKLE"]  = {"x": 0.45, "y": 0.99, "visibility": 0.92}
feet["RIGHT_ANKLE"] = {"x": 0.55, "y": 0.99, "visibility": 0.92}
check("feet below frame does not block UPPER", V.validate_frame(feet, "UPPER_BODY")[0])
check("feet below frame blocks LOWER", not V.validate_frame(feet, "LOWER_BODY")[0])

print("\n7. ANKLE ANGLE, FRONT VIEW vs SIDE VIEW")
def pt(x, y): return {"x": x, "y": y, "z": 0.0, "visibility": 0.95}
aspect = 640 / 480
front = E._calculate_ankle_angle(pt(0.45, 0.72), pt(0.45, 0.92), pt(0.455, 0.94), aspect)
check("front-on foot returns None, not ~175 degrees", front is None, str(front))
side = E._calculate_ankle_angle(pt(0.50, 0.60), pt(0.50, 0.90), pt(0.62, 0.94), aspect)
check("side-on foot still measured", side is not None, f"{side} deg")
check("side-on value is plausible", side is not None and 60 <= side <= 130, str(side))

print("\n" + "=" * 72)
print(f"RESULT: {'ALL LOWER BODY CHECKS PASS' if not FAIL else f'{len(FAIL)} FAILURE(S)'}")
for f in FAIL: print("   -", f)
sys.exit(1 if FAIL else 0)

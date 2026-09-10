# Run from the project root:  python tests/test_api_contract.py
"""
Cross-checks the Flutter client against the Python server.

A typo in a route or a JSON key is invisible until runtime and then presents as
an empty screen, which is exactly the failure mode this whole phase is meant to
avoid. So every path the Dart client calls is matched against the routes FastAPI
actually declares, and every key the Dart models read is matched against the
columns and dict keys Python actually emits.
"""
import re, sys, pathlib

ROOT = pathlib.Path(".")
FAIL = []

def check(label, ok, detail=""):
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAIL.append(label)

# ---------------------------------------------------------------- routes ----
api_py = (ROOT / "upper_body_ai/records/api.py").read_text(encoding="utf-8")
server_routes = set()
for m in re.finditer(r'@router\.(get|post|patch|delete)\("([^"]+)"', api_py):
    server_routes.add((m.group(1).upper(), "/api" + m.group(2)))

dart = (ROOT / "therayu_app/lib/services/records_api.dart").read_text(encoding="utf-8")
client_calls = set()
for m in re.finditer(r"_(get|post|patch)\('(/api[^']+)'", dart):
    client_calls.add((m.group(1).upper(), m.group(2)))
for m in re.finditer(r"_uri\('(/api[^']+)'\)", dart):
    client_calls.add(("GET", m.group(1)))

def norm(path):
    return re.sub(r"\$\{?\w+\}?", "{}", re.sub(r"\{[^}]+\}", "{}", path))

server_norm = {(v, norm(p)) for v, p in server_routes}
print("\n1. ROUTE CONTRACT")
print(f"     server declares {len(server_routes)} routes, client calls {len(client_calls)}")
for verb, path in sorted(client_calls):
    n = (verb, norm(path))
    check(f"{verb:5} {path}", n in server_norm,
          "" if n in server_norm else f"no such route (have: {sorted(p for v,p in server_norm if v==verb)})")

# ------------------------------------------------------------- json keys ----
print("\n2. JSON KEYS THE DART MODELS READ")
models = (ROOT / "therayu_app/lib/models/records.dart").read_text(encoding="utf-8")
dart_keys = set(re.findall(r"j\['([a-z_]+)'\]", models))

sources = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in [
    "upper_body_ai/records/repository.py",
    "upper_body_ai/records/schema.sql",
    "upper_body_ai/records/session_recorder.py",
    "upper_body_ai/server/ws_server.py",
])
missing = sorted(k for k in dart_keys if k not in sources)
check(f"all {len(dart_keys)} keys exist server-side", not missing, str(missing))

# ------------------------------------------ websocket control round-trip ----
print("\n3. WEBSOCKET CONTROL MESSAGES")
ws = (ROOT / "upper_body_ai/server/ws_server.py").read_text(encoding="utf-8")
sock = (ROOT / "therayu_app/lib/services/pose_socket.dart").read_text(encoding="utf-8")
ctrl = (ROOT / "therayu_app/lib/services/session_controller.dart").read_text(encoding="utf-8")

for kind in ["session_start", "session_end", "exercise_start", "exercise_stop"]:
    check(f"client sends {kind:16} -> server handles it",
          f"'type': '{kind}'" in sock and f'kind == "{kind}"' in ws)

for reply in ["session_started", "session_ended", "exercise_started",
              "exercise_saved", "records_error"]:
    check(f"server sends {reply:17} -> client handles it",
          f'"type": "{reply}"' in ws and f"'{reply}'" in sock and f"'{reply}'" in ctrl)

# ---------------------------------------------- pose reply extra fields ----
print("\n4. LIVE EXERCISE FIELDS ON THE POSE REPLY")
frame = (ROOT / "therayu_app/lib/models/pose_frame.dart").read_text(encoding="utf-8")
for key in ["exercise_active", "exercise_reps"]:
    check(f"{key} sent by server and parsed by client",
          f'"{key}"' in ws and f"'{key}'" in frame)

# ---------------------------------------------------- theme discipline ----
print("\n5. THEME DISCIPLINE")
new_ui = ["therayu_app/lib/widgets/record_widgets.dart",
          "therayu_app/lib/widgets/exercise_runner.dart",
          "therayu_app/lib/screens/patients_screen.dart",
          "therayu_app/lib/screens/patient_detail_screen.dart"]
literals = []
for f in new_ui:
    src = (ROOT / f).read_text(encoding="utf-8")
    for m in re.finditer(r"Color\(0x[0-9A-Fa-f]{8}\)|Colors\.\w+", src):
        literals.append(f"{pathlib.Path(f).name}: {m.group(0)}")
check("no colour literals in the new UI files", not literals, str(literals[:5]))

# --------------------------------------------------- engine still clean ----
print("\n6. CLINICAL ENGINE")
# Detection, filtering and the ROM accumulator are never edited by feature work;
# those stay byte-identical. physio_angles.py is excluded on purpose: it is the
# measurement engine and DOES get corrected when a measurement is proven wrong.
# Byte-equality is the wrong guard for it, so its own accuracy suite is run
# instead - that asserts what actually matters, which is that the numbers are
# right and that MediaPipe's z still has no influence.
import subprocess
for f in ["upper_body_ai/inference/pipeline.py",
          "upper_body_ai/src/pose_detector.py",
          "upper_body_ai/src/physio_analysis.py"]:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", f])
    check(f"{pathlib.Path(f).name:24} unchanged since last commit", r.returncode == 0)

r = subprocess.run([sys.executable, "../tests/test_angle_accuracy.py"],
                   cwd="upper_body_ai", capture_output=True, text=True)
check("physio_angles.py still passes its accuracy suite", r.returncode == 0,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-120:])

print("\n" + "=" * 72)
print(f"RESULT: {'ALL CONTRACT CHECKS PASS' if not FAIL else str(len(FAIL)) + ' FAILURE(S)'}")
for f in FAIL:
    print("   -", f)
sys.exit(1 if FAIL else 0)

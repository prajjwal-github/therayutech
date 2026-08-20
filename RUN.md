# How to run Therayu

**Three commands. No Android Studio, no phone, no manual downloads.**

```powershell
cd C:\Users\Prajjwal\OneDrive\Desktop\therayu

powershell -ExecutionPolicy Bypass -File .\setup_python.ps1    # reuses your working Python
powershell -ExecutionPolicy Bypass -File .\setup_flutter.ps1   # installs Flutter for you
```

Then **close VS Code and reopen it** (so it picks up the new PATH), and press
`Ctrl+Shift+D` → **▶ Server + Chrome (start here)** → `F5`.

Chrome opens, asks for camera permission, and you're live.

---

## Why Chrome and not Android

Android needs Android Studio, a ~5 GB SDK, a physical phone, USB debugging and a
shared Wi-Fi network — five things that can each fail independently.

Chrome needs the Flutter SDK and nothing else. The browser supplies the camera,
the server is on `localhost` so there's no IP to type and no firewall to fight,
and the address field is prefilled.

**Android still works** and `setup_flutter.ps1` sets it up too. It's just the
second thing to try, not the first.

| | Chrome | Android |
| --- | --- | --- |
| Extra installs | none | Android Studio + SDK (~5 GB) |
| Hardware | your webcam | a phone + USB cable |
| Network | localhost | shared Wi-Fi + firewall rule |
| Frame rate | 10–15 fps | ~20 fps |
| Time to first run | ~10 min | ~60 min |

The frame-rate gap is inherent: `camera_web` can't hand out raw sensor planes, so
the web path polls `takePicture()` and sends JPEG, while Android streams raw
YUV420 repacked to NV21. Same server, same clinical maths, different pixel
plumbing.

---

## What the two setup scripts do

### `setup_python.ps1`

Finds a Python that can actually import `mediapipe` and `cv2`, then builds a venv
on top of it with `--system-site-packages` so your existing install is reused
rather than re-downloading 300 MB. Adds FastAPI, uvicorn and websockets.

> **Note on an earlier bug:** the first version of this script gated on the
> version number (3.9–3.12) and wrongly rejected your working Python. MediaPipe
> has since shipped wheels for newer versions, so any hard-coded range goes
> stale. It now asks whether the thing works instead of what version it claims
> to be.

### `setup_flutter.ps1`

- Downloads the Flutter SDK to `C:\src\flutter` if missing (resolves the current
  stable release from Flutter's manifest rather than hard-coding a version)
- Sets your user PATH permanently
- Generates `web/` and `android/` platform folders
- Patches the Android manifest for camera + cleartext LAN access
- Runs `pub get` and `analyze`

Flags: `-SkipAndroid` for web only, `-Force` to re-download the SDK.

---

## Running it

### From VS Code (recommended)

`Ctrl+Shift+D` → pick a config → `F5`:

| Config | What it does |
| --- | --- |
| **▶ Server + Chrome (start here)** | server + app in one go |
| **▶ Server + Android** | same, on a connected phone |
| Therayu in Chrome | app only, server already running |
| Inference server | Python with breakpoints |
| Therayu on Android (release) | phone, full speed |

### From the terminal

```powershell
# Terminal 1 — leave running
.\start_server.bat

# Terminal 2
cd therayu_app
flutter run -d chrome
```

In the app: pick a body profile → the address is prefilled with `localhost:8765`
→ **Test connection** → **Start live session** → allow the camera → step back
until the status chip turns green.

While `flutter run` is attached: `r` hot reload, `R` hot restart, `q` quit.

---

## Adding Android later

```powershell
winget install Google.AndroidStudio
```

Open it once so it downloads the SDK, close it, then:

```powershell
flutter doctor
flutter doctor --android-licenses     # press y at every prompt
```

On the phone: **Settings → About phone** → tap **Build number** seven times →
**Developer options** → enable **USB debugging** → plug in → tap **Allow**.

```powershell
flutter devices                        # confirm it appears
cd therayu_app
flutter run --release                  # --release matters, see below
```

Now the address is your **PC's LAN IP**, not localhost — the server prints it, or
run `ipconfig` and take the IPv4 address under your Wi-Fi adapter. Allow Python
through Windows Firewall on **private networks** when prompted.

Build a shareable APK:

```powershell
flutter build apk --release
# build\app\outputs\flutter-apk\app-release.apk
```

---

## Troubleshooting

### `flutter` not recognised after setup

The script set your PATH permanently, but terminals opened before then still
have the old copy. **Close VS Code entirely and reopen it.** Verify with
`echo $env:Path`.

### Chrome shows no camera / permission denied

Chrome only grants camera access on `localhost` or HTTPS. Flutter's dev server
uses `localhost`, so this works — but if you denied the prompt, clear it via the
padlock icon in the address bar and reload.

### "Test connection" fails in Chrome

Is the server running? Open `http://localhost:8765/health` directly — JSON means
it's up. If that works but the app's check doesn't, the server predates the CORS
fix; restart it.

### Frame rate is low in Chrome

Expected: 10–15 fps. The browser JPEG-encodes every frame. For higher, use
Android with `--release`.

### On Android: connects, then "Reconnecting…"

PC asleep, or the phone roamed to another access point. Also check both are on
the same Wi-Fi *band* — many routers expose 2.4 GHz and 5 GHz as separate
networks.

### On Android: "Timed out"

Firewall. Run PowerShell as Administrator:

```powershell
New-NetFirewallRule -DisplayName "Therayu inference server" `
  -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

### Skeleton offset from the body

Controls (slider icon, top right) → toggle **Mirror view**. Some devices mirror
the camera preview in hardware.

### All angles show `N/A`

Framing is invalid — the engine refuses to report numbers it can't stand behind.
Follow the on-screen guidance. `TRACKING…` on one joint means that landmark is
below the 0.50 confidence floor. `SIDE VIEW REQ` on shoulder flexion is correct
in a front view; sagittal flexion needs a side-on camera.

### Gradle hangs on the first Android build

It's downloading its toolchain — give it ten minutes. If it truly fails:
`flutter clean; flutter pub get; flutter run --release`.

---

## Command reference

| Task | Command |
| --- | --- |
| Check prerequisites | `.\check_setup.ps1` |
| Set up Python | `powershell -ExecutionPolicy Bypass -File .\setup_python.ps1` |
| Set up Flutter | `powershell -ExecutionPolicy Bypass -File .\setup_flutter.ps1` |
| Web only | `.\setup_flutter.ps1 -SkipAndroid` |
| Start server | `.\start_server.bat` |
| Server on another port | `cd upper_body_ai; python -m server.ws_server --port 9000` |
| Run in Chrome | `cd therayu_app; flutter run -d chrome` |
| Run on Android | `cd therayu_app; flutter run --release` |
| List devices | `flutter devices` |
| Build APK | `cd therayu_app; flutter build apk --release` |
| Lint | `cd therayu_app; flutter analyze` |
| Clean rebuild | `cd therayu_app; flutter clean; flutter pub get` |
| Original desktop app | `cd upper_body_ai; python live_pose.py` |
| Server health | `http://localhost:8765/health` |

---

## What runs where

```
                    ┌──────────────────────────────────────┐
  Chrome / phone ──►│  camera  ──►  JPEG (web)             │
                    │              NV21  (android)         │
                    └───────────────┬──────────────────────┘
                                    │  WebSocket
                    ┌───────────────▼──────────────────────┐
  PC (.venv)        │  ws_server.py                        │
                    │    RealTimeInferencePipeline         │
                    │    MediaPipe · filters · goniometry  │
                    │    PhysiotherapyAnalysisEngine       │
                    └───────────────┬──────────────────────┘
                                    │  landmarks + angles JSON
                    ┌───────────────▼──────────────────────┐
  Chrome / phone ◄──│  skeleton overlay · HUD · ROM cards  │
                    └──────────────────────────────────────┘
```

The client never does inference. It captures frames and renders what comes back.
Every clinical number is produced by the Python engine you already validated —
`live_pose.py` and the app give identical readings.

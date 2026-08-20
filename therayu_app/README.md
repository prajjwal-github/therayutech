# Therayu — Flutter Android app

The AI physiotherapy platform as a native Android app, backed by the existing
Python inference engine over Wi-Fi.

---

## How it fits together

```
┌─────────────────────── ANDROID PHONE ───────────────────────┐
│  camera (YUV420)                                            │
│      └─> NV21 repack (strided copy, ~2-4 ms)                │
│              └─> WebSocket binary frame ──────────┐         │
│                                                   │         │
│  CustomPainter skeleton + HUD  <── PoseFrame JSON ─┤         │
└───────────────────────────────────────────────────┼─────────┘
                                                    │ Wi-Fi (LAN)
┌──────────────────────────── PC ───────────────────┼─────────┐
│  server/ws_server.py                              │         │
│      decode NV21 -> rotate upright -> mirror  <───┘         │
│      └─> RealTimeInferencePipeline        (UNCHANGED)        │
│              MediaPipe Pose + Hands                         │
│              SubPixelRefiner                                │
│              ConfidenceCalibrator                           │
│              AnatomicalValidator                            │
│              One-Euro / Kalman / EMA filters                │
│              PhysiotherapyAngleEngine                       │
│      └─> PhysiotherapyAnalysisEngine      (UNCHANGED)        │
│      └─> JointTracker                     (UNCHANGED)        │
│      └─> MedicalGUIRenderer + SessionLogger  (captures only) │
└─────────────────────────────────────────────────────────────┘
```

**No clinical code was reimplemented.** The server imports your existing modules
and calls them in the same order as `live_pose.py`'s `inference_worker`. Angles,
filtering, framing validation and ROM tracking are byte-for-byte the same as the
desktop app.

### Why frames go to the PC instead of running on-device

MediaPipe Holistic, the One-Euro filter chain, the anatomical validator and the
goniometric engine are all Python/NumPy. Porting them to Dart would mean
reimplementing validated clinical maths and revalidating every angle. Streaming
pixels instead keeps the engine you already trust as the single source of truth.

Worth knowing: `models/final/best_upper_body_model.pkl` is **not** part of the
live path — only `src/trainer.py`, `src/evaluator.py` and `src/inference.py` load
it. `live_pose.py` never touches it. So nothing about the trained classifier is
affected by any of this.

---

## Setup

### 1. Start the server (PC)

```bash
cd upper_body_ai
pip install -r server/requirements-server.txt
python -m server.ws_server
```

It prints every LAN address it is reachable on:

```
  ENTER ONE OF THESE IN THE ANDROID APP:
    ws://192.168.1.7:8765/ws
```

On the first run Windows will ask to allow Python through the firewall —
**allow it, and make sure "Private networks" is ticked.** This is the single most
common reason the app cannot connect.

Sanity check from any browser on the same Wi-Fi: `http://192.168.1.7:8765/health`

### 2. Build the app (PC)

```powershell
cd therayu_app
.\setup_android.ps1
```

The script generates the `android/` folder, patches the manifest for camera +
cleartext LAN traffic, and runs `flutter pub get`. It preserves `lib/` and
`pubspec.yaml`, so it is safe to re-run.

Prerequisites: Flutter SDK on PATH, Android Studio for the SDK, and
`flutter doctor` showing no Android issues.

### 3. Run on the phone

Same Wi-Fi as the PC, USB debugging on, plugged in:

```bash
flutter run --release
```

`--release` matters — a debug build runs Dart unoptimised and the NV21 repack
feels sluggish.

Shareable APK instead:

```bash
flutter build apk --release
# build/app/outputs/flutter-apk/app-release.apk
```

### 4. In the app

Pick a body profile, type the address from step 1 (`192.168.1.7:8765` is enough —
the scheme and `/ws` path are filled in), tap **Test connection**, then
**Start live session**.

---

## What's on the live screen

| Region | Contents |
| --- | --- |
| Top strip | connection dot, session timer, throughput, round-trip latency, active filter, REC indicator, controls, exit |
| Camera viewport | live video, skeleton, glowing joint nodes, finger skeletons, goniometric arcs with floating angle badges, framing brackets, tracking badge, positioning guidance |
| Bottom panel | movement-quality ring, detected movement, symmetry / COG pills, clinical cue bar, scrollable clinical angle cards with session peaks |
| Body mode | Upper / Lower / Full segmented control over the viewport |

### Desktop hotkey → app equivalent

| `live_pose.py` | In the app |
| --- | --- |
| startup prompt, `1`/`2`/`3`, `U`/`L`/`F` | body-mode segmented control |
| `R` record | Controls → Record annotated video |
| `S` screenshot | Controls → Save annotated screenshot |
| `H` hands | Controls → Hand & finger skeleton |
| `B` bones / `J` joints | Controls → Bones / Joint nodes |
| `A` angle HUD | Controls → Angle cards |
| `C` confidence badge | Controls → Tracking badge |
| `1`/`2`/`3` filter | Controls → Temporal filter |
| `Q` quit | ✕ in the top strip |

Recordings and screenshots are rendered by `MedicalGUIRenderer` on the PC and
land in `output/recordings/` and `output/screenshots/`, exactly as before.

---

## Design decisions worth knowing

**Latest-frame-wins, not a queue.** The socket refuses to send when two frames
are already unacknowledged, and the server overwrites any frame that has not been
processed yet. Buffering video on Wi-Fi converts dropped frames into growing
latency, which is worse for live movement assessment than a lower frame rate.
This mirrors `live_pose.py`'s `queue.Queue(maxsize=2)` eviction.

**Raw NV21, not JPEG.** JPEG encoding in Dart costs 30–60 ms per frame and would
cap the session in the single digits. Repacking YUV420 planes to NV21 is a
strided memory copy (~2–4 ms) and OpenCV converts colour on the PC with one SIMD
call. The stride handling matters: Android pads plane rows to hardware alignment
and delivers chroma as planar or semi-planar depending on the device — ignoring
that is the classic cause of green-skewed or sheared frames.

**Default resolution is Fast (~320×240).** Uncompressed frames cost bandwidth in
proportion to pixels: roughly 18 / 55 / 165 Mbps for the three presets. Fast is
not much of a compromise — MediaPipe's detector runs near 256×256 internally, and
`PoseDetector` downsamples anything wider than 640 px before inference anyway.
Raise it only on 5 GHz Wi-Fi.

**Skeleton alignment is structural.** The viewport computes the `BoxFit.cover`
rect itself and hands the identical rect to both `CameraPreview` and the painter,
so the overlay cannot drift. Landmarks arrive normalised against the upright,
already-mirrored frame (`frame_w`/`frame_h` come back with every reply), so no
correction happens on the phone.

**Left/right colour mapping was made consistent.** `medical_gui.py` used blue for
the left arm but amber for the left leg, and vice versa. Here LEFT is always the
brand teal and RIGHT always the brand gold — the side cue and the identity doing
the same job. Flip `boneLeft`/`boneRight` in `app_theme.dart` to restore the
original mapping.

**Mirroring has a clinical caveat.** Mirroring is on by default to match
`config.yaml`'s `flip_horizontal: true`. A mirrored frame swaps which limb
MediaPipe labels LEFT vs RIGHT, since the model reasons about the image as
presented. Great for a patient watching themselves; turn it off (Controls →
Mirror view) when side labels must be anatomically literal.

**Three "no value" states are preserved.** The engine deliberately returns `None`
for a joint below the 0.50 confidence floor, the string `SIDE VIEW REQ` for
sagittal shoulder flexion, and zeroes everything when framing is invalid. The app
renders these as `TRACKING…`, `SIDE VIEW REQ` and `N/A` respectively rather than
collapsing them to `0°` — the "no fake angles" policy carried through to the UI.

---

## Theme

Applied from the Therayu "Final Designs" Figma. The brand runs on two colours
over a dark ground, and that maps onto clinical semantics cleanly enough that it
is used directly rather than having a separate status palette bolted over it:

| Token | Hex | Where it appears |
| --- | --- | --- |
| `brandTeal` | `#0E3A46` | splash / header ground, HUD card fill |
| `brandTealDeep` | `#092B34` | app background |
| `brandTealLight` | `#14495A` | card headers, inputs, sheets |
| `brandGold` | `#D9A32B` | the wave, right-side limbs, end-of-range warnings |
| `brandGoldLight` / `brandGoldDeep` | `#EFC559` / `#A97F1E` | wave gradient edges |
| `brandCyan` | `#34AFAF` | wordmark, joint nodes, active chips, arcs |
| `brandCyanLight` | `#62C4C3` | primary button fill (the Get OTP / Verify colour) |
| `success` | `#4FD1A5` | ready state, in-range angles, torso bones |
| `danger` | `#E2664C` | terracotta, warmed to sit beside the gold |

**teal = interactive / tracked / in-range. gold = attention / end-of-range.**

Two consequences worth flagging:

- **Limbs are now LEFT = teal, RIGHT = gold** — the two brand colours doing the
  side cue. This also fixes the original renderer's inconsistency, where
  `medical_gui.py` used blue for the left arm but amber for the left leg.
- **Gold is the warning colour.** In the Figma frames gold is the only thing
  allowed to demand attention, which is exactly the job "positioning needed" and
  "approaching end of range" do here.

### Brand elements

`lib/widgets/brand.dart` rebuilds the identity as widgets rather than shipping
raster assets, so it stays crisp at any density and recolours instantly:

- `BrandHeader` — the login-screen composition: teal block with the gold wave
  along its bottom edge. The gold layer is drawn with a small downward bias and
  the teal is clipped to the same curve, which is what produces the gold sliver
  peeking out from underneath. Both layers call the same path builder, so they
  cannot drift apart and leave a seam.
- `BrandBackdrop` — the splash: full-bleed teal with the gold sweeping a corner.
- `Wordmark` — "therayu" with the gold `y` descender and the Meditech Solutions
  tagline.
- `BrandMarkTile`, `GoldRule` — the logo tile and gold divider.

The faint watermark on the teal ground is a sparse arc lattice at 3.5% alpha.

### Using the real logo

The wordmark is currently set type, not the actual letterforms. To drop in the
export: put it at `assets/images/therayu_wordmark.png`, declare it under
`assets:` in `pubspec.yaml`, and replace the `Text.rich` in `Wordmark` with an
`Image.asset`. Spacing and the tagline already match the lockup, so nothing else
changes.

For the typeface, add `.ttf` files to `assets/fonts/`, uncomment the `fonts:`
block in `pubspec.yaml`, and set `AppTheme.fontFamily`. Poppins or Quicksand read
closest to the Figma wordmark if you don't have the original licensed.

### Re-skinning further

Every colour, radius, gap, stroke and text style lives in
**`lib/theme/app_theme.dart`** — verified: no widget file contains a literal
colour. `AppPalette` for colours, `AppRadii` / `AppGaps` / `AppStrokes` for
geometry, `AppTheme` for text styles. Each constant is commented with where it
appears on screen.

### Not built

The Figma set includes phone-number and OTP verification screens. Those need an
SMS provider (Firebase Auth, Twilio) and a backend, so they are out of scope
here — the app opens on the splash and goes straight to the connect screen. Say
the word if you want them as UI-only screens wired to a stub.

---

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Test connection times out | Windows Firewall blocking Python on private networks, or phone on a different Wi-Fi band/network |
| Connects, then "Reconnecting…" | PC went to sleep, or the phone roamed to another access point |
| Skeleton offset from the body | `Mirror view` disagrees with what the preview shows — toggle it in Controls |
| Frame rate below ~10 fps | drop Stream quality to Fast; check you built with `--release` |
| `TRACKING…` on a joint | landmark confidence under 0.50 — the engine is refusing to guess |
| `SIDE VIEW REQ` | sagittal shoulder flexion needs a side-on camera; expected in front view |
| All angles `N/A` | framing invalid — follow the on-screen positioning guidance |
| Black preview after backgrounding | Android revoked the camera; the app reacquires on resume |

---

## Files

```
therayu_app/
  lib/
    main.dart                        app entry, portrait lock
    theme/app_theme.dart             ← THE ONLY FILE TO EDIT FOR RE-SKINNING
    models/
      pose_frame.dart                wire models, three-way angle state
      skeleton_topology.dart         bones/arcs/HUD groups, ported from medical_gui.py
    services/
      pose_socket.dart               transport, backpressure, auto-reconnect
      camera_streamer.dart           camera + YUV420->NV21 repack
      session_controller.dart        single ChangeNotifier the UI listens to
    screens/
      splash_screen.dart             brand splash, warms the camera
      connect_screen.dart            mode picker, server address, health check
      live_session_screen.dart       the live session
    widgets/
      brand.dart                     wave, wordmark, logo tile, watermark
      skeleton_painter.dart          skeleton, arcs, badges, quality ring
      angle_card.dart                clinical angle HUD card
      status_widgets.dart            telemetry bar, guidance, assessment, cues
      controls_sheet.dart            everything the hotkeys used to do
  setup_android.ps1                  generates android/ and patches the manifest
  android_manifest_snippet.xml       reference manifest

upper_body_ai/server/
  ws_server.py                       LAN inference server (new; imports only)
  requirements-server.txt            fastapi + uvicorn + websockets
```

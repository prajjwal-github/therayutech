# Therayu — Intern Test Pass

Fill this in as you go, save it as `TESTING-<yourname>.md`, and send it back.

Every test below has an **Expected** line. If what you see matches, tick Pass. If
it doesn't, tick Fail and write what you actually saw — including the numbers in
the top-left corner of the screen. "It didn't work" is not usable; "0 fps · 0 ms,
green dot, no skeleton" tells us exactly where to look.

---

## 0. Your setup

| | |
|---|---|
| Name | |
| Date | |
| Windows version | |
| Chrome version | *(paste from `chrome://version`)* |
| Webcam make/model | |
| Laptop or external camera | |

Run this and paste the output into the box below:

```powershell
cd C:\path\to\therayu
.\diagnose.ps1
```

<details><summary>diagnose.ps1 output</summary>

```
paste here
```

</details>

---

## 1. Getting it running

Full instructions are in [RUN.md](RUN.md). The short version:

```powershell
git clone https://github.com/prajjwal-github/therayutech.git
cd therayutech

.\setup_python.ps1
.\setup_flutter.ps1
```

Then two terminals **inside VS Code**:

```powershell
# Terminal 1 — leave this running
cd upper_body_ai
python server\ws_server.py

# Terminal 2
cd therayu_app
flutter run -d chrome
```

| # | Test | Expected | Pass | Notes |
|---|---|---|---|---|
| 1.1 | `setup_python.ps1` completes | Ends with a success summary, no red text | ☐ | |
| 1.2 | `setup_flutter.ps1` completes | Ends with a success summary, no red text | ☐ | |
| 1.3 | Server starts | Banner prints, shows a LAN IP and port 8765 | ☐ | |
| 1.4 | Chrome opens the app | Splash screen, then the connect screen | ☐ | |
| 1.5 | Server address is pre-filled | Shows `localhost:8765` without typing | ☐ | |
| 1.6 | "Test connection" succeeds | Green confirmation | ☐ | |

**How long did setup take, start to finish?** ______ minutes

**Anything in RUN.md that was wrong, missing, or confusing?**

---

## 2. Camera and capture health

Stand about 2 metres back, upper body in frame, decent room light.

| # | Test | Expected | Pass | Notes |
|---|---|---|---|---|
| 2.1 | Chrome asks for camera permission | Prompt appears; Allow works | ☐ | |
| 2.2 | Live preview appears | Full-screen video, not cropped or stretched | ☐ | |
| 2.3 | Frame counter moves | Top-left shows a non-zero fps within ~3 seconds | ☐ | |
| 2.4 | Round-trip is sane | ms figure between roughly 40 and 250 | ☐ | |
| 2.5 | No stall banner | You do **not** see "CAMERA FRAMES NOT REACHING SERVER" | ☐ | |

**Record the steady-state figures:** ______ fps · ______ ms

> If you get a green connection dot but **0 fps**, that is a specific bug we
> care about. Screenshot it, and copy whatever the server terminal printed.

---

## 3. Body modes

Use the `Upper` / `Lower` / `Full` buttons at the bottom.

| # | Mode | Stand so that… | Expected | Pass | Notes |
|---|---|---|---|---|---|
| 3.1 | Upper | head, shoulders, both arms visible | Skeleton appears, badge reads Ready | ☐ | |
| 3.2 | Upper | hip line visible | A line connects left hip to right hip | ☐ | |
| 3.3 | Lower | hips, knees, feet visible | Skeleton appears, badge reads Ready | ☐ | |
| 3.4 | Full | whole body visible | Skeleton appears, badge reads Ready | ☐ | |
| 3.5 | Any | switch modes while live | Changes within a second, no freeze or crash | ☐ | |

---

## 4. Framing guidance

Deliberately stand wrong and check the app tells you something **useful and
relevant to the mode you're in**.

| # | Mode | Do this | Expected message | Pass | Actual message |
|---|---|---|---|---|---|
| 4.1 | Upper | let your head go above the top edge | asks you to move back / tilt the camera, mentions the **head** | ☐ | |
| 4.2 | Upper | drop both hands below the bottom edge | asks you to keep your **hands** in frame | ☐ | |
| 4.3 | Upper | step so your legs leave the frame | **stays Ready** — upper mode ignores legs | ☐ | |
| 4.4 | Lower | let your head leave the frame | **stays Ready** — lower mode ignores the head | ☐ | |
| 4.5 | Lower | let your feet leave the bottom edge | asks you to step back, mentions **feet** | ☐ | |
| 4.6 | Full | let your feet leave the bottom edge | asks you to step back, lower body not visible | ☐ | |
| 4.7 | Any | step far to one side | tells you to move the **opposite** way | ☐ | |
| 4.8 | Any | walk out of frame entirely | "Waiting for … detection", no skeleton | ☐ | |

> 4.3 and 4.4 are the important ones. If upper-body mode complains about your
> legs, that's a bug.

---

## 5. Angle accuracy

This is the part we most need checked. Hold each pose still for ~3 seconds and
read the corner cards.

| # | Pose | Reading | Expected | Pass | Actual |
|---|---|---|---|---|---|
| 5.1 | Arms hanging straight down at your sides | Elbow flexion, both | **0–10°** | ☐ | L ___ R ___ |
| 5.2 | Same pose | Shoulder abduction, both | **0–20°** | ☐ | L ___ R ___ |
| 5.3 | T-pose, arms straight out horizontally | Shoulder abduction, both | **80–100°** | ☐ | L ___ R ___ |
| 5.4 | T-pose | Elbow flexion, both | **0–15°** | ☐ | L ___ R ___ |
| 5.5 | Upper arms down, forearms up at a right angle | Elbow flexion, both | **75–105°** | ☐ | L ___ R ___ |
| 5.6 | Both arms straight overhead | Shoulder abduction, both | **150–180°** | ☐ | L ___ R ___ |
| 5.7 | Left and right values in a symmetric pose | Difference between sides | **under 15°** | ☐ | diff ___ |
| 5.8 | Any pose held still | Numbers jitter | **under ±5°** frame to frame | ☐ | |

**The single most important check:** in 5.1 and 5.4 your arms are *straight*. If
the app reports 20°, 30° or more of elbow flexion for a straight arm, write down
the exact number — that was a real bug and we need to know if it's back.

---

## 6. Skeleton tracking

| # | Test | Expected | Pass | Notes |
|---|---|---|---|---|
| 6.1 | Step to your left | Skeleton moves the **same** way you do, not opposite | ☐ | |
| 6.2 | Raise one arm | Only that arm's skeleton moves | ☐ | |
| 6.3 | Move at normal speed | Skeleton keeps up, no obvious drag | ☐ | |
| 6.4 | Skeleton position | Bones sit **on** your limbs, not offset to one side | ☐ | |
| 6.5 | Turn hand tracking on (Controls) | Finger skeleton appears | ☐ | |
| 6.6 | With hand tracking on | Note the fps drop | ☐ | before ___ after ___ |

---

## 7. Controls

Open the sliders icon, top right.

| # | Control | Expected | Pass | Notes |
|---|---|---|---|---|
| 7.1 | Bones toggle | Bones disappear / reappear | ☐ | |
| 7.2 | Joint nodes toggle | Dots disappear / reappear | ☐ | |
| 7.3 | Goniometric arcs toggle | Angle sweeps disappear / reappear | ☐ | |
| 7.4 | Angle cards toggle | Corner cards disappear / reappear | ☐ | |
| 7.5 | Fast pose model | fps goes up, accuracy drops slightly | ☐ | before ___ after ___ |
| 7.6 | Mirror view | Preview flips; skeleton still follows you correctly | ☐ | |
| 7.7 | Save screenshot | File appears in `upper_body_ai/output/screenshots` | ☐ | |
| 7.8 | Start/stop recording | File appears in `upper_body_ai/output/recordings` | ☐ | |
| 7.9 | Reset ROM history | Peak values reset to current | ☐ | |
| 7.10 | Switch camera *(if you have two)* | Switches without crashing | ☐ | |

---

## 8. Robustness

| # | Test | Expected | Pass | Notes |
|---|---|---|---|---|
| 8.1 | Stop the server (Ctrl+C) while live | App shows disconnected, doesn't hang or crash | ☐ | |
| 8.2 | Restart the server | App reconnects on its own within ~10s | ☐ | |
| 8.3 | Cover the camera completely | "No person detected", no crash | ☐ | |
| 8.4 | Uncover it | Skeleton returns within a second or two | ☐ | |
| 8.5 | Two people in frame | Tracks one person, doesn't flicker between them | ☐ | |
| 8.6 | Resize the browser window small | Cards don't overlap or get cut off | ☐ | |
| 8.7 | Leave it running 10 minutes | fps stays steady, no slowdown | ☐ | fps at start ___ end ___ |
| 8.8 | Refresh the page mid-session | Recovers cleanly | ☐ | |

---

## 9. Anything else

**Bugs found that aren't covered above:**

For each one, give us: what you did, what you expected, what happened, the
fps/ms readout, and a screenshot.

1.
2.
3.

**Things that felt slow, awkward or confusing (not bugs, just bad UX):**

1.
2.
3.

**Overall — would you trust the angle numbers this app produced?**

☐ Yes  ☐ Mostly  ☐ No

Why:

---

## How to send this back

1. Save as `TESTING-<yourname>.md`
2. Attach any screenshots in a folder named `TESTING-<yourname>-screenshots`
3. Send both to Prajjwal

Screenshots matter more than descriptions. If something looks wrong, capture the
**whole window** so the fps/ms readout in the corner is visible.

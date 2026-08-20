<#
================================================================================
 THERAYU — PREREQUISITE CHECK
================================================================================
 Read-only. Tells you exactly what is installed, what is missing, and what to do
 about it. Run this first, and again any time something stops working.

     .\check_setup.ps1
================================================================================
#>

Set-Location $PSScriptRoot

$pass = 0; $fail = 0

function Head($t) { Write-Host "`n$t" -ForegroundColor Cyan; Write-Host ('-' * 72) -ForegroundColor DarkGray }
function Good($t) { Write-Host "  [ok]   $t" -ForegroundColor Green; $script:pass++ }
function Bad($t, $fix) {
    Write-Host "  [x]    $t" -ForegroundColor Red
    if ($fix) { Write-Host "         -> $fix" -ForegroundColor Yellow }
    $script:fail++
}
function Note($t) { Write-Host "  [i]    $t" -ForegroundColor DarkGray }

Write-Host "`n============================ THERAYU SETUP CHECK ============================" -ForegroundColor White

# ------------------------------------------------------------------ 1. Python
Head '1. Python (runs the pose engine)'

if (Get-Command python -ErrorAction SilentlyContinue) {
    # Probe via a temp file, never `python -c "..."`. Windows PowerShell 5.1
    # strips embedded double quotes when passing arguments to native commands,
    # so an inline -c script arrives as a SyntaxError and looks like a broken
    # Python install. A file path has no quotes to strip.
    $probe = Join-Path $env:TEMP "therayu_check_$PID.py"
    @'
import sys
try:
    import mediapipe, cv2
    print("ENGINE|%d.%d.%d|%s" % (sys.version_info[0], sys.version_info[1], sys.version_info[2], mediapipe.__version__))
except Exception:
    print("BARE|%d.%d.%d" % sys.version_info[:3])
'@ | Set-Content -Path $probe -Encoding ASCII

    $out = (& python $probe 2>&1 | Select-Object -First 1)
    Remove-Item $probe -ErrorAction SilentlyContinue

    if ("$out" -like 'ENGINE|*') {
        $p = "$out".Split('|')
        Good "python $($p[1])  ·  mediapipe $($p[2]) importable"
    } elseif ("$out" -like 'BARE|*') {
        $p = "$out".Split('|')
        Bad "python $($p[1]) runs but cannot import mediapipe" `
            'setup_python.ps1 will install it into .venv'
    } else {
        Bad "python found but the probe failed: $out" 'Run .\diagnose.ps1 for detail'
    }
} else {
    Bad 'python not on PATH in THIS terminal' `
        'Works in cmd but not here? Close VS Code completely and reopen. Run .\diagnose.ps1'
}

# ------------------------------------------------------------------- 2. venv
Head '2. Virtual environment'

if (Test-Path '.venv\Scripts\python.exe') {
    Good '.venv exists'

    $vprobe = Join-Path $env:TEMP "therayu_venvcheck_$PID.py"
    @'
for m in ["cv2", "mediapipe", "numpy", "yaml", "fastapi", "uvicorn", "websockets"]:
    try:
        __import__(m)
        print("OK|" + m)
    except Exception:
        print("MISSING|" + m)
'@ | Set-Content -Path $vprobe -Encoding ASCII

    $res = & '.venv\Scripts\python.exe' $vprobe 2>&1
    Remove-Item $vprobe -ErrorAction SilentlyContinue

    foreach ($line in $res) {
        $t = "$line"
        if ($t -like 'OK|*')      { Good "  $($t.Split('|')[1]) importable" }
        elseif ($t -like 'MISSING|*') { Bad "  $($t.Split('|')[1]) missing" 'Re-run setup_python.ps1' }
    }
} else {
    Bad '.venv not created' 'Run: powershell -ExecutionPolicy Bypass -File setup_python.ps1'
}

# ----------------------------------------------------------------- 3. Flutter
Head '3. Flutter (builds the Android app)'

if (Get-Command flutter -ErrorAction SilentlyContinue) {
    $fv = (flutter --version 2>$null | Select-Object -First 1)
    Good $fv

    Note 'Running flutter doctor (this takes a moment)...'
    $doctor = (flutter doctor 2>&1 | Out-String)

    if ($doctor -match '\[.\] Flutter') { Good 'Flutter SDK detected' }

    if ($doctor -match '\[√\] Android toolchain' -or $doctor -match '\[✓\] Android toolchain') {
        Good 'Android toolchain ready'
    } elseif ($doctor -match 'Android license status unknown' -or $doctor -match 'not accepted') {
        Bad 'Android SDK licences not accepted' 'Run: flutter doctor --android-licenses  (press y to everything)'
    } elseif ($doctor -match 'Android toolchain') {
        Bad 'Android toolchain incomplete' 'Install Android Studio, open it once, then run: flutter doctor'
    } else {
        Bad 'Android toolchain not found' 'Install Android Studio from developer.android.com/studio'
    }
} else {
    Bad 'flutter not on PATH' 'Install from docs.flutter.dev/get-started/install/windows, add flutter\bin to PATH, reopen the terminal'
}

# ------------------------------------------------------- 4. Flutter project
Head '4. Flutter project state'

if (Test-Path 'therayu_app\pubspec.yaml') { Good 'therayu_app/pubspec.yaml present' }
else { Bad 'therayu_app/pubspec.yaml missing' 'The app folder is incomplete' }

if (Test-Path 'therayu_app\android') {
    Good 'android/ scaffolding generated'

    $manifest = 'therayu_app\android\app\src\main\AndroidManifest.xml'
    if (Test-Path $manifest) {
        $m = Get-Content $manifest -Raw
        if ($m -match 'android.permission.CAMERA') { Good '  CAMERA permission present' }
        else { Bad '  CAMERA permission missing' 'Re-run therayu_app\setup_android.ps1' }

        if ($m -match 'usesCleartextTraffic') { Good '  cleartext traffic enabled (needed for ws:// on a LAN)' }
        else { Bad '  cleartext traffic not enabled' 'Re-run therayu_app\setup_android.ps1' }
    }
} else {
    Bad 'android/ not generated' 'Run: cd therayu_app; .\setup_android.ps1'
}

if (Test-Path 'therayu_app\.dart_tool\package_config.json') { Good 'packages resolved (flutter pub get has run)' }
else { Note 'packages not resolved yet - run: cd therayu_app; flutter pub get' }

# ------------------------------------------------------------------ 5. Device
Head '5. Connected device'

if (Get-Command flutter -ErrorAction SilentlyContinue) {
    $devices = (flutter devices 2>&1 | Out-String)
    if ($devices -match 'android') {
        Good 'an Android device is visible to Flutter'
        $devices.Split("`n") | Where-Object { $_ -match 'android' } | ForEach-Object { Note $_.Trim() }
    } else {
        Bad 'no Android device connected' 'Plug the phone in via USB, enable Developer options + USB debugging, tap "Allow" on the phone'
    }
}

# --------------------------------------------------------------- 6. Networking
Head '6. Network'

Write-Host '  Addresses to type into the phone app:' -ForegroundColor White
$ips = Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL' }
if ($ips) {
    $ips | ForEach-Object { Write-Host "    $($_.IPAddress):8765    [$($_.InterfaceAlias)]" -ForegroundColor Cyan }
    Note 'Pick the Wi-Fi one. The phone must be on the SAME network.'
} else {
    Bad 'no LAN address found' 'Connect this PC to Wi-Fi'
}

$rule = Get-NetFirewallRule -DisplayName '*python*' -ErrorAction SilentlyContinue
if ($rule) { Good 'a firewall rule mentioning python exists' }
else { Note 'no python firewall rule yet - Windows will prompt on first server start. Tick "Private networks" and allow.' }

# ------------------------------------------------------------------- summary
Write-Host "`n=============================================================================" -ForegroundColor White
if ($fail -eq 0) {
    Write-Host "  All $pass checks passed. You are ready to run." -ForegroundColor Green
    Write-Host @'

  Terminal 1:   .\start_server.bat
  Terminal 2:   cd therayu_app
                flutter run --release
'@ -ForegroundColor White
} else {
    Write-Host "  $pass passed, $fail need attention. Fix the [x] items above and re-run." -ForegroundColor Yellow
}
Write-Host ''

<#
================================================================================
 THERAYU — PYTHON ENVIRONMENT SETUP  (run this once)
================================================================================
     .\setup_python.ps1

 HOW THIS PICKS A PYTHON
 It writes a small probe script to a temp file and runs it under each Python it
 can find, keeping the first one that successfully imports mediapipe and cv2.

 WHY A TEMP FILE AND NOT `python -c "..."`
 Windows PowerShell 5.1 mangles embedded double quotes when passing arguments to
 native executables. `python -c 'print("hi")'` arrives at the interpreter as
 `print(hi)` and dies with a SyntaxError - which looks exactly like "Python is
 broken" when it is really "PowerShell ate the quotes". Two earlier versions of
 this script failed that way and wrongly reported no usable Python. A file path
 contains no quotes, so there is nothing left to mangle.
================================================================================
#>

Set-Location $PSScriptRoot

function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [ok]  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!]   $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  [x]   $t" -ForegroundColor Red }
function Note($t) { Write-Host "        $t" -ForegroundColor DarkGray }

# Native commands legitimately return non-zero here (that is the signal we are
# testing for), so 'Stop' would abort the script on a perfectly normal probe.
$ErrorActionPreference = 'Continue'

# ------------------------------------------------------------------ probe file
$probeFile  = Join-Path $env:TEMP "therayu_probe_$PID.py"
$verifyFile = Join-Path $env:TEMP "therayu_verify_$PID.py"

@'
import sys
v = "%d.%d.%d" % sys.version_info[:3]
try:
    import mediapipe, cv2, numpy
    print("ENGINE|" + v + "|" + mediapipe.__version__ + "|" + cv2.__version__)
except Exception as e:
    print("BARE|" + v + "|" + type(e).__name__)
print("EXE|" + sys.executable)
'@ | Set-Content -Path $probeFile -Encoding ASCII

@'
import sys
missing = []
for m in ["cv2", "mediapipe", "numpy", "yaml", "fastapi", "uvicorn", "websockets"]:
    try:
        mod = __import__(m)
        print("  [ok]  %-12s %s" % (m, getattr(mod, "__version__", "")))
    except Exception as e:
        missing.append(m)
        print("  [x]   %-12s %s" % (m, e))
sys.exit(1 if missing else 0)
'@ | Set-Content -Path $verifyFile -Encoding ASCII

# --------------------------------------------------------- enumerate candidates
Step 'Looking for a Python that can run the pose engine'

$candidates = @()

# The `py` launcher is optional - Microsoft Store builds often omit it, which is
# why its absence must not be treated as "no Python".
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @('3.12', '3.11', '3.13', '3.10', '3.9')) {
        $candidates += [pscustomobject]@{ Exe = 'py'; Pre = @("-$v"); Label = "py -$v" }
    }
}
foreach ($name in @('python', 'python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $candidates += [pscustomobject]@{ Exe = $cmd.Source; Pre = @(); Label = $name }
    }
}

if ($candidates.Count -eq 0) {
    Fail 'No Python found on PATH at all.'
    Note 'Install from https://www.python.org/downloads/ and tick "Add python.exe to PATH".'
    Note 'Then close every terminal (and VS Code) and open a fresh one.'
    Remove-Item $probeFile, $verifyFile -ErrorAction SilentlyContinue
    exit 1
}

Note "$($candidates.Count) candidate interpreter(s) to probe"

# ------------------------------------------------------------------ probe them
$engineReady = $null
$fallback    = $null
$seen        = @{}

foreach ($c in $candidates) {
    $out = & $c.Exe @($c.Pre + @($probeFile)) 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $out) { continue }

    $lines = @($out | ForEach-Object { "$_" })
    $info  = $lines | Where-Object { $_ -like 'ENGINE|*' -or $_ -like 'BARE|*' } | Select-Object -First 1
    $exe   = ($lines | Where-Object { $_ -like 'EXE|*' } | Select-Object -First 1) -replace '^EXE\|', ''
    if (-not $info) { continue }

    # `py -3.12` and `python` are frequently the same binary; probe each once.
    if ($exe -and $seen.ContainsKey($exe)) { continue }
    if ($exe) { $seen[$exe] = $true }

    $parts = $info.Split('|')
    if ($parts[0] -eq 'ENGINE') {
        Ok "$($c.Label) -> Python $($parts[1])  ·  mediapipe $($parts[2])  ·  opencv $($parts[3])"
        if (-not $engineReady) {
            $engineReady = $c
            $engineReady | Add-Member -NotePropertyName Exe2 -NotePropertyValue $exe -Force
        }
    } else {
        Warn "$($c.Label) -> Python $($parts[1])  (no mediapipe: $($parts[2]))"
        if (-not $fallback) { $fallback = $c }
    }
}

Remove-Item $probeFile -ErrorAction SilentlyContinue

$chosen = if ($engineReady) { $engineReady } else { $fallback }
$reuse  = [bool]$engineReady

if (-not $chosen) {
    Fail 'Found Python, but none of them could run the probe.'
    Note 'Run this and paste the output if it persists:'
    Note '    python -V'
    Note '    python -c "import mediapipe, cv2; print(mediapipe.__version__, cv2.__version__)"'
    Remove-Item $verifyFile -ErrorAction SilentlyContinue
    exit 1
}

if ($reuse) {
    Ok "Using $($chosen.Label) - the engine is already there, so it will be reused."
} else {
    Warn "Using $($chosen.Label) - the engine will be installed fresh (~300 MB)."
}

# --------------------------------------------------------------------- the venv
Step 'Creating .venv'

if (Test-Path '.venv\Scripts\python.exe') {
    Warn '.venv already exists - reusing. Delete the folder for a clean start.'
} else {
    if (Test-Path '.venv') { Remove-Item '.venv' -Recurse -Force }

    # --system-site-packages lets the venv see the interpreter's existing
    # mediapipe/opencv while keeping the server packages local to this project.
    $venvArgs = @('-m', 'venv')
    if ($reuse) { $venvArgs += '--system-site-packages' }
    $venvArgs += '.venv'

    & $chosen.Exe @($chosen.Pre + $venvArgs)

    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Fail 'venv creation failed.'
        Note 'If Python came from the Microsoft Store, install it from python.org instead -'
        Note 'the Store build sandboxes venv creation in ways that break this.'
        Remove-Item $verifyFile -ErrorAction SilentlyContinue
        exit 1
    }

    if ($reuse) { Ok 'created .venv (inheriting the existing engine)' }
    else        { Ok 'created .venv' }
}

$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

& $py -m pip install --upgrade pip --quiet 2>&1 | Out-Null
Ok 'pip ready'

# -------------------------------------------------------------------- installs
if (-not $reuse) {
    Step 'Installing the pose engine (opencv, mediapipe, numpy, scipy, sklearn)'
    Note 'First run pulls ~300 MB.'
    & $py -m pip install -r 'upper_body_ai\requirements.txt'
    if ($LASTEXITCODE -ne 0) { Fail 'engine install failed - see pip output above.'; exit 1 }
    Ok 'engine installed'
} else {
    Step 'Skipping engine install'
    Note 'Inherited from the interpreter above.'
}

Step 'Installing the LAN server (fastapi, uvicorn, websockets)'
& $py -m pip install -r 'upper_body_ai\server\requirements-server.txt'
if ($LASTEXITCODE -ne 0) { Fail 'server install failed - see pip output above.'; exit 1 }
Ok 'server installed'

# ---------------------------------------------------------------------- verify
Step 'Verifying'
& $py $verifyFile
$verifyOk = ($LASTEXITCODE -eq 0)
Remove-Item $verifyFile -ErrorAction SilentlyContinue

if (-not $verifyOk) {
    Fail 'Some packages failed to import.'
    Note 'Delete .venv and re-run to retry from scratch.'
    exit 1
}

# ------------------------------------------------------------------- addresses
Step 'Your LAN addresses'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL' } |
    ForEach-Object { Write-Host "    $($_.IPAddress):8765    [$($_.InterfaceAlias)]" -ForegroundColor Cyan }
Note 'Only needed for a phone. In Chrome the address is localhost:8765.'

# ------------------------------------------------------------------------ done
Step 'Done'
Write-Host @'
  Everything is installed. To run:

    Ctrl+Shift+D in VS Code  ->  "Server + Chrome (start here)"  ->  F5

  Or from two terminals:

    .\start_server.bat
    cd therayu_app ; flutter run -d chrome
'@ -ForegroundColor White

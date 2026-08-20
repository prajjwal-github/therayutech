<#
================================================================================
 THERAYU — TERMINAL DIAGNOSTIC
================================================================================
 Read-only. Answers "why does this work in cmd but not in VS Code?" by showing
 exactly what THIS terminal resolves and where it came from.

     .\diagnose.ps1

 Run it in whichever terminal is misbehaving.
================================================================================
#>

Set-Location $PSScriptRoot
$ErrorActionPreference = 'Continue'

function Head($t) { Write-Host "`n$t" -ForegroundColor Cyan; Write-Host ('-' * 74) -ForegroundColor DarkGray }
function Good($t) { Write-Host "  [ok]   $t" -ForegroundColor Green }
function Bad($t)  { Write-Host "  [x]    $t" -ForegroundColor Red }
function Note($t) { Write-Host "         $t" -ForegroundColor DarkGray }

Write-Host "`n========================= TERMINAL DIAGNOSTIC =========================" -ForegroundColor White

# ------------------------------------------------------------------- the shell
Head 'This shell'
Write-Host "  PowerShell   : $($PSVersionTable.PSVersion)"
Write-Host "  Edition      : $($PSVersionTable.PSEdition)"
Write-Host "  Host         : $($Host.Name)"
if ($env:TERM_PROGRAM -eq 'vscode' -or $env:VSCODE_INJECTION) {
    Note 'Running inside the VS Code integrated terminal.'
} else {
    Note 'Running outside VS Code (plain PowerShell / cmd window).'
}

# ------------------------------------------------------------------ the python
Head 'Python'

$pythons = @(Get-Command python, python3, py -ErrorAction SilentlyContinue)
if ($pythons.Count -eq 0) {
    Bad 'No python / python3 / py resolves in THIS terminal.'
    Note 'If it works in cmd.exe but not here, this terminal has a stale PATH:'
    Note 'close every VS Code window and reopen (a reload is not always enough).'
} else {
    foreach ($p in $pythons) {
        Write-Host "  $($p.Name.PadRight(8)) -> $($p.Source)"
        $v = & $p.Source -V 2>&1
        Note "$v"
    }

    # Probe via a temp file: PowerShell 5.1 strips embedded double quotes when
    # passing arguments to native commands, so `python -c "print(1)"` can fail
    # for reasons that have nothing to do with Python.
    $probe = Join-Path $env:TEMP "therayu_diag_$PID.py"
    @'
import sys
print("  executable : " + sys.executable)
print("  version    : %d.%d.%d" % sys.version_info[:3])
for m in ["cv2", "mediapipe", "numpy", "yaml", "fastapi", "uvicorn"]:
    try:
        mod = __import__(m)
        print("  [ok]  %-11s %s" % (m, getattr(mod, "__version__", "")))
    except Exception as e:
        print("  [--]  %-11s not installed" % m)
'@ | Set-Content -Path $probe -Encoding ASCII

    Write-Host ''
    & python $probe 2>&1
    Remove-Item $probe -ErrorAction SilentlyContinue
}

# ------------------------------------------------------------------- the venv
Head 'Project venv'
if (Test-Path '.venv\Scripts\python.exe') {
    Good '.venv exists'
    & '.venv\Scripts\python.exe' -V 2>&1 | ForEach-Object { Note $_ }
} else {
    Bad '.venv not created yet'
    Note 'Run: powershell -ExecutionPolicy Bypass -File .\setup_python.ps1'
}

# ------------------------------------------------------------------ the flutter
Head 'Flutter'
$fl = Get-Command flutter -ErrorAction SilentlyContinue
if ($fl) {
    Good $fl.Source
    (& flutter --version 2>&1 | Select-Object -First 1) | ForEach-Object { Note $_ }
} else {
    Bad 'flutter does not resolve in THIS terminal'
    if (Test-Path 'C:\src\flutter\bin\flutter.bat') {
        Note 'BUT it IS installed at C:\src\flutter.'
        Note 'This terminal has a stale PATH. Close VS Code completely and reopen it.'
    } else {
        Note 'Not installed. Run: powershell -ExecutionPolicy Bypass -File .\setup_flutter.ps1'
    }
}

# --------------------------------------------------------------------- the PATH
Head 'PATH comparison'

$sessionPath = $env:Path
$storedPath  = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
               [Environment]::GetEnvironmentVariable('Path', 'Machine')

# The stored PATH is what a NEW terminal gets. If an entry is stored but missing
# from this session, the terminal simply predates the change.
$interesting = @('flutter', 'Python', 'python')
foreach ($needle in $interesting) {
    $inSession = @($sessionPath -split ';' | Where-Object { $_ -like "*$needle*" })
    $inStored  = @($storedPath  -split ';' | Where-Object { $_ -like "*$needle*" })

    Write-Host "  '$needle' entries:"
    if ($inSession.Count -eq 0 -and $inStored.Count -eq 0) {
        Note '  none anywhere - not installed'
    } elseif ($inSession.Count -eq 0) {
        Bad "  MISSING from this terminal, but PRESENT in the stored PATH"
        $inStored | ForEach-Object { Note "    $_" }
        Note '  -> this terminal is stale. Close VS Code entirely and reopen.'
    } else {
        $inSession | ForEach-Object { Good "  $_" }
    }
}

# ------------------------------------------------------------------- conclusion
Head 'Verdict'

$staleFlutter = (-not $fl) -and (Test-Path 'C:\src\flutter\bin\flutter.bat')
$noPython     = $pythons.Count -eq 0

if ($staleFlutter -or $noPython) {
    Write-Host @'
  This terminal has an out-of-date copy of your environment.

  Windows hands each process a snapshot of PATH when it starts. Installers
  update the stored value, but already-running terminals keep the old snapshot -
  and VS Code passes its own snapshot down to every integrated terminal it opens,
  so "reload window" is often not enough.

  FIX: close every VS Code window, then reopen the folder.
       (Ctrl+Shift+P -> "Developer: Reload Window" does NOT reliably do it.)
'@ -ForegroundColor Yellow
} else {
    Write-Host '  This terminal looks healthy.' -ForegroundColor Green
}
Write-Host ''

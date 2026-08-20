<#
================================================================================
 THERAYU — FLUTTER SETUP  (run this once, nothing manual)
================================================================================
     .\setup_flutter.ps1

 Does everything:
   1. Installs the Flutter SDK if it is missing (downloads, extracts, sets PATH)
   2. Generates the web/ and android/ platform folders
   3. Patches the Android manifest for camera + LAN access
   4. Fetches packages and analyses

 WHY CHROME IS THE DEFAULT TARGET
 Running on Android needs Android Studio, an ~5 GB SDK, a physical phone, USB
 debugging and a shared Wi-Fi network. Running in Chrome needs none of that - the
 Flutter SDK alone is enough, the browser supplies the camera, and the server is
 on localhost so there is no firewall or IP to get wrong. Android still works and
 is set up here too, but it should be the second thing you try, not the first.

 OPTIONS
   -SkipAndroid    web only, skips the android/ scaffolding
   -Force          re-download the SDK even if one is present
================================================================================
#>

param(
    [switch]$SkipAndroid,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [ok]  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!]   $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  [x]   $t" -ForegroundColor Red }
function Note($t) { Write-Host "        $t" -ForegroundColor DarkGray }

$FlutterRoot = 'C:\src\flutter'
$FlutterBin  = Join-Path $FlutterRoot 'bin'
$FlutterExe  = Join-Path $FlutterBin 'flutter.bat'
$AppDir      = Join-Path $PSScriptRoot 'therayu_app'

# ============================================================================
# 1. FLUTTER SDK
# ============================================================================
Step 'Flutter SDK'

$flutterCmd = $null

if (-not $Force) {
    $onPath = Get-Command flutter -ErrorAction SilentlyContinue
    if ($onPath) {
        $flutterCmd = $onPath.Source
        Ok "already on PATH: $flutterCmd"
    } elseif (Test-Path $FlutterExe) {
        $flutterCmd = $FlutterExe
        Ok "found at $FlutterRoot (not on PATH yet)"
    }
}

if (-not $flutterCmd) {
    Note 'Not installed. Downloading the SDK (~1 GB) - this takes a few minutes.'

    $parent = Split-Path $FlutterRoot -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    if ((Test-Path $FlutterRoot) -and $Force) {
        Note 'Removing the existing SDK folder (-Force)...'
        Remove-Item $FlutterRoot -Recurse -Force
    }

    # Resolve the current stable build from Flutter's release manifest rather than
    # hard-coding a version, which would rot within weeks.
    Note 'Resolving the latest stable release...'
    $manifestUrl = 'https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $manifest = Invoke-RestMethod -Uri $manifestUrl -UseBasicParsing -TimeoutSec 60
        $stableHash = $manifest.current_release.stable
        $release = $manifest.releases | Where-Object { $_.hash -eq $stableHash } | Select-Object -First 1
        $zipUrl = "$($manifest.base_url)/$($release.archive)"
        Ok "stable $($release.version)"
    } catch {
        Fail "Could not reach the Flutter release manifest: $_"
        Note 'Check your internet connection, or install manually from'
        Note 'https://docs.flutter.dev/get-started/install/windows'
        exit 1
    }

    $zipPath = Join-Path $env:TEMP "flutter_windows_$($release.version).zip"

    if ((Test-Path $zipPath) -and -not $Force) {
        Ok "reusing the download already in TEMP"
    } else {
        Note "Downloading $zipUrl"
        Note 'No progress bar - PowerShell downloads far faster with it disabled.'
        $prevPref = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 1800
        } catch {
            Fail "Download failed: $_"
            exit 1
        } finally {
            $ProgressPreference = $prevPref
        }
        Ok ("downloaded {0:N0} MB" -f ((Get-Item $zipPath).Length / 1MB))
    }

    Note 'Extracting to C:\src (a few minutes - lots of small files)...'
    try {
        Expand-Archive -Path $zipPath -DestinationPath $parent -Force
    } catch {
        Fail "Extract failed: $_"
        Note 'If this is a "path too long" error, the SDK must live somewhere short like C:\src.'
        exit 1
    }

    if (-not (Test-Path $FlutterExe)) { Fail "Extract finished but $FlutterExe is missing."; exit 1 }
    Ok "installed to $FlutterRoot"
    $flutterCmd = $FlutterExe
}

# ------------------------------------------------------------------------ PATH
Step 'PATH'

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$FlutterBin*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$FlutterBin", 'User')
    Ok "added $FlutterBin to your user PATH (permanent)"
    Note 'New terminals pick this up automatically.'
} else {
    Ok 'already on your user PATH'
}

# Also set it for THIS session so the rest of the script can just call `flutter`.
if ($env:Path -notlike "*$FlutterBin*") {
    $env:Path = "$env:Path;$FlutterBin"
    Ok 'added to the current session'
}

# ------------------------------------------------------------------- first run
Step 'Flutter version'
Note 'First run unpacks the Dart SDK - allow a minute.'
& $flutterCmd --version
if ($LASTEXITCODE -ne 0) { Fail 'flutter --version failed.'; exit 1 }

& $flutterCmd config --no-analytics 2>&1 | Out-Null

# ============================================================================
# 2. PLATFORM SCAFFOLDING
# ============================================================================
Step 'Generating platform folders'

if (-not (Test-Path $AppDir)) { Fail "therayu_app not found at $AppDir"; exit 1 }
Set-Location $AppDir

# lib/ and pubspec.yaml are hand-written and live in git; android/ and web/ are
# machine-generated boilerplate tied to your Flutter version, so they are created
# here rather than committed. Back them up so `flutter create` cannot clobber them.
$backup = Join-Path $env:TEMP "therayu_backup_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($item in @('lib', 'pubspec.yaml', 'analysis_options.yaml')) {
    if (Test-Path $item) { Copy-Item $item -Destination $backup -Recurse -Force }
}
Ok "hand-written files backed up to $backup"

$platforms = if ($SkipAndroid) { 'web' } else { 'web,android' }
Note "Running flutter create --platforms=$platforms"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $flutterCmd create --platforms=$platforms --project-name therayu_app --org com.therayu . 2>&1 |
    ForEach-Object { "$_" } | Where-Object { $_ -notmatch '^\s*$' } | Select-Object -Last 3
$ErrorActionPreference = $prevEap
Ok "generated: $platforms"

foreach ($item in @('lib', 'pubspec.yaml', 'analysis_options.yaml')) {
    $src = Join-Path $backup $item
    if (Test-Path $src) {
        if (Test-Path $item) { Remove-Item $item -Recurse -Force }
        Copy-Item $src -Destination $AppDir -Recurse -Force
    }
}
Ok 'hand-written files restored'

# ============================================================================
# 3. ANDROID MANIFEST
# ============================================================================
if (-not $SkipAndroid) {
    Step 'Patching AndroidManifest.xml'

    $manifestPath = 'android\app\src\main\AndroidManifest.xml'
    if (Test-Path $manifestPath) {
        $m = Get-Content $manifestPath -Raw

        if ($m -notmatch 'android.permission.CAMERA') {
            $perms = @"
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.INTERNET" />

    <uses-feature android:name="android.hardware.camera" android:required="true" />

"@
            $m = $m -replace '(?m)^(\s*)<application', "$perms`$1<application"
            Ok 'added CAMERA + INTERNET'
        } else { Ok 'permissions already present' }

        # Android 9+ blocks unencrypted traffic by default; the LAN server speaks
        # plain ws://, so without this the socket fails with no useful error.
        if ($m -notmatch 'usesCleartextTraffic') {
            $m = $m -replace '(<application)', ('$1' + "`n        android:usesCleartextTraffic=`"true`"")
            Ok 'enabled cleartext traffic'
        } else { Ok 'cleartext already enabled' }

        $m = $m -replace 'android:label="[^"]*"', 'android:label="Therayu"'
        Set-Content $manifestPath -Value $m -Encoding UTF8 -NoNewline
        Ok 'label set to Therayu'
    } else {
        Warn 'manifest not found - patch by hand using android_manifest_snippet.xml'
    }
}

# ============================================================================
# 4. PACKAGES
# ============================================================================
Step 'Fetching packages'
& $flutterCmd pub get
if ($LASTEXITCODE -ne 0) { Fail 'pub get failed.'; exit 1 }
Ok 'dependencies resolved'

Step 'Analysing'

# `flutter analyze` exits non-zero for ANY issue, including style-level infos.
# Under ErrorActionPreference=Stop that becomes a terminating NativeCommandError
# and kills the script over lint noise, so it is scoped to Continue here and the
# result is reported rather than thrown.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

$analysis = & $flutterCmd analyze 2>&1 | ForEach-Object { "$_" }
$ErrorActionPreference = $prevEap

$errors = @($analysis | Where-Object { $_ -match '^\s*error\s' })
$warns  = @($analysis | Where-Object { $_ -match '^\s*warning\s' })
$infos  = @($analysis | Where-Object { $_ -match '^\s*info\s' })

if ($errors.Count -gt 0) {
    Fail "$($errors.Count) error(s) - these WILL stop the app from building:"
    $errors | Select-Object -First 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
} else {
    Ok 'no errors - the app will build and run'
}

if ($warns.Count -gt 0) { Warn "$($warns.Count) warning(s)" }
if ($infos.Count -gt 0) {
    Note "$($infos.Count) style info(s) - cosmetic, safe to ignore"
    Note 'See them all with:  cd therayu_app ; flutter analyze'
}

# ============================================================================
# DONE
# ============================================================================
Set-Location $PSScriptRoot
Step 'Ready'
Write-Host @'
  Two terminals:

    Terminal 1        .\start_server.bat
    Terminal 2        cd therayu_app
                      flutter run -d chrome

  Chrome opens, asks for camera permission, and the address to enter is:

      localhost:8765

  In VS Code instead: Ctrl+Shift+D, pick "Therayu in Chrome", press F5.

  IF `flutter` IS NOT FOUND IN A NEW TERMINAL
  This script set your PATH permanently, but terminals opened before now still
  have the old copy. Close them, or restart VS Code entirely.
'@ -ForegroundColor White

<#
================================================================================
 THERAYU — ANDROID PROJECT SETUP
================================================================================
 Generates the android/ platform scaffolding for this Flutter app and patches
 the manifest with the camera + cleartext-LAN settings it needs.

 WHY THIS SCRIPT EXISTS
 The lib/, pubspec.yaml and theme files are hand-written and live in git. The
 android/ folder is machine-generated boilerplate tied to your installed Flutter
 and Gradle versions, so it is better generated locally than committed. This
 script does that, then re-applies the three manifest edits `flutter create`
 does not know about.

 RUN (from this folder, in PowerShell):
     .\setup_android.ps1

 Safe to re-run. It never overwrites lib/ or pubspec.yaml.
================================================================================
#>

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  [ok] $text" -ForegroundColor Green }
function Write-Warn2($text) { Write-Host "  [!]  $text" -ForegroundColor Yellow }

# ---------------------------------------------------------------- prerequisites
Write-Step 'Checking Flutter'

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Write-Host @'
Flutter is not on your PATH.

Install it, then re-run this script:
  1. Download: https://docs.flutter.dev/get-started/install/windows
  2. Unzip to C:\src\flutter
  3. Add C:\src\flutter\bin to your PATH
  4. Open a NEW PowerShell and run:  flutter doctor

You also need Android Studio (for the Android SDK + platform tools):
  https://developer.android.com/studio
Then accept the SDK licences:  flutter doctor --android-licenses
'@ -ForegroundColor Red
    exit 1
}

Write-Ok (flutter --version | Select-Object -First 1)

# --------------------------------------------------------- preserve handwritten
Write-Step 'Backing up hand-written files'

$backup = Join-Path $env:TEMP "therayu_backup_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

foreach ($item in @('lib', 'pubspec.yaml', 'analysis_options.yaml')) {
    if (Test-Path $item) {
        Copy-Item $item -Destination $backup -Recurse -Force
        Write-Ok "backed up $item"
    }
}
Write-Host "  backup at: $backup" -ForegroundColor DarkGray

# -------------------------------------------------------------- create platform
Write-Step 'Generating android/ scaffolding'

# --platforms=android limits generation to Android; --project-name must match
# pubspec.yaml's `name:` or Flutter refuses to wire up the entrypoint.
flutter create --platforms=android --project-name therayu_app --org com.therayu .

Write-Ok 'android/ generated'

# ------------------------------------------------------------------ restore ours
Write-Step 'Restoring hand-written files'

foreach ($item in @('lib', 'pubspec.yaml', 'analysis_options.yaml')) {
    $source = Join-Path $backup $item
    if (Test-Path $source) {
        if (Test-Path $item) { Remove-Item $item -Recurse -Force }
        Copy-Item $source -Destination $root -Recurse -Force
        Write-Ok "restored $item"
    }
}

# ------------------------------------------------------------------- manifest
Write-Step 'Patching AndroidManifest.xml'

$manifestPath = 'android\app\src\main\AndroidManifest.xml'
if (-not (Test-Path $manifestPath)) {
    Write-Warn2 "Manifest not found at $manifestPath - patch it by hand using android_manifest_snippet.xml"
} else {
    $manifest = Get-Content $manifestPath -Raw

    # 1. permissions
    if ($manifest -notmatch 'android.permission.CAMERA') {
        $permissions = @'
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.INTERNET" />

    <uses-feature android:name="android.hardware.camera" android:required="true" />

'@
        $manifest = $manifest -replace '(?m)^(\s*)<application', "$permissions`$1<application"
        Write-Ok 'added CAMERA + INTERNET permissions'
    } else {
        Write-Ok 'permissions already present'
    }

    # 2. cleartext ws:// on the LAN
    if ($manifest -notmatch 'usesCleartextTraffic') {
        $manifest = $manifest -replace '(<application)', '$1' + "`n        android:usesCleartextTraffic=`"true`""
        Write-Ok 'enabled cleartext traffic (required for ws:// on a LAN)'
    } else {
        Write-Ok 'cleartext traffic already enabled'
    }

    # 3. launcher label
    $manifest = $manifest -replace 'android:label="[^"]*"', 'android:label="Therayu"'
    Write-Ok 'set launcher label to Therayu'

    Set-Content $manifestPath -Value $manifest -Encoding UTF8 -NoNewline
}

# ------------------------------------------------------------------ min sdk
Write-Step 'Checking minSdk'

$gradleKts = 'android\app\build.gradle.kts'
$gradleOld = 'android\app\build.gradle'

# The camera plugin needs API 21+; recent camera versions want 21 and
# wakelock_plus/shared_preferences are fine there too. Newer Flutter templates
# already default high enough, so this only nudges the old flutter.minSdkVersion
# placeholder when it is present.
foreach ($g in @($gradleKts, $gradleOld)) {
    if (Test-Path $g) {
        $content = Get-Content $g -Raw
        if ($content -match 'minSdk(Version)?\s*=?\s*flutter\.minSdk(Version)?') {
            $content = $content -replace 'minSdk(Version)?\s*=?\s*flutter\.minSdk(Version)?', 'minSdk = 21'
            Set-Content $g -Value $content -Encoding UTF8 -NoNewline
            Write-Ok "pinned minSdk = 21 in $g"
        } else {
            Write-Ok "$g needs no change"
        }
        break
    }
}

# ------------------------------------------------------------------- packages
Write-Step 'Fetching packages'
flutter pub get
Write-Ok 'dependencies resolved'

# -------------------------------------------------------------------- analyse
Write-Step 'Analysing'
$analysis = flutter analyze 2>&1 | Out-String
Write-Host $analysis

# --------------------------------------------------------------------- done
Write-Step 'Next steps'
Write-Host @'
  1. Start the inference server on this PC:

         cd ..\upper_body_ai
         pip install -r server\requirements-server.txt
         python -m server.ws_server

     Note the ws:// address it prints.

  2. Put the phone on the SAME Wi-Fi, enable USB debugging, plug it in, then:

         flutter devices
         flutter run --release

     --release matters: debug builds run Dart unoptimised and the NV21 repack
     will feel sluggish.

  3. In the app, enter the address from step 1 and tap Test connection.

  Build a shareable APK instead:
         flutter build apk --release
     Output: build\app\outputs\flutter-apk\app-release.apk
'@ -ForegroundColor White

@echo off
REM ===========================================================================
REM  THERAYU - start the inference server
REM
REM  Runs IN THIS WINDOW. Nothing is spawned outside it, so this behaves
REM  correctly inside the VS Code integrated terminal.
REM
REM  An earlier version of this script used `start cmd /k` to launch the server
REM  in its own console window. That was wrong: it dragged you out of VS Code
REM  every time. Use two integrated terminals instead (or the VS Code task
REM  "RUN EVERYTHING", which opens both for you).
REM
REM  Terminal 1 (this one):   run.bat
REM  Terminal 2:              cd therayu_app  &&  flutter run -d chrome
REM ===========================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [x] Python environment missing.
    echo       Run:  powershell -ExecutionPolicy Bypass -File setup_python.ps1
    echo.
    exit /b 1
)

echo.
echo   ============================================
echo     THERAYU - inference server
echo   ============================================
echo.
echo   Leave this terminal running.
echo   Open a SECOND terminal for the app:
echo.
echo       cd therayu_app
echo       flutter run -d chrome
echo.
echo   Ctrl+C here stops the server.
echo.

cd upper_body_ai
"..\.venv\Scripts\python.exe" -m server.ws_server

if errorlevel 1 (
    echo.
    echo   The server exited with an error. Scroll up for the traceback.
    echo.
)

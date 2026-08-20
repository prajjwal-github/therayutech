@echo off
REM ===========================================================================
REM  THERAYU - start the LAN inference server
REM  Double-click this, or run it from a terminal. Leave the window open while
REM  you use the phone app; closing it ends the session.
REM ===========================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   The Python environment is missing.
    echo   Run this first:   powershell -ExecutionPolicy Bypass -File setup_python.ps1
    echo.
    pause
    exit /b 1
)

echo.
echo   Starting the Therayu inference server...
echo   Press Ctrl+C to stop.
echo.

cd upper_body_ai
"..\.venv\Scripts\python.exe" -m server.ws_server

REM Keep the window open if the server exits with an error, so the traceback
REM is readable instead of vanishing with the console.
if errorlevel 1 (
    echo.
    echo   The server exited with an error. Scroll up for the traceback.
    pause
)

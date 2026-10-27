@echo off
REM SceneLens launcher: creates the local virtualenv on first run.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [SceneLens] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

set PYTHONIOENCODING=utf-8
start "" ".venv\Scripts\pythonw.exe" app.py %*
exit /b 0

:error
echo.
echo [SceneLens] Setup failed. See the messages above.
pause
exit /b 1

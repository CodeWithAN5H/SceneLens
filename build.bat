@echo off
REM SceneLens packager: builds a standalone dist\SceneLens.exe (icon + all
REM dependencies bundled, no Python required on the target machine).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [SceneLens] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo [SceneLens] Installing runtime dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :error

echo [SceneLens] Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install -q "pyinstaller>=6.6"
if errorlevel 1 goto :error

echo [SceneLens] Building the executable...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean SceneLens.spec
if errorlevel 1 goto :error

echo.
echo [SceneLens] Built dist\SceneLens.exe
echo [SceneLens] Run it with:   dist\SceneLens.exe
echo [SceneLens] Or a frame:    dist\SceneLens.exe frame.png
exit /b 0

:error
echo.
echo [SceneLens] Build failed. See the messages above.
pause
exit /b 1

@echo off
REM SceneLens packager: builds a portable Windows bundle (icon + all
REM dependencies included, no Python needed on the target machine).
REM
REM   build.bat            folder build (default) -> dist\SceneLens\SceneLens.exe
REM   build.bat onefile    single executable       -> dist\SceneLens.exe
setlocal
cd /d "%~dp0"

set "PACKAGE=folder"
if /I "%~1"=="onefile" set "PACKAGE=onefile"
if /I "%~1"=="single" set "PACKAGE=onefile"
if /I "%~1"=="folder" set "PACKAGE=folder"
if /I "%~1"=="onedir" set "PACKAGE=folder"

if "%~1"=="" goto :package_ready
if /I "%~1"=="onefile" goto :package_ready
if /I "%~1"=="single" goto :package_ready
if /I "%~1"=="folder" goto :package_ready
if /I "%~1"=="onedir" goto :package_ready
echo [SceneLens] Unknown option "%~1".
echo [SceneLens] Usage: build.bat [folder^|onefile]
exit /b 2

:package_ready
set "SCENELENS_PACKAGE=%PACKAGE%"

if exist ".venv\Scripts\python.exe" goto :dependencies

echo [SceneLens] Creating virtual environment...
python -m venv .venv
if errorlevel 1 goto :error

:dependencies
echo [SceneLens] Installing runtime dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :error

echo [SceneLens] Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install -q "pyinstaller>=6.6"
if errorlevel 1 goto :error

REM Drop the other shape's output so dist\ always shows the current build.
if /I "%PACKAGE%"=="onefile" if exist "dist\SceneLens\" rmdir /s /q "dist\SceneLens"
if /I "%PACKAGE%"=="folder" if exist "dist\SceneLens.exe" del /q "dist\SceneLens.exe"

echo [SceneLens] Building the %PACKAGE% build...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean SceneLens.spec
if errorlevel 1 goto :error

if /I "%PACKAGE%"=="onefile" goto :report_onefile

echo.
echo [SceneLens] Built the folder build: dist\SceneLens\SceneLens.exe
echo [SceneLens] Run it with:   dist\SceneLens\SceneLens.exe
echo [SceneLens] Or a frame:    dist\SceneLens\SceneLens.exe frame.png
echo [SceneLens] Single file?   build.bat onefile
exit /b 0

:report_onefile
echo.
echo [SceneLens] Built the single-file build: dist\SceneLens.exe
echo [SceneLens] Run it with:   dist\SceneLens.exe
echo [SceneLens] Or a frame:    dist\SceneLens.exe frame.png
echo [SceneLens] Instant start? build.bat
exit /b 0

:error
echo.
echo [SceneLens] Build failed. See the messages above.
pause
exit /b 1

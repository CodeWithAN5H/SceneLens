# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the standalone SceneLens.exe.

Build it with::

    build.bat
    .venv\\Scripts\\python.exe -m PyInstaller SceneLens.spec      (same thing, manually)

The result is a single windowed ``dist\\SceneLens.exe`` that bundles CPython, Tk,
CustomTkinter (themes, fonts, icons), the tkdnd drag-and-drop extension and the
app icon, so it runs on a Windows machine with no Python installed.
"""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scenelens.config import APP_NAME  # noqa: E402
from scenelens.gui.glyphs import app_icon  # noqa: E402

# The window icon is drawn in code, so the executable icon is generated here from
# the same artwork instead of shipping a binary asset in the repository.
ICON_PATH = Path(workpath) / f"{APP_NAME}.ico"
ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
app_icon(256).save(
    ICON_PATH,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)

datas, binaries, hiddenimports = [], [], []
for package in ("customtkinter", "tkinterdnd2"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# tkinterdnd2 ships every platform's tkdnd binaries; keep only the Windows ones.
datas = [
    (source, destination)
    for source, destination in datas
    if not any(
        marker in destination.replace("\\", "/") for marker in ("/linux-", "/osx-")
    )
]
binaries = [
    (source, destination)
    for source, destination in binaries
    if not any(
        marker in destination.replace("\\", "/") for marker in ("/linux-", "/osx-")
    )
]

analysis = Analysis(
    ["app.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "setuptools", "pip", "numpy", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # windowed app: no console window, diagnostics go to the log file
    disable_windowed_traceback=False,
    icon=str(ICON_PATH),
)

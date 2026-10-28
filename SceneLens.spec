# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the standalone SceneLens build.

Two shapes, selected by the ``SCENELENS_PACKAGE`` environment variable:

* ``folder`` (default) — ``dist\\SceneLens\\SceneLens.exe`` plus its DLLs. Nothing
  is unpacked on launch, so the window appears immediately.
* ``onefile`` — a single ``dist\\SceneLens.exe`` that unpacks to a temp folder on
  every start (slower launch, convenient for handing someone one file).

Build through ``build.bat``; it sets the variable for you::

    build.bat             folder build
    build.bat onefile     single-file build
"""

import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scenelens.config import (  # noqa: E402
    APP_NAME,
    APP_FILE_VERSION,
    APP_MAJOR,
    APP_MINOR,
    APP_PATCH,
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_COPYRIGHT,
)
from scenelens.gui.glyphs import app_icon  # noqa: E402

ONE_FILE = os.environ.get("SCENELENS_PACKAGE", "folder").strip().lower() in {
    "onefile",
    "one-file",
    "single",
}

# Windows version resource: makes Explorer show proper file properties
# (File description, Company, File version, Product version, Copyright).
from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=APP_FILE_VERSION,
        prodvers=APP_FILE_VERSION,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", APP_AUTHOR),
                        StringStruct("FileDescription", APP_DESCRIPTION),
                        StringStruct("FileVersion", f"{APP_MAJOR}.{APP_MINOR}.{APP_PATCH}.0"),
                        StringStruct("ProductVersion", f"{APP_MAJOR}.{APP_MINOR}.{APP_PATCH}.0"),
                        StringStruct("InternalName", APP_NAME),
                        StringStruct("LegalCopyright", APP_COPYRIGHT),
                        StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
                        StringStruct("ProductName", APP_NAME),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

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

if ONE_FILE:
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
        console=False,  # windowed app: no console, diagnostics go to the log file
        disable_windowed_traceback=False,
        icon=str(ICON_PATH),
        version=version_info,
    )
else:
    # Folder build: the executable stays small and loads its DLLs in place.
    exe = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon=str(ICON_PATH),
        version=version_info,
    )
    bundle = COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )

"""Clipboard image access, a background watcher, and safe clipboard copies.

``PIL.ImageGrab.grabclipboard`` works on Windows and macOS; on Linux it needs an
X11 clipboard helper (xclip/xsel) and simply returns ``None`` when unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageGrab

from .image_utils import SUPPORTED_EXTENSIONS, image_signature


def read_clipboard_image() -> Image.Image | None:
    """Return an RGB copy of the clipboard image, or ``None``.

    Handles both a bitmap on the clipboard and a copied image *file*.
    """
    try:
        content = ImageGrab.grabclipboard()
    except Exception:  # noqa: BLE001 - platform clipboard backends vary wildly
        return None

    if isinstance(content, Image.Image):
        try:
            return content.convert("RGB")
        except (OSError, ValueError):
            return None

    if isinstance(content, list):
        for entry in content:
            try:
                path = Path(entry)
            except TypeError:
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file():
                try:
                    with Image.open(path) as opened:
                        return opened.convert("RGB")
                except OSError:
                    continue
    return None


class ClipboardWatcher(threading.Thread):
    """Polls the clipboard for new images while SceneLens is running.

    Polling (rather than a system-wide keyboard hook) keeps the app dependency
    free and works even while the window is unfocused. The callback runs on this
    worker thread, so the GUI is responsible for hopping back to the main loop.
    """

    def __init__(
        self,
        on_image: Callable[[Image.Image], None],
        interval: float = 1.6,
    ) -> None:
        super().__init__(daemon=True, name="scenelens-clipboard")
        self._on_image = on_image
        self._interval = interval
        self._stop_event = threading.Event()
        self._last_signature: str | None = None
        self._suspended_until = 0.0

    def prime(self) -> None:
        """Remember what is already on the clipboard so startup is quiet."""
        image = read_clipboard_image()
        if image is not None:
            self._last_signature = image_signature(image)

    def pause(self, seconds: float = 2.5) -> None:
        """Ignore clipboard changes we caused ourselves (e.g. copying a card)."""
        self._suspended_until = time.monotonic() + seconds

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - timing based
        self.prime()
        while not self._stop_event.wait(self._interval):
            if time.monotonic() < self._suspended_until:
                continue
            image = read_clipboard_image()
            if image is None:
                continue
            signature = image_signature(image)
            if signature == self._last_signature:
                continue
            self._last_signature = signature
            try:
                self._on_image(image)
            except Exception:  # noqa: BLE001 - a watcher must never crash the app
                pass


def copy_text(root: Any, text: str) -> bool:
    """Copy text using Tk's clipboard (falls back to clip.exe on Windows)."""
    if root is not None:
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update_idletasks()
            return True
        except Exception:  # noqa: BLE001
            pass

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["clip"],
                input=text.encode("utf-16le"),
                check=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def _powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def copy_image_to_clipboard(path: Path) -> bool:
    """Best-effort copy of a PNG file as a clipboard bitmap.

    Markdown sharing never depends on this; it is a bonus for users who want to
    paste the generated card directly into Discord.
    """
    path = Path(path)
    if not path.is_file():
        return False

    if sys.platform == "win32":
        shell = _powershell()
        if not shell:
            return False
        escaped = str(path.resolve()).replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            f"$img=[System.Drawing.Image]::FromFile('{escaped}');"
            "[System.Windows.Forms.Clipboard]::SetImage($img);"
            "$img.Dispose();"
        )
        try:
            completed = subprocess.run(
                [shell, "-NoProfile", "-STA", "-Command", script],
                capture_output=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    if sys.platform.startswith("linux") and shutil.which("xclip"):
        try:
            completed = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", str(path)],
                capture_output=True,
                timeout=15,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    return False


def reveal_in_file_manager(path: Path) -> None:
    """Open the containing folder (used after exporting a card)."""
    path = Path(path)
    try:
        if sys.platform == "win32":
            os.startfile(str(path.parent))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path.parent)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except (OSError, subprocess.SubprocessError):
        pass

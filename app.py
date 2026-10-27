"""SceneLens desktop entry point.

Usage:
    python app.py                 # open the window
    python app.py path/to/frame.png   # open and immediately identify a frame
"""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _enable_dpi_awareness() -> None:
    """Crisp text on Windows instead of OS bitmap scaling."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - older Windows builds
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def _configure_logging() -> Path:
    from scenelens.config import DATA_DIR

    log_path = DATA_DIR / "scenelens.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [file_handler]

    # A windowed build has no console, so sys.stderr is None there.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        handlers.append(console)

    logging.basicConfig(level=logging.INFO, handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return log_path


def main() -> int:
    _enable_dpi_awareness()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    log_path = _configure_logging()
    logger = logging.getLogger("scenelens")

    initial_image: Path | None = None
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1]).expanduser()
        if candidate.is_file():
            initial_image = candidate
        else:
            logger.warning("Ignoring missing image argument: %s", candidate)

    try:
        from scenelens.gui.main_window import SceneLensApp
    except Exception as error:  # noqa: BLE001
        logger.exception("SceneLens could not start")
        print("SceneLens could not start:", error)
        print("Install dependencies with:  python -m pip install -r requirements.txt")
        return 1

    try:
        app = SceneLensApp(initial_image=initial_image)
        app.mainloop()
    except Exception:  # noqa: BLE001
        logger.exception("Fatal error in SceneLens")
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "SceneLens",
                f"SceneLens hit an unexpected error.\n\nDetails were written to:\n{log_path}",
            )
        except Exception:  # noqa: BLE001
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

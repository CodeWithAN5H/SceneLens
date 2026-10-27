"""Main application window: navigation, scan orchestration and clipboard flow."""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog

from ..config import THUMB_DIR, Settings, load_settings, save_settings
from ..database import HistoryStore
from ..engines.router import IdentityRouter, ScanReport
from ..models import EngineStatus
from ..utils.clipboard import ClipboardWatcher, read_clipboard_image
from ..utils.image_utils import (
    SUPPORTED_EXTENSIONS,
    ImageInputError,
    image_signature,
    load_image,
    save_history_thumbnail,
)
from . import theme as t
from .drop_zone import DropView
from .glyphs import ensure_icon_asset
from .history_view import HistoryView
from .results_view import ResultsView
from .scan_view import ScanView
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
from .widgets import Badge, ToastHost

logger = logging.getLogger(__name__)


class SceneLensApp(ctk.CTk):
    def __init__(self, initial_image: Path | None = None) -> None:
        t.setup()
        super().__init__(fg_color=t.BG)

        self.settings = load_settings()
        self.db = HistoryStore()
        self.router = IdentityRouter(self.settings)
        self.toast = ToastHost(self)
        self.clipboard_watcher: ClipboardWatcher | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._queue: queue.Queue = queue.Queue()
        self._drain_after = None
        self._closing = False

        self._scan_token = 0
        self._scan_thread: threading.Thread | None = None
        self.current_image = None
        self.current_source_path: Path | None = None
        self._mode = "drop"
        self.results_view: ResultsView | None = None
        self.history_view: HistoryView | None = None

        self.title("SceneLens — universal scene identifier")
        self._configure_window()
        self._set_icon()

        # tkdnd is optional: without it the app still supports browse + paste.
        self.dnd_enabled = False
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD.require(self)
            self.dnd_enabled = True
        except Exception:  # noqa: BLE001 - drag & drop is a progressive enhancement
            logger.info("Drag and drop unavailable", exc_info=True)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self, self)
        self.sidebar.grid(row=0, column=0, sticky="ns")

        main = ctk.CTkFrame(self, fg_color=t.BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        self._build_header(main)

        ctk.CTkFrame(main, height=1, fg_color=t.BORDER, corner_radius=0).grid(
            row=1, column=0, sticky="ew", padx=28
        )

        self.body = ctk.CTkFrame(main, fg_color=t.BG, corner_radius=0)
        self.body.grid(row=2, column=0, sticky="nsew", padx=28, pady=(16, 22))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        self.drop_view = DropView(self.body, self)
        self.scan_view = ScanView(self.body, self)
        self._show_frame(self.drop_view, "drop")

        self.sidebar.refresh_engines(self.settings)
        self.sidebar.refresh_history(self.db.recent(5))
        self._restart_watcher()
        self._bind_shortcuts()
        self._drain_after = self.after(40, self._drain_queue)

        if initial_image is not None:
            self.after(500, lambda: self.open_paths([str(initial_image)]))

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _configure_window(self) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1380, max(1100, int(screen_w * 0.92)))
        height = min(900, max(660, int(screen_h * 0.86)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 16)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1100, 660)

    def _set_icon(self) -> None:
        path = ensure_icon_asset()
        if not path:
            return
        try:
            self._icon_photo = tk.PhotoImage(file=str(path))
            self.iconphoto(True, self._icon_photo)
        except Exception:  # noqa: BLE001
            logger.debug("Could not set window icon", exc_info=True)

    def _build_header(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color=t.BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 14))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")

        self.header_title = ctk.CTkLabel(
            titles,
            text="Identify any scene",
            font=t.ui_font(21, "bold"),
            text_color=t.TEXT,
            anchor="w",
        )
        self.header_title.pack(anchor="w")
        self.header_subtitle = ctk.CTkLabel(
            titles,
            text="Drop a screenshot, paste a frame, or browse a file.",
            font=t.ui_font(10),
            text_color=t.MUTED,
            anchor="w",
        )
        self.header_subtitle.pack(anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")

        self.mode_badge = Badge(
            actions,
            "READY",
            text_color=t.GREEN,
            fg_color=t.GREEN_SOFT,
            height=28,
        )
        self.mode_badge.pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            actions,
            text="Paste  Ctrl+V",
            command=self.paste_clipboard,
            width=118,
            height=36,
            corner_radius=9,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.CYAN,
            font=t.ui_font(11, "bold"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="Browse image",
            command=self.browse_files,
            width=126,
            height=36,
            corner_radius=9,
            fg_color=t.CYAN,
            hover_color="#5BF0FF",
            text_color="#06141A",
            font=t.ui_font(11, "bold"),
        ).pack(side="left")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-v>", lambda _event: self.paste_clipboard())
        self.bind("<Control-V>", lambda _event: self.paste_clipboard())
        self.bind("<Control-o>", lambda _event: self.browse_files())
        self.bind("<Control-n>", lambda _event: self.new_scan())
        self.bind("<Control-h>", lambda _event: self.show_history())
        self.bind("<Control-comma>", lambda _event: self.open_settings())

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def _show_frame(self, frame, mode: str) -> None:
        for child in self.body.winfo_children():
            if child is not frame:
                child.grid_forget()
        frame.grid(row=0, column=0, sticky="nsew")
        self._mode = mode

    def _set_header(self, title: str, subtitle: str) -> None:
        self.header_title.configure(text=title)
        self.header_subtitle.configure(text=subtitle)

    def _set_mode_badge(self, text: str, color: str, soft: str) -> None:
        try:
            self.mode_badge.configure(text=f"  {text}  ", text_color=color, fg_color=soft)
        except Exception:  # noqa: BLE001
            pass

    def new_scan(self) -> None:
        self._scan_token += 1
        self.scan_view.stop()
        self._set_header(
            "Identify any scene",
            "Drop a screenshot, paste a frame, or browse a file.",
        )
        self._set_mode_badge("READY", t.GREEN, t.GREEN_SOFT)
        self._show_frame(self.drop_view, "drop")
        self.sidebar.set_active("scan")

    def show_history(self) -> None:
        self._scan_token += 1
        self.scan_view.stop()
        records = self.db.recent(60)
        if self.history_view is not None:
            self.history_view.destroy()
        self.history_view = HistoryView(self.body, self, records)
        self._show_frame(self.history_view, "history")
        self._set_header(
            "Scan history",
            "Every identification is saved locally on this device.",
        )
        self._set_mode_badge("HISTORY", t.CYAN, t.CYAN_SOFT)
        self.sidebar.set_active("history")
        self.sidebar.refresh_history(self.db.recent(5))

    def open_history(self, scan_id: int) -> None:
        record = self.db.get(scan_id)
        if record is None:
            self.toast.show("That scan is no longer in your history.", kind="warning")
            self.show_history()
            return

        self._scan_token += 1
        self.scan_view.stop()

        image = None
        for candidate in (record.source_path, record.thumbnail_path):
            if not candidate:
                continue
            path = Path(candidate)
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
                continue
            try:
                image = load_image(path)
                break
            except ImageInputError:
                continue

        report = ScanReport(
            best=record.result,
            alternatives=[],
            used_fallback=record.result.confidence < self.settings.confidence_threshold,
            threshold=self.settings.confidence_threshold,
            statuses=[EngineStatus(record.result.source, True, "stored scan", 0)],
            notices=[],
            image_hash="",
            elapsed_seconds=0.0,
        )

        if self.results_view is not None:
            self.results_view.destroy()
        self.results_view = ResultsView(self.body, self, report, image, from_history=True)
        self._show_frame(self.results_view, "results")
        self._set_header("Saved scan", "Loaded from your local history.")
        self._set_mode_badge("HISTORY", t.CYAN, t.CYAN_SOFT)
        self.sidebar.set_active("scan")
        self.sidebar.refresh_history(self.db.recent(5))

    # ------------------------------------------------------------------
    # Input entry points
    # ------------------------------------------------------------------

    def browse_files(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a frame to identify",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.open_paths([path])

    def paste_clipboard(self) -> None:
        image = read_clipboard_image()
        if image is None:
            self.toast.show(
                "No image on the clipboard. Copy a frame first, then try again.",
                kind="warning",
            )
            return
        self.start_scan(image, source_path=None)

    def open_paths(self, paths: list[str]) -> None:
        if not paths:
            self.toast.show("Drop a PNG, JPG or WEBP image to identify it.", kind="warning")
            return
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                image = load_image(path)
            except ImageInputError as error:
                self.toast.show(str(error), kind="error")
                continue
            self.start_scan(image, source_path=path)
            return
        self.toast.show("No supported image found (PNG, JPG, WEBP).", kind="warning")

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def start_scan(self, image, source_path: Path | None = None) -> None:
        self._scan_token += 1
        token = self._scan_token
        self.current_image = image
        self.current_source_path = source_path

        self._set_header(
            "Analyzing frame",
            "The anime index and vision engine are running side by side.",
        )
        self._set_mode_badge("SCANNING", t.CYAN, t.CYAN_SOFT)
        self.sidebar.set_active("scan")

        self._show_frame(self.scan_view, "scanning")
        filename = source_path.name if source_path else "clipboard frame"
        self.scan_view.start(image, filename)

        def worker() -> None:
            try:
                report = self.router.scan_sync(
                    image,
                    progress=lambda message: self.post(self._on_progress, token, message),
                )
            except Exception as error:  # noqa: BLE001
                logger.exception("Scan failed")
                self.post(self._on_scan_failed, token, str(error) or error.__class__.__name__)
                return
            self.post(self._on_scan_complete, token, report)

        self._scan_thread = threading.Thread(
            target=worker, daemon=True, name=f"scenelens-scan-{token}"
        )
        self._scan_thread.start()

    def _on_progress(self, token: int, message: str) -> None:
        if token != self._scan_token:
            return
        self.scan_view.set_stage(message)

    def _on_scan_failed(self, token: int, message: str) -> None:
        if token != self._scan_token:
            return
        self.scan_view.stop()
        self.new_scan()
        self.toast.show(f"Scan failed: {message}", kind="error", duration=6000)

    def _on_scan_complete(self, token: int, report: ScanReport) -> None:
        if token != self._scan_token:
            return
        self.scan_view.stop()

        if report.best is None:
            if self.results_view is not None:
                self.results_view.destroy()
            self.results_view = ResultsView(self.body, self, report, self.current_image)
            self._show_frame(self.results_view, "results")
            self._set_header("No confident match", "Try another frame or add a vision engine.")
            self._set_mode_badge("NO MATCH", t.AMBER, t.AMBER_SOFT)
            self.toast.show("No confident match was found.", kind="warning")
            return

        thumbnail_path = None
        try:
            key = report.image_hash or image_signature(self.current_image)
            thumbnail_path = save_history_thumbnail(self.current_image, key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not save history thumbnail", exc_info=True)

        try:
            self.db.add(
                report.best,
                thumbnail_path=thumbnail_path,
                source_path=str(self.current_source_path) if self.current_source_path else None,
                image_hash=report.image_hash or None,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Could not write scan history")
            self.toast.show("Match found, but saving to history failed.", kind="warning")

        if self.results_view is not None:
            self.results_view.destroy()
        self.results_view = ResultsView(self.body, self, report, self.current_image)
        self._show_frame(self.results_view, "results")
        unverified = (
            report.best.source == "trace.moe" and not self.settings.vision_configured
        )
        if report.used_fallback:
            header_title = "Low confidence match"
        elif unverified:
            header_title = "Anime-only match"
        else:
            header_title = "Match found"
        self._set_header(
            header_title,
            f"{report.best.title} · identified in {report.elapsed_seconds:0.1f}s",
        )
        if report.used_fallback:
            self._set_mode_badge("LOW MATCH", t.AMBER, t.AMBER_SOFT)
        elif unverified:
            self._set_mode_badge("UNVERIFIED", t.AMBER, t.AMBER_SOFT)
        else:
            self._set_mode_badge("MATCH", t.GREEN, t.GREEN_SOFT)
        self.sidebar.set_active("scan")
        self.sidebar.refresh_history(self.db.recent(5))
        self.toast.show(
            f"{report.best.title} · {report.best.confidence_pct}% match",
            kind="success" if not report.used_fallback else "warning",
        )

    # ------------------------------------------------------------------
    # Clipboard watching
    # ------------------------------------------------------------------

    def _restart_watcher(self) -> None:
        if self.clipboard_watcher is not None:
            self.clipboard_watcher.stop()
            self.clipboard_watcher = None
        if self.settings.watch_clipboard:
            watcher = ClipboardWatcher(self._on_clipboard_frame)
            watcher.start()
            self.clipboard_watcher = watcher

    def _on_clipboard_frame(self, image) -> None:
        self.post(self._clipboard_notice, image)

    def _clipboard_notice(self, image) -> None:
        if self._mode == "scanning":
            return
        if self.settings.auto_scan_clipboard:
            self.start_scan(image)
            return
        self.toast.show(
            "New image on the clipboard.",
            kind="info",
            action_label="Scan now",
            action=lambda: self.start_scan(image),
            duration=7000,
        )

    # ------------------------------------------------------------------
    # Settings + history maintenance
    # ------------------------------------------------------------------

    def open_settings(self) -> None:
        if self._settings_dialog is not None:
            try:
                if self._settings_dialog.winfo_exists():
                    self._settings_dialog.lift()
                    self._settings_dialog.focus_force()
                    return
            except Exception:  # noqa: BLE001
                pass
            self._settings_dialog = None
        self._settings_dialog = SettingsDialog(self)

    def apply_settings(self, settings: Settings) -> None:
        save_settings(settings)
        self.settings = settings
        self.router.update_settings(settings)
        self.sidebar.refresh_engines(settings)
        self.scan_view.refresh_engines(settings)
        self._restart_watcher()
        self.toast.show("Settings saved.", kind="success")

    def delete_history(self, scan_id: int, thumbnail_path: str | None) -> None:
        self.db.delete(scan_id)
        if thumbnail_path:
            try:
                path = Path(thumbnail_path).resolve()
                if THUMB_DIR.resolve() in path.parents and path.is_file():
                    path.unlink()
            except OSError:
                logger.debug("Could not delete thumbnail", exc_info=True)
        self.sidebar.refresh_history(self.db.recent(5))
        self.show_history()
        self.toast.show("Scan removed from history.", kind="success")

    def clear_history(self) -> None:
        self.db.clear()
        try:
            for path in THUMB_DIR.glob("*.jpg"):
                path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not clear thumbnails", exc_info=True)
        self.sidebar.refresh_history(self.db.recent(5))
        self.show_history()
        self.toast.show("History cleared.", kind="success")

    # ------------------------------------------------------------------
    # Cross-thread plumbing
    # ------------------------------------------------------------------

    def post(self, callback, *args, **kwargs) -> None:
        self._queue.put((callback, args, kwargs))

    def _drain_queue(self) -> None:
        self._drain_after = None
        while True:
            try:
                callback, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.exception("UI callback failed")
        if not self._closing:
            self._drain_after = self.after(40, self._drain_queue)

    def report_callback_exception(self, exc, val, tb) -> None:
        logger.error("Tk callback error", exc_info=(exc, val, tb))
        try:
            self.toast.show("Something went wrong. Check the log for details.", kind="error")
        except Exception:  # noqa: BLE001
            pass

    def destroy(self) -> None:
        self._closing = True
        if self._drain_after:
            try:
                self.after_cancel(self._drain_after)
            except Exception:  # noqa: BLE001
                pass
        if self.clipboard_watcher is not None:
            self.clipboard_watcher.stop()
        super().destroy()

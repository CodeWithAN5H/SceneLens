"""Settings modal for engine credentials, threshold and clipboard behaviour."""

from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from urllib.parse import urlparse

import customtkinter as ctk

from ..config import CONFIG_PATH, Settings
from ..engines.vision import VisionClient
from . import theme as t
from .widgets import SectionTitle


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app) -> None:
        super().__init__(app, fg_color=t.BG)
        self.app = app
        self.settings = app.settings
        self.title("SceneLens settings")
        self.resizable(False, False)
        self.transient(app)
        self._closing = False

        self._vision_key = tk.StringVar(value=self.settings.vision_api_key)
        self._base_url = tk.StringVar(value=self.settings.vision_base_url)
        self._model = tk.StringVar(value=self.settings.vision_model)
        self._tmdb_key = tk.StringVar(value=self.settings.tmdb_api_key)
        self._threshold = tk.DoubleVar(value=self.settings.confidence_threshold)
        self._watch = tk.BooleanVar(value=self.settings.watch_clipboard)
        self._auto_scan = tk.BooleanVar(value=self.settings.auto_scan_clipboard)
        self._cut_borders = tk.BooleanVar(value=self.settings.cut_borders)
        self._key_visible = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Settings",
            font=t.ui_font(20, "bold"),
            text_color=t.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Engines, keys and scanning behaviour",
            font=t.ui_font(10),
            text_color=t.MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ctk.CTkButton(
            header,
            text="✕",
            command=self._close,
            width=28,
            height=28,
            corner_radius=7,
            fg_color="transparent",
            hover_color=t.BORDER,
            text_color=t.FAINT,
            font=t.ui_font(11),
        ).grid(row=0, column=1, rowspan=2, sticky="ne")

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=t.BORDER,
            scrollbar_button_hover_color=t.FAINT,
        )
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=(14, 8))
        self.scroll.grid_columnconfigure(0, weight=1)

        self._build_vision_section()
        self._build_metadata_section()
        self._build_scanning_section()
        self._build_clipboard_section()

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(10, 18))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer,
            text=f"Keys stay on this device · {CONFIG_PATH}",
            font=t.mono_font(8),
            text_color=t.FAINT,
            anchor="w",
            wraplength=330,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer,
            text="Cancel",
            command=self._close,
            width=86,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.MUTED,
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=1, padx=(10, 8))
        ctk.CTkButton(
            footer,
            text="Save settings",
            command=self._save,
            width=130,
            height=36,
            corner_radius=8,
            fg_color=t.CYAN,
            hover_color="#5BF0FF",
            text_color="#06141A",
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=2)

        self.bind("<Escape>", lambda _event: self._close())
        self.update_idletasks()
        self.geometry(f"640x{min(760, self.winfo_screenheight() - 80)}")
        self._center(app)
        self.after(60, self._make_modal)

    # ------------------------------------------------------------------

    def _make_modal(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:  # noqa: BLE001
            pass

    def _center(self, parent) -> None:
        try:
            width = 640
            height = min(760, self.winfo_screenheight() - 80)
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + max(20, (parent.winfo_height() - height) // 2)
            self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass

    def _section(self, title: str, description: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.scroll,
            fg_color=t.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=t.BORDER,
        )
        card.grid(row=self._next_row(), column=0, sticky="ew", padx=10, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        SectionTitle(card, title).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(
            card,
            text=description,
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
            justify="left",
            wraplength=540,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 10))
        return card

    def _next_row(self) -> int:
        if not hasattr(self, "_section_row"):
            self._section_row = 0
        self._section_row += 1
        return self._section_row - 1

    @staticmethod
    def _field_label(parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=text,
            font=t.ui_font(9, "bold"),
            text_color=t.MUTED,
            anchor="w",
        )

    def _entry(self, parent, variable: tk.StringVar, placeholder: str = "", show: str = ""):
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=36,
            corner_radius=8,
            fg_color=t.PANEL_ALT,
            border_color=t.BORDER,
            border_width=1,
            text_color=t.TEXT,
            placeholder_text=placeholder,
            placeholder_text_color=t.FAINT,
            font=t.ui_font(11),
            show=show,
        )
        return entry

    # ---- sections --------------------------------------------------------

    def _build_vision_section(self) -> None:
        card = self._section(
            "Vision engine",
            "Any OpenAI-compatible multimodal endpoint. Used for movies, TV series and games.",
        )

        key_row = ctk.CTkFrame(card, fg_color="transparent")
        key_row.grid(row=2, column=0, sticky="ew", padx=18)
        key_row.grid_columnconfigure(0, weight=1)
        self._field_label(key_row, "API key").grid(row=0, column=0, sticky="w")
        self._show_key_button = ctk.CTkButton(
            key_row,
            text="show",
            command=self._toggle_key,
            width=44,
            height=20,
            corner_radius=6,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            text_color=t.FAINT,
            font=t.ui_font(8, "bold"),
        )
        self._show_key_button.grid(row=0, column=1, sticky="e")

        env_hint = "Using OPENAI_API_KEY from the environment" if not self.settings.vision_api_key and self.settings.vision_configured else ""
        self.vision_key_entry = self._entry(
            card, self._vision_key, env_hint or "sk-…", show="" if self._key_visible else "•"
        )
        self.vision_key_entry.grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 10))

        self._field_label(card, "Base URL").grid(row=4, column=0, sticky="w", padx=18)
        self._entry(card, self._base_url, "https://api.openai.com/v1").grid(
            row=5, column=0, sticky="ew", padx=18, pady=(4, 10)
        )

        self._field_label(card, "Model").grid(row=6, column=0, sticky="w", padx=18)
        self._entry(card, self._model, "gpt-4o-mini").grid(
            row=7, column=0, sticky="ew", padx=18, pady=(4, 10)
        )

        test_row = ctk.CTkFrame(card, fg_color="transparent")
        test_row.grid(row=8, column=0, sticky="ew", padx=18, pady=(0, 16))
        test_row.grid_columnconfigure(1, weight=1)

        self._test_button = ctk.CTkButton(
            test_row,
            text="Test connection",
            command=self._test_connection,
            width=112,
            height=30,
            corner_radius=7,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(9, "bold"),
        )
        self._test_button.grid(row=0, column=0, sticky="w")
        self._test_status = ctk.CTkLabel(
            test_row,
            text="",
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
            wraplength=370,
            justify="left",
        )
        self._test_status.grid(row=0, column=1, sticky="w", padx=(10, 0))

    def _build_metadata_section(self) -> None:
        card = self._section(
            "Film metadata",
            "Optional free TMDB API key. Adds posters, canonical titles, studios and synopses.",
        )
        self._field_label(card, "TMDB API key").grid(row=2, column=0, sticky="w", padx=18)
        self._entry(card, self._tmdb_key, "optional").grid(
            row=3, column=0, sticky="ew", padx=18, pady=(4, 16)
        )

    def _build_scanning_section(self) -> None:
        card = self._section(
            "Scanning",
            "Below this confidence the result screen shows the closest alternatives instead of a confident match.",
        )

        threshold_row = ctk.CTkFrame(card, fg_color="transparent")
        threshold_row.grid(row=2, column=0, sticky="ew", padx=18)
        threshold_row.grid_columnconfigure(0, weight=1)
        self._field_label(threshold_row, "Confidence threshold").grid(row=0, column=0, sticky="w")
        self._threshold_label = ctk.CTkLabel(
            threshold_row,
            text=f"{round(self._threshold.get() * 100)}%",
            font=t.mono_font(10, "bold"),
            text_color=t.CYAN,
            anchor="e",
        )
        self._threshold_label.grid(row=0, column=1, sticky="e")

        self._slider = ctk.CTkSlider(
            card,
            from_=0.2,
            to=0.9,
            number_of_steps=14,
            command=self._on_threshold,
            height=16,
            fg_color=t.PANEL_ALT,
            progress_color=t.CYAN,
            button_color=t.CYAN,
            button_hover_color="#5BF0FF",
        )
        self._slider.set(self._threshold.get())
        self._slider.grid(row=3, column=0, sticky="ew", padx=18, pady=(8, 14))

        self._cut_switch = ctk.CTkSwitch(
            card,
            text="Crop black borders before anime search",
            variable=self._cut_borders,
            progress_color=t.CYAN,
            button_color=t.TEXT,
            button_hover_color=t.TEXT,
            text_color=t.MUTED,
            font=t.ui_font(10),
        )
        self._cut_switch.grid(row=4, column=0, sticky="w", padx=18, pady=(0, 16))

    def _build_clipboard_section(self) -> None:
        card = self._section(
            "Clipboard",
            "SceneLens can watch the clipboard while it runs and offer a one-click scan of new frames.",
        )

        self._watch_switch = ctk.CTkSwitch(
            card,
            text="Watch clipboard for images",
            variable=self._watch,
            command=self._sync_clipboard_switches,
            progress_color=t.CYAN,
            button_color=t.TEXT,
            button_hover_color=t.TEXT,
            text_color=t.MUTED,
            font=t.ui_font(10),
        )
        self._watch_switch.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 8))

        self._auto_switch = ctk.CTkSwitch(
            card,
            text="Scan new clipboard frames automatically",
            variable=self._auto_scan,
            progress_color=t.CYAN,
            button_color=t.TEXT,
            button_hover_color=t.TEXT,
            text_color=t.MUTED,
            font=t.ui_font(10),
        )
        self._auto_switch.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 8))
        self._sync_clipboard_switches()

        ctk.CTkLabel(
            card,
            text="Automatic scanning uses your vision API credits for every new image.",
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
            wraplength=540,
            justify="left",
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(0, 16))

    # ---- interactions ----------------------------------------------------

    def _toggle_key(self) -> None:
        self._key_visible = not self._key_visible
        self.vision_key_entry.configure(show="" if self._key_visible else "•")
        self._show_key_button.configure(text="hide" if self._key_visible else "show")

    def _sync_clipboard_switches(self) -> None:
        state = "normal" if self._watch.get() else "disabled"
        self._auto_switch.configure(state=state)

    def _on_threshold(self, value: float) -> None:
        self._threshold_label.configure(text=f"{round(value * 100)}%")

    def _collect(self) -> Settings:
        return Settings(
            vision_api_key=self._vision_key.get().strip(),
            vision_base_url=self._base_url.get().strip(),
            vision_model=self._model.get().strip(),
            tmdb_api_key=self._tmdb_key.get().strip(),
            confidence_threshold=round(float(self._threshold.get()), 2),
            watch_clipboard=bool(self._watch.get()),
            auto_scan_clipboard=bool(self._auto_scan.get()),
            cut_borders=bool(self._cut_borders.get()),
        ).sanitized()

    def _save(self) -> None:
        settings = self._collect()
        parsed = urlparse(settings.resolved_vision_base_url)
        if settings.vision_api_key and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            self._test_status.configure(text="Base URL must start with http:// or https://", text_color=t.RED)
            return
        self.app.apply_settings(settings)
        self._close()

    def _test_connection(self) -> None:
        settings = self._collect()
        if not settings.vision_configured:
            self._test_status.configure(text="Add an API key first.", text_color=t.AMBER)
            return
        parsed = urlparse(settings.resolved_vision_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._test_status.configure(text="Base URL is invalid.", text_color=t.RED)
            return

        self._test_button.configure(state="disabled", text="Testing…")
        self._test_status.configure(text="Contacting endpoint…", text_color=t.MUTED)

        def worker() -> None:
            try:
                ok, message = asyncio.run(VisionClient(settings).check_access())
            except Exception as error:  # noqa: BLE001
                ok, message = False, str(error)
            self.app.post(self._test_done, ok, message)

        threading.Thread(target=worker, daemon=True, name="scenelens-test").start()

    def _test_done(self, ok: bool, message: str) -> None:
        if self._closing or not self.winfo_exists():
            return
        try:
            self._test_button.configure(state="normal", text="Test connection")
            self._test_status.configure(text=message, text_color=t.GREEN if ok else t.RED)
        except Exception:  # noqa: BLE001
            pass

    # ---- lifecycle -------------------------------------------------------

    def _close(self) -> None:
        self._closing = True
        self.destroy()

    def destroy(self) -> None:
        if getattr(self.app, "_settings_dialog", None) is self:
            self.app._settings_dialog = None
        super().destroy()

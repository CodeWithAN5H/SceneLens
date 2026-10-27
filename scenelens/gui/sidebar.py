"""Left rail: brand, navigation, recent scans and engine status."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from PIL import Image

from ..config import Settings
from ..database import ScanRecord
from . import theme as t
from .glyphs import lens_icon
from .widgets import SectionTitle


class NavButton(ctk.CTkFrame):
    def __init__(self, master, text: str, glyph: str, command) -> None:
        super().__init__(master, fg_color="transparent", height=44)
        self.grid_columnconfigure(1, weight=1)
        self.grid_propagate(False)

        self.bar = ctk.CTkFrame(self, width=3, height=22, fg_color="transparent", corner_radius=2)
        self.bar.grid(row=0, column=0, padx=(0, 8), pady=11)

        self.button = ctk.CTkButton(
            self,
            text=f"{glyph}    {text}",
            anchor="w",
            height=40,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.PANEL,
            text_color=t.MUTED,
            font=t.ui_font(12, "bold"),
            command=command,
        )
        self.button.grid(row=0, column=1, sticky="ew", pady=2)

    def set_active(self, active: bool) -> None:
        self.bar.configure(fg_color=t.CYAN if active else "transparent")
        self.button.configure(
            fg_color=t.PANEL_ALT if active else "transparent",
            text_color=t.CYAN if active else t.MUTED,
        )


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=t.SIDEBAR, corner_radius=0, width=252)
        self.app = app
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkFrame(self, width=1, fg_color=t.BORDER, corner_radius=0).place(
            relx=1.0, rely=0, relheight=1, anchor="ne"
        )

        # ---- brand -------------------------------------------------------
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 18))
        brand.grid_columnconfigure(1, weight=1)

        icon = lens_icon(34)
        self._brand_icon = ctk.CTkImage(light_image=icon, dark_image=icon, size=(34, 34))
        ctk.CTkLabel(brand, image=self._brand_icon, text="", width=34).grid(
            row=0, column=0, rowspan=2, padx=(0, 10)
        )
        ctk.CTkLabel(
            brand,
            text="SCENELENS",
            font=t.ui_font(16, "bold"),
            text_color=t.TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            brand,
            text="universal scene identifier",
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
        ).grid(row=1, column=1, sticky="w")

        # ---- navigation --------------------------------------------------
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=12)
        nav.grid_columnconfigure(0, weight=1)

        self.scan_nav = NavButton(nav, "Scan", "◈", app.new_scan)
        self.scan_nav.grid(row=0, column=0, sticky="ew")
        self.history_nav = NavButton(nav, "History", "◷", app.show_history)
        self.history_nav.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._active = "scan"
        self.set_active("scan")

        # ---- recent ------------------------------------------------------
        recent_header = ctk.CTkFrame(self, fg_color="transparent")
        recent_header.grid(row=2, column=0, sticky="ew", padx=22, pady=(20, 8))
        recent_header.grid_columnconfigure(0, weight=1)
        SectionTitle(recent_header, "Recent scans").grid(row=0, column=0, sticky="w")
        self.recent_button = ctk.CTkLabel(
            recent_header,
            text="View all",
            font=t.ui_font(9, "bold"),
            text_color=t.FAINT,
            cursor="hand2",
        )
        self.recent_button.grid(row=0, column=1, sticky="e")
        self.recent_button.bind("<Button-1>", lambda _e: app.show_history())
        self.recent_button.bind("<Enter>", lambda _e: self.recent_button.configure(text_color=t.CYAN))
        self.recent_button.bind("<Leave>", lambda _e: self.recent_button.configure(text_color=t.FAINT))

        self.recent_list = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=t.BORDER,
            scrollbar_button_hover_color=t.FAINT,
        )
        self.recent_list.grid(row=3, column=0, sticky="nsew", padx=(12, 6), pady=(0, 6))
        self.recent_list.grid_columnconfigure(0, weight=1)
        self._recent_images: list[ctk.CTkImage] = []
        self._empty_recent = None

        # ---- engine status ----------------------------------------------
        self._build_engine_panel()

    # ------------------------------------------------------------------

    def _build_engine_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=t.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=t.BORDER,
        )
        panel.grid(row=4, column=0, sticky="ew", padx=14, pady=(8, 8))
        panel.grid_columnconfigure(1, weight=1)

        SectionTitle(panel, "Engines").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6)
        )

        self.engine_rows: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        for index, name in enumerate(("trace.moe", "Vision", "TMDB"), start=1):
            dot = ctk.CTkLabel(panel, text="●", font=t.ui_font(7), width=12, text_color=t.BORDER)
            dot.grid(row=index, column=0, padx=(14, 0), pady=2, sticky="w")
            label = ctk.CTkLabel(
                panel,
                text=name,
                font=t.ui_font(10),
                text_color=t.MUTED,
                anchor="w",
            )
            label.grid(row=index, column=1, padx=(2, 14), pady=2, sticky="w")
            self.engine_rows[name] = (dot, label)

        self.engine_hint = ctk.CTkLabel(
            panel,
            text="",
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
            justify="left",
            wraplength=190,
        )
        self.engine_hint.grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 12))

        ctk.CTkButton(
            self,
            text="⚙    Settings",
            anchor="w",
            command=self.app.open_settings,
            height=38,
            corner_radius=9,
            fg_color="transparent",
            hover_color=t.PANEL,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.MUTED,
            font=t.ui_font(11, "bold"),
        ).grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 16))

    def refresh_engines(self, settings: Settings) -> None:
        vision_ready = settings.vision_configured
        tmdb_ready = settings.tmdb_configured
        states = {
            "trace.moe": (True, "online"),
            "Vision": (vision_ready, settings.resolved_vision_model if vision_ready else "not set"),
            "TMDB": (tmdb_ready, "posters" if tmdb_ready else "optional"),
        }
        for name, (dot, label) in self.engine_rows.items():
            ready, detail = states[name]
            color = t.GREEN if ready else (t.AMBER if name == "Vision" else t.BORDER)
            dot.configure(text_color=color)
            label.configure(text=f"{name}  ·  {detail}", text_color=t.TEXT if ready else t.FAINT)

        if not vision_ready:
            self.engine_hint.configure(
                text="Add a vision API key for movies, TV and games."
            )
        elif not tmdb_ready:
            self.engine_hint.configure(text="Add a TMDB key for film posters and studios.")
        else:
            self.engine_hint.configure(text="All engines ready.")

    # ------------------------------------------------------------------

    def set_active(self, name: str) -> None:
        self._active = name
        self.scan_nav.set_active(name in {"scan", "scanning", "results"})
        self.history_nav.set_active(name == "history")

    def refresh_history(self, records: list[ScanRecord]) -> None:
        for child in self.recent_list.winfo_children():
            child.destroy()
        self._recent_images.clear()

        if not records:
            ctk.CTkLabel(
                self.recent_list,
                text="Nothing scanned yet.\nDrop a frame to begin.",
                font=t.ui_font(10),
                text_color=t.FAINT,
                justify="left",
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        for index, record in enumerate(records[:5]):
            self._build_recent_row(record, index)

    def _build_recent_row(self, record: ScanRecord, index: int) -> None:
        result = record.result
        accent = t.accent_for(result.media_type)

        row = ctk.CTkFrame(
            self.recent_list,
            fg_color="transparent",
            corner_radius=8,
            height=48,
        )
        row.grid(row=index, column=0, sticky="ew", pady=1, padx=(0, 2))
        row.grid_columnconfigure(1, weight=1)
        row.grid_propagate(False)

        image = self._thumb(record)
        thumb = ctk.CTkLabel(row, text="", image=image, width=52, height=30, corner_radius=5)
        thumb.grid(row=0, column=0, padx=(8, 10), pady=9)

        title = result.title if len(result.title) <= 24 else result.title[:23] + "…"
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            text,
            text=title,
            font=t.ui_font(10, "bold"),
            text_color=t.TEXT,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text,
            text=f"{result.tag}  ·  {result.confidence_pct}%",
            font=t.ui_font(8),
            text_color=accent if result.confidence >= 0.6 else t.AMBER,
            anchor="w",
        ).pack(anchor="w")

        def enter(_event=None):
            row.configure(fg_color=t.PANEL)
            title_label.configure(text_color=t.CYAN)

        def leave(_event=None):
            row.configure(fg_color="transparent")
            title_label.configure(text_color=t.TEXT)

        title_label = text.winfo_children()[0]

        def bind_tree(widget):
            widget.bind("<Enter>", enter, add="+")
            widget.bind("<Leave>", leave, add="+")
            widget.bind("<Button-1>", lambda _e: self.app.open_history(record.id), add="+")
            try:
                widget.configure(cursor="hand2")
            except Exception:  # noqa: BLE001
                pass
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(row)

    def _thumb(self, record: ScanRecord) -> ctk.CTkImage:
        image = None
        for candidate in (record.thumbnail_path, record.source_path):
            if candidate and Path(candidate).is_file():
                try:
                    with Image.open(candidate) as opened:
                        image = opened.convert("RGB")
                    break
                except OSError:
                    continue
        if image is None:
            image = Image.new("RGB", (104, 60), (20, 26, 36))
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(52, 30))
        self._recent_images.append(ctk_image)
        return ctk_image

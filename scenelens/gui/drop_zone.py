"""The central drag-and-drop landing view."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from urllib.parse import unquote, urlparse

import customtkinter as ctk

from . import theme as t
from .glyphs import lens_icon
from .widgets import Badge


class DropView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=t.BG)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.panel = ctk.CTkFrame(
            self,
            fg_color=t.PANEL,
            corner_radius=20,
            border_width=1,
            border_color=t.BORDER,
        )
        self.panel.grid(row=0, column=0, sticky="nsew", padx=4, pady=(0, 10))
        self.panel.grid_columnconfigure(0, weight=1)
        self.panel.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self.panel,
            bg=t.PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.content = ctk.CTkFrame(self.panel, fg_color="transparent")
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self._lens = ctk.CTkImage(light_image=lens_icon(88), dark_image=lens_icon(88), size=(88, 88))
        ctk.CTkLabel(self.content, image=self._lens, text="").pack(pady=(0, 18))

        self.title = ctk.CTkLabel(
            self.content,
            text="Drop an image to identify",
            font=t.ui_font(23, "bold"),
            text_color=t.TEXT,
        )
        self.title.pack()

        self.subtitle = ctk.CTkLabel(
            self.content,
            text="Anime, movies, TV series or games — one frame is enough.",
            font=t.ui_font(12),
            text_color=t.MUTED,
        )
        self.subtitle.pack(pady=(7, 2))

        ctk.CTkLabel(
            self.content,
            text="PNG  ·  JPG  ·  WEBP   —   up to 30 MB",
            font=t.mono_font(9),
            text_color=t.FAINT,
        ).pack(pady=(0, 22))

        buttons = ctk.CTkFrame(self.content, fg_color="transparent")
        buttons.pack()
        ctk.CTkButton(
            buttons,
            text="Browse files",
            command=self.app.browse_files,
            width=168,
            height=40,
            corner_radius=9,
            fg_color=t.CYAN,
            hover_color="#5BF0FF",
            text_color="#06141A",
            font=t.ui_font(12, "bold"),
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            buttons,
            text="Paste  Ctrl+V",
            command=self.app.paste_clipboard,
            width=168,
            height=40,
            corner_radius=9,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(12, "bold"),
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            self.content,
            text="Ctrl+O browse   ·   Ctrl+V paste   ·   drop anywhere",
            font=t.ui_font(9),
            text_color=t.FAINT,
        ).pack(pady=(18, 0))

        chips = ctk.CTkFrame(self.content, fg_color="transparent")
        chips.pack(pady=(20, 0))
        for index, (media_type, label) in enumerate(
            (("anime", "ANIME"), ("movie", "MOVIE"), ("tv", "TV SERIES"), ("game", "GAME"))
        ):
            Badge(
                chips,
                label,
                text_color=t.accent_for(media_type),
                fg_color=t.soft_for(media_type),
            ).grid(row=0, column=index, padx=3)

        ctk.CTkLabel(
            self.panel,
            text="trace.moe anime index   ·   multimodal vision model   ·   local history",
            font=t.ui_font(9),
            text_color=t.FAINT,
        ).place(relx=0.5, rely=1.0, anchor="s", y=-32)

        self._hover_depth = 0
        self._reset_after: str | None = None
        self.canvas.bind("<Configure>", self._draw_decoration)
        self.panel.bind("<Configure>", self._draw_decoration)
        self._register_drops()

    # ---- decorations -----------------------------------------------------

    def _draw_decoration(self, _event=None) -> None:
        if not self.canvas.winfo_exists():
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 40 or height < 40:
            return

        active = self._hover_depth > 0
        bracket_color = t.CYAN if active else "#143A44"
        guide_color = "#10262E" if active else t.BORDER_SOFT

        self.canvas.delete("decor")
        self.canvas.create_rectangle(
            14,
            14,
            width - 14,
            height - 14,
            outline=guide_color,
            dash=(2, 7),
            width=1,
            tags="decor",
        )

        margin, length = 20, 30
        corners = (
            (margin, margin, 1, 1),
            (width - margin, margin, -1, 1),
            (margin, height - margin, 1, -1),
            (width - margin, height - margin, -1, -1),
        )
        for x, y, dx, dy in corners:
            self.canvas.create_line(
                x,
                y,
                x + dx * length,
                y,
                fill=bracket_color,
                width=2,
                capstyle=tk.ROUND,
                tags="decor",
            )
            self.canvas.create_line(
                x,
                y,
                x,
                y + dy * length,
                fill=bracket_color,
                width=2,
                capstyle=tk.ROUND,
                tags="decor",
            )
            self.canvas.create_oval(
                x - 2,
                y - 2,
                x + 2,
                y + 2,
                fill=bracket_color,
                outline="",
                tags="decor",
            )

        # Tiny center ticks on the long edges.
        for x in (width * 0.18, width * 0.82):
            self.canvas.create_line(
                x - 8, height - 18, x + 8, height - 18, fill=guide_color, width=1, tags="decor"
            )

    def _set_drag_state(self, active: bool) -> None:
        self.panel.configure(border_color=t.CYAN if active else t.BORDER)
        self.canvas.configure(bg="#0D1820" if active else t.PANEL)
        self.title.configure(text_color=t.CYAN if active else t.TEXT)
        self._draw_decoration()

    # ---- drag & drop -----------------------------------------------------

    def _register_drops(self) -> None:
        if not getattr(self.app, "dnd_enabled", False):
            return
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return

        for widget in self._walk(self.panel):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:  # noqa: BLE001 - registration differs per backend
                continue

    @staticmethod
    def _walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from DropView._walk(child)

    def _on_drag_enter(self, _event):
        from tkinterdnd2 import COPY

        self._hover_depth += 1
        if self._reset_after:
            try:
                self.after_cancel(self._reset_after)
            except Exception:  # noqa: BLE001
                pass
            self._reset_after = None
        self._set_drag_state(True)
        return COPY

    def _on_drag_leave(self, _event):
        from tkinterdnd2 import COPY

        self._hover_depth = max(0, self._hover_depth - 1)
        if self._hover_depth == 0:
            self._reset_after = self.after(90, self._clear_drag_state)
        return COPY

    def _clear_drag_state(self) -> None:
        self._reset_after = None
        if self._hover_depth == 0:
            self._set_drag_state(False)

    def _on_drop(self, event):
        from tkinterdnd2 import COPY

        self._hover_depth = 0
        self._set_drag_state(False)
        self.app.open_paths(self._parse_paths(event.data))
        return COPY

    def _parse_paths(self, data: str) -> list[str]:
        if not data:
            return []
        try:
            parts = self.tk.splitlist(data)
        except Exception:  # noqa: BLE001
            parts = [data]

        paths: list[str] = []
        for part in parts:
            text = str(part).strip()
            if text.startswith("file://"):
                parsed = urlparse(text)
                text = unquote(parsed.path)
                if text.startswith("/") and len(text) > 2 and text[2] == ":":
                    text = text[1:]
            if text:
                paths.append(text)
        return [path for path in paths if Path(path).suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".webp", ".bmp"
        }]

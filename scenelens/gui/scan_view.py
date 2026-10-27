"""Animated scanning state shown while engines are working."""

from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from ..utils.image_utils import fit_contain
from . import theme as t
from .widgets import Badge


class ScanView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=t.BG)
        self.app = app
        self._image: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._render_after: str | None = None
        self._animate_after: str | None = None
        self._timer_after: str | None = None
        self._animating = False
        self._scan_y = 40
        self._started_at = 0.0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.card = ctk.CTkFrame(
            self,
            fg_color=t.PANEL,
            corner_radius=18,
            border_width=1,
            border_color=t.BORDER,
        )
        self.card.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        header.grid_columnconfigure(1, weight=1)

        self.status_badge = Badge(
            header,
            "◉  SCANNING",
            text_color=t.CYAN,
            fg_color=t.CYAN_SOFT,
            border_color="#0E5C67",
            height=26,
        )
        self.status_badge.grid(row=0, column=0, sticky="w")

        self.filename_label = ctk.CTkLabel(
            header,
            text="",
            font=t.mono_font(9),
            text_color=t.FAINT,
            anchor="w",
        )
        self.filename_label.grid(row=0, column=1, sticky="w", padx=12)

        self.elapsed_label = ctk.CTkLabel(
            header,
            text="0.0s",
            font=t.mono_font(10),
            text_color=t.MUTED,
            anchor="e",
        )
        self.elapsed_label.grid(row=0, column=2, padx=(6, 10))

        ctk.CTkButton(
            header,
            text="Cancel",
            command=self.app.new_scan,
            width=76,
            height=28,
            corner_radius=7,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.MUTED,
            font=t.ui_font(10, "bold"),
        ).grid(row=0, column=3)

        self.canvas = tk.Canvas(
            self.card,
            bg="#0B0E14",
            highlightthickness=0,
            bd=0,
            height=300,
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=18)
        self.canvas.bind("<Configure>", self._schedule_render)

        footer = ctk.CTkFrame(self.card, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(12, 16))
        footer.grid_columnconfigure(0, weight=1)

        stage_row = ctk.CTkFrame(footer, fg_color="transparent")
        stage_row.grid(row=0, column=0, sticky="ew")
        stage_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            stage_row,
            text="●",
            font=t.ui_font(8),
            text_color=t.CYAN,
            width=12,
        ).grid(row=0, column=0, padx=(0, 6))
        self.stage_label = ctk.CTkLabel(
            stage_row,
            text="Preparing the frame…",
            font=t.ui_font(12),
            text_color=t.TEXT,
            anchor="w",
        )
        self.stage_label.grid(row=0, column=1, sticky="w")

        chips = ctk.CTkFrame(stage_row, fg_color="transparent")
        chips.grid(row=0, column=2, sticky="e")
        Badge(chips, "TRACE.MOE", text_color=t.CYAN, fg_color=t.CYAN_SOFT).grid(
            row=0, column=0, padx=3
        )
        vision_on = bool(self.app.settings.vision_configured)
        self.vision_badge = Badge(
            chips,
            "VISION" if vision_on else "VISION OFF",
            text_color=t.VIOLET if vision_on else t.AMBER,
            fg_color=t.VIOLET_SOFT if vision_on else t.AMBER_SOFT,
        )
        self.vision_badge.grid(row=0, column=1, padx=3)

        self.progress = ctk.CTkProgressBar(
            footer,
            height=4,
            corner_radius=2,
            mode="indeterminate",
            fg_color="#1B2130",
            progress_color=t.CYAN,
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    # ---- lifecycle -------------------------------------------------------

    def start(self, image: Image.Image, filename: str = "clipboard frame") -> None:
        self._image = image
        label = filename if len(filename) <= 44 else f"…{filename[-42:]}"
        self.filename_label.configure(text=label)
        self.stage_label.configure(text="Preparing the frame…")
        self._scan_y = 40
        self._started_at = time.perf_counter()
        self.elapsed_label.configure(text="0.0s")

        self._animating = True
        try:
            self.progress.start()
        except Exception:  # noqa: BLE001
            pass
        self._render_now()
        self._animate()
        self._tick_timer()

    def stop(self) -> None:
        self._animating = False
        for attribute in ("_animate_after", "_timer_after", "_render_after"):
            after_id = getattr(self, attribute)
            if after_id:
                try:
                    self.after_cancel(after_id)
                except Exception:  # noqa: BLE001
                    pass
                setattr(self, attribute, None)
        try:
            self.progress.stop()
        except Exception:  # noqa: BLE001
            pass

    def set_stage(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self.stage_label.configure(text=f"{message}…")

    def refresh_engines(self, settings) -> None:
        on = bool(settings.vision_configured)
        try:
            self.vision_badge.configure(
                text="  VISION  " if on else "  VISION OFF  ",
                text_color=t.VIOLET if on else t.AMBER,
                fg_color=t.VIOLET_SOFT if on else t.AMBER_SOFT,
            )
        except Exception:  # noqa: BLE001
            pass

    def _tick_timer(self) -> None:
        if not self._animating or not self.winfo_exists():
            return
        elapsed = time.perf_counter() - self._started_at
        self.elapsed_label.configure(text=f"{elapsed:0.1f}s")
        self._timer_after = self.after(180, self._tick_timer)

    # ---- canvas painting -------------------------------------------------

    def _schedule_render(self, _event=None) -> None:
        if self._render_after:
            try:
                self.after_cancel(self._render_after)
            except Exception:  # noqa: BLE001
                pass
        self._render_after = self.after(90, self._render_now)

    def _render_now(self) -> None:
        self._render_after = None
        if not self.winfo_exists() or self._image is None:
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 80 or height < 60:
            self._render_after = self.after(120, self._render_now)
            return

        self.canvas.delete("all")
        framed = fit_contain(self._image, (width, height), background=(11, 14, 20))
        self._photo = ImageTk.PhotoImage(framed)
        self.canvas.create_image(width // 2, height // 2, image=self._photo, anchor="center")

        # Dim the frame so the scanner and labels stay readable.
        self.canvas.create_rectangle(
            0, 0, width, height, fill="#080B11", stipple="gray50", outline=""
        )

        margin, length = 18, 26
        for x, y, dx, dy in (
            (margin, margin, 1, 1),
            (width - margin, margin, -1, 1),
            (margin, height - margin, 1, -1),
            (width - margin, height - margin, -1, -1),
        ):
            self.canvas.create_line(
                x, y, x + dx * length, y, fill=t.CYAN, width=2, capstyle=tk.ROUND
            )
            self.canvas.create_line(
                x, y, x, y + dy * length, fill=t.CYAN, width=2, capstyle=tk.ROUND
            )

        self.canvas.create_text(
            margin + 8,
            margin + 12,
            text="ANALYZING FRAME",
            fill="#7FE9F4",
            font=("Consolas", 9),
            anchor="w",
        )
        self.canvas.create_text(
            width - margin - 8,
            margin + 12,
            text="SCENELENS · LOCAL",
            fill="#4E6774",
            font=("Consolas", 9),
            anchor="e",
        )

        self._scan_y = min(max(self._scan_y, margin + 4), height - margin - 4)
        self._scan_glow = self.canvas.create_rectangle(
            margin,
            self._scan_y - 16,
            width - margin,
            self._scan_y + 16,
            fill="#06333C",
            outline="",
            stipple="gray50",
        )
        self._scan_line = self.canvas.create_line(
            margin,
            self._scan_y,
            width - margin,
            self._scan_y,
            fill=t.CYAN,
            width=2,
        )

    def _animate(self) -> None:
        self._animate_after = None
        if not self._animating or not self.winfo_exists():
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        margin = 18
        top, bottom = margin + 6, max(margin + 10, height - margin - 6)
        self._scan_y += 5
        if self._scan_y > bottom:
            self._scan_y = top
        if hasattr(self, "_scan_line") and hasattr(self, "_scan_glow"):
            try:
                self.canvas.coords(self._scan_line, margin, self._scan_y, width - margin, self._scan_y)
                self.canvas.coords(
                    self._scan_glow,
                    margin,
                    self._scan_y - 16,
                    width - margin,
                    self._scan_y + 16,
                )
            except tk.TclError:
                pass
        self._animate_after = self.after(26, self._animate)

    def destroy(self) -> None:
        self.stop()
        super().destroy()

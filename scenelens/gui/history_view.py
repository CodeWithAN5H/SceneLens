"""Persistent scan history, stored locally in SQLite."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

from ..database import ScanRecord
from . import theme as t
from .widgets import Badge, ConfirmDialog


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app, records: list[ScanRecord]) -> None:
        super().__init__(master, fg_color=t.BG)
        self.app = app
        self.records = records
        self._thumb_cache: dict[int, ctk.CTkImage] = {}
        self._leave_after: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 12))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text=f"{len(records)} saved scan{'s' if len(records) != 1 else ''}",
            font=t.ui_font(11, "bold"),
            text_color=t.MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="stored locally · SQLite",
            font=t.mono_font(9),
            text_color=t.FAINT,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=12)

        if records:
            ctk.CTkButton(
                header,
                text="Clear all",
                command=self._confirm_clear,
                width=92,
                height=30,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#2A121A",
                border_width=1,
                border_color="#3A2029",
                text_color=t.RED,
                font=t.ui_font(10, "bold"),
            ).grid(row=0, column=2, sticky="e")

        if not records:
            self._build_empty()
            return

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=t.BORDER,
            scrollbar_button_hover_color=t.FAINT,
        )
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        for index, record in enumerate(records):
            self._build_row(record, index)

        ctk.CTkLabel(
            self.scroll,
            text="History lives on this device only. Deleting a scan removes its thumbnail too.",
            font=t.ui_font(9),
            text_color=t.FAINT,
            anchor="w",
        ).grid(row=len(records), column=0, sticky="w", padx=14, pady=(8, 16))

    # ---- rows ------------------------------------------------------------

    def _build_row(self, record: ScanRecord, index: int) -> None:
        result = record.result
        accent = t.accent_for(result.media_type)

        row = ctk.CTkFrame(
            self.scroll,
            fg_color=t.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=t.BORDER,
            height=94,
        )
        row.grid(row=index, column=0, sticky="ew", pady=(0, 9), padx=2)
        row.grid_columnconfigure(1, weight=1)
        row.grid_propagate(False)

        thumb = ctk.CTkLabel(row, text="", width=120, height=68, fg_color=t.PANEL_ALT, corner_radius=8)
        thumb.grid(row=0, column=0, padx=(12, 12), pady=12)
        image = self._thumbnail_for(record)
        if image is not None:
            thumb.configure(image=image)
            self._thumb_cache[record.id] = image
        else:
            thumb.configure(text="NO FRAME", font=t.ui_font(8), text_color=t.FAINT)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=(12, 10))
        info.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            info,
            text=result.title,
            font=t.ui_font(14, "bold"),
            text_color=t.TEXT,
            anchor="w",
            justify="left",
            wraplength=420,
        )
        title.grid(row=0, column=0, sticky="w")

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.grid(row=1, column=0, sticky="w", pady=(6, 0))
        Badge(
            meta,
            result.tag,
            text_color=accent,
            fg_color=t.soft_for(result.media_type),
            height=20,
            font_size=8,
        ).pack(side="left", padx=(0, 6))
        if result.episode_code:
            ctk.CTkLabel(
                meta,
                text=result.episode_code,
                font=t.mono_font(9),
                text_color=t.MUTED,
            ).pack(side="left", padx=(0, 8))
        if result.year:
            ctk.CTkLabel(
                meta,
                text=str(result.year),
                font=t.ui_font(9),
                text_color=t.FAINT,
            ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            meta,
            text=record.created_local.strftime("%b %d · %H:%M"),
            font=t.ui_font(9),
            text_color=t.FAINT,
        ).pack(side="left")

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(10, 14), pady=12)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text=f"{result.confidence_pct}%",
            font=t.mono_font(12, "bold"),
            text_color=accent,
            anchor="e",
        ).grid(row=0, column=0, sticky="e")

        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="e", pady=(10, 0))
        open_button = ctk.CTkButton(
            actions,
            text="Open",
            command=lambda: self.app.open_history(record.id),
            width=58,
            height=26,
            corner_radius=7,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(9, "bold"),
        )
        open_button.pack(side="left", padx=(0, 5))
        delete_button = ctk.CTkButton(
            actions,
            text="✕",
            command=lambda: self._confirm_delete(record),
            width=28,
            height=26,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#2A121A",
            text_color=t.FAINT,
            font=t.ui_font(9),
        )
        delete_button.pack(side="left")

        self._attach_row_behaviour(
            row,
            record,
            exclude={
                open_button,
                delete_button,
                getattr(open_button, "_canvas", None),
                getattr(delete_button, "_canvas", None),
            },
        )

    def _thumbnail_for(self, record: ScanRecord) -> ctk.CTkImage | None:
        path = record.thumbnail_path
        image = None
        if path and Path(path).is_file():
            try:
                with Image.open(path) as opened:
                    image = opened.convert("RGB")
            except OSError:
                image = None
        if image is None and record.source_path and Path(record.source_path).is_file():
            try:
                with Image.open(record.source_path) as opened:
                    image = opened.convert("RGB")
            except OSError:
                image = None
        if image is None:
            image = self._placeholder_thumb(record.result.media_type)
        return ctk.CTkImage(light_image=image, dark_image=image, size=(120, 68))

    def _placeholder_thumb(self, media_type: str) -> Image.Image:
        canvas = Image.new("RGB", (240, 136), (20, 26, 36))
        draw = ImageDraw.Draw(canvas)
        color = t.accent_for(media_type).lstrip("#")
        rgb = tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))
        draw.ellipse((88, 36, 152, 100), outline=rgb, width=2)
        draw.ellipse((114, 62, 126, 74), fill=rgb)
        return canvas

    # ---- interaction -----------------------------------------------------

    def _attach_row_behaviour(self, row, record: ScanRecord, exclude: set) -> None:
        def cancel_pending_leave() -> None:
            if self._leave_after:
                try:
                    self.after_cancel(self._leave_after)
                except Exception:  # noqa: BLE001
                    pass
                self._leave_after = None

        def on_enter(_event=None):
            cancel_pending_leave()
            row.configure(fg_color=t.PANEL_HOVER, border_color="#2A3446")

        def on_leave(event):
            cancel_pending_leave()
            self._leave_after = self.after(
                70, lambda: self._check_leave(row, event.x_root, event.y_root)
            )

        def bind_tree(widget) -> None:
            if widget in exclude:
                return
            try:
                widget.bind("<Enter>", on_enter, add="+")
                widget.bind("<Leave>", on_leave, add="+")
                widget.bind("<Button-1>", lambda _e: self.app.open_history(record.id), add="+")
                if widget is not row:
                    widget.configure(cursor="hand2")
            except Exception:  # noqa: BLE001
                return
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(row)

    def _check_leave(self, row, x_root: int, y_root: int) -> None:
        if not self.winfo_exists() or not row.winfo_exists():
            return
        try:
            under = row.winfo_containing(x_root, y_root)
        except Exception:  # noqa: BLE001
            under = None
        if under is None or not self._is_descendant(under, row):
            row.configure(fg_color=t.PANEL, border_color=t.BORDER)

    @staticmethod
    def _is_descendant(widget, ancestor) -> bool:
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _confirm_delete(self, record: ScanRecord) -> None:
        ConfirmDialog(
            self.app,
            "Delete this scan?",
            f"“{record.title}” will be removed from your local history, along with its thumbnail.",
            confirm_label="Delete",
            on_confirm=lambda: self.app.delete_history(record.id, record.thumbnail_path),
        )

    def _confirm_clear(self) -> None:
        ConfirmDialog(
            self.app,
            "Clear scan history?",
            "This permanently removes every saved scan and thumbnail from this device.",
            confirm_label="Clear all",
            on_confirm=self.app.clear_history,
        )

    def destroy(self) -> None:
        if self._leave_after:
            try:
                self.after_cancel(self._leave_after)
            except Exception:  # noqa: BLE001
                pass
            self._leave_after = None
        super().destroy()

    def _build_empty(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=t.PANEL,
            corner_radius=16,
            border_width=1,
            border_color=t.BORDER,
        )
        panel.grid(row=1, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid(row=0, column=0)
        ctk.CTkLabel(
            body,
            text="◷",
            font=t.ui_font(34),
            text_color=t.BORDER,
        ).pack()
        ctk.CTkLabel(
            body,
            text="No scans yet",
            font=t.ui_font(19, "bold"),
            text_color=t.TEXT,
        ).pack(pady=(10, 4))
        ctk.CTkLabel(
            body,
            text="Every frame you identify is saved here, on this device only.",
            font=t.ui_font(11),
            text_color=t.MUTED,
        ).pack()
        ctk.CTkButton(
            body,
            text="Identify a frame",
            command=self.app.new_scan,
            width=150,
            height=36,
            corner_radius=8,
            fg_color=t.CYAN,
            hover_color="#5BF0FF",
            text_color="#06141A",
            font=t.ui_font(11, "bold"),
        ).pack(pady=(20, 0))

"""Small, reusable GUI pieces: badges, adaptive image panels, toasts, dialogs."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw

from ..utils.image_utils import fit_contain
from . import theme as t


class Badge(ctk.CTkLabel):
    """A compact status pill such as ``[ANIME]`` or ``S01E05``."""

    def __init__(
        self,
        master,
        text: str,
        *,
        text_color: str = t.CYAN,
        fg_color: str | None = None,
        border_color: str | None = None,
        font_size: int = 9,
        height: int = 24,
    ) -> None:
        super().__init__(
            master,
            text=f"  {text.upper()}  ",
            font=t.ui_font(font_size, "bold"),
            text_color=text_color,
            fg_color=fg_color or t.PANEL_ALT,
            corner_radius=7,
            height=height,
            border_width=1 if border_color else 0,
            border_color=border_color or text_color,
        )


class Divider(ctk.CTkFrame):
    def __init__(self, master, color: str = t.BORDER_SOFT, **kwargs):
        super().__init__(master, height=1, fg_color=color, corner_radius=0, **kwargs)


class SectionTitle(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text.upper(),
            font=t.ui_font(9, "bold"),
            text_color=t.FAINT,
            anchor="w",
            **kwargs,
        )


class ImagePanel(ctk.CTkFrame):
    """Framed, letterboxed image that re-fits itself when the window resizes."""

    def __init__(
        self,
        master,
        caption: str,
        accent: str = t.CYAN,
        placeholder: str = "NO IMAGE",
        height: int = 236,
    ) -> None:
        super().__init__(
            master,
            fg_color=t.PANEL,
            corner_radius=14,
            border_width=1,
            border_color=t.BORDER,
            height=height,
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Keep the requested frame height; otherwise the short header row and a
        # not-yet-rendered image label collapse the panel to ~70px.
        self.grid_propagate(False)

        header = ctk.CTkFrame(self, fg_color="transparent", height=30)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        header.grid_columnconfigure(1, weight=1)

        self._dot = ctk.CTkLabel(
            header,
            text="●",
            font=t.ui_font(8),
            text_color=accent,
            width=12,
        )
        self._dot.grid(row=0, column=0, padx=(0, 6))

        self._caption = ctk.CTkLabel(
            header,
            text=caption.upper(),
            font=t.ui_font(9, "bold"),
            text_color=t.MUTED,
            anchor="w",
        )
        self._caption.grid(row=0, column=1, sticky="w")

        self._tag = ctk.CTkLabel(
            header,
            text="",
            font=t.mono_font(9),
            text_color=t.FAINT,
            anchor="e",
        )
        self._tag.grid(row=0, column=2, sticky="e")

        self.image_label = ctk.CTkLabel(
            self,
            text=placeholder,
            font=t.ui_font(10),
            text_color=t.FAINT,
            fg_color="transparent",
            justify="center",
        )
        self.image_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 10))

        self._source: Image.Image | None = None
        self._placeholder = placeholder
        self._ctk_image: ctk.CTkImage | None = None
        self._render_after: str | None = None
        self._last_box: tuple[int, int] = (0, 0)

        self.image_label.bind("<Configure>", self._schedule_render)

    def set_image(self, image: Image.Image | None, placeholder: str | None = None) -> None:
        self._source = image
        if placeholder is not None:
            self._placeholder = placeholder
        # Force a repaint even when the box size is unchanged (e.g. clearing a
        # failed remote image back to its placeholder).
        self._last_box = (0, 0)
        self._render_now()

    def set_caption(self, text: str, accent: str | None = None) -> None:
        self._caption.configure(text=text.upper())
        if accent:
            self._dot.configure(text_color=accent)

    def set_tag(self, text: str) -> None:
        self._tag.configure(text=text)

    def _schedule_render(self, _event=None) -> None:
        if self._render_after:
            try:
                self.after_cancel(self._render_after)
            except Exception:  # noqa: BLE001
                pass
        self._render_after = self.after(110, self._render_now)

    def _render_now(self) -> None:
        self._render_after = None
        if not self.winfo_exists():
            return

        width = max(1, self.image_label.winfo_width() - 4)
        height = max(1, self.image_label.winfo_height() - 4)
        if width < 60 or height < 50:
            return
        box = (width, height)
        if box == self._last_box and self._ctk_image is not None:
            return

        if self._source is None:
            self.image_label.configure(image=None, text=self._placeholder)
            self._ctk_image = None
            self._last_box = box
            return

        framed = fit_contain(self._source, box, background=(17, 21, 30))
        rounded = Image.new("RGBA", box, (0, 0, 0, 0))
        mask = Image.new("L", box, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, box[0] - 1, box[1] - 1), radius=10, fill=255
        )
        rounded.paste(framed, (0, 0), mask)

        ctk_image = ctk.CTkImage(light_image=rounded, dark_image=rounded, size=box)
        self.image_label.configure(image=ctk_image, text="")
        self._ctk_image = ctk_image
        self._last_box = box


class ConfidenceMeter(ctk.CTkFrame):
    def __init__(self, master, value: float, accent: str = t.CYAN, threshold: float | None = None):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        SectionTitle(self, "Match confidence").grid(row=0, column=0, sticky="w")

        percent = min(99, max(0, round(value * 100)))
        self._value = ctk.CTkLabel(
            self,
            text=f"{percent}%",
            font=t.ui_font(32, "bold"),
            text_color=accent,
            anchor="w",
        )
        self._value.grid(row=1, column=0, sticky="w", pady=(2, 8))

        self._bar = ctk.CTkProgressBar(
            self,
            height=7,
            corner_radius=4,
            progress_color=accent,
            fg_color="#1B2130",
        )
        self._bar.set(max(0.0, min(1.0, value)))
        self._bar.grid(row=2, column=0, sticky="ew")

        if value >= 0.85:
            band, band_color = "High confidence", accent
        elif value >= 0.6:
            band, band_color = "Medium confidence", t.AMBER
        else:
            band, band_color = "Low confidence", t.RED

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text=band.upper(),
            font=t.ui_font(9, "bold"),
            text_color=band_color,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if threshold is not None:
            ctk.CTkLabel(
                footer,
                text=f"threshold {round(threshold * 100)}%",
                font=t.mono_font(9),
                text_color=t.FAINT,
                anchor="e",
            ).grid(row=0, column=1, sticky="e")


class MetricRow(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self,
            text=label,
            font=t.ui_font(11),
            text_color=t.MUTED,
            anchor="w",
            width=88,
        ).grid(row=0, column=0, sticky="w", pady=5)
        ctk.CTkLabel(
            self,
            text=value,
            font=t.ui_font(11, "bold"),
            text_color=t.TEXT,
            anchor="e",
            justify="right",
            wraplength=180,
        ).grid(row=0, column=1, sticky="e", pady=5)


class ToastHost:
    """Single bottom-right notification with an optional action button."""

    def __init__(self, root) -> None:
        self.root = root
        self._frame: ctk.CTkFrame | None = None
        self._timer: str | None = None

    def show(
        self,
        message: str,
        *,
        kind: str = "info",
        action_label: str | None = None,
        action: Callable[[], None] | None = None,
        duration: int = 4600,
    ) -> None:
        try:
            self._dismiss()
        except Exception:  # noqa: BLE001
            pass

        color = {
            "info": t.CYAN,
            "success": t.GREEN,
            "warning": t.AMBER,
            "error": t.RED,
        }.get(kind, t.CYAN)

        frame = ctk.CTkFrame(
            self.root,
            fg_color=t.PANEL_ALT,
            corner_radius=12,
            border_width=1,
            border_color=t.BORDER,
        )
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="●", font=t.ui_font(9), text_color=color, width=14).grid(
            row=0, column=0, padx=(14, 4), pady=13, sticky="n"
        )
        ctk.CTkLabel(
            frame,
            text=message,
            font=t.ui_font(11),
            text_color=t.TEXT,
            justify="left",
            wraplength=330,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=12)

        if action_label and action:
            ctk.CTkButton(
                frame,
                text=action_label,
                command=lambda: (self._dismiss(), action()),
                width=76,
                height=26,
                corner_radius=7,
                fg_color=color,
                hover_color=color,
                text_color="#08121A",
                font=t.ui_font(10, "bold"),
            ).grid(row=0, column=2, padx=(8, 4))

        ctk.CTkButton(
            frame,
            text="✕",
            command=self._dismiss,
            width=22,
            height=22,
            corner_radius=6,
            fg_color="transparent",
            hover_color=t.BORDER,
            text_color=t.FAINT,
            font=t.ui_font(10),
        ).grid(row=0, column=3, padx=(2, 8), pady=10)

        frame.place(relx=1.0, rely=1.0, x=-26, y=-26, anchor="se")
        frame.lift()
        self._frame = frame
        if duration > 0:
            self._timer = self.root.after(duration, self._dismiss)

    def _dismiss(self) -> None:
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:  # noqa: BLE001
                pass
            self._timer = None
        if self._frame is not None:
            try:
                self._frame.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._frame = None


class ConfirmDialog(ctk.CTkToplevel):
    """Dark confirmation modal used for destructive history actions."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        *,
        confirm_label: str = "Delete",
        danger: bool = True,
        on_confirm: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, fg_color=t.BG)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self._on_confirm = on_confirm

        self.grid_columnconfigure(0, weight=1)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=24, pady=(22, 16))
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text=title,
            font=t.ui_font(17, "bold"),
            text_color=t.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text=message,
            font=t.ui_font(11),
            text_color=t.MUTED,
            justify="left",
            wraplength=380,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(10, 22))

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="e")
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=self.destroy,
            width=88,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.BORDER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.MUTED,
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            buttons,
            text=confirm_label,
            command=self._confirm,
            width=104,
            height=34,
            corner_radius=8,
            fg_color=t.RED if danger else t.CYAN,
            hover_color="#FF7C93" if danger else "#5BF0FF",
            text_color="#0C0F16",
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        self.geometry(f"440x{max(210, self.winfo_reqheight())}")
        self._center(parent)
        self.after(60, self.grab_set)
        self.after(80, self.focus_force)

    def _center(self, parent) -> None:
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - 440) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass

    def _confirm(self) -> None:
        callback = self._on_confirm
        self.destroy()
        if callback:
            callback()

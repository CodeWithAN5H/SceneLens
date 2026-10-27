"""GUI theme helpers built on the shared palette."""

from __future__ import annotations

import customtkinter as ctk

from .. import theme as palette

# Convenience aliases used throughout the GUI.
BG = palette.BG
SIDEBAR = palette.SIDEBAR
PANEL = palette.PANEL
PANEL_ALT = palette.PANEL_ALT
PANEL_HOVER = palette.PANEL_HOVER
BORDER = palette.BORDER
BORDER_SOFT = palette.BORDER_SOFT
TEXT = palette.TEXT
MUTED = palette.TEXT_MUTED
FAINT = palette.TEXT_FAINT
CYAN = palette.CYAN
CYAN_SOFT = palette.CYAN_SOFT
VIOLET = palette.VIOLET
VIOLET_SOFT = palette.VIOLET_SOFT
AMBER = palette.AMBER
AMBER_SOFT = palette.AMBER_SOFT
GREEN = palette.GREEN
GREEN_SOFT = palette.GREEN_SOFT
RED = palette.RED


def setup() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


def ui_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=palette.UI_FONT, size=size, weight=weight)


def mono_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=palette.MONO_FONT, size=size, weight=weight)


def accent_for(media_type: str) -> str:
    return palette.TYPE_ACCENTS.get(media_type, CYAN)


def soft_for(media_type: str) -> str:
    return palette.TYPE_SOFT.get(media_type, PANEL_ALT)

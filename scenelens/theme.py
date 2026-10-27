"""Shared palette and type accents.

Kept free of GUI imports so the Discord card renderer (Pillow) can reuse the
exact same colors as the application.
"""

from __future__ import annotations

# Surfaces
BG = "#0F1117"
SIDEBAR = "#0B0E14"
PANEL = "#11151E"
PANEL_ALT = "#141A24"
PANEL_HOVER = "#182030"
BORDER = "#1F2430"
BORDER_SOFT = "#171C27"

# Type
TEXT = "#E9EEF7"
TEXT_MUTED = "#8B94A7"
TEXT_FAINT = "#5B6478"

# Accents
CYAN = "#00E5FF"
CYAN_DIM = "#0E7C8C"
CYAN_SOFT = "#082329"
VIOLET = "#7C4DFF"
VIOLET_SOFT = "#1B1435"
AMBER = "#FFB74D"
AMBER_SOFT = "#2A2114"
GREEN = "#3DDC97"
GREEN_SOFT = "#0C2721"
RED = "#FF5C7A"

TYPE_ACCENTS = {
    "anime": CYAN,
    "movie": AMBER,
    "tv": GREEN,
    "game": VIOLET,
}

TYPE_SOFT = {
    "anime": CYAN_SOFT,
    "movie": AMBER_SOFT,
    "tv": GREEN_SOFT,
    "game": VIOLET_SOFT,
}

UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"

# RGB tuples for Pillow.
RGB = {
    "bg": (15, 17, 23),
    "sidebar": (11, 14, 20),
    "panel": (17, 21, 30),
    "panel_alt": (20, 26, 36),
    "border": (31, 36, 48),
    "text": (233, 238, 247),
    "muted": (139, 148, 167),
    "faint": (91, 100, 120),
    "cyan": (0, 229, 255),
    "violet": (124, 77, 255),
    "amber": (255, 183, 77),
    "green": (61, 220, 151),
    "red": (255, 92, 122),
    "white": (255, 255, 255),
}

TYPE_RGB = {
    "anime": RGB["cyan"],
    "movie": RGB["amber"],
    "tv": RGB["green"],
    "game": RGB["violet"],
}

TYPE_RGB_SOFT = {
    "anime": (8, 35, 41),
    "movie": (42, 33, 20),
    "tv": (12, 39, 33),
    "game": (27, 20, 53),
}

TYPE_LABELS = {
    "anime": "ANIME",
    "movie": "MOVIE",
    "tv": "TV SERIES",
    "game": "GAME",
}

"""Programmatic lens branding, so the app ships without binary assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ..config import BASE_DIR
from ..theme import RGB

ICON_PATH = BASE_DIR / "assets" / "icon.png"


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def lens_icon(
    size: int = 96,
    color: tuple[int, int, int] = RGB["cyan"],
    with_glow: bool = True,
) -> Image.Image:
    """Anti-aliased lens/crosshair mark on transparency."""
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    center = canvas / 2
    radius = canvas * 0.33

    if with_glow:
        glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse(
            (center - radius * 1.15, center - radius * 1.15, center + radius * 1.15, center + radius * 1.15),
            fill=color + (80,),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(canvas * 0.06))
        image = Image.alpha_composite(image, glow)

    draw = ImageDraw.Draw(image)
    stroke = max(2, int(canvas * 0.016))
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=color + (235,),
        width=stroke,
    )
    inner = radius * 0.46
    draw.ellipse(
        (center - inner, center - inner, center + inner, center + inner),
        outline=color + (150,),
        width=max(1, stroke // 2),
    )
    dot = canvas * 0.035
    draw.ellipse((center - dot, center - dot, center + dot, center + dot), fill=color + (255,))

    tick_start = radius * 1.16
    tick_end = radius * 1.42
    tick_width = max(1, int(canvas * 0.009))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        draw.line(
            (
                center + dx * tick_start,
                center + dy * tick_start,
                center + dx * tick_end,
                center + dy * tick_end,
            ),
            fill=color + (140,),
            width=tick_width,
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def app_icon(size: int = 256) -> Image.Image:
    """Square app icon: dark rounded tile with the cyan lens mark."""
    canvas = size * 2
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1),
        radius=int(canvas * 0.22),
        fill=_hex("#0B0E14") + (255,),
        outline=_hex("#1F2430") + (255,),
        width=int(canvas * 0.012),
    )
    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (canvas * 0.18, canvas * 0.12, canvas * 0.82, canvas * 0.76),
        fill=RGB["cyan"] + (46,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(canvas * 0.12))
    image = Image.alpha_composite(image, glow)

    mark = lens_icon(int(canvas * 0.64), with_glow=False)
    offset = (canvas - mark.width) // 2
    image.alpha_composite(mark, (offset, offset))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def ensure_icon_asset() -> Path | None:
    """Write ``assets/icon.png`` once so the window can use a real icon."""
    try:
        if not ICON_PATH.exists():
            ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
            app_icon(256).save(ICON_PATH, format="PNG")
        return ICON_PATH
    except OSError:
        return None

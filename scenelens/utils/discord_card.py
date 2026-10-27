"""Shareable result cards.

Two outputs are produced from the same data:

* Discord-flavored markdown for instant pasting into chat.
* A rendered PNG summary card (1080x660) with both compared frames.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .. import theme
from ..config import EXPORT_DIR
from ..models import MediaResult

CARD_SIZE = (1080, 660)
PAD = 88

_FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "semibold": [
        "C:/Windows/Fonts/seguisb.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "regular": [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "mono": [
        "C:/Windows/Fonts/consola.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ],
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key in _font_cache:
        return _font_cache[key]
    for candidate in _FONT_CANDIDATES.get(weight, []):
        try:
            font = ImageFont.truetype(candidate, size)
            _font_cache[key] = font
            return font
        except OSError:
            continue
    font = ImageFont.load_default(size=size)
    _font_cache[key] = font
    return font


# ---------------------------------------------------------------------------
# Discord markdown
# ---------------------------------------------------------------------------


def build_discord_markdown(result: MediaResult) -> str:
    """Compact, Discord-safe markdown summary (always below 2000 chars)."""
    lines: list[str] = [f"**SceneLens**  `[{result.tag}]`", f"### {result.title}"]

    meta_parts = [str(result.year)] if result.year else []
    if result.studio:
        meta_parts.append(result.studio)
    if meta_parts:
        lines.append(" · ".join(meta_parts))

    scene_parts: list[str] = []
    if result.episode_code:
        scene_parts.append(result.episode_code)
    if result.timestamp:
        scene_parts.append(f"at {result.timestamp}")
    if result.level:
        scene_parts.append(result.level)
    if scene_parts:
        lines.append("  ·  ".join(scene_parts))

    filled = min(10, max(1, round(result.confidence * 10)))
    bar = "▰" * filled + "▱" * (10 - filled)
    lines.append(f"**Match** {result.confidence_pct}%  `{bar}`")
    lines.append(f"> Identified from a single frame with {result.source}")
    if result.external_url:
        lines.append(result.external_url)

    markdown = "\n".join(lines)
    if len(markdown) > 1900:
        markdown = markdown[:1890].rstrip() + "…"
    return markdown


# ---------------------------------------------------------------------------
# Rendered PNG card
# ---------------------------------------------------------------------------


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = text[:middle].rstrip() + ellipsis
        if draw.textlength(candidate, font=font) <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ellipsis


def _rounded_image(image: Image.Image, size: tuple[int, int], radius: int = 14) -> Image.Image:
    fitted = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(fitted, (0, 0), mask)
    return result


def _draw_spaced(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    spacing: int = 2,
) -> None:
    x, y = origin
    for character in text:
        draw.text((x, y), character, font=font, fill=fill)
        x += int(draw.textlength(character, font=font)) + spacing


def _placeholder(size: tuple[int, int], label: str) -> Image.Image:
    canvas = Image.new("RGB", size, theme.RGB["panel_alt"])
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1),
        radius=14,
        outline=theme.RGB["border"],
        width=1,
    )
    draw.text(
        (size[0] // 2, size[1] // 2),
        label,
        font=_font("regular", 14),
        fill=theme.RGB["faint"],
        anchor="mm",
    )
    return canvas


def _paste_panel(
    card: Image.Image,
    image: Image.Image | None,
    box: tuple[int, int, int, int],
    label: str,
    empty_label: str,
) -> None:
    x, y, width, height = box
    draw = ImageDraw.Draw(card)
    draw.text(
        (x, y - 20),
        label,
        font=_font("semibold", 11),
        fill=theme.RGB["faint"],
    )
    if image is None:
        panel = _placeholder((width, height), empty_label)
    else:
        panel = _rounded_image(image, (width, height))
    if panel.mode == "RGBA":
        card.paste(panel, (x, y), panel)
    else:
        card.paste(panel, (x, y))


def render_share_card(
    result: MediaResult,
    own_image: Image.Image | None,
    matched_image: Image.Image | None,
    output_path: Path | None = None,
) -> Path:
    """Compose the dark summary card and return the written PNG path."""
    width, height = CARD_SIZE
    accent = theme.TYPE_RGB.get(result.media_type, theme.RGB["cyan"])
    soft = theme.TYPE_RGB_SOFT.get(result.media_type, theme.RGB["panel_alt"])

    card = Image.new("RGB", CARD_SIZE, theme.RGB["bg"])

    # Soft, low-opacity accent glow in two corners for depth.
    glow = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-260, -300, 620, 420), fill=accent + (52,))
    glow_draw.ellipse((700, -360, 1320, 260), fill=theme.RGB["violet"] + (34,))
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    card = Image.alpha_composite(card.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (1, 1, width - 2, height - 2),
        radius=26,
        outline=theme.RGB["border"],
        width=2,
    )

    # Top accent hairline, fading from cyan into violet.
    line = Image.new("RGB", (width - PAD * 2, 3), theme.RGB["panel"])
    line_draw = ImageDraw.Draw(line)
    for index in range(line.width):
        ratio = index / max(1, line.width - 1)
        color = tuple(
            round(accent[channel] * (1 - ratio) + theme.RGB["violet"][channel] * ratio)
            for channel in range(3)
        )
        line_draw.line((index, 0, index, 3), fill=color)
    card.paste(line, (PAD, 22))
    draw = ImageDraw.Draw(card)

    # Header: brand + tiny lens glyph.
    lens_center = (PAD + 9, 56)
    draw.ellipse(
        (lens_center[0] - 9, lens_center[1] - 9, lens_center[0] + 9, lens_center[1] + 9),
        outline=accent,
        width=2,
    )
    draw.ellipse(
        (lens_center[0] - 3, lens_center[1] - 3, lens_center[0] + 3, lens_center[1] + 3),
        fill=accent,
    )
    _draw_spaced(draw, (PAD + 30, 45), "SCENELENS", _font("bold", 16), theme.RGB["text"], 3)
    draw.text(
        (PAD + 30, 67),
        "SCENE IDENTIFIED",
        font=_font("regular", 10),
        fill=theme.RGB["faint"],
    )

    # Type badge, right aligned.
    badge_text = result.tag
    badge_font = _font("semibold", 13)
    badge_width = int(draw.textlength(badge_text, font=badge_font)) + 30
    badge_top = 38
    draw.rounded_rectangle(
        (width - PAD - badge_width, badge_top, width - PAD, badge_top + 30),
        radius=8,
        fill=soft,
        outline=accent,
        width=1,
    )
    draw.text(
        (width - PAD - badge_width / 2, badge_top + 15),
        badge_text,
        font=badge_font,
        fill=accent,
        anchor="mm",
    )

    # Compared frames.
    frame_size = (442, 248)
    _paste_panel(
        card,
        own_image,
        (PAD, 128, frame_size[0], frame_size[1]),
        "YOUR FRAME",
        "UPLOADED FRAME",
    )
    _paste_panel(
        card,
        matched_image,
        (PAD + frame_size[0] + 20, 128, frame_size[0], frame_size[1]),
        "BEST MATCH",
        "NO REFERENCE FRAME",
    )
    draw = ImageDraw.Draw(card)

    # Title and metadata.
    title_font = _font("bold", 36)
    title = _ellipsize(draw, result.title, title_font, width - PAD * 2)
    draw.text((PAD, 388), title, font=title_font, fill=theme.RGB["text"])

    meta_font = _font("regular", 18)
    meta = "  ·  ".join(part for part in (str(result.year) if result.year else "", result.studio or "") if part)
    if meta:
        draw.text((PAD, 438), _ellipsize(draw, meta, meta_font, 760), font=meta_font, fill=theme.RGB["muted"])

    scene_parts = []
    if result.episode_code:
        scene_parts.append(result.episode_code)
    if result.timestamp:
        scene_parts.append(result.timestamp)
    if result.level:
        scene_parts.append(result.level)
    if scene_parts:
        scene_font = _font("semibold", 16)
        draw.text(
            (PAD, 468),
            _ellipsize(draw, "  ·  ".join(scene_parts), scene_font, 880),
            font=scene_font,
            fill=accent,
        )

    # Confidence block.
    draw.text(
        (PAD, 522),
        "MATCH CONFIDENCE",
        font=_font("regular", 10),
        fill=theme.RGB["faint"],
    )
    confidence_font = _font("bold", 26)
    draw.text((PAD, 538), f"{result.confidence_pct}%", font=confidence_font, fill=accent)
    percent_width = draw.textlength(f"{result.confidence_pct}%", font=confidence_font)

    bar_left = PAD + int(percent_width) + 22
    bar_right = width - PAD
    bar_y = 551
    draw.rounded_rectangle(
        (bar_left, bar_y, bar_right, bar_y + 10),
        radius=5,
        fill=theme.RGB["panel_alt"],
    )
    filled_right = bar_left + int((bar_right - bar_left) * min(1.0, result.confidence))
    if filled_right > bar_left:
        draw.rounded_rectangle(
            (bar_left, bar_y, max(filled_right, bar_left + 10), bar_y + 10),
            radius=5,
            fill=accent,
        )

    # Footer.
    draw.line((PAD, 602, width - PAD, 602), fill=theme.RGB["border"], width=1)
    footer_font = _font("regular", 11)
    draw.text(
        (PAD, 618),
        f"IDENTIFIED WITH {result.source.upper()}",
        font=footer_font,
        fill=theme.RGB["faint"],
    )
    footer_right = "SCENELENS · DESKTOP"
    draw.text(
        (width - PAD - draw.textlength(footer_right, font=footer_font), 618),
        footer_right,
        font=footer_font,
        fill=theme.RGB["faint"],
    )

    if output_path is None:
        slug = re.sub(r"[^a-z0-9]+", "-", result.title.lower()).strip("-")[:40] or "scene"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = EXPORT_DIR / f"scenelens-{slug}-{stamp}.png"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.save(output_path, format="PNG", optimize=True)
    return output_path


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    return _hex(value)

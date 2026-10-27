"""Image loading, API preparation and thumbnail helpers.

All recognition engines receive a :class:`PreparedImage`: a normalized RGB
Pillow image plus a JPEG copy small enough for upload (trace.moe caps uploads at
10 MB and vision APIs charge by pixel count).
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from ..config import THUMB_DIR

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 30 * 1024 * 1024
API_MAX_SIDE = 1280
API_JPEG_QUALITY = 88


class ImageInputError(Exception):
    """Raised when a dropped file cannot be used as a scene image."""


@dataclass
class PreparedImage:
    """A normalized image ready for local display and upload."""

    image: Image.Image
    jpeg_bytes: bytes
    filename: str = "scene.jpg"

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.jpeg_bytes).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.jpeg_bytes).hexdigest()

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


def load_image(source: Path | str | bytes | Image.Image) -> Image.Image:
    """Open and normalize an image from a path, raw bytes or a PIL image."""
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        elif isinstance(source, (bytes, bytearray)):
            image = Image.open(io.BytesIO(bytes(source)))
        else:
            path = Path(source)
            if not path.is_file():
                raise ImageInputError("That file no longer exists.")
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ImageInputError(
                    f"Unsupported format '{path.suffix or 'unknown'}'. Use PNG, JPG or WEBP."
                )
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ImageInputError("That image is larger than 30 MB.")
            with Image.open(path) as opened:
                image = opened.copy()

        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA", "P"}:
            # Flatten transparency against the app background instead of black.
            rgba = image.convert("RGBA")
            backdrop = Image.new("RGBA", rgba.size, (15, 17, 23, 255))
            image = Image.alpha_composite(backdrop, rgba)
        return image.convert("RGB")
    except ImageInputError:
        raise
    except (OSError, ValueError) as error:
        raise ImageInputError("That file could not be read as an image.") from error


def encode_for_api(
    image: Image.Image,
    max_side: int = API_MAX_SIDE,
    quality: int = API_JPEG_QUALITY,
) -> bytes:
    """Resize proportionally and encode as JPEG for upload."""
    working = image.copy()
    if max(working.size) > max_side:
        working.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    working.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def prepare_image(
    source: Path | str | bytes | Image.Image,
    max_side: int = API_MAX_SIDE,
) -> PreparedImage:
    image = load_image(source)
    return PreparedImage(image=image, jpeg_bytes=encode_for_api(image, max_side=max_side))


def image_signature(image: Image.Image) -> str:
    """Small perceptual-ish fingerprint used to deduplicate clipboard content."""
    sample = image.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
    return hashlib.sha1(sample.tobytes()).hexdigest()


def fit_contain(
    image: Image.Image,
    size: tuple[int, int],
    background: tuple[int, int, int] = (17, 21, 30),
) -> Image.Image:
    """Letterbox an image into an exact box without distorting it."""
    canvas = Image.new("RGB", size, background)
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    offset = ((size[0] - copy.width) // 2, (size[1] - copy.height) // 2)
    canvas.paste(copy, offset)
    return canvas


def save_history_thumbnail(image: Image.Image, key: str) -> str:
    """Persist a small JPEG thumbnail and return its absolute path."""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    target = THUMB_DIR / f"{key[:20]}.jpg"
    thumbnail = image.copy()
    thumbnail.thumbnail((480, 270), Image.Resampling.LANCZOS)
    thumbnail.save(target, format="JPEG", quality=84, optimize=True)
    return str(target)


def save_png(image: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
    return path

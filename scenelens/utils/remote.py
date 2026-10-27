"""Disk-cached downloads for reference frames and posters."""

from __future__ import annotations

import hashlib
import io
import threading
from pathlib import Path

import httpx
from PIL import Image

from ..config import IMAGE_CACHE_DIR, USER_AGENT

_lock = threading.Lock()


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return IMAGE_CACHE_DIR / f"{digest}.jpg"


def fetch_remote_image(url: str | None, timeout: float = 20.0) -> Image.Image | None:
    """Download an image once, then serve it from the local cache.

    Safe to call from worker threads. Returns ``None`` on any failure so the UI
    can simply keep using a placeholder.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return None

    path = _cache_path(url)
    with _lock:
        if path.exists() and path.stat().st_size > 0:
            try:
                with Image.open(path) as cached:
                    return cached.convert("RGB")
            except OSError:
                path.unlink(missing_ok=True)

    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as downloaded:
            image = downloaded.convert("RGB")
        temporary = path.with_suffix(".tmp")
        image.save(temporary, format="JPEG", quality=90)
        temporary.replace(path)
        return image
    except (httpx.HTTPError, OSError, ValueError):
        return None

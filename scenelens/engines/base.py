"""Engine primitives and the single candidate-normalization path."""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlparse

from ..models import (
    MediaResult,
    clamp_confidence,
    format_timestamp,
    normalize_media_type,
)
from ..models import build_search_links
from ..utils.image_utils import PreparedImage

ProgressCallback = Callable[[str], None]


class EngineError(Exception):
    """A recoverable identification-engine failure shown in the scan report."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


def safe_url(value: Any) -> str | None:
    """Only keep absolute http(s) URLs that a browser can actually open."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None


def _as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _as_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 1900 <= int(value) <= 2100:
        return int(value)
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group()) if match else None


def _as_small_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def normalize_candidate(
    raw: dict[str, Any],
    source: str,
    *,
    default_type: str | None = None,
) -> MediaResult | None:
    """Convert one engine-specific candidate into a :class:`MediaResult`.

    Accepts vision-model JSON and canonical dicts, so a new engine can simply
    produce this shape without touching the UI.
    """
    if not isinstance(raw, dict):
        return None

    title = _as_text(raw.get("title")) or _as_text(raw.get("name"))
    if not title:
        return None

    media_type = normalize_media_type(raw.get("media_type"), default_type)
    if media_type is None and default_type is not None:
        media_type = default_type
    if media_type is None:
        return None

    year = _as_year(raw.get("year")) or _as_year(raw.get("release_date"))
    studio = _as_text(raw.get("studio")) or _as_text(raw.get("developer"))
    if not studio:
        studios = raw.get("production_companies") or []
        if isinstance(studios, list) and studios:
            first = studios[0]
            studio = _as_text(first.get("name")) if isinstance(first, dict) else _as_text(first)

    timestamp = raw.get("timestamp")
    timestamp_seconds: float | None = None
    if isinstance(timestamp, (int, float)):
        timestamp_seconds = float(timestamp)
        timestamp = format_timestamp(timestamp_seconds)
    else:
        timestamp = _as_text(timestamp)
        if timestamp and re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", timestamp):
            parts = [int(part) for part in timestamp.split(":")]
            timestamp_seconds = float(sum(value * 60**index for index, value in enumerate(reversed(parts))))
        elif timestamp and re.fullmatch(r"\d+(?:\.\d+)?", timestamp):
            timestamp_seconds = float(timestamp)
            timestamp = format_timestamp(timestamp_seconds)

    if timestamp is None and isinstance(raw.get("from"), (int, float)):
        timestamp_seconds = float(raw["from"])
        timestamp = format_timestamp(timestamp_seconds)

    confidence = clamp_confidence(raw.get("confidence"), 0.5)
    links = dict(raw.get("links") or {})
    if not links:
        links = build_search_links(media_type, title, year)

    alt_titles: list[str] = []
    for item in raw.get("alternative_titles") or raw.get("alt_titles") or []:
        text = _as_text(item)
        if text and text != title and text not in alt_titles:
            alt_titles.append(text)

    evidence = _as_text(raw.get("evidence")) or _as_text(raw.get("reason"))
    synopsis = _as_text(raw.get("synopsis")) or _as_text(raw.get("overview"))

    return MediaResult(
        media_type=media_type,
        title=title,
        confidence=confidence,
        source=source,
        year=year,
        studio=studio,
        season=_as_small_int(raw.get("season")),
        episode=_as_small_int(raw.get("episode")),
        timestamp=timestamp,
        timestamp_seconds=timestamp_seconds,
        level=_as_text(raw.get("level")) or _as_text(raw.get("level_or_mission")),
        synopsis=synopsis,
        evidence=evidence,
        cover_url=safe_url(raw.get("cover_url")) or safe_url(raw.get("poster")),
        matched_frame_url=safe_url(raw.get("matched_frame_url")),
        preview_video_url=safe_url(raw.get("preview_video_url")),
        external_url=safe_url(raw.get("external_url")) or safe_url(raw.get("url")),
        alt_titles=alt_titles[:3],
        links={str(key): str(value) for key, value in links.items() if safe_url(value)},
    )


def prepare_for_scan(image: Any) -> PreparedImage:
    """Local import keeps the heavy PIL path out of type-check-only consumers."""
    from ..utils.image_utils import prepare_image

    return prepare_image(image)

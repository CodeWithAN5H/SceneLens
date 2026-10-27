"""The single normalized data model every engine speaks.

Recognition engines return wildly different payloads (trace.moe scene diffs,
vision-model JSON, metadata providers).  They all funnel into :class:`MediaResult`
so the UI, the Discord card and the history database only ever deal with one
shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

MEDIA_TYPES = ("anime", "movie", "tv", "game")

MEDIA_LABELS = {
    "anime": "ANIME",
    "movie": "MOVIE",
    "tv": "TV SERIES",
    "game": "GAME",
}

_MEDIA_ALIASES = {
    "anime": "anime",
    "animation": "anime",
    "animated": "anime",
    "movie": "movie",
    "film": "movie",
    "cinema": "movie",
    "tv": "tv",
    "tv series": "tv",
    "tv show": "tv",
    "series": "tv",
    "show": "tv",
    "television": "tv",
    "game": "game",
    "video game": "game",
    "videogame": "game",
    "gaming": "game",
}


def normalize_media_type(value: Any, default: str | None = None) -> str | None:
    if not isinstance(value, str):
        return default
    return _MEDIA_ALIASES.get(value.strip().lower(), default)


def clamp_confidence(value: Any, default: float = 0.5) -> float:
    """Accept 0..1 or 0..100 confidence values and clamp into 0..1."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0:
        number = number / 100.0
    return min(1.0, max(0.0, number))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _clean_text(value: Any, limit: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def format_timestamp(seconds: float | int | None) -> str | None:
    """Turn a second offset into a scene timestamp such as ``00:04:12``."""
    if seconds is None:
        return None
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_search_links(
    media_type: str,
    title: str,
    year: int | None = None,
) -> dict[str, str]:
    """Quick external lookups shown on the result card and in fallbacks."""
    if not title:
        return {}

    query = quote_plus(title)
    query_with_year = quote_plus(f"{title} {year}" if year else title)
    links: dict[str, str] = {"Google": f"https://www.google.com/search?q={query_with_year}"}

    if media_type == "anime":
        links["MyAnimeList"] = f"https://myanimelist.net/anime.php?q={query}"
        links["AniList"] = f"https://anilist.co/search/anime?search={query}"
    elif media_type == "game":
        links["IGDB"] = f"https://www.igdb.com/search?q={query}"
        links["Steam"] = f"https://store.steampowered.com/search/?term={query}"
    else:
        links["IMDb"] = f"https://www.imdb.com/find/?q={query_with_year}&s=tt"
        links["TMDB"] = f"https://www.themoviedb.org/search?query={query}"
    return links


@dataclass
class MatchCandidate:
    """A weaker alternative kept around for the low-confidence fallback view."""

    title: str
    media_type: str
    confidence: float = 0.0
    year: int | None = None
    note: str | None = None
    links: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return MEDIA_LABELS.get(self.media_type, self.media_type.upper())

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "media_type": self.media_type,
            "confidence": self.confidence,
            "year": self.year,
            "note": self.note,
            "links": dict(self.links),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchCandidate":
        return cls(
            title=str(data.get("title") or "Unknown"),
            media_type=normalize_media_type(data.get("media_type"), "movie") or "movie",
            confidence=clamp_confidence(data.get("confidence"), 0.0),
            year=_as_int(data.get("year")),
            note=_clean_text(data.get("note")),
            links=dict(data.get("links") or {}),
        )


@dataclass
class MediaResult:
    """Normalized identification result shared by all engines."""

    media_type: str
    title: str
    confidence: float
    source: str

    year: int | None = None
    studio: str | None = None
    season: int | None = None
    episode: int | None = None
    timestamp: str | None = None
    timestamp_seconds: float | None = None
    level: str | None = None
    synopsis: str | None = None
    evidence: str | None = None

    cover_url: str | None = None
    matched_frame_url: str | None = None
    preview_video_url: str | None = None
    external_url: str | None = None
    alt_titles: list[str] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    candidates: list[MatchCandidate] = field(default_factory=list)

    # ---- presentation helpers -------------------------------------------

    @property
    def tag(self) -> str:
        return MEDIA_LABELS.get(self.media_type, self.media_type.upper())

    @property
    def confidence_pct(self) -> int:
        return min(99, max(0, round(self.confidence * 100)))

    @property
    def confidence_band(self) -> str:
        if self.confidence >= 0.85:
            return "high"
        if self.confidence >= 0.6:
            return "medium"
        return "low"

    @property
    def confidence_label(self) -> str:
        if self.source == "trace.moe":
            return f"{self.confidence_pct}% frame similarity"
        return f"{self.confidence_pct}% confidence"

    @property
    def subtitle(self) -> str:
        parts: list[str] = []
        if self.year:
            parts.append(str(self.year))
        if self.studio:
            parts.append(self.studio)
        if not parts:
            parts.append(MEDIA_LABELS.get(self.media_type, self.media_type.title()))
        return "  ·  ".join(parts)

    @property
    def episode_code(self) -> str | None:
        if self.season and self.episode:
            return f"S{self.season:02d}E{self.episode:02d}"
        if self.episode:
            return f"Episode {self.episode}"
        return None

    def detail_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        if self.season:
            rows.append(("Season", f"{self.season}"))
        if self.episode:
            rows.append(("Episode", f"{self.episode}"))
        if self.timestamp:
            rows.append(("Timestamp", self.timestamp))
        if self.level:
            rows.append(("Level / Mission", self.level))
        if self.studio:
            rows.append(("Studio / Dev", self.studio))
        if self.year:
            rows.append(("Released", str(self.year)))
        rows.append(("Engine", self.source))
        return rows

    @property
    def search_links(self) -> dict[str, str]:
        if self.links:
            return self.links
        return build_search_links(self.media_type, self.title, self.year)

    @property
    def dedupe_key(self) -> tuple[str, str]:
        normalized = re.sub(r"[^a-z0-9]+", "", self.title.lower())
        return (self.media_type, normalized)

    # ---- persistence -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_type": self.media_type,
            "title": self.title,
            "confidence": self.confidence,
            "source": self.source,
            "year": self.year,
            "studio": self.studio,
            "season": self.season,
            "episode": self.episode,
            "timestamp": self.timestamp,
            "timestamp_seconds": self.timestamp_seconds,
            "level": self.level,
            "synopsis": self.synopsis,
            "evidence": self.evidence,
            "cover_url": self.cover_url,
            "matched_frame_url": self.matched_frame_url,
            "preview_video_url": self.preview_video_url,
            "external_url": self.external_url,
            "alt_titles": list(self.alt_titles),
            "links": dict(self.links),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaResult":
        if not isinstance(data, dict):
            raise ValueError("result payload must be an object")
        media_type = normalize_media_type(data.get("media_type"), "movie") or "movie"
        return cls(
            media_type=media_type,
            title=str(data.get("title") or "Unknown"),
            confidence=clamp_confidence(data.get("confidence"), 0.5),
            source=str(data.get("source") or "unknown"),
            year=_as_int(data.get("year")),
            studio=_clean_text(data.get("studio")),
            season=_as_int(data.get("season")),
            episode=_as_int(data.get("episode")),
            timestamp=_clean_text(data.get("timestamp")),
            timestamp_seconds=(
                float(data["timestamp_seconds"])
                if isinstance(data.get("timestamp_seconds"), (int, float))
                else None
            ),
            level=_clean_text(data.get("level")),
            synopsis=_clean_text(data.get("synopsis"), 700),
            evidence=_clean_text(data.get("evidence"), 400),
            cover_url=_clean_text(data.get("cover_url")),
            matched_frame_url=_clean_text(data.get("matched_frame_url")),
            preview_video_url=_clean_text(data.get("preview_video_url")),
            external_url=_clean_text(data.get("external_url")),
            alt_titles=[str(item) for item in data.get("alt_titles") or [] if str(item).strip()],
            links={str(k): str(v) for k, v in (data.get("links") or {}).items()},
            candidates=[
                MatchCandidate.from_dict(item)
                for item in data.get("candidates") or []
                if isinstance(item, dict)
            ],
        )


@dataclass
class EngineStatus:
    """Outcome of one engine during a scan, surfaced in the UI."""

    name: str
    ok: bool
    detail: str = ""
    elapsed_ms: int = 0

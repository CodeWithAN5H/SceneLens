"""Movies and TV series: vision-guided identification + TMDB enrichment.

The vision model does the frame recognition; TMDB (when the user supplies a free
API key) canonicalizes the title/year, adds a poster, synopsis and production
company so the result card looks complete.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import httpx

from ..config import TMDB_ENDPOINT, USER_AGENT, Settings
from ..models import MediaResult
from .base import EngineError, normalize_candidate, safe_url

FILM_GUIDANCE = """
- For live-action or animated films/series, infer the title from cast, costumes,
  sets, cinematography, title cards and visual style. Distinguish a TV episode
  from a film and give the season/episode only when the frame makes it clear.
- Use official English release titles where one exists; keep the original title
  in alternative_titles.
"""

_TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"


def normalize_film_candidate(raw: dict[str, Any], source: str) -> MediaResult | None:
    """Normalize a movie/TV candidate returned by the vision engine."""
    result = normalize_candidate(raw, source, default_type="movie")
    if result is None or result.media_type not in {"movie", "tv"}:
        return None
    return result


def _similarity(left: str, right: str) -> float:
    normalized = lambda value: "".join(char for char in value.lower() if char.isalnum())  # noqa: E731
    return SequenceMatcher(None, normalized(left), normalized(right)).ratio()


async def enrich_from_tmdb(
    result: MediaResult,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Attach TMDB metadata in place. Returns ``True`` when anything was added."""
    api_key = settings.resolved_tmdb_key
    if not api_key or result.media_type not in {"movie", "tv"}:
        return False

    kind = "movie" if result.media_type == "movie" else "tv"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        )

    try:
        params: dict[str, Any] = {
            "api_key": api_key,
            "query": result.title,
            "include_adult": "false",
            "language": "en-US",
        }
        if result.year:
            params["year" if kind == "movie" else "first_air_date_year"] = result.year

        search = await client.get(f"{TMDB_ENDPOINT}/search/{kind}", params=params)
        if search.status_code != 200:
            raise EngineError(f"TMDB search returned HTTP {search.status_code}.")
        payload = search.json()
        matches = payload.get("results") or []
        if not matches:
            return False

        best_match = None
        best_ratio = 0.0
        for match in matches[:5]:
            name = match.get("title") or match.get("name") or ""
            ratio = _similarity(result.title, name)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = match
        if best_match is None or best_ratio < 0.55:
            return False

        details: dict[str, Any] = best_match
        match_id = best_match.get("id")
        if match_id:
            detail_response = await client.get(
                f"{TMDB_ENDPOINT}/{kind}/{match_id}",
                params={"api_key": api_key, "language": "en-US"},
            )
            if detail_response.status_code == 200:
                details = detail_response.json()

        changed = False
        official_title = details.get("title") or details.get("name")
        if isinstance(official_title, str) and official_title.strip() and best_ratio >= 0.8:
            result.title = official_title.strip()
            changed = True

        release = details.get("release_date") or details.get("first_air_date") or ""
        if not result.year and len(release) >= 4 and release[:4].isdigit():
            result.year = int(release[:4])
            changed = True

        poster_path = details.get("poster_path")
        poster = safe_url(f"{_TMDB_POSTER_BASE}{poster_path}") if poster_path else None
        if poster and not result.cover_url:
            result.cover_url = poster
            changed = True

        overview = details.get("overview")
        if isinstance(overview, str) and overview.strip() and not result.synopsis:
            result.synopsis = overview.strip()
            changed = True

        if not result.studio:
            companies = details.get("production_companies") or details.get("networks") or []
            if isinstance(companies, list) and companies:
                first = companies[0]
                name = first.get("name") if isinstance(first, dict) else None
                if isinstance(name, str) and name.strip():
                    result.studio = name.strip()
                    changed = True

        if details.get("id"):
            result.external_url = f"https://www.themoviedb.org/{kind}/{details['id']}"
            result.links = {**result.links, "TMDB": result.external_url}
            changed = True

        imdb_id = details.get("imdb_id")
        if isinstance(imdb_id, str) and imdb_id.startswith("tt"):
            result.links = {**result.links, "IMDb": f"https://www.imdb.com/title/{imdb_id}"}

        return changed
    except (httpx.HTTPError, ValueError, EngineError):
        # Enrichment is optional; a missing poster should not fail a scan.
        return False
    finally:
        if owns_client:
            await client.aclose()

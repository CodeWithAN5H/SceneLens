"""Video games: vision-guided identification with Steam as a free cross-check.

Games have no open scene-index API, so the vision model does the heavy lifting
(HUD, UI language, character models, art direction). Steam's public store search
then validates the candidate title and supplies box-art style key art without
requiring any API key.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import httpx

from ..config import STEAM_SEARCH_ENDPOINT, USER_AGENT
from ..models import MediaResult, build_search_links
from .base import EngineError, normalize_candidate, safe_url

GAME_GUIDANCE = """
- For games, read the HUD, map/objective text, ability icons, inventory UI,
  character models and art style. Name the game, and add the level, mission,
  mode or boss only when it is readable in the frame.
- Match the specific instalment (e.g. a sequel, remaster or expansion) whenever
  the UI or characters make it identifiable.
- Put the developer/publisher studio in "studio".
"""


def normalize_game_candidate(raw: dict[str, Any], source: str) -> MediaResult | None:
    result = normalize_candidate(raw, source, default_type="game")
    if result is None or result.media_type != "game":
        return None
    if "IGDB" not in result.links:
        result.links.update(build_search_links("game", result.title, result.year))
    return result


def _normalized(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


async def enrich_from_steam(
    result: MediaResult,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Validate the title against Steam and attach key art. No key required."""
    if result.media_type != "game" or not result.title:
        return False

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT})

    try:
        response = await client.get(
            STEAM_SEARCH_ENDPOINT,
            params={"term": result.title, "l": "english", "cc": "US"},
        )
        if response.status_code != 200:
            raise EngineError(f"Steam search returned HTTP {response.status_code}.")
        items = (response.json() or {}).get("items") or []
        if not items:
            return False

        target = _normalized(result.title)
        best_item = None
        best_ratio = 0.0
        for item in items[:8]:
            name = item.get("name") or ""
            ratio = SequenceMatcher(None, target, _normalized(name)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_item = item

        if best_item is None or best_ratio < 0.72:
            return False

        changed = False
        art = safe_url(best_item.get("tiny_image"))
        if art and not result.cover_url:
            result.cover_url = art
            changed = True

        app_id = best_item.get("id")
        if app_id:
            store_url = f"https://store.steampowered.com/app/{app_id}"
            result.external_url = result.external_url or store_url
            result.links = {**result.links, "Steam": store_url}
            changed = True

        return changed
    except (httpx.HTTPError, ValueError, EngineError):
        return False
    finally:
        if owns_client:
            await client.aclose()

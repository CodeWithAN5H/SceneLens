"""Anime scene matching via the free trace.moe index.

trace.moe returns the closest indexed anime frames for an upload, including the
episode and exact second. Its ``similarity`` is a frame-level similarity score:
close to 1.0 for a real scene match, but also high for unrelated images (the
index always returns its nearest neighbors), so the router treats this engine's
score as *anime evidence* rather than a universal confidence value.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import TRACE_MOE_ENDPOINT, USER_AGENT, Settings
from ..models import MediaResult, build_search_links, format_timestamp
from ..utils.image_utils import PreparedImage
from .base import EngineError, ProgressCallback, safe_url


class AnimeEngine:
    name = "trace.moe"

    def __init__(self, settings: Settings, timeout: float = 35.0) -> None:
        self.settings = settings
        self.timeout = timeout

    async def identify(
        self,
        prepared: PreparedImage,
        progress: ProgressCallback | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[MediaResult]:
        if progress:
            progress("Searching the trace.moe anime index")

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )

        try:
            response = await client.post(
                TRACE_MOE_ENDPOINT,
                params={
                    "anilistInfo": "",
                    **({"cutBorders": ""} if self.settings.cut_borders else {}),
                },
                files={"image": (prepared.filename, prepared.jpeg_bytes, "image/jpeg")},
            )
        except httpx.TimeoutException as error:
            raise EngineError("trace.moe did not respond in time.") from error
        except httpx.HTTPError as error:
            raise EngineError("Could not reach trace.moe.") from error
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 402:
            raise EngineError("trace.moe daily search quota reached. Try again tomorrow.")
        if response.status_code == 429:
            raise EngineError("trace.moe is rate limiting requests. Wait a moment.")
        if response.status_code >= 400:
            raise EngineError(f"trace.moe returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as error:
            raise EngineError("trace.moe returned an unreadable response.") from error

        error_message = payload.get("error")
        if error_message:
            raise EngineError(f"trace.moe: {error_message}")

        raw_results = payload.get("result") or []
        if not raw_results:
            return []

        results: list[MediaResult] = []
        seen: set[tuple[str, int | None]] = set()
        for item in raw_results[:6]:
            result = self._parse_item(item)
            if result is None:
                continue
            key = (result.title, result.episode)
            if key in seen:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= 4:
                break
        return results

    def _parse_item(self, item: dict[str, Any]) -> MediaResult | None:
        if not isinstance(item, dict):
            return None
        anilist = item.get("anilist") or {}
        if anilist.get("isAdult"):
            return None

        titles = anilist.get("title") or {}
        title = (
            titles.get("english")
            or titles.get("romaji")
            or titles.get("native")
            or item.get("filename")
        )
        if not isinstance(title, str) or not title.strip():
            return None

        similarity = item.get("similarity")
        try:
            confidence = min(1.0, max(0.0, float(similarity)))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence <= 0.01:
            return None

        studios = anilist.get("studios") or {}
        studio_edges = studios.get("edges") if isinstance(studios, dict) else None
        studio = None
        if isinstance(studio_edges, list) and studio_edges:
            main = next(
                (edge for edge in studio_edges if isinstance(edge, dict) and edge.get("isMain")),
                studio_edges[0],
            )
            if isinstance(main, dict):
                node = main.get("node") or {}
                studio = node.get("name") if isinstance(node, dict) else None

        start_date = anilist.get("startDate") or {}
        end_date = anilist.get("endDate") or {}
        year = None
        for source in (start_date, end_date):
            if isinstance(source, dict) and isinstance(source.get("year"), int):
                year = source["year"]
                break

        cover = anilist.get("coverImage") or {}
        cover_url = safe_url(cover.get("large")) if isinstance(cover, dict) else None

        raw_frame = item.get("image")
        if isinstance(raw_frame, str) and raw_frame.startswith("//"):
            raw_frame = f"https:{raw_frame}"
        elif isinstance(raw_frame, str) and raw_frame.startswith("/"):
            raw_frame = f"https://trace.moe{raw_frame}"
        frame_url = safe_url(raw_frame)

        raw_video = item.get("video")
        if isinstance(raw_video, str) and raw_video.startswith("//"):
            raw_video = f"https:{raw_video}"
        elif isinstance(raw_video, str) and raw_video.startswith("/"):
            raw_video = f"https://trace.moe{raw_video}"
        video_url = safe_url(raw_video)

        from_seconds = item.get("from")
        timestamp = format_timestamp(from_seconds)
        raw_episode = item.get("episode")
        episode = int(raw_episode) if isinstance(raw_episode, (int, float)) else None
        external_url = safe_url(anilist.get("siteUrl")) or (
            f"https://anilist.co/anime/{anilist['id']}" if anilist.get("id") else None
        )

        alt_titles = []
        for candidate in (titles.get("romaji"), titles.get("native"), titles.get("chinese")):
            if isinstance(candidate, str) and candidate.strip() and candidate != title:
                alt_titles.append(candidate.strip())

        links = build_search_links("anime", title, year)
        if external_url:
            links["AniList"] = external_url
        mal_id = anilist.get("idMal")
        if mal_id:
            links["MyAnimeList"] = f"https://myanimelist.net/anime/{mal_id}"

        genres = anilist.get("genres") or []
        episode_label = f"Episode {episode}" if episode else "an anime frame"
        evidence = f"Frame match in {episode_label}"
        if timestamp:
            evidence += f" at {timestamp}"
        evidence += f" · {confidence * 100:.1f}% similarity"
        if genres:
            evidence += f" · {', '.join(str(genre) for genre in genres[:3])}"

        return MediaResult(
            media_type="anime",
            title=title.strip(),
            confidence=confidence,
            source=self.name,
            year=year,
            studio=studio,
            episode=episode,
            timestamp=timestamp,
            timestamp_seconds=float(from_seconds) if isinstance(from_seconds, (int, float)) else None,
            synopsis=", ".join(str(genre) for genre in genres[:4]) or None,
            evidence=evidence,
            cover_url=cover_url,
            matched_frame_url=frame_url,
            preview_video_url=video_url,
            external_url=external_url,
            alt_titles=alt_titles[:3],
            links=links,
        )

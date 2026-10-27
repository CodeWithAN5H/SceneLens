"""The identification cascade.

Every scan runs the free anime index and the multimodal vision engine at the
same time, normalizes both into :class:`MediaResult`, ranks the candidates and
finally enriches the winner with TMDB / Steam metadata. All of this happens in a
worker thread with its own event loop; the GUI only receives progress strings.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from ..config import Settings
from ..models import EngineStatus, MediaResult
from .anime_engine import AnimeEngine
from .base import EngineError, ProgressCallback
from .game_engine import enrich_from_steam
from .movie_engine import enrich_from_tmdb
from .vision import identify_with_vision
from .vision_fallback import rank_results, to_candidates

logger = logging.getLogger(__name__)


@dataclass
class ScanReport:
    best: MediaResult | None
    alternatives: list[MediaResult]
    used_fallback: bool
    threshold: float
    statuses: list[EngineStatus]
    notices: list[str] = field(default_factory=list)
    image_hash: str = ""
    elapsed_seconds: float = 0.0

    @property
    def has_match(self) -> bool:
        return self.best is not None


class IdentityRouter:
    """Orchestrates engines. Safe to call ``scan_sync`` from a worker thread."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings

    # ---- public API ------------------------------------------------------

    def scan_sync(self, image: Image.Image, progress: ProgressCallback | None = None) -> ScanReport:
        return asyncio.run(self.scan(image, progress))

    async def scan(self, image: Image.Image, progress: ProgressCallback | None = None) -> ScanReport:
        started = time.perf_counter()
        emit = self._make_emitter(progress)

        emit("Preparing the frame")
        prepared = await asyncio.to_thread(self._prepare, image)

        emit("Cross-checking the anime index and vision engine")
        anime_engine = AnimeEngine(self.settings)

        jobs: list[tuple[str, asyncio.Task[Any]]] = []
        jobs.append(
            (
                "trace.moe",
                asyncio.create_task(
                    self._timed("trace.moe", anime_engine.identify(prepared, emit))
                ),
            )
        )
        if self.settings.vision_configured:
            jobs.append(
                (
                    "vision",
                    asyncio.create_task(
                        self._timed(
                            f"Vision · {self.settings.resolved_vision_model}",
                            identify_with_vision(prepared, self.settings, emit),
                        )
                    ),
                )
            )

        results: list[MediaResult] = []
        statuses_by_job: dict[str, EngineStatus] = {}
        pending = {task for _, task in jobs}
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                job_key = next(key for key, candidate in jobs if candidate is task)
                engine_results, status = task.result()
                results.extend(engine_results)
                statuses_by_job[job_key] = status
                if status.ok:
                    emit(f"{status.name} finished — {status.detail}")

        statuses = [statuses_by_job[key] for key, _ in jobs if key in statuses_by_job]
        if not self.settings.vision_configured:
            statuses.append(
                EngineStatus(
                    "Vision model",
                    ok=False,
                    detail="Not configured — add an API key in Settings",
                )
            )

        emit("Ranking the candidates")
        ranked = rank_results(results)
        best = ranked[0] if ranked else None
        alternatives = ranked[1:4]

        if best is not None:
            emit("Fetching reference art and metadata")
            await self._enrich(best)
            best.candidates = to_candidates(ranked[:3])

        used_fallback = best is None or best.confidence < self.settings.confidence_threshold

        report = ScanReport(
            best=best,
            alternatives=alternatives,
            used_fallback=used_fallback,
            threshold=self.settings.confidence_threshold,
            statuses=statuses,
            notices=self._notices(best, statuses),
            image_hash=prepared.sha1,
            elapsed_seconds=round(time.perf_counter() - started, 2),
        )
        emit("Scan complete")
        return report

    # ---- internals -------------------------------------------------------

    @staticmethod
    def _prepare(image: Image.Image):
        from .base import prepare_for_scan

        return prepare_for_scan(image)

    async def _timed(self, label: str, awaitable: Any) -> tuple[list[MediaResult], EngineStatus]:
        started = time.perf_counter()
        try:
            results = await awaitable
            elapsed = int((time.perf_counter() - started) * 1000)
            detail = f"{len(results)} candidate{'s' if len(results) != 1 else ''}" if results else "no match"
            return results, EngineStatus(label, True, detail, elapsed)
        except EngineError as error:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.warning("%s engine failed: %s", label, error.message)
            return [], EngineStatus(label, False, error.message, elapsed)
        except Exception:  # noqa: BLE001 - one engine must not kill the scan
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.exception("%s engine crashed", label)
            return [], EngineStatus(label, False, "Unexpected engine error.", elapsed)

    async def _enrich(self, result: MediaResult) -> None:
        try:
            if result.media_type in {"movie", "tv"}:
                await enrich_from_tmdb(result, self.settings)
            elif result.media_type == "game":
                await enrich_from_steam(result)
        except Exception:  # noqa: BLE001 - enrichment is strictly optional
            logger.debug("Metadata enrichment failed", exc_info=True)

    def _notices(self, best: MediaResult | None, statuses: list[EngineStatus]) -> list[str]:
        notices: list[str] = []
        if not self.settings.vision_configured:
            if best is not None and best.source == "trace.moe":
                notices.append(
                    "Anime-only mode: this is trace.moe's closest anime frame, not a "
                    "verified identification. Add a vision key in Settings to identify "
                    "movies, TV series and games."
                )
            else:
                notices.append(
                    "Vision engine is off: anime frames work now, but movies, TV and "
                    "games need a multimodal API key in Settings."
                )

        for status in statuses:
            if status.ok:
                continue
            if status.name == "Vision model" and status.detail.startswith("Not configured"):
                continue
            notices.append(f"{status.name}: {status.detail}")

        if best is None:
            notices.append(
                "No engine returned a match. Try a clearer frame or a different screenshot."
            )
        elif best.media_type in {"movie", "tv"} and not self.settings.tmdb_configured:
            notices.append("Add a free TMDB key in Settings for posters and canonical film metadata.")
        elif best.source == "trace.moe" and self.settings.vision_configured:
            notices.append(
                "Anime match from trace.moe · its similarity score is relative to "
                "the closest indexed frame."
            )
        return notices

    @staticmethod
    def _make_emitter(progress: ProgressCallback | None) -> ProgressCallback:
        def emit(message: str) -> None:
            if progress is None:
                return
            try:
                progress(message)
            except Exception:  # noqa: BLE001 - UI callbacks are best effort
                logger.debug("Progress callback failed", exc_info=True)

        return emit

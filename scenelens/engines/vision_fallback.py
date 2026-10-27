"""Ranking, deduplication and the low-confidence fallback view.

trace.moe always returns its closest indexed frames, so its raw similarity can
beat an honest vision-model guess on a game screenshot. Ranking therefore treats
trace.moe as *anime evidence*: when the vision model confidently identifies a
different medium, that result wins; when it also sees anime (or is not
configured), the anime frame match keeps its weight.
"""

from __future__ import annotations

from ..models import MatchCandidate, MediaResult


def dedupe(results: list[MediaResult]) -> list[MediaResult]:
    seen: dict[tuple[str, str], MediaResult] = {}
    for result in results:
        key = result.dedupe_key
        existing = seen.get(key)
        if existing is None or result.confidence > existing.confidence:
            seen[key] = result
    return list(seen.values())


def rank_results(results: list[MediaResult]) -> list[MediaResult]:
    unique = dedupe(results)
    if not unique:
        return []

    vision_results = [result for result in unique if result.source != "trace.moe"]
    vision_has_anime = any(
        result.media_type == "anime" and result.confidence >= 0.5
        for result in vision_results
    )
    vision_is_confident = any(result.confidence >= 0.55 for result in vision_results)

    def score(result: MediaResult) -> float:
        if result.source != "trace.moe":
            return result.confidence
        # Uncalibrated against non-anime images; demote it when a vision engine
        # has confidently named another medium.
        if vision_is_confident and not vision_has_anime:
            return result.confidence * 0.6
        return result.confidence

    return sorted(unique, key=lambda item: (score(item), item.confidence), reverse=True)


def to_candidates(results: list[MediaResult], limit: int = 3) -> list[MatchCandidate]:
    """Build the compact alternative list stored with a result."""
    candidates: list[MatchCandidate] = []
    for result in results[:limit]:
        candidates.append(
            MatchCandidate(
                title=result.title,
                media_type=result.media_type,
                confidence=result.confidence,
                year=result.year,
                note=f"{result.source} · {result.confidence_pct}%",
                links=result.search_links,
            )
        )
    return candidates

"""Multimodal vision engine used for movies, TV series and video games.

Works with any OpenAI-compatible chat-completions endpoint that accepts image
input (OpenAI, Azure-compatible gateways, OpenRouter, local vLLM/Ollama proxies,
…). The user supplies the base URL, model and key in Settings; nothing is sent
anywhere until they scan an image.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import USER_AGENT, Settings
from ..models import MediaResult, normalize_media_type
from ..utils.image_utils import PreparedImage
from .base import EngineError, ProgressCallback, normalize_candidate
from .game_engine import GAME_GUIDANCE, normalize_game_candidate
from .movie_engine import FILM_GUIDANCE, normalize_film_candidate

SYSTEM_PROMPT = f"""You are SceneLens, a precise media-identification engine.
The user sends ONE frame, screenshot or photo. Decide whether it comes from an
anime, a movie, a TV/web series or a video game, then identify it.

Return ONLY a JSON object, no markdown fences, shaped exactly like:
{{
  "scene_summary": "one short sentence describing what is visible",
  "candidates": [
    {{
      "media_type": "anime" | "movie" | "tv" | "game",
      "title": "official title",
      "year": 2019,
      "season": 2,
      "episode": 7,
      "timestamp": "00:12:34",
      "level": "level, mission or mode if visible",
      "studio": "studio or game developer",
      "confidence": 0.0,
      "evidence": "short visual reasons",
      "alternative_titles": ["original title"]
    }}
  ]
}}

Rules:
- Return 1 to 4 candidates, strongest first. Omit fields you cannot support.
- Confidence must be calibrated: 0.9+ only when unambiguous, 0.6-0.8 for a
  strong likeness, below 0.5 for a guess from style alone. Never invent an
  episode or timestamp; omit it instead.
- Distinguish anime from western animation by production style, not by content.
- For movie/TV, season/episode requires on-screen or unmistakable evidence.
- For games, HUD, UI wording, ability icons and level design are strong clues.
{FILM_GUIDANCE}
{GAME_GUIDANCE}
"""

USER_PROMPT = (
    "Identify the source of this image. If it is not from any recognizable "
    "media, return a low-confidence best guess rather than an error. JSON only."
)


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerate fences, leading prose and trailing commentary."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise EngineError("The vision model did not return valid JSON.")


class VisionClient:
    def __init__(self, settings: Settings, timeout: float = 90.0) -> None:
        self.settings = settings
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return self.settings.vision_configured

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.resolved_vision_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    async def complete_json(
        self,
        prepared: PreparedImage,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise EngineError("No vision model configured.")

        payload: dict[str, Any] = {
            "model": self.settings.resolved_vision_model,
            "temperature": 0.1,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": prepared.data_url, "detail": "high"},
                        },
                    ],
                },
            ],
        }

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, headers=self._headers())

        try:
            response = await client.post(
                f"{self.settings.resolved_vision_base_url}/chat/completions",
                json=payload,
            )
            if response.status_code == 400 and "response_format" in payload:
                # Some compatible providers reject JSON mode; retry without it.
                payload.pop("response_format", None)
                response = await client.post(
                    f"{self.settings.resolved_vision_base_url}/chat/completions",
                    json=payload,
                )

            if response.status_code in {401, 403}:
                raise EngineError("The vision API key was rejected (HTTP 401/403).")
            if response.status_code == 429:
                raise EngineError("The vision provider is rate limiting requests.")
            if response.status_code >= 400:
                detail = response.text.strip().replace("\n", " ")[:160]
                raise EngineError(f"Vision provider error {response.status_code}: {detail}")

            data = response.json()
            message = ((data.get("choices") or [{}])[0]).get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )
            if not isinstance(content, str) or not content.strip():
                raise EngineError("The vision model returned an empty answer.")
            return _extract_json(content)
        except httpx.TimeoutException as error:
            raise EngineError("The vision model took too long to answer.") from error
        except httpx.HTTPError as error:
            raise EngineError("Could not reach the vision endpoint.") from error
        finally:
            if owns_client:
                await client.aclose()

    async def check_access(self, timeout: float = 15.0) -> tuple[bool, str]:
        """Lightweight credential check against ``GET /models``."""
        if not self.configured:
            return False, "No API key set."
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=self._headers()) as client:
                response = await client.get(f"{self.settings.resolved_vision_base_url}/models")
            if response.status_code == 200:
                return True, "Connection OK — model endpoint reachable."
            if response.status_code in {401, 403}:
                return False, "The API key was rejected."
            return False, f"Endpoint returned HTTP {response.status_code}."
        except httpx.HTTPError:
            return False, "Could not reach the endpoint."


async def identify_with_vision(
    prepared: PreparedImage,
    settings: Settings,
    progress: ProgressCallback | None = None,
) -> list[MediaResult]:
    """Ask the multimodal model to classify and identify the frame."""
    if not settings.vision_configured:
        raise EngineError("No vision model configured.")

    if progress:
        progress(f"Reading the frame with {settings.resolved_vision_model}")

    client = VisionClient(settings)
    payload = await client.complete_json(prepared)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = [payload] if payload.get("title") else []
    if not raw_candidates:
        return []

    source = settings.resolved_vision_model
    scene_summary = payload.get("scene_summary")
    results: list[MediaResult] = []

    for raw in raw_candidates[:5]:
        if not isinstance(raw, dict):
            continue
        media_type = normalize_media_type(raw.get("media_type"))
        if media_type in {"movie", "tv"}:
            result = normalize_film_candidate(raw, source)
        elif media_type == "game":
            result = normalize_game_candidate(raw, source)
        else:
            result = normalize_candidate(raw, source, default_type=media_type or "movie")
        if result is None:
            continue
        if not result.evidence and isinstance(scene_summary, str):
            result.evidence = scene_summary.strip() or None
        results.append(result)

    results.sort(key=lambda item: item.confidence, reverse=True)
    return results[:4]

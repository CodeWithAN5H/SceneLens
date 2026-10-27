"""Application paths and persistent user settings.

The whole app stores its state under the current user's application-data
folder, so uninstalling or moving the source tree never destroys scan history:

    Windows   %APPDATA%\\SceneLens
    macOS     ~/Library/Application Support/SceneLens
    Linux     ~/.local/share/SceneLens

API keys are written to ``config.json`` in that folder (never to the repo) and
can alternatively be supplied through environment variables or a project-local
``.env`` file for development.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "SceneLens"
APP_TAGLINE = "universal scene identifier"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent

# A local .env is a convenient way to keep development keys out of source.
load_dotenv(BASE_DIR / ".env")


def _data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


DATA_DIR = _data_root()
DATA_DIR.mkdir(parents=True, exist_ok=True)

THUMB_DIR = DATA_DIR / "thumbnails"
EXPORT_DIR = DATA_DIR / "exports"
IMAGE_CACHE_DIR = DATA_DIR / "image-cache"
for _directory in (THUMB_DIR, EXPORT_DIR, IMAGE_CACHE_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "scenelens.db"
CONFIG_PATH = DATA_DIR / "config.json"

TRACE_MOE_ENDPOINT = "https://api.trace.moe/search"
TMDB_ENDPOINT = "https://api.themoviedb.org/3"
STEAM_SEARCH_ENDPOINT = "https://store.steampowered.com/api/storesearch/"

DEFAULT_VISION_BASE_URL = "https://api.openai.com/v1"
DEFAULT_VISION_MODEL = "gpt-4o-mini"
DEFAULT_CONFIDENCE_THRESHOLD = 0.55

USER_AGENT = f"{APP_NAME}/{APP_VERSION} (desktop scene identifier)"


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


@dataclass
class Settings:
    """User-editable preferences, persisted as JSON."""

    vision_api_key: str = ""
    vision_base_url: str = DEFAULT_VISION_BASE_URL
    vision_model: str = DEFAULT_VISION_MODEL
    tmdb_api_key: str = ""
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    watch_clipboard: bool = True
    auto_scan_clipboard: bool = False
    cut_borders: bool = True

    # --- resolved values (settings file wins, environment is the fallback) ---

    @property
    def resolved_vision_key(self) -> str:
        return self.vision_api_key.strip() or _env("SCENELENS_VISION_API_KEY", "OPENAI_API_KEY")

    @property
    def resolved_vision_base_url(self) -> str:
        value = (
            self.vision_base_url.strip()
            or _env("SCENELENS_VISION_BASE_URL", "OPENAI_BASE_URL")
            or DEFAULT_VISION_BASE_URL
        )
        return value.rstrip("/")

    @property
    def resolved_vision_model(self) -> str:
        return (
            self.vision_model.strip()
            or _env("SCENELENS_VISION_MODEL", "OPENAI_VISION_MODEL")
            or DEFAULT_VISION_MODEL
        )

    @property
    def resolved_tmdb_key(self) -> str:
        return self.tmdb_api_key.strip() or _env("SCENELENS_TMDB_API_KEY", "TMDB_API_KEY")

    @property
    def vision_configured(self) -> bool:
        return bool(self.resolved_vision_key)

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.resolved_tmdb_key)

    def sanitized(self) -> "Settings":
        """Return a copy with values clamped to safe ranges."""
        threshold = float(self.confidence_threshold)
        self.confidence_threshold = min(0.95, max(0.2, threshold))
        return self


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from disk, ignoring unknown or malformed entries."""
    path = path or CONFIG_PATH
    if not path.exists():
        return Settings()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()

    known = {field.name for field in fields(Settings)}
    values = {key: value for key, value in raw.items() if key in known}
    try:
        return Settings(**values).sanitized()
    except (TypeError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Atomically persist settings so a crash cannot truncate the file."""
    path = path or CONFIG_PATH
    payload = json.dumps(asdict(settings.sanitized()), indent=2)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def open_exports_dir() -> Path:
    """Where generated share cards are written."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR

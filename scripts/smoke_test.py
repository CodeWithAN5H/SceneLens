"""Offline smoke tests for SceneLens.

Run with the project virtualenv:

    .venv\\Scripts\\python.exe scripts\\smoke_test.py
    .venv\\Scripts\\python.exe scripts\\smoke_test.py --gui
    .venv\\Scripts\\python.exe scripts\\smoke_test.py --live   # hits trace.moe

The default run is fully offline: the vision, TMDB and Steam endpoints are
replaced by a local mock server, and trace.moe is stubbed for the router test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scenelens.config import Settings  # noqa: E402
from scenelens.database import HistoryStore  # noqa: E402
from scenelens.engines.anime_engine import AnimeEngine  # noqa: E402
from scenelens.engines.base import normalize_candidate  # noqa: E402
from scenelens.engines.game_engine import enrich_from_steam  # noqa: E402
from scenelens.engines.movie_engine import enrich_from_tmdb  # noqa: E402
from scenelens.engines.router import IdentityRouter  # noqa: E402
from scenelens.engines.vision import VisionClient, identify_with_vision  # noqa: E402
from scenelens.engines.vision_fallback import rank_results  # noqa: E402
from scenelens.models import MediaResult  # noqa: E402
from scenelens.utils.discord_card import build_discord_markdown, render_share_card  # noqa: E402
from scenelens.utils.image_utils import prepare_image  # noqa: E402

VISION_PAYLOAD = {
    "scene_summary": "A retro corporate corridor at night.",
    "candidates": [
        {
            "media_type": "tv",
            "title": "Severance",
            "year": 2022,
            "season": 1,
            "episode": 3,
            "studio": "Red Hour",
            "confidence": 0.84,
            "evidence": "Retro office set and corridor lighting",
            "alternative_titles": ["Severance (TV series)"],
        },
        {
            "media_type": "game",
            "title": "Control",
            "year": 2019,
            "level": "The Oldest House",
            "confidence": 0.31,
        },
    ],
}

TMDB_SEARCH = {
    "results": [
        {"id": 95396, "name": "Severance", "first_air_date": "2022-02-18"},
    ]
}
TMDB_DETAILS = {
    "id": 95396,
    "name": "Severance",
    "first_air_date": "2022-02-18",
    "poster_path": "/poster.jpg",
    "overview": "Mark leads a team whose memories are surgically divided.",
    "networks": [{"name": "Apple TV+"}],
    "production_companies": [{"name": "Red Hour"}],
}
STEAM_SEARCH = {
    "items": [
        {
            "type": "app",
            "name": "Control",
            "id": 870780,
            "tiny_image": "https://cdn.example/control.jpg",
            "metascore": "85",
        }
    ]
}


class _MockHandler(BaseHTTPRequestHandler):
    server_version = "SceneLensMock/1.0"
    requests_seen: list[dict] = []

    def log_message(self, *args) -> None:  # noqa: D401 - silence test server
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/models":
            self._send(200, {"data": [{"id": "mock-vision"}]})
        elif path == "/3/search/tv":
            self._send(200, TMDB_SEARCH)
        elif path.startswith("/3/tv/"):
            self._send(200, TMDB_DETAILS)
        elif path == "/steam/storesearch":
            self._send(200, STEAM_SEARCH)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"})
            return

        _MockHandler.requests_seen.append(payload)
        image_attached = False
        for message in payload.get("messages") or []:
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    url = (part.get("image_url") or {}).get("url", "")
                    if url.startswith("data:image/jpeg;base64,"):
                        image_attached = True
        if not image_attached:
            self._send(400, {"error": "missing image"})
            return

        # Fenced JSON proves the tolerant extractor works on real-world models.
        content = "```json\n" + json.dumps(VISION_PAYLOAD) + "\n```"
        self._send(
            200,
            {
                "id": "mock",
                "model": payload.get("model"),
                "choices": [{"message": {"role": "assistant", "content": content}}],
            },
        )


def start_mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_normalization() -> None:
    result = normalize_candidate(
        {
            "media_type": "TV series",
            "title": "Severance",
            "year": 2022,
            "season": 1,
            "episode": 3,
            "confidence": 82,
            "studio": "Red Hour",
            "evidence": "retro office",
        },
        "mock-vision",
    )
    assert result is not None
    assert result.media_type == "tv"
    assert result.confidence == 0.82
    assert result.episode_code == "S01E03"
    assert "IMDb" in result.search_links


def test_database() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = HistoryStore(Path(tmp) / "history.db")
        result = MediaResult(
            media_type="anime",
            title="MIX",
            confidence=0.99,
            source="trace.moe",
            year=2019,
            studio="OLM",
            episode=11,
            timestamp="00:06:10",
        )
        scan_id = store.add(result, thumbnail_path=None, image_hash="hash")
        record = store.get(scan_id)
        assert record is not None and record.result.title == "MIX"
        assert store.count() == 1
        store.delete(scan_id)
        assert store.count() == 0


def test_anime_parse() -> None:
    item = {
        "similarity": 0.9821,
        "episode": 11,
        "from": 370.62,
        "to": 375.5,
        "image": "https://media.trace.moe/frame.jpg",
        "video": "https://media.trace.moe/clip.mp4",
        "anilist": {
            "id": 103555,
            "idMal": 38098,
            "isAdult": False,
            "title": {
                "romaji": "MIX: MEISEI STORY",
                "english": "MIX",
                "native": "MIX MEISEI STORY",
            },
            "genres": ["Comedy", "Sports"],
            "startDate": {"year": 2019, "month": 4, "day": 6},
            "siteUrl": "https://anilist.co/anime/103555",
            "coverImage": {"large": "https://img.example/cover.jpg"},
            "studios": {"edges": [{"isMain": True, "node": {"name": "OLM"}}]},
        },
    }
    parsed = AnimeEngine(Settings())._parse_item(item)
    assert parsed is not None
    assert parsed.title == "MIX"
    assert parsed.year == 2019
    assert parsed.studio == "OLM"
    assert parsed.episode == 11
    assert parsed.timestamp == "00:06:10"
    assert parsed.preview_video_url and parsed.matched_frame_url


def test_ranking_conflict() -> None:
    anime = MediaResult(media_type="anime", title="Nearest Anime Frame", confidence=0.995, source="trace.moe")
    game = MediaResult(media_type="game", title="Cyberpunk 2077", confidence=0.9, source="mock-vision")
    ranked = rank_results([anime, game])
    assert ranked[0].title == "Cyberpunk 2077", ranked

    anime_strong = MediaResult(media_type="anime", title="Actual Anime", confidence=0.98, source="trace.moe")
    anime_vision = MediaResult(media_type="anime", title="Actual Anime", confidence=0.7, source="mock-vision")
    ranked = rank_results([anime_vision, anime_strong])
    assert ranked[0].source == "trace.moe"


def test_share_card() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = MediaResult(
            media_type="anime",
            title="Attack on Titan",
            confidence=0.964,
            source="trace.moe",
            year=2013,
            studio="WIT Studio",
            season=1,
            episode=5,
            timestamp="00:12:34",
        )
        markdown = build_discord_markdown(result)
        assert "Attack on Titan" in markdown and "[ANIME]" in markdown
        path = render_share_card(
            result,
            Image.new("RGB", (640, 360), (20, 30, 45)),
            Image.new("RGB", (640, 360), (60, 20, 40)),
            Path(tmp) / "card.png",
        )
        assert path.exists() and path.stat().st_size > 5000


def test_mock_engines_and_router() -> None:
    server, base = start_mock_server()
    import scenelens.engines.game_engine as game_engine
    import scenelens.engines.movie_engine as movie_engine

    original_steam = game_engine.STEAM_SEARCH_ENDPOINT
    original_tmdb = movie_engine.TMDB_ENDPOINT
    original_identify = AnimeEngine.identify
    game_engine.STEAM_SEARCH_ENDPOINT = f"{base}/steam/storesearch"
    movie_engine.TMDB_ENDPOINT = f"{base}/3"

    try:
        settings = Settings(
            vision_api_key="test-key",
            vision_base_url=f"{base}/v1",
            vision_model="mock-vision",
            tmdb_api_key="test-tmdb",
            watch_clipboard=False,
        )
        image = Image.new("RGB", (640, 360), (24, 36, 54))
        ImageDraw.Draw(image).rectangle((100, 80, 320, 240), fill=(240, 170, 60))
        prepared = prepare_image(image)

        ok, message = asyncio.run(VisionClient(settings).check_access())
        assert ok, message

        results = asyncio.run(identify_with_vision(prepared, settings))
        assert len(results) == 2, results
        top = results[0]
        assert top.title == "Severance" and top.media_type == "tv"
        assert top.season == 1 and top.episode == 3
        assert _MockHandler.requests_seen, "mock endpoint was not called"
        assert any(
            message.get("role") == "system"
            for message in _MockHandler.requests_seen[-1].get("messages", [])
        )

        enriched = asyncio.run(enrich_from_tmdb(top, settings))
        assert enriched
        assert top.cover_url and "poster.jpg" in top.cover_url
        assert top.studio == "Red Hour"
        assert top.external_url and "themoviedb.org/tv/95396" in top.external_url

        game = next(item for item in results if item.media_type == "game")
        assert asyncio.run(enrich_from_steam(game))
        assert game.cover_url == "https://cdn.example/control.jpg"
        assert "Steam" in game.links

        async def fake_anime(self, prepared_image, progress=None, client=None):
            if progress:
                progress("fake anime search")
            return [
                MediaResult(
                    media_type="anime",
                    title="Nearest Anime Frame",
                    confidence=0.995,
                    source="trace.moe",
                )
            ]

        AnimeEngine.identify = fake_anime
        router = IdentityRouter(settings)
        report = router.scan_sync(image)
        assert report.best is not None
        assert report.best.title == "Severance", report.best.to_dict()
        assert not report.used_fallback
        assert all(status.ok for status in report.statuses), report.statuses
        assert report.best.candidates, "fallback candidates should be stored with the winner"
    finally:
        game_engine.STEAM_SEARCH_ENDPOINT = original_steam
        movie_engine.TMDB_ENDPOINT = original_tmdb
        AnimeEngine.identify = original_identify
        server.shutdown()
        server.server_close()


def test_live_trace_moe() -> None:
    from scenelens.engines.anime_engine import AnimeEngine

    settings = Settings()
    image = Image.new("RGB", (640, 360), (24, 36, 54))
    prepared = prepare_image(image)
    results = asyncio.run(AnimeEngine(settings).identify(prepared))
    assert results, "trace.moe returned no candidates"
    print("   live best:", results[0].title, results[0].confidence_pct, "%")


def test_gui() -> None:
    import scenelens.database.db as db_module
    import scenelens.gui.main_window as main_window
    import scenelens.utils.image_utils as image_utils

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        original_db = db_module.DB_PATH
        original_thumb = image_utils.THUMB_DIR
        original_loader = main_window.load_settings
        db_module.DB_PATH = tmp_path / "gui.db"
        image_utils.THUMB_DIR = tmp_path / "thumbs"
        image_utils.THUMB_DIR.mkdir()
        main_window.load_settings = lambda: Settings(watch_clipboard=False)

        app = None
        try:
            app = main_window.SceneLensApp()
            app.geometry("1340x880+-3000+0")
            app.update()
            assert app.dnd_enabled, "tkinterdnd2 failed to initialise"

            app._show_frame(app.scan_view, "scanning")
            app.update()
            app.scan_view.start(Image.new("RGB", (1280, 720), (24, 36, 54)), "frame.png")
            for _ in range(12):
                app.update()
            assert len(app.scan_view.canvas.find_all()) > 0
            app.scan_view.stop()

            best = MediaResult(
                media_type="tv",
                title="Severance",
                confidence=0.84,
                source="mock-vision",
                year=2022,
                studio="Red Hour",
                season=1,
                episode=3,
                timestamp="00:12:34",
            )
            report = main_window.ScanReport(
                best=best,
                alternatives=[],
                used_fallback=False,
                threshold=0.55,
                statuses=[],
                notices=[],
                image_hash="abc",
                elapsed_seconds=1.2,
            )
            app.results_view = main_window.ResultsView(
                app.body, app, report, Image.new("RGB", (1280, 720), (24, 36, 54))
            )
            app._show_frame(app.results_view, "results")
            app.update_idletasks()
            app.update()
            panel = app.results_view._reference_panel
            assert panel.winfo_height() >= 200, panel.winfo_height()

            app.show_history()
            app.update()
            assert app._mode == "history"

            app.open_settings()
            app.update()
            assert app._settings_dialog is not None
            app._settings_dialog._close()
            app.update()
            assert app._settings_dialog is None
        finally:
            if app is not None:
                app.destroy()
            db_module.DB_PATH = original_db
            image_utils.THUMB_DIR = original_thumb
            main_window.load_settings = original_loader


def main() -> int:
    parser = argparse.ArgumentParser(description="SceneLens smoke tests")
    parser.add_argument("--gui", action="store_true", help="also build the Tk interface")
    parser.add_argument("--live", action="store_true", help="hit the real trace.moe API")
    args = parser.parse_args()

    tests = [
        ("normalization", test_normalization),
        ("database", test_database),
        ("anime response parsing", test_anime_parse),
        ("ranking conflict", test_ranking_conflict),
        ("discord card", test_share_card),
        ("mock vision / TMDB / Steam / router", test_mock_engines_and_router),
    ]
    if args.live:
        tests.append(("live trace.moe", test_live_trace_moe))
    if args.gui:
        tests.append(("gui construction", test_gui))

    failures = 0
    for name, test in tests:
        try:
            test()
            print(f"PASS  {name}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {name}: {error}")
            traceback.print_exc()

    print(f"\n{len(tests) - failures}/{len(tests)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

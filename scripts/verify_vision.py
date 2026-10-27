"""Live end-to-end verification for SceneLens.

    .venv\\Scripts\\python.exe scripts\\verify_vision.py            # verify (fetches fixtures once)
    .venv\\Scripts\\python.exe scripts\\verify_vision.py --gui      # also drive the real window
    .venv\\Scripts\\python.exe scripts\\verify_vision.py --no-fetch  # only use frames already present

What it does
------------
1. Builds a small fixture set under ``testframes/`` (one frame per fixture) from
   public-domain film/TV on archive.org and official Steam store screenshots, so
   every frame has known ground truth. Fixture media stays out of git.
2. Pushes each frame through the real scan pipeline (:class:`IdentityRouter`)
   using exactly the settings SceneLens itself reads (``config.json`` in the app
   data folder, then ``.env`` / environment variables).
3. Reports per frame whether the app produced the expected media type and title,
   then writes a JSON + Markdown report.

Adding your own frames
----------------------
Drop a PNG/JPG into ``testframes/`` and, optionally, add an entry to
``testframes/manifest.json``::

    {"file": "my_frame.jpg", "expect_type": "tv",
     "expect_titles": ["severance"], "note": "S01E03 corridor"}

Frames without an entry are still scanned and reported, but left out of the
accuracy summary. This is the way to check modern film/TV frames, which cannot
be shipped as fixtures.

Fetching fixtures needs ``imageio-ffmpeg`` (it bundles an ffmpeg binary) and
network access::

    .venv\\Scripts\\python.exe -m pip install imageio-ffmpeg
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scenelens.config import CONFIG_PATH, Settings, load_settings  # noqa: E402
from scenelens.engines.base import EngineError  # noqa: E402
from scenelens.engines.router import IdentityRouter  # noqa: E402
from scenelens.engines.vision import VisionClient  # noqa: E402
from scenelens.utils.image_utils import load_image  # noqa: E402

USER_AGENT = {"User-Agent": "SceneLensVerify/1.0 (local desktop-app verification)"}
BEVERLY_HILLBILLIES = (
    "aqn-3-jci-oqpyb-uymm-vuq-jtr-2-k-0p-rt-qjt-6ym-0-uvl-d-7-auot-9-ju-pc-bz-o-mae-t"
)

# Every fixture: what the app should say, where the frame comes from, how to get it.
BUILTIN_FIXTURES: list[dict[str, Any]] = [
    {
        "name": "movie_nosferatu_1922",
        "file": "movie_nosferatu_1922.jpg",
        "expect_type": "movie",
        "expect_titles": ["nosferatu"],
        "note": "Count Orlok aboard the Demeter (clip 00:27)",
        "origin": "Nosferatu (1922), dir. F. W. Murnau",
        "source_url": "https://archive.org/details/turner_video_384150",
        "license": "Public domain (US)",
        "fetch": {"kind": "ia", "item": "turner_video_384150", "at": 27.0},
    },
    {
        "name": "movie_great_train_robbery_1903",
        "file": "movie_great_train_robbery_1903.jpg",
        "expect_type": "movie",
        "expect_titles": ["great train robbery"],
        "note": "The bound telegraph operator (03:17)",
        "origin": "The Great Train Robbery (1903), dir. Edwin S. Porter",
        "source_url": "https://archive.org/details/TheGreatTrainRobbery1903SilentFilm",
        "license": "Public domain (US)",
        "fetch": {"kind": "ia", "item": "TheGreatTrainRobbery1903SilentFilm", "at": 197.0},
    },
    {
        "name": "tv_beverly_hillbillies_s01e01",
        "file": "tv_beverly_hillbillies_s01e01.jpg",
        "expect_type": "tv",
        "expect_titles": ["beverly hillbillies"],
        "note": "Jed Clampett and Granny (S01E01, 14:05)",
        "origin": "The Beverly Hillbillies, season 1 episode 1 (1962)",
        "source_url": f"https://archive.org/details/{BEVERLY_HILLBILLIES}",
        "license": "Public domain in the US (copyright not renewed); hosted on archive.org",
        "fetch": {"kind": "ia", "item": BEVERLY_HILLBILLIES, "at": 845.0},
    },
    {
        "name": "game_hades",
        "file": "game_hades.jpg",
        "expect_type": "game",
        "expect_titles": ["hades"],
        "note": "Gameplay with HUD, boss health bar and boon icons",
        "origin": "Hades — official Steam store screenshot",
        "source_url": "https://store.steampowered.com/app/1145360/",
        "license": "© Supergiant Games — used locally as identification input only",
        "fetch": {"kind": "steam", "appid": 1145360, "shot": 0},
    },
    {
        "name": "game_the_witcher_3",
        "file": "game_the_witcher_3.jpg",
        "expect_type": "game",
        "expect_titles": ["witcher"],
        "note": "Geralt character close-up (no HUD)",
        "origin": "The Witcher 3: Wild Hunt — official Steam store screenshot",
        "source_url": "https://store.steampowered.com/app/292030/",
        "license": "© CD Projekt Red — used locally as identification input only",
        "fetch": {"kind": "steam", "appid": 292030, "shot": 3},
    },
    {
        "name": "game_cyberpunk_2077",
        "file": "game_cyberpunk_2077.jpg",
        "expect_type": "game",
        "expect_titles": ["cyberpunk"],
        "note": "Cinematic vehicle shot (no HUD) — the hard case",
        "origin": "Cyberpunk 2077 — official Steam store screenshot",
        "source_url": "https://store.steampowered.com/app/1091500/",
        "license": "© CD Projekt Red — used locally as identification input only",
        "fetch": {"kind": "steam", "appid": 1091500, "shot": 4},
    },
]

MANIFEST_NAME = "manifest.json"


# ----------------------------------------------------------------------
# Fixture fetching
# ----------------------------------------------------------------------


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def _video_duration(video: Path) -> float:
    result = subprocess.run(
        [_ffmpeg() or "ffmpeg", "-hide_banner", "-i", str(video)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError(f"could not read the duration of {video.name}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _smallest_video(item: str, max_bytes: int = 400_000_000) -> str:
    payload = httpx.get(
        f"https://archive.org/metadata/{item}", headers=USER_AGENT, timeout=45
    ).json()
    options = [
        (entry["name"], int(entry.get("size") or 0))
        for entry in payload.get("files", [])
        if entry.get("name", "").lower().endswith((".mp4", ".ogv"))
        and 0 < int(entry.get("size") or 0) <= max_bytes
    ]
    if not options:
        raise RuntimeError(f"no downloadable video in archive.org item {item}")
    return min(options, key=lambda pair: pair[1])[0]


def _download(url: str, target: Path) -> Path:
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"      downloading {target.name} …", flush=True)
    with httpx.stream("GET", url, headers=USER_AGENT, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    print(f"      saved {target.stat().st_size / 1e6:.1f} MB")
    return target


def _save_frame(image: Image.Image, target: Path) -> Path:
    if max(image.size) > 1280:
        image = image.copy()
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target, format="JPEG", quality=88)
    return target


def _fetch_archive_org(spec: dict[str, Any], target: Path, cache_dir: Path) -> Path:
    item = spec["item"]
    cached = sorted(cache_dir.glob(f"{item}__*"))
    if cached:
        video = cached[0]
    else:
        name = _smallest_video(item)
        url = f"https://archive.org/download/{item}/{urllib.parse.quote(name)}"
        video = _download(url, cache_dir / f"{item}__{Path(name).name}")

    at = float(spec["at"])
    if at <= 0:  # ratio of the runtime, resolved lazily
        at = _video_duration(video) * float(spec.get("ratio", 0.5))

    raw = target.with_suffix(".frame.jpg")
    subprocess.run(
        [
            _ffmpeg() or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(raw),
        ],
        check=True,
    )
    with Image.open(raw) as frame:
        _save_frame(frame, target)
    raw.unlink(missing_ok=True)
    return target


def _fetch_steam(spec: dict[str, Any], target: Path) -> Path:
    appid = str(spec["appid"])
    payload = httpx.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": appid, "l": "english"},
        headers=USER_AGENT,
        timeout=45,
    ).json()
    data = (payload.get(appid) or {}).get("data") or {}
    shots = data.get("screenshots") or []
    index = int(spec.get("shot", 0))
    if index >= len(shots):
        raise RuntimeError(f"app {appid} has no screenshot #{index}")
    print(f"      {data.get('name')} — {shots[index]['path_full']}")
    raw = httpx.get(shots[index]["path_full"], headers=USER_AGENT, timeout=60).content
    with Image.open(io.BytesIO(raw)) as image:
        _save_frame(image, target)
    return target


def fetch_fixtures(frames_dir: Path, only: list[str]) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = frames_dir / "_cache"
    manifest = read_manifest(frames_dir)
    known = {entry["file"]: entry for entry in manifest["frames"]}

    for fixture in BUILTIN_FIXTURES:
        if only and not any(token.lower() in fixture["name"].lower() for token in only):
            continue
        target = frames_dir / fixture["file"]
        entry = {key: value for key, value in fixture.items() if key != "fetch"}
        known[fixture["file"]] = entry
        if target.exists():
            print(f"   ✓ {fixture['file']} (cached)")
            continue
        if _ffmpeg() is None and fixture["fetch"]["kind"] == "ia":
            print(f"   ! {fixture['file']} — needs imageio-ffmpeg (pip install imageio-ffmpeg)")
            continue
        print(f"   · {fixture['file']}")
        try:
            if fixture["fetch"]["kind"] == "ia":
                _fetch_archive_org(fixture["fetch"], target, cache_dir)
            else:
                _fetch_steam(fixture["fetch"], target)
            print(f"   ✓ {fixture['file']}")
        except Exception as error:  # noqa: BLE001 - one bad fixture must not stop the rest
            print(f"   ✗ {fixture['file']}: {error}")

    manifest["frames"] = list(known.values())
    write_manifest(frames_dir, manifest)


def read_manifest(frames_dir: Path) -> dict[str, Any]:
    path = frames_dir / MANIFEST_NAME
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("frames"), list):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return {"version": 1, "frames": []}


def write_manifest(frames_dir: Path, manifest: dict[str, Any]) -> None:
    (frames_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def collect_frames(frames_dir: Path, only: list[str]) -> list[dict[str, Any]]:
    """Manifest entries that exist on disk, plus any extra images found there."""
    manifest = read_manifest(frames_dir)
    entries = [dict(entry) for entry in manifest["frames"]]
    listed = {entry.get("file") for entry in entries}

    for path in sorted(frames_dir.glob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or path.name in listed:
            continue
        entries.append(
            {
                "file": path.name,
                "name": path.stem,
                "expect_type": None,
                "expect_titles": [],
                "note": "unlabeled frame (excluded from the accuracy summary)",
                "origin": "local frame",
            }
        )

    usable = []
    for entry in entries:
        if only and not any(token.lower() in str(entry.get("name", entry.get("file"))).lower() for token in only):
            continue
        if (frames_dir / entry["file"]).is_file():
            usable.append(entry)
        else:
            print(f"   ! skipping {entry.get('file')} — file is missing")
    return usable


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def title_matches(expected_titles: list[str], got: str) -> bool:
    """Forgiving title comparison: substring, token cover or high similarity."""
    got_norm = _normalize(got)
    if not got_norm:
        return False
    for expected in expected_titles:
        expected_norm = _normalize(expected)
        if not expected_norm:
            continue
        if expected_norm in got_norm or got_norm in expected_norm:
            return True
        expected_tokens = set(expected_norm.split())
        if expected_tokens and expected_tokens <= set(got_norm.split()):
            return True
        if SequenceMatcher(None, expected_norm, got_norm).ratio() >= 0.72:
            return True
    return False


def describe_result(result: dict[str, Any] | None) -> str:
    """One line for a serialized result record."""
    if not result:
        return "no match"
    return (
        f"{result['tag']:<9} {result['title']!r}  {round(result['confidence'] * 100)}%"
        f"  ← {result['source']}"
    )


def verify_frame(entry: dict[str, Any], frames_dir: Path, router: IdentityRouter) -> dict[str, Any]:
    path = frames_dir / entry["file"]
    record: dict[str, Any] = {
        "file": entry["file"],
        "name": entry.get("name") or path.stem,
        "expect_type": entry.get("expect_type"),
        "expect_titles": entry.get("expect_titles") or [],
        "note": entry.get("note"),
        "origin": entry.get("origin"),
    }

    started = time.perf_counter()
    try:
        image = load_image(path)
        report = router.scan_sync(image)
    except Exception as error:  # noqa: BLE001 - report, never crash mid-run
        record["error"] = f"{type(error).__name__}: {error}"
        record["seconds"] = round(time.perf_counter() - started, 2)
        return record

    best = report.best
    record["seconds"] = round(time.perf_counter() - started, 2)
    record["used_fallback"] = report.used_fallback
    record["threshold"] = report.threshold
    record["engines"] = [
        {"name": status.name, "ok": status.ok, "detail": status.detail, "ms": status.elapsed_ms}
        for status in report.statuses
    ]
    record["notices"] = list(report.notices)
    record["result"] = None if best is None else {
        "media_type": best.media_type,
        "tag": best.tag,
        "title": best.title,
        "confidence": round(best.confidence, 4),
        "source": best.source,
        "year": best.year,
        "studio": best.studio,
        "season": best.season,
        "episode": best.episode,
        "timestamp": best.timestamp,
        "level": best.level,
        "evidence": best.evidence,
        "external_url": best.external_url,
    }
    record["ranked"] = [
        {
            "media_type": item.media_type,
            "tag": item.tag,
            "title": item.title,
            "confidence": round(item.confidence, 4),
            "source": item.source,
        }
        for item in ([best] if best else []) + list(report.alternatives)
    ]
    record["engine_candidates"] = [
        {"media_type": candidate.media_type, "tag": candidate.label, "title": candidate.title,
         "confidence": round(candidate.confidence, 4)}
        for candidate in (best.candidates if best else [])
    ]

    expect_type = entry.get("expect_type")
    if expect_type and best is not None:
        record["type_ok"] = best.media_type == expect_type
        record["type_loose_ok"] = (
            best.media_type == expect_type
            or (expect_type in {"movie", "tv"} and best.media_type in {"movie", "tv"})
        )
        record["title_ok"] = title_matches(record["expect_titles"], best.title)
        record["vision_won"] = best.source != "trace.moe"
    return record


def verify(frames_dir: Path, only: list[str], want_gui: bool) -> int:
    settings = load_settings()
    entries = collect_frames(frames_dir, only)

    print("\nSceneLens live verification")
    print("─" * 72)
    if not entries:
        print("No frames found. Run without --no-fetch, or drop images into testframes/.")
        return 2

    labeled = [entry for entry in entries if entry.get("expect_type")]
    print(f"frames          {len(entries)} ({len(labeled)} labeled)")
    print(f"vision engine   {settings.resolved_vision_model} @ {settings.resolved_vision_base_url}")
    print(f"vision key      {_key_source(settings)}")
    print(f"tmdb key        {'configured' if settings.tmdb_configured else 'not configured'}")

    if not settings.vision_configured:
        print("\nNo vision API key is configured, so movies, TV and games cannot be identified.")
        print("Add one in the app (Settings → Vision engine) or in .env:")
        print("   SCENELENS_VISION_API_KEY=…")
        print("   SCENELENS_VISION_BASE_URL=https://api.openai.com/v1")
        print("   SCENELENS_VISION_MODEL=gpt-4o-mini")
        print(f"Settings file:  {CONFIG_PATH}")
        return 2

    try:
        import asyncio

        ok, message = asyncio.run(VisionClient(settings).check_access())
    except EngineError as error:
        ok, message = False, error.message
    print(f"connection      {'OK' if ok else 'FAILED'} — {message}")
    if not ok:
        print("\nFix the key/endpoint before verifying identification.")
        return 2

    router = IdentityRouter(settings)
    records: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        print(f"\n[{index}/{len(entries)}] {entry['file']}")
        if entry.get("note"):
            print(f"      expect {entry.get('expect_type') or '?'} · {entry['note']}")
        record = verify_frame(entry, frames_dir, router)
        records.append(record)

        if "error" in record:
            print(f"      ERROR  {record['error']}")
            continue
        for status in record["engines"]:
            flag = "✓" if status["ok"] else "✗"
            print(f"      {flag} {status['name']:<26} {status['detail']} ({status['ms']} ms)")
        print(f"      → {describe_result(record.get('result'))}  ({record['seconds']}s)")
        if len(record["ranked"]) > 1:
            others = " · ".join(
                f"{item['tag']}/{item['title']} {round(item['confidence'] * 100)}%"
                for item in record["ranked"][1:]
            )
            print(f"      ranked others: {others}")
        if record.get("expect_type"):
            verdict = "PASS" if record.get("type_ok") else "TYPE MISMATCH"
            title = "title ✓" if record.get("title_ok") else "title ✗"
            print(f"      verdict {verdict} ({record['result']['media_type']} vs {record['expect_type']}) · {title}")

    summary = _summarize(records)
    print("\n" + "─" * 72)
    for line in summary["lines"]:
        print(line)

    gui_record = None
    if want_gui:
        target = next((record for record in records if record.get("expect_type") == "game"), None)
        target = target or next((record for record in records if "result" in record), None)
        if target:
            print("\nDriving the real SceneLens window with", target["file"])
            gui_record = verify_gui(frames_dir / target["file"], target["file"])
            print(f"   {gui_record.get('verdict')}")

    write_report(frames_dir, settings, records, summary, gui_record)

    failures = [record for record in records if record.get("expect_type") and not record.get("type_ok")]
    return 1 if failures else 0


def _key_source(settings: Settings) -> str:
    if settings.vision_api_key.strip():
        return f"app settings ({CONFIG_PATH})"
    import os

    for name in ("SCENELENS_VISION_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(name, "").strip():
            return f"environment/{name}"
    return "missing"


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [record for record in records if record.get("expect_type") and "result" in record]
    type_ok = [record for record in labeled if record.get("type_ok")]
    loose_ok = [record for record in labeled if record.get("type_loose_ok")]
    title_ok = [record for record in labeled if record.get("title_ok")]
    by_type: dict[str, list[bool]] = {}
    for record in labeled:
        by_type.setdefault(record["expect_type"], []).append(bool(record.get("type_ok")))

    lines = [
        f"classified correctly   {len(type_ok)}/{len(labeled)}",
        f"titles matched         {len(title_ok)}/{len(labeled)}",
        f"vision engine decided  {len([r for r in labeled if r.get('vision_won')])}/{len(labeled)}",
    ]
    for media_type, results in sorted(by_type.items()):
        lines.append(f"  {media_type:<6} {sum(1 for item in results if item)}/{len(results)}")
    errors = [record for record in records if "error" in record]
    if errors:
        lines.append(f"frames that errored    {len(errors)}")
    return {
        "labeled": len(labeled),
        "type_ok": len(type_ok),
        "type_loose_ok": len(loose_ok),
        "title_ok": len(title_ok),
        "errors": len(errors),
        "lines": lines,
    }


def verify_gui(image_path: Path, label: str) -> dict[str, Any]:
    """Run one live scan through the real window, offscreen, on a scratch history."""
    import scenelens.database.db as db_module
    import scenelens.gui.main_window as main_window
    import scenelens.utils.image_utils as image_utils

    record: dict[str, Any] = {"file": label}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        original_db = db_module.DB_PATH
        original_thumbs = image_utils.THUMB_DIR
        original_loader = main_window.load_settings
        db_module.DB_PATH = tmp_path / "verify.db"
        image_utils.THUMB_DIR = tmp_path / "thumbs"
        image_utils.THUMB_DIR.mkdir()
        main_window.load_settings = lambda: Settings(
            **{**load_settings().__dict__, "watch_clipboard": False}
        )

        app = None
        try:
            app = main_window.SceneLensApp()
            app.geometry("1340x880+-3000+0")
            app.update()
            app.start_scan(load_image(image_path), image_path)

            deadline = time.time() + 240
            while time.time() < deadline:
                app.update()
                if app.results_view is not None and getattr(app, "_mode", "") == "results":
                    break
                time.sleep(0.05)

            view = app.results_view
            best = getattr(view, "best", None)
            rendered = None
            label_widget = getattr(view, "title_label", None)
            if label_widget is not None:
                try:
                    rendered = str(label_widget.cget("text"))
                except Exception:  # noqa: BLE001
                    rendered = None
            record.update(
                {
                    "mode": getattr(app, "_mode", None),
                    "rendered_title": rendered,
                    "best_title": None if best is None else best.title,
                    "best_type": None if best is None else best.media_type,
                    "engine_log": [
                        f"{status.name}: {'ok' if status.ok else 'failed'} — {status.detail}"
                        for status in (getattr(getattr(view, "report", None), "statuses", []) or [])
                    ],
                }
            )
            if best is not None and rendered and best.title.lower()[:12] in rendered.lower():
                record["verdict"] = f"window rendered {best.tag} · {rendered!r}"
            elif best is not None:
                record["verdict"] = f"window rendered a result ({best.tag} · {best.title!r})"
            else:
                record["verdict"] = "window rendered no match"
        finally:
            if app is not None:
                app.destroy()
            db_module.DB_PATH = original_db
            image_utils.THUMB_DIR = original_thumbs
            main_window.load_settings = original_loader
    return record


def write_report(
    frames_dir: Path,
    settings: Settings,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    gui_record: dict[str, Any] | None,
) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "vision_model": settings.resolved_vision_model,
        "vision_base_url": settings.resolved_vision_base_url,
        "tmdb_configured": settings.tmdb_configured,
        "threshold": settings.confidence_threshold,
        "summary": summary,
        "frames": records,
        "gui": gui_record,
    }
    json_path = frames_dir / "verification-report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# SceneLens live verification",
        "",
        f"- run: {payload['generated_at']}",
        f"- vision engine: `{settings.resolved_vision_model}` @ {settings.resolved_vision_base_url}",
        f"- tmdb: {'configured' if settings.tmdb_configured else 'not configured'}",
        f"- confidence threshold: {settings.confidence_threshold}",
        "",
        "## Summary",
        "",
        *[f"- {line}" for line in summary["lines"]],
        "",
        "## Frames",
        "",
        "| frame | expected | got | confidence | engine | title | seconds |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        result = record.get("result") or {}
        lines.append(
            "| {file} | {expected} | {got} | {confidence} | {engine} | {title} | {seconds} |".format(
                file=record["file"],
                expected=record.get("expect_type") or "—",
                got=result.get("tag") or record.get("error") or "no match",
                confidence=f"{round(result.get('confidence', 0) * 100)}%" if result else "—",
                engine=result.get("source") or "—",
                title=result.get("title") or "—",
                seconds=record.get("seconds", "—"),
            )
        )
    lines += ["", "## Details", ""]
    for record in records:
        lines.append(f"### {record['file']}")
        lines.append("")
        lines.append(f"- expected: {record.get('expect_type')} · {record.get('expect_titles')}")
        lines.append(f"- frame: {record.get('note') or '—'}")
        lines.append(f"- origin: {record.get('origin') or '—'}")
        if record.get("result"):
            result = record["result"]
            lines.append(
                f"- result: **{result['tag']}** {result['title']!r} — {round(result['confidence'] * 100)}% "
                f"via {result['source']}"
            )
            if result.get("year") or result.get("studio") or result.get("episode") or result.get("timestamp"):
                lines.append(
                    "- metadata: "
                    + ", ".join(
                        part
                        for part in (
                            f"year {result['year']}" if result.get("year") else "",
                            f"studio {result['studio']}" if result.get("studio") else "",
                            f"S{result['season']:02d}" if result.get("season") else "",
                            f"E{result['episode']:02d}" if result.get("episode") else "",
                            f"at {result['timestamp']}" if result.get("timestamp") else "",
                        )
                        if part
                    )
                )
            if result.get("evidence"):
                lines.append(f"- model evidence: {result['evidence']}")
        if record.get("ranked"):
            lines.append(
                "- ranked: "
                + " · ".join(
                    f"{item['tag']}/{item['title']} {round(item['confidence'] * 100)}%"
                    for item in record["ranked"]
                )
            )
        for status in record.get("engines") or []:
            lines.append(
                f"- engine {status['name']}: {'ok' if status['ok'] else 'failed'} — {status['detail']} "
                f"({status['ms']} ms)"
            )
        for notice in record.get("notices") or []:
            lines.append(f"- notice: {notice}")
        if record.get("error"):
            lines.append(f"- error: {record['error']}")
        lines.append("")
    if gui_record:
        lines += ["## Window check", "", f"- {gui_record.get('verdict')}"]
        for entry in gui_record.get("engine_log") or []:
            lines.append(f"- {entry}")
        lines.append("")

    md_path = frames_dir / "verification-report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport  {json_path}")
    print(f"report  {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live end-to-end verification for SceneLens")
    parser.add_argument("--frames", default=str(PROJECT_ROOT / "testframes"),
                        help="folder holding the fixture frames (default: testframes/)")
    parser.add_argument("--only", action="append", default=[],
                        help="verify only frames whose name contains this text (repeatable)")
    parser.add_argument("--no-fetch", action="store_true", help="do not download fixtures")
    parser.add_argument("--gui", action="store_true", help="also drive one live scan through the window")
    parser.add_argument("--list", action="store_true", help="list the fixture set and exit")
    args = parser.parse_args()

    frames_dir = Path(args.frames)
    if args.list:
        for fixture in BUILTIN_FIXTURES:
            print(f"{fixture['name']:<32} expect {fixture['expect_type']:<6} {fixture['note']}")
            print(f"{'':32} {fixture['origin']}")
            print(f"{'':32} {fixture['source_url']}")
        return 0

    if not args.no_fetch:
        missing = [
            fixture
            for fixture in BUILTIN_FIXTURES
            if not (frames_dir / fixture["file"]).is_file()
            and (not args.only or any(token.lower() in fixture["name"].lower() for token in args.only))
        ]
        if missing:
            print(f"Fetching {len(missing)} fixture frame(s) into {frames_dir}")
            fetch_fixtures(frames_dir, args.only)

    return verify(frames_dir, args.only, args.gui)


if __name__ == "__main__":
    raise SystemExit(main())

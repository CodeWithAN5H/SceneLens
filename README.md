# SceneLens

A dark-mode desktop app that identifies a single frame from **anime, movies, TV
series or video games** and turns the match into a shareable Discord card.

Built with Python 3.10+, CustomTkinter, Pillow, httpx and SQLite.

## Highlights

- **Drop, browse or paste** a PNG / JPG / WEBP frame, or let the clipboard
  watcher notice a freshly copied image.
- **Scanner animation** while engines work in a background thread — the window
  never freezes.
- **Unified results view** with your frame beside the matched reference frame,
  media tag, title, year, studio, season/episode/timestamp/level, and a
  confidence meter.
- **Anime scene matching** through the free [trace.moe](https://trace.moe)
  index: exact episode and second, plus a preview clip.
- **Movies, TV and games** through any OpenAI-compatible multimodal vision model.
- **Optional TMDB + Steam enrichment** for posters, canonical titles, studios
  and box art.
- **Low-confidence fallback** with the top three alternatives and quick links to
  IMDb, IGDB, MyAnimeList, AniList or Steam.
- **One-click Discord sharing**: copies Discord markdown, or renders a 1080×660
  PNG card and copies it as an image on Windows (and on Linux with xclip); the
  PNG is always saved to your exports folder.
- **Local SQLite history** with thumbnails, recent scans in the sidebar, and a
  full history tab. Nothing is synced to a server.

## Quick start (Windows)

```bat
run.bat
```

On first run the launcher creates `.venv`, installs the requirements and starts
the app. You can also do it manually:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

You can open a frame directly:

```bat
.venv\Scripts\python.exe app.py "C:\screenshots\frame.png"
```

## Standalone Windows build

The default build is a **folder build**, which starts as fast as a normally
installed app because nothing is unpacked at launch:

```bat
build.bat                                  :: -> dist\SceneLens\SceneLens.exe  (default)
build.bat onefile                          :: -> dist\SceneLens.exe            (single file)
```

Both shapes bundle CPython, Tk, CustomTkinter (themes, fonts, icons), the tkdnd
drag-and-drop extension and the app icon, so they run on a Windows machine with
no Python installed. `build.bat` installs PyInstaller into `.venv` and is a thin
wrapper around the checked-in recipe:

```bat
set SCENELENS_PACKAGE=folder      :: or onefile
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean SceneLens.spec
```

Measured window-visible times on this machine (warm run, `SceneLens.exe frame.png`):

| shape | output | launch | size |
| --- | --- | --- | --- |
| folder (default) | `dist\SceneLens\SceneLens.exe` | ~0.6 s | 5.5 MB exe in a 48 MB folder |
| onefile | `dist\SceneLens.exe` | ~1.7 s | 23 MB single file |

The first run of either shape is slower (cold file cache and a virus scan of the
freshly written output). Copy the folder build anywhere — it is relocatable —
while the single file is convenient when you need to hand over one file.

### Windows installer

For distribution, build a proper installer with file properties shown in
Explorer (right-click the exe → Properties → Details):

```bat
build.bat installer                     :: -> dist\SceneLens-Setup-1.0.0.exe
```

This builds the folder shape first, then compiles [installer/SceneLens.iss](installer/SceneLens.iss)
with [Inno Setup 6](https://jrsoftware.org/isinfo.php) (install it once with
`winget install --id JRSoftware.InnoSetup`). The installer:

- installs per-user into `%LOCALAPPDATA%\Programs\SceneLens` — no admin prompt;
- creates Start Menu entries and an optional desktop shortcut;
- registers an uninstaller in Windows Apps & Features;
- leaves `%APPDATA%\SceneLens` (settings, history, exports) untouched when
  uninstalling;
- embeds its own version resource, so `SceneLens-Setup-1.0.0.exe` shows the
  same 1.0.0.0 file properties as the app.

Silent install / uninstall (useful for scripted rollouts):

```bat
SceneLens-Setup-1.0.0.exe /VERYSILENT /NORESTART
%LOCALAPPDATA%\Programs\SceneLens\unins000.exe /VERYSILENT /NORESTART
```

Both `SceneLens.exe` and the setup exe embed a PE version resource generated
from the constants in `scenelens/config.py` (`APP_VERSION`, `APP_DESCRIPTION`,
…), so bump the version there once — the app build and the installer both pick
it up.

Notes:

- The executable icon is generated from the same code-drawn artwork as the window
  icon (`scenelens/gui/glyphs.py`), so no binary asset is stored in the
  repository. `dist/` and `build/` are git-ignored.
- Building one shape removes the other shape's output from `dist/` so the folder
  never shows a stale executable.
- Scan history, settings and logs still live in the per-user app-data folder
  (`%APPDATA%\SceneLens`), so replacing the executable never touches your data.
- The executables are unsigned, so Windows SmartScreen may warn on first run.
- `SceneLens.exe frame.png` opens and identifies a frame immediately.

## API keys

Anime matching works with no account. Results are labelled **unverified** until
a vision key is configured, because trace.moe returns its nearest frame for any
image.

Open **Settings** (⚙ in the sidebar or `Ctrl+,`) and add:

| Field | Needed for | Notes |
| --- | --- | --- |
| Vision API key | Movies, TV series, games | Any OpenAI-compatible endpoint with image input |
| Vision base URL | — | Defaults to `https://api.openai.com/v1` |
| Vision model | — | Defaults to `gpt-4o-mini`; set your provider's vision model |
| TMDB API key | Posters, canonical film metadata | Optional and free at themoviedb.org |

Settings → **Test connection** checks the endpoint's `/models` route. Nothing is
sent anywhere until you scan.

Keys saved in the app are stored only in the per-user config file. For
development you can instead copy `.env.example` to `.env` and fill it in;
`OPENAI_API_KEY` and `OPENAI_BASE_URL` are also accepted.

```text
Any OpenAI-compatible endpoint works, e.g. OpenAI, an OpenRouter-compatible
gateway, or a local vLLM/Ollama OpenAI proxy.
```

## Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+V` | Scan the clipboard image |
| `Ctrl+O` | Browse for an image |
| `Ctrl+N` | New scan |
| `Ctrl+H` | Scan history |
| `Ctrl+,` | Settings |
| `Esc` | Close the settings dialog |

## How identification works

1. The image is normalized and JPEG-encoded (max 1280 px) in a worker thread.
2. Two engines run concurrently:
   - **trace.moe** for anime frames (episode, timestamp, similarity, clip).
   - **Vision model** for film/TV/game classification and title candidates.
3. Results are normalized into one `MediaResult`, deduplicated and ranked.
4. The winner is enriched via TMDB (film/TV) or Steam search (games).
5. If the best confidence is below your threshold, the result screen switches to
   the fallback panel: top three closest candidates with external search links.
6. Every confident result is stored in SQLite with a thumbnail.

**On trace.moe similarity:** trace.moe always returns its nearest indexed frames,
even for unrelated images, so its similarity score is not a universal confidence
value. SceneLens treats it as anime evidence and demotes it when a vision model
confidently names another medium. With no vision key, anime results are labelled
UNVERIFIED · ANIME and carry an explanatory notice.

## Project layout

```text
app.py                      Entry point, DPI awareness, logging
scenelens/
  config.py                 Paths, API keys, persisted settings
  models.py                 MediaResult + normalized candidate model
  theme.py                  Shared palette (GUI + share card)
  engines/
    router.py               Concurrent cascade, ranking, enrichment
    anime_engine.py         trace.moe upload + AniList metadata parsing
    vision.py               OpenAI-compatible multimodal client + prompts
    movie_engine.py         Film/TV normalization + TMDB enrichment
    game_engine.py          Game normalization + Steam enrichment
    vision_fallback.py      Dedupe, ranking, top-3 fallback candidates
    base.py                 Normalization and engine error types
  gui/
    main_window.py          Window, navigation, scanning, clipboard queue
    drop_zone.py            Drag-and-drop landing view
    scan_view.py            Scanner animation and live stage messages
    results_view.py         Comparison, metadata, fallback, sharing
    history_view.py         SQLite history tab
    sidebar.py              Brand, nav, recent scans, engine status
    settings_dialog.py      Keys, threshold and clipboard options
    widgets.py              Badges, image panels, toasts, dialogs
  utils/
    image_utils.py          Pillow loading, resize, thumbnails
    clipboard.py            Clipboard read, watcher, copy helpers
    discord_card.py         Markdown + PNG card renderer
    remote.py               Cached reference-frame downloads
  database/db.py            SQLite schema and history store
scripts/smoke_test.py       Offline engine/UI smoke tests
```

## Local data

Everything lives under the current user's application-data directory:

```text
Windows  %APPDATA%\SceneLens\
macOS    ~/Library/Application Support/SceneLens/
Linux    ~/.local/share/SceneLens/
```

- `scenelens.db` — scan history
- `config.json` — settings and API keys
- `thumbnails/` — history preview images
- `exports/` — generated share cards
- `scenelens.log` — rotating diagnostics log

## Tests

The default suite is offline: the vision, TMDB and Steam endpoints are replaced
by a local mock server, and trace.moe is stubbed for the router test.

```bat
.venv\Scripts\python.exe scripts\smoke_test.py
.venv\Scripts\python.exe scripts\smoke_test.py --gui
.venv\Scripts\python.exe scripts\smoke_test.py --live   :: hits trace.moe
```

## Live verification

`scripts/verify_vision.py` checks the real engines with your own key instead of
mocks. It builds a fixture set in `testframes/` (one frame per fixture: silent-era
public-domain film and TV from archive.org, plus official Steam store screenshots
for games), scans every frame through the same pipeline the app uses, and reports
whether the media type and title matched the known ground truth. It writes
`testframes/verification-report.json` and `.md`.

```bat
.venv\Scripts\python.exe scripts\verify_vision.py          :: verify all fixtures
.venv\Scripts\python.exe scripts\verify_vision.py --gui    :: also drive the real window
.venv\Scripts\python.exe scripts\verify_vision.py --list   :: show the fixture set
.venv\Scripts\python.exe scripts\verify_vision.py --no-fetch
```

Fetching fixtures needs `imageio-ffmpeg` (a bundled ffmpeg binary) and network
access:

```bat
.venv\Scripts\python.exe -m pip install imageio-ffmpeg
```

To verify modern film/TV frames, drop your own PNG/JPG into `testframes/` and add
an entry to `testframes/manifest.json`:

```json
{"file": "my_frame.jpg", "expect_type": "tv", "expect_titles": ["severance"], "note": "S01E03 corridor"}
```

Unlabeled images are scanned and reported but excluded from the accuracy summary.
Fixture media is git-ignored; only your own frames stay in the working copy.

## Notes and limitations

- **Anime season numbers** are not part of trace.moe's response, so only the
  episode and timestamp are shown for anime (season appears when a vision model
  supplies it).
- **Clipboard watching** runs while SceneLens is open; it detects a new clipboard
  image even when the window is unfocused. There is no OS-wide hotkey because
  that would require a privileged global keyboard hook.
- **Drag and drop** uses `tkinterdnd2`; browse and paste still work if the drag
  library cannot load.
- **Linux clipboard reads** depend on `xclip`/`xsel` being installed.
- **TMDB and Steam enrichment** are best-effort; a network failure never fails a
  scan.
- The first run creates `assets/icon.png` from code, so the repository ships no
  binary assets.

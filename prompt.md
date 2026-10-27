# Role & Project Overview
You are an expert full-stack desktop software engineer. Your task is to build a modern, high-performance, dark-mode desktop application named **SceneLens**.

**SceneLens** is a universal media and game identifier desktop app. Users can drag-and-drop or paste (via clipboard hotkey) any screenshot, video frame, or image clip, and the app will instantly identify whether it is from an Anime, Video Game, Movie, or Web Series. It provides exact title details, season/episode/timestamp info (where applicable), creator/studio metadata, and generates an aesthetic, shareable summary card ready to copy straight into Discord or social media.

---

# Key Features & Requirements

### 1. Modern Dark-Mode GUI
* **Design System:** Minimalist, cyberpunk/sleek dark aesthetic (Deep dark backgrounds `#0F1117`, clean borders `#1F2430`, vibrant accents like Neon Cyan `#00E5FF` or Violet `#7C4DFF`).
* **Drop Zone:** Prominent central drag-and-drop zone supporting PNG, JPG, WEBP formats, plus a clear "Paste from Clipboard" button (`Ctrl+V`).
* **Live Status:** Smooth loading state with a scanner overlay effect while an image is being processed.
* **Results View:** Clean multi-column card layout displaying:
  * Uploaded thumbnail vs. matched reference frame.
  * Media Type Tag (`[ANIME]`, `[GAME]`, `[MOVIE]`, `[TV SERIES]`).
  * Main Title, Release Year, Studio/Developer.
  * Exact Episode / Season / Timestamp / Game Level (if available).
  * Confidence score badge.
* **Discord Share Card Generator:** One-click button to export/copy a beautifully formatted markdown card or styled summary image to clipboard.

### 2. Multi-Engine Identification Pipeline
Build a modular recognition engine that cascades through identification services:
* **Anime Matcher Engine:** Connect to open APIs (e.g., Trace.moe API) to pinpoint exact anime title, episode number, exact timestamp, and preview video clip.
* **Movies & TV Series Engine:** Multi-modal image identification API (e.g., Google Lens/Vision API, TMDB visual search, or a local/API multimodal vision model like Gemini Vision / Qwen-VL) to return title, year, season, and episode details.
* **Video Game Engine:** Multimodal vision processing tuned to recognize game HUDs, art styles, character models, UI layouts, and game titles.
* **Fallback Handler:** If confidence is below threshold, display top 3 closest potential matches with quick search links (IMDb, IGDB, MyAnimeList).

### 3. Desktop Integration & Utility
* **Global Clipboard Listener:** Ability to instantly pull images from the system clipboard.
* **History Log:** Persistent local SQLite database saving past scans so users can browse previously identified scenes.

---

# Recommended Tech Architecture
* **Language/Framework:** Python 3.10+ using `CustomTkinter` or `PyQt6` for native desktop look & feel, OR `Electron` / `Tauri` with React + Tailwind CSS.
* **Image Processing:** `Pillow` (PIL) and `OpenCV` for image handling, resizing, clipboard extraction, and format conversions.
* **Async & Networking:** `requests` / `httpx` / `aiohttp` for non-blocking API requests.
* **Storage:** Local `sqlite3` database for scan history and user settings.

---

# Initial Code Structure Plan
Organize the codebase cleanly into modules:
`app.py` / `main.py` - Entry point and GUI main window initialization.
`gui/` - Layout components, drag-drop zone, dark mode theme configs, result cards.
`engines/` - Modular matchers (`anime_engine.py`, `movie_engine.py`, `game_engine.py`, `vision_fallback.py`).
`utils/` - Clipboard watcher, image preprocessor, Discord card formatting helper.
`database/` - SQLite manager for local scan history.

---

# Implementation Step-by-Step Instructions
1. Setup the main window, application layout, drag-and-drop zone, and event handlers for clipboard images.
2. Build the API/Engine routing logic: send input image through matchers asynchronously without freezing the GUI main loop.
3. Parse and normalize API responses into a unified `MediaResult` data model.
4. Render the results view with image previews, metadata tags, and the Discord card generator export button.
5. Add SQLite database support to store local scan history in a side drawer or history tab.

Generate clean, robust, well-commented code. Start by laying out the project file structure and building the core desktop GUI layout and drop zone.
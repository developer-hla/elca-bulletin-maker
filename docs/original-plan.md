# Church Bulletin Generator — Project Plan

## Overview

A tool that takes a **date + hymn numbers** as input and outputs a print-ready Word document (.docx) formatted as a legal-paper saddle-stitched booklet. Content is sourced automatically from Sundays & Seasons (sundaysandseasons.com).

---

## Physical Bulletin Format

- **Paper:** Legal (8.5" × 14"), folded in half
- **Page size:** Each bulletin "page" is 8.5" × 7"
- **Binding:** Pages come in multiples of 4 (each sheet = 4 bulletin pages)
- **Insert:** When there's an odd number of page groups, a half-sheet insert (8.5" × 7") is used for announcements/graphics — this is done manually in Word and slipped in separately

---

## Architecture

### Input
- Liturgical date (e.g., `2025-03-02`)
- List of hymn numbers (e.g., `ELW 504, ELW 779`)

### Output
- A `.docx` file on legal paper, fold-ready, containing:
  - Liturgical readings and scriptures
  - Prayers and propers for the day
  - Hymn text with scored notation (embedded as images)
  - Logos and formatting matching the existing bulletin template

### Separate (Manual)
- Announcements insert — created manually in Word as needed, printed separately and tucked in

---

## Tech Stack

### Backend
- **Python** + **FastAPI** — web server and API logic
- **httpx** — HTTP requests to Sundays & Seasons (no browser needed at runtime)
- **python-docx** — bulletin document generation
- **python-dotenv** — reading credentials from `.env`
- **uvicorn** — ASGI server to run FastAPI

### Frontend
- Single HTML/JS page served by FastAPI
- Form fields: date picker, hymn number inputs, optional insert upload
- "Generate Bulletin" button that triggers download of the `.docx`

### Dev Only (not shipped to end users)
- **Playwright** — for reverse-engineering the Sundays & Seasons API
- **mitmproxy** — optional fallback for API capture

---

## Repo Structure

```
bulletin-generator/
├── setup.py                  # One-time setup: venv, deps, credentials
├── start.bat                 # Windows: activate venv and launch server
├── start.sh                  # macOS: activate venv and launch server
├── .env.example              # Template: SNDS_USERNAME, SNDS_PASSWORD
├── .gitignore                # Exclude .env, venv, __pycache__, etc.
├── requirements.txt          # Production dependencies only
├── requirements-dev.txt      # Playwright, mitmproxy, etc. (dev only)
├── backend/
│   ├── main.py               # FastAPI app, routes
│   ├── sns_client.py         # All Sundays & Seasons API calls
│   └── docx_builder.py       # Bulletin DOCX generation logic
├── frontend/
│   └── index.html            # Single-page UI
└── template/
    └── bulletin.docx         # Master Word template with styles/logo
```

---

## Deployment

- **Platform:** Windows and macOS (developed on Mac)
- **Distribution:** Private GitHub repo, manual install on ~3 machines
- **Install process:** Clone repo → run `setup.py` → use `start.bat` or `start.sh`
- **Updates:** `git pull` from each machine (optionally exposed as a button in the UI)
- **Credentials:** Stored in a local `.env` file, never committed to the repo

### Cross-Platform Notes
- Use `pathlib.Path` everywhere — never hardcoded string paths with slashes
- Virtual env activation differs: `venv\Scripts\activate` (Windows) vs `venv/bin/activate` (Mac)
- `start.bat` for Windows, `start.sh` for Mac
- Playwright browser binaries: `playwright install chromium` runs during dev setup only
- `python-docx` is pure Python — identical behavior on both platforms

---

## Data Flows

### 1. Date → Liturgical Content
Given a date, determine the Sunday or feast day in the liturgical calendar and fetch:
- Assigned lectionary readings
- Psalm
- Gospel
- Prayers of intercession
- Propers (collect, etc.)

**API discovery needed:** Browse to several day types in Sundays & Seasons with Playwright to capture endpoint patterns:
- Ordinary Sunday
- Major feast (Christmas, Easter)
- Minor festival

### 2. Hymn Numbers → Hymn Content
Given a list of ELW numbers, fetch:
- Hymn title
- Tune name
- Scored notation (expected to be served as image assets)
- Copyright line

**Note:** If the site uses internal IDs that hymn numbers map to, two requests may be needed — a lookup and then a detail fetch.

---

## Bulletin Content & Formatting

- **Scored notation:** Embedded as images (currently screenshots in the existing Word bulletin — expected to be served as image assets from Sundays & Seasons)
- **Liturgical formatting:** Bold for congregation parts, italic for leader cues
- **Logo:** Embedded in the Word template
- **Styles:** Defined once in `bulletin.docx` template; script pours content in

---

## Development Phases

### Phase 1 — API Discovery
Run Playwright capture script while manually browsing Sundays & Seasons. Log all requests/responses to `captured_requests.json`. Identify:
- Authentication mechanism (session cookie, Bearer token, CSRF token)
- Endpoint patterns for liturgical content by date
- Endpoint patterns for hymn lookup and detail
- How notation images are served

### Phase 2 — Word Template
Build `template/bulletin.docx` in Word with:
- Legal paper size, correct margins for folded booklet
- All paragraph styles defined (heading, body, congregation response, leader cue)
- Logo and decorative elements placed
- Image placeholder zones for notation

### Phase 3 — Python Script
Build `sns_client.py` and `docx_builder.py`:
- Authenticate with Sundays & Seasons using credentials from `.env`
- Fetch liturgical content by date
- Fetch hymn content by ELW number
- Download notation images
- Populate the Word template and output a `.docx`

### Phase 4 — Web UI
Build `frontend/index.html` and wire up `main.py` FastAPI routes:
- Date picker
- Hymn number input fields (add/remove dynamically)
- Optional announcements insert upload
- Generate button → downloads completed `.docx`
- Optional: "Check for updates" button that runs `git pull`

### Phase 5 — Packaging & Install
- Write `setup.py` (prompts for credentials, creates `.env`, installs deps, verifies login)
- Write `start.bat` and `start.sh`
- Test fresh install on both Windows and macOS
- Document the install process in `README.md`

---

## Setup Script Behavior (`setup.py`)

1. Check Python version
2. Create virtual environment
3. Install `requirements.txt`
4. Prompt for Sundays & Seasons username and password
5. Write `.env` file
6. Do a test login to verify credentials work
7. Print instructions for launching the app

---

## `.env` Format

```
SNDS_USERNAME=your@email.com
SNDS_PASSWORD=yourpassword
```

---

## Key Open Questions (resolved by Phase 1 Playwright capture)

- What authentication mechanism does the site use?
- What are the exact endpoint URLs for liturgical content and hymns?
- Are hymn numbers used directly in API calls or do they map to internal IDs?
- Are notation images served as direct URLs in the API response?
- Does the response structure differ between ordinary Sundays and feast days?

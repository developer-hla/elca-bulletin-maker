# Bulletin Maker

Automated church bulletin generator for Ascension Lutheran Church (Jackson, MS). Takes a date and hymn selections, fetches liturgical content from Sundays & Seasons, and produces four print-ready PDF documents.

## Output Documents

1. **Bulletin for Congregation** — Legal-size saddle-stitched booklet with notation images
2. **Full with Hymns LARGE PRINT** — Letter-size, single-column, all text (no notation except Gospel Acclamation)
3. **Pulpit Scripture** — Letter front/back readings + psalm for the scripture reader
4. **Pulpit Prayers** — Letter front/back creed + prayers for the prayer leader

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[app]"
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your Sundays & Seasons credentials:

```
SNDS_USERNAME=your@email.com
SNDS_PASSWORD=yourpassword
```

## Usage

Launch the desktop wizard:

```bash
bulletin-maker
```

Or run directly:

```bash
venv/bin/python -m bulletin_maker.ui.app
```

## Development

```bash
pip install -e ".[dev]"
venv/bin/python -m pytest tests/ -v
```

## Project Structure

- `src/bulletin_maker/sns/` — Sundays & Seasons client (auth, content fetching, hymn search/download)
- `src/bulletin_maker/renderer/` — HTML/CSS + Playwright PDF generation (4 document types)
- `src/bulletin_maker/ui/` — pywebview desktop wizard application
- `src/bulletin_maker/exceptions.py` — Custom exception hierarchy
- `tests/` — Pytest test suite with fixtures in `tests/fixtures/`
- `scripts/` — Dev utilities (generate_test, visual_diff, test_sns_client)

# Bulletin Maker

Automated church bulletin generator for Ascension Lutheran Church (Jackson, MS). Takes a date and hymn numbers, fetches content from Sundays & Seasons, and produces print-ready Word documents.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in your Sundays & Seasons credentials:

```
SNDS_USERNAME=your@email.com
SNDS_PASSWORD=yourpassword
```

## Verify

```bash
python -c "from bulletin_maker.sns import SundaysClient; print('OK')"
python tests/test_sns_client.py
```

## Project Structure

- `src/bulletin_maker/sns/` — Sundays & Seasons client (auth, content fetching, hymn search)
- `src/bulletin_maker/renderer/` — Document generation (planned)
- `src/bulletin_maker/web/` — FastAPI UI (planned)
- `tests/` — Test suite
- `scripts/` — Dev-only tools (network capture)
- `docs/` — Format specs and API documentation

# Bulletin Maker

Automated church bulletin generator for Ascension Lutheran Church (Jackson, MS). Takes a date and hymn selections, fetches liturgical content from Sundays & Seasons, and produces five print-ready PDF documents.

## Output Documents

1. **Bulletin for Congregation** — Legal-size saddle-stitched booklet with notation images
2. **Full with Hymns LARGE PRINT** — Letter-size, single-column, all text (no notation except Gospel Acclamation)
3. **Leader Guide** — Large print plus sung notation pages for the pastor
4. **Pulpit Scripture** — Letter front/back readings + psalm for the scripture reader
5. **Pulpit Prayers** — Letter front/back creed + prayers for the prayer leader

## Install

With [uv](https://docs.astral.sh/uv/) (recommended — one command, easy updates):

```bash
uv tool install git+https://github.com/developer-hla/elca-bulletin-maker
```

Or with pip: `pip install git+https://github.com/developer-hla/elca-bulletin-maker`

## Run

```bash
bulletin-maker
```

The wizard opens in your browser; the first run downloads the PDF
renderer (Chromium) automatically. On a fresh install you register your
church (one time) and, under Settings, link the church's Sundays &
Seasons account — after that, volunteers sign in with their own simple
accounts (created with the church's invite code) and never handle the
S&S password.

## Update

```bash
uv tool upgrade bulletin-maker
```

## Another congregation?

Everything a church customizes lives in Settings inside the app: name,
address, service time, welcome text, license footer, plus the two
bounded options (ELW liturgical setting and paper size). Everything
else — the five documents, their layout, and the liturgy — is fixed
house style by design. To host one instance for several churches, see
`docs/hosted-deploy.md` and `docs/hosted-hardening.md`.

## Development

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
python -m pytest tests/ -v            # fast suite
python -m pytest tests/ -m layout -v  # layout regression (renders real PDFs)
```

## Project Structure

- `src/bulletin_maker/sns/` — Sundays & Seasons client (auth, content fetching, hymn search/download)
- `src/bulletin_maker/renderer/` — HTML/CSS + Playwright PDF generation (5 document types)
- `src/bulletin_maker/web/` — FastAPI server, accounts (PostgreSQL + encrypted S&S vault), entry point
- `src/bulletin_maker/ui/templates/` — wizard SPA (HTML/JS/CSS)
- `src/bulletin_maker/exceptions.py` — Custom exception hierarchy
- `tests/` — Pytest test suite with fixtures in `tests/fixtures/`
- `scripts/` — Dev utilities (generate_test, test_sns_client)

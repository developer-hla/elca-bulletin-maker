# Project Instructions

## Git Commits
- One-line commit messages only (no body, no co-author tags)
- Imperative mood ("Add feature" not "Added feature")
- Keep under 72 characters

## Python
- Target Python 3.9.6 — always use `from __future__ import annotations`
- Virtual env: `venv/bin/python`
- Run tests: `venv/bin/python -m pytest tests/ -v`

## Project Structure
- `src/bulletin_maker/sns/` — Sundays & Seasons API client
- `src/bulletin_maker/renderer/` — HTML/CSS + Playwright PDF generation
- `src/bulletin_maker/exceptions.py` — Custom exception hierarchy
- `scripts/` — Dev utilities (generate_test, visual_diff, test_sns_client)
- `tests/` — Pytest test suite with fixtures in `tests/fixtures/`

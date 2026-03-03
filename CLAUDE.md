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
- `scripts/` — Dev utilities (generate_test, visual_diff, test_sns_client, explore_and_download)
- `scripts/data/` — Exploration output (JSON dumps, API responses) — scripts should save here
- `docs/` — API discovery notes and reference docs
- `tests/` — Pytest test suite with fixtures in `tests/fixtures/`

## CLEAN Code Standards
- **Early returns**: Exit early to reduce nesting — avoid deep if/else chains
- **Small functions**: Keep functions short and focused — split when doing too many things
- **Minimal parameters**: Limit function parameters (ideally 3 or fewer); use dataclasses or config objects to group related params
- **No nested control structures**: Don't nest if/for/while inside each other; extract to helper functions or flatten with boolean logic
- **Self-documenting code**: Use clear, descriptive names — don't rely on comments to explain intent
- **Use temp variables**: Don't nest function calls as arguments — assign to a variable first
- **Single responsibility**: Each function should do one thing well
- **No magic values**: Extract magic numbers/strings into named constants
- **DRY**: Extract duplicated logic into reusable functions — never copy-paste code blocks

## Comments
- Do not add comments, docstrings, or type annotations to code you didn't change
- Only add comments where the logic isn't self-evident from clear naming
- Prefer self-documenting code over comments

## Error Handling
- **Fail fast**: No silent fallbacks — raise explicit errors, fail loudly on misconfiguration
- Let exceptions bubble up naturally — don't catch and re-raise without adding value
- Minimize try/except — only catch when you can meaningfully handle or transform the error
- Never silently swallow exceptions — always log if catching
- Prefer specific exception types over bare `except Exception`

## Logging
- Log warnings and errors only — avoid `logger.info()` for routine operations
- Don't log function entry/exit or successful operations
- `logger.warning()` for recoverable issues needing attention
- `logger.error()` for errors that affect functionality

## Imports
- All imports at top of file — no inline imports inside functions
- Exception: Playwright and pypdf use lazy imports in `pdf_engine.py` to avoid heavy startup cost

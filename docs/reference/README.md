# Known-Good Setup & Artifacts — Reference Snapshot

Captured July 20, 2026. This preserves the current, verified-correct Ascension setup and the
bulletins it produces, so the careful layout/formatting work is never lost and there's a visual
golden to compare against.

## Where the "looks correct and nice" work actually lives (all in git + pushed to GitHub)

Everything that determines how the bulletins look is version-controlled — losing the database or a
machine loses nothing:

| What | Path (in the repo) |
|---|---|
| Congregation profile (identity, address, welcome, standing instructions, copyright, **liturgical setting = Setting Two**, paper size) | `src/bulletin_maker/profiles/ascension.toml` |
| Rites (the service structures, as data) | `src/bulletin_maker/core/library/*.json` — Holy Communion, Service of the Word, Morning/Evening/Night Prayer, Holy Baptism module |
| Print templates + CSS (the actual layout) | `src/bulletin_maker/renderer/templates/html/*.html` + `*.css` |
| Bundled Setting Two notation images | `src/bulletin_maker/renderer/assets/setting_two/*.jpg` |
| Public-domain liturgical text | `src/bulletin_maker/renderer/pd_text.py` |
| Pagination/auto-tighten tuning | `src/bulletin_maker/renderer/html_renderer.py` (tighten/loosen tiers) + `pdf_engine.py` |
| The pinned layout expectations | `tests/test_layout_regression.py` (bulletin 15 seq / 8 imposed, large print 17, leader guide 19, pulpit ≤2) |
| Byte-level output goldens (4 config variants × 5 docs) | `tests/parity/golden/*.json` |
| The reference fixture Sunday | `tests/fixtures/day_content/lectionary16_2026-07-19.json` |

The database (`bulletin_maker`) holds only runtime state — a church's registration, profile edits
made in the UI, past runs, and church-forked custom rites. The canonical profile is the committed
`ascension.toml`; a church row's profile is *seeded* from it. If you build up runtime state worth
keeping, back it up with `python -m bulletin_maker.web.backup` (pg_dump → artifact store).

## The known-good bulletins (this folder)

`known-good-bulletins/` holds the five documents generated from the reference fixture Sunday
(Lectionary 16, Year A, July 19 2026) with the current templates/profile/rites — i.e. exactly how
the output looks today, verified correct:
- `Bulletin for Congregation …pdf` — the congregation worship folder
- `Full with Hymns LARGE PRINT …pdf`
- `Leader Guide …pdf`
- `Pulpit PRAYERS + APOSTLES …pdf`, `Pulpit SCRIPTURE …pdf`

Regenerate them anytime (offline, no S&S needed):
```
PYTHONPATH=src:tests venv/bin/python -c "
import sys; sys.path.insert(0,'tests')
from parity.variants import load_fixture, _regular
from bulletin_maker.core.documents import generate_documents
from bulletin_maker.core.profile import load_profile, BUNDLED_PROFILE
from pathlib import Path
d,h=load_fixture(); v=_regular(d,h)
generate_documents(v.day, v.config, Path('/tmp/out'), season=v.season, profile=load_profile(BUNDLED_PROFILE))"
```

## Restore / anchor
This snapshot is anchored by the git tag **`known-good-setup-2026-07-20`**. To return to this exact
known-good state: `git checkout known-good-setup-2026-07-20`. The parity suite (`pytest -m parity`)
and layout suite (`pytest -m layout`) both enforce that output has not drifted from this baseline.

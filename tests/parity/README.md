# Output-parity harness (LWS-0a)

## What this is

The upcoming rite-engine refactor extracts the hardcoded service order
out of `renderer/templates/` and into data. Its hard acceptance gate is:
**the generated documents must not change.** This harness is the
instrument that proves it.

It renders all five documents (bulletin, pulpit prayers, pulpit
scripture, large print, leader guide) for four config variants of the
same recorded S&S day used by the layout regression suite
(`tests/fixtures/day_content/lectionary16_2026-07-19.json`):

- `regular` — the exact config the layout suite uses today.
- `baptism` — baptism toggle on, with candidate names.
- `lenten` — kyrie off, canticle none, extended eucharistic prayer,
  nicene creed — mirrors `fill_seasonal_defaults()` for
  `LiturgicalSeason.LENT`.
- `festival` — canticle "this_is_the_feast", memorial acclamation sung,
  nicene creed.

For each (variant, document) pair, `tests/parity/golden/` stores a
JSON "golden extract" — not a golden PDF — containing:

- `page_count`
- `line_counts` — normalized line count per page
- `pages` — normalized extracted text per page (trailing whitespace
  stripped, runs of blank lines collapsed to one, leading/trailing
  blank lines trimmed)

Text-only extraction (via `pypdf`) is deterministic and git-diffable;
it deliberately never captures PDF metadata (`CreationDate`, `ModDate`,
`Producer`), which Chromium stamps with the real render timestamp on
every run and would make the harness flap. The harness also pins the
congregation profile to the bundled Ascension default
(`bulletin_maker.core.profile.BUNDLED_PROFILE`) rather than letting
`generate_documents()` fall back to `~/.bulletin-maker/profile.toml` or
`$BULLETIN_PROFILE` — otherwise the golden extracts would depend on
whatever happens to be on the machine running the tests.

## Running it

```
venv/bin/python -m pytest tests/ -m parity -v
```

Like the `layout` suite, this is slow (renders real PDFs via
Chromium) and excluded from the default test run.

A failing test names the variant and document, and for any page whose
normalized text changed prints a unified diff of that page only. A
page-count or line-count-only change (no text diff) is reported as
such directly.

## Rebaselining

```
BULLETIN_PARITY_REBASELINE=1 venv/bin/python -m pytest tests/ -m parity -v
```

This regenerates every golden file from the current renderer output
instead of comparing against it, and prints a loud
`PARITY REBASELINE SUMMARY` block at the end of the run listing every
(variant, document) pair as `NEW`, `CHANGED` (with the changed page
numbers or page-count delta), or `unchanged`.

**Rebaselining requires owner approval before the resulting golden
files are merged.** Per the Liturgy Engine implementation vision
(`docs/research/2026-07-liturgy-strategy/07-implementation-vision.md`,
Verification section): a surviving parity gap during the refactor
means producing a before/after PDF pair, an owner eyeball pass, and a
deliberate re-baseline recorded in the commit message — never a
silent `git add` of new golden files.

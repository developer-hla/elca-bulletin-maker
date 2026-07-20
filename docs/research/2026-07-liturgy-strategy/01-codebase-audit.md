# Liturgical/ELCA Assumption Audit — elca-bulletin-maker (July 2026)

All paths relative to `src/bulletin_maker/`. Read-only audit by a research agent; verified against the tree at the time of the strategy work.

## 1. The service order (ordo)

**Hardcoded twice, in raw HTML template sequence, not data-driven.**

- `renderer/templates/html/bulletin.html` (~467 lines) and `renderer/templates/html/large_print.html` (~524 lines) each contain the entire Sunday-morning ordo as a linear sequence of Jinja `{% if %}` blocks in document order: cover → welcome → gathering → confession → gathering hymn → greeting → kyrie → canticle → prayer of the day → readings/psalm → gospel → sermon → creed/baptism → prayers → peace → offering → great thanksgiving → eucharistic prayer → Lord's Prayer → communion → post-communion → blessing → sending.
- `_macros.html` states: "These two documents print the same service order with different typography" — shared widget macros (`dialog_lines`, `cover`, `psalm_verses`, `creed_stanzas`, `baptism_rite`, `music_line`) exist, but the *order itself* is duplicated prose in both files.
- No ordo data structure exists anywhere. Reordering/inserting a rite means hand-editing two ~500-line templates in lockstep.
- Five output documents registered in `core/documents.py` (`DOCUMENTS` tuple): `bulletin`, `prayers`, `scripture`, `large_print`, `leader_guide`. `prayers`/`scripture` are narrow excerpts; `leader_guide` = large_print + overlaid notation via `is_leader_guide` flag.
- Cross-document coupling: `generate_documents()` runs `bulletin` first to back-fill `creed_page` for the `prayers` document — must survive any pluggable-ordo redesign.

## 2. Liturgical texts

- **`renderer/static_text.py` (532 lines) is the single hardcoded-liturgy warehouse**: NICENE_CREED, APOSTLES_CREED, LORDS_PRAYER, GREETING, KYRIE_DIALOG, canticle texts, GREAT_THANKSGIVING_DIALOG/PREFACE, SANCTUS, eucharistic prayers, AGNUS_DEI, NUNC_DIMITTIS, AARONIC_BLESSING, DISMISSAL, CONFESSION_AND_FORGIVENESS (Form A), INVITATION_TO_LENT, full Holy Baptism rite, OFFERTORY_HYMN_VERSES.
- Module header documents provenance: which texts S&S never provides (always static) vs provides (fetched, static fallback).
- **Resolution priority chain** — `resolve_text_defaults()` in `html_renderer.py`: user-set value → S&S DayContent HTML → static fallback. The one genuinely pluggable seam by design.
- Custom-text support: `ServiceConfig` optional fields (confession_entries as `(DialogRole, text)` tuples; offering_prayer_text; prayer_after_communion_text; blessing_text; dismissal_entries). `core/content_views.py build_liturgical_text_options()` is the preset catalog — options are just "S&S this week" vs one static house preset. **No persistence**: the wizard warns "Custom edits are not saved and will not be available next week."
- **`DialogRole` enum** (`renderer/text_utils.py`): PASTOR="P", CONGREGATION="C", INSTRUCTION, NONE — used consistently for confession, greeting, kyrie, dismissal, baptism. A good primitive for a general call-response system.
- Ascension-specific: INVITATION_TO_COMMUNION always static, never overridable.

## 3. ELW Settings 1–5

- `renderer/settings.py`: `LiturgicalSetting` dataclass (key, label, atom_prefix e.g. `elw_hc2`, bundled, ga_segment, missing_pieces). Setting Two bundled; others downloaded per-church via S&S login into `~/.bulletin-maker/assets/`.
- Structural differences between settings: ga_segment ("accltext" vs "alleluia") and missing_pieces (3/4 lack Nunc Dimittis; 5 also lacks This Is the Feast). **Everything else is "same text, different notation image"** — atom code `f"{prefix}_{segment}_m"` via `image_manager._PIECE_ATOM_SEGMENTS`.
- Practically: switching settings changes ~8–10 JPEGs plus 2 conditional omissions. Cheapest generalization axis in the codebase.

## 4. Seasonal/calendar logic

- `renderer/season.py`: `LiturgicalSeason` 7-value enum (RCL/Western hardcoded); `detect_season(title)` is English string-matching against S&S's exact title phrasing — a different content source or non-RCL calendar breaks it outright; no date-math fallback.
- `_SEASON_CONFIGS` hardcodes per-season SeasonalConfig (has_kyrie, canticle, creed_default, eucharistic_form, has_memorial_acclamation, preface, show_confession/greeting/nunc_dimittis) — **these are Ascension's house customs, not ELW mandates**, conflated with calendar facts.
- `fill_seasonal_defaults(config, season)` fills `None` fields from the season table; user overrides win. Good injection-point pattern.
- 16 hardcoded ELW `PrefaceType` variants (incl. occasional: funeral, healing, marriage).
- **All actual calendar computation is S&S's server's** (`get_day_texts` scrapes their HTML). The app never computes "which Sunday is this."

## 5. Content coupling to Sundays & Seasons

- `sns/models.py` shapes (DayContent, Reading, HymnResult, HymnLyrics) threaded by concrete type through renderer + core.
- `SundaysClient` is the only implementation of fetch-day/passage/hymns/images — regex-scraping S&S markup; atom-code machinery in `image_manager.py` has no abstraction seam.
- `sns/content_service.py` isolates **fetch/cache/entitlement only** — renderer and image_manager import sns models/client directly. A second content source must produce S&S-shaped objects and satisfy the atom-code contract, or new seams must be built.
- Manual/PD sources fit easily for the S&S-optional text fields (fallback chain exists); hardest for readings/hymn notation (markup-specific parsing conventions baked into text_utils).

## 6. The form/wizard

- Per-Sunday (3-step wizard): date; 4 hymn slots (number/collection/verses); prelude/offertory/postlude/choral; creed type; kyrie bool; canticle; eucharistic form; memorial acclamation; preface; show confession/nunc dimittis; 6 liturgical-text presets with free-edit; baptism toggle + names; cover image; document selection; reading_overrides exist server-side.
- Per-church (Settings/profile): identity fields, welcome, standing instructions, copyright paragraphs, liturgical setting, paper size. `core/profile.py` docstring documents this as the explicit product boundary.
- NOT a knob anywhere: the ordo, the text-preset catalog beyond one house set, the season→defaults mapping, the document registry, Invitation to Communion.

## 7. Renderer/typography

- One Jinja template per document + `_macros.html`; custom filters (`nl2br`, `hymn_text`, `creed_line`, `terminal_amen`).
- Built entirely for "same ordo, different content." Changing ordo = editing raw HTML twice + re-baselining pinned tests.
- Pagination: CSS `.flow-group` break rules + elaborate auto-adjust (12 tighten/loosen CSS tiers, Playwright page counting, booklet imposition math in pdf_engine).
- Pinned regression: `tests/test_layout_regression.py` — BULLETIN_SEQ_PAGES=15, IMPOSED=8, LARGE_PRINT=17, LEADER_GUIDE=19, PULPIT≤2 against one fixture Sunday.
- `renderer/paper.py` PaperPreset registry — the model for bounded geometry options.

## Summary

**Top 5 chokepoints by blast radius**
1. Ordo as linear HTML in two templates (+ pinned layout tests).
2. `season.py` conflating RCL calendar + house customs; string-match season detection.
3. `sns/client.py` + atom-code image machinery as the only content implementation; content_service isolates fetching, not generation.
4. `static_text.py` single fixed text per slot; no persisted per-church text library.
5. Fixed 5-document registry with bulletin→prayers coupling.

**Already surprisingly general:** bounded-registry pattern (settings, paper); `(DialogRole, text)` primitive; user→vendor→static resolution chain; `Optional=None` seasonal-default convention; disciplined core/UI separation; profile as extension point.

**Cheap:** new setting/paper presets; more text presets (+ small persistence layer); per-church seasonal defaults; pluggable RCL-shaped naming.
**Expensive:** configurable ordo (the big rock); non-RCL calendars; second content source for readings/notation; configurable document sets.

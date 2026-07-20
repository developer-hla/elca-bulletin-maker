# Flexible Calendar & Rite Architecture

July 20, 2026 · Design note (owner steer: "design around non-RCL calendars now; rites and
calendars must both be engineered for dev + user flexibility"). Grounds the calendar/rite
abstractions against the full range of calendar SHAPES from the domain research (02) and
open-data audit (05), so ELCA/RCL is the first *content* on a system that is *architecturally*
tradition- and calendar-agnostic from the start. No non-ELCA content or non-RCL data is built
yet — this note defines the extension points those later phases drop into without rework.

## 1. Principle

Two independent pluggable systems, each with a dev extension point and a user flexibility story:

| System | What plugs in | Dev adds one by… | User flexibility |
|---|---|---|---|
| **Rites** | a rite (ordered typed blocks) | authoring a rite JSON / via the editor; `tradition` is a label, not a code path | build/duplicate/edit rites freely; per-service rite pick; occasion modules |
| **Calendars** | a `CalendarProvider` | implementing the provider + supplying its data (lookup table or computation) + registering it | pick a calendar per church; manual/sermon-series mode; per-week override; overlays |

Neither system may hardcode the assumptions of one tradition (ELCA) or one calendar (RCL) in
its core types. Content and data are ELCA/RCL-first; the *shapes* are open.

## 2. The calendar shapes we must be able to represent (design targets)

From the domain research — these are the structural axes that vary, and therefore the axes the
abstraction must NOT fix:

| Calendar | Cycle structure | Season vocabulary | Propers per day | Day resolution |
|---|---|---|---|---|
| **RCL** (ELCA, now) | 1 axis, 3-yr A/B/C, Advent-start | Western 7 (Advent…Pentecost) | 4 (OT/Psalm/Epistle/Gospel) | S&S server today; RCL tables (LWS-3b) |
| Roman Catholic | 2 axes (Sunday A/B/C + weekday I/II) | Western + forward Ordinary Time | 3–4, different numbering | computation + tables |
| LCMS 1-year historic | 1 axis, single year (~57 propers) | Western + Gesima pre-Lent | 3 (OT/Epistle/Gospel) | lookup table |
| Narrative Lectionary | 1 axis, 4-yr, **Sept–May** + summer track | narrative arc, not liturgical seasons | **1** primary text | lookup table |
| Manual / sermon-series | none | church-defined or none | church-supplied | church input, no fetch |
| Overlay: Season of Creation | n/a (layered) | adds "creation" Sundays | inherits base | date window over any base |
| Occasion (wedding/funeral/Ash Wed/Triduum) | n/a | n/a | rite-specific | event- or date-triggered |

The axes that must stay open: **number and keys of cycles**, **season vocabulary**, **number
and keys of proper slots**, **day naming/numbering scheme**, **resolution method** (compute vs
lookup vs church-supplied), **overlays**, **occasion triggering**.

## 3. Core types (shape-agnostic)

```
SeasonRef:
  id: str            # "advent","lent",... for RCL/Western; providers may add "gesima","creation"
  label: str         # display
  color: str?        # parament color / UI accent
  # NOTE: replaces the closed LiturgicalSeason enum as the CARRIED identity. The RCL/Western
  # provider's season ids ARE today's LiturgicalSeason values, so ELCA output is unchanged.
  # Rite conditions match on season id strings; seasonal_customs is keyed by season id.

LiturgicalDay:
  date
  day_name: str            # provider-produced (Proper 12 / 3 Epiphany / Reminiscere / NL wk 12)
  season: SeasonRef
  cycles: dict[str,str|int]  # OPEN: {"rcl":"C"} | {"rc_sunday":"C","rc_weekday":"II"} | {"nl":4}
  propers: dict[str,str]     # OPEN slot→citation: {"first":..,"psalm":..,"second":..,"gospel":..}
  overlays: list[SeasonRef]  # e.g. Season of Creation, applied after base resolution
  occasion: str?             # "wedding"|"funeral"|"ash_wednesday"|... when rite-triggered

CalendarProvider (ABC, one per calendar; id "rcl"|"catholic"|"lcms_1yr"|"narrative"|"manual"|"sns"):
  resolve(date, church, manual_input?) -> LiturgicalDay
  capabilities() -> {
     computes_propers: bool,      # False for manual (church supplies)
     cycle_keys: [str],
     season_ids: [str],
     needs_manual_input: bool,
     supports_overlays: [str],
  }
```

Why open dicts over typed fields: RCL's four readings, Narrative's one, and Catholic's
two-cycle indexing cannot share a fixed struct. A dict keyed by slot/cycle name lets every
provider populate what it has; renderer rite `reading_slot`/`proper_slot` blocks look up by key
and simply render nothing (or a fallback) when a key is absent — the same
present-or-fallback discipline the rite engine already uses.

## 4. Season: the one real refactor the flexibility requires

Today `renderer/season.py` has a **closed 7-value `LiturgicalSeason` enum**, and both the rite
conditions (`{"seasons":["lent"]}`) and `seasonal_customs.json` key off it. That enum is the
single most RCL-shaped thing in the codebase. The flexible design:

- Season identity becomes a **string id**. The RCL/Western id set == today's enum values
  (`advent`, `christmas`, `epiphany`, `lent`, `easter`, `pentecost`, `christmas_eve`), so ELCA
  behavior and output are unchanged.
- Rite `condition.seasons` already matches strings — no schema change.
- `seasonal_customs.json` is already keyed by season name (LWS-0d-2) — no data change for ELCA.
- New providers introduce new season ids (`gesima`, `creation`) with their own customs entries.
- **Migration path that preserves parity:** keep the `LiturgicalSeason` enum as the RCL
  provider's *internal* vocabulary and the value the `sns` path emits; introduce `SeasonRef`
  as the carried type whose `id` equals the enum's value for ELCA. Non-RCL providers never
  touch the enum. This opens the type without changing any ELCA value → parity holds.

This is a design constraint on LWS-3a's abstraction (guidance already sent) and the governing
spec for LWS-3b. It is deliberately NOT a "rip out the enum" refactor — output-neutrality for
the ELCA path stays the hard gate.

## 5. Resolution pipeline (per church, per service)

```
1. church.calendar_provider (default "sns"/"rcl" for ELCA) selects the provider.
2. provider.resolve(date, church, manual_input?) -> LiturgicalDay
     - sns:     fetch DayContent, classify season (today's behavior, output-neutral)
     - rcl:     RCL tables + Easter computus (dateutil) → day_name, season, 3-yr cycle, propers
     - manual:  build LiturgicalDay from church-supplied day_name + citations, no fetch
3. overlays applied (Season of Creation window, if church opted in)
4. per-week override merges on top (church edits day_name / a citation for this Sunday)
5. LiturgicalDay feeds the rite resolver: season → block conditions; propers → slot lookups;
   content sources (LWS-4) fetch the actual reading/hymn text for the resolved citations.
```

Providers own their resolution method; the pipeline and the rite engine are provider-blind.

## 6. Rite flexibility (already largely built — confirmation)

The rite side is in better shape; LWS-0b built it tradition-agnostic:
- **Dev**: a rite is data (`core/library/*.json`) — typed blocks + conditions + a `tradition`
  label that is metadata, not a branch. Adding LSB/BCP rites later = new JSON, no core change.
  The block type set is closed and sufficient (validated against the 11-bulletin corpus).
- **User**: the LWS-2 editor edits blocks structurally (reorder/toggle/edit text, choose
  role-label convention) with NO layout controls; per-service rite pick (LWS-1) already lands;
  occasion modules insert as block groups.
- Guardrail unchanged: structural/textual flexibility, never visual (no WYSIWYG).
- The one open extension already reserved: the five announcement block types (LWS-7).

So "engineer rites for flexibility" is mostly *done* and just needs the editor (LWS-2) to expose
it to users. The calendar side is where the new design work concentrates.

## 7. What this changes in the plan

- **Scope correction to the July 20 note:** the *architecture* for both systems is flexible /
  non-RCL-ready **now** (this note governs). Only the *content* (rites) and *data* (lectionary
  tables) stay ELCA/RCL-first. Nothing non-ELCA/non-RCL is implemented yet.
- **LWS-3a** (running): abstraction hardened to §3–§4 (guidance sent). Still interface + sns +
  manual, output-neutral.
- **LWS-3b** (ELCA/RCL content on the flexible seam): `rcl` provider with real RCL 3-year data
  (Vanderbilt-seeded owned tables) + Easter computus, producing `LiturgicalDay` per §3. Season
  ids = today's values. This is the ELCA calendar-completeness deliverable.
- **Deferred, unchanged:** `catholic`, `lcms_1yr`, `narrative` providers + their data; non-ELCA
  rites. Each is now a well-defined "implement CalendarProvider + supply data" or "author rite
  JSON" task with no core rework — which is the whole point of designing the shapes in now.
- **LWS-2** (ELCA rite editor + starter rites): builds against the confirmed-flexible rite model;
  agents do not fabricate liturgical text (derive Service of the Word from the existing ordo;
  net-new composed liturgy waits for sourced text + owner taste).

## 8. Verification posture

Every step stays under the parity net: opening the calendar/season TYPES must not change any
ELCA VALUE, proven by the 4-variant parity suite + the credentialed generation gate. The
provider abstraction gets a conformance test suite (shared by every future provider) asserting
each returns a well-formed `LiturgicalDay`; the `sns`/`rcl` providers additionally assert
season-id and proper equality against today's S&S-derived values for a fixture set of dates.

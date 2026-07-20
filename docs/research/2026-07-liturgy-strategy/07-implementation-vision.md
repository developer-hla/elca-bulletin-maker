# Liturgy Engine — Implementation Vision (canonical plan)

Markdown twin of `07-implementation-vision.html` (same content, brief-citable). July 20, 2026.
Owner decisions locked: announcements block types in schema day one (UI later); calendar-niche
churches = second segment (LCMS last); LWS-0 = strict parity + owner-ratified re-baseline escape hatch.

## Vision

- **Product:** church defines its liturgy once (or imports it) as structured data; a volunteer
  turns a date into typeset print documents in minutes. Customization is structural/textual,
  never visual. Identity = the finish line nobody else ships (print).
- **Engineering:** one rite engine renders every document from typed blocks; calendars and
  content sources are providers behind narrow interfaces; the current ELCA product becomes an
  instance of the engine, proven by regression before anything new is built on it.
- **Prime directive:** no change visible to Ascension's Sunday bulletin without the owner
  deciding it. Enforced by the 18-test layout suite + the LWS-0a parity harness.

## Core architecture

### Rite schema (LDF-informed)

```
Rite { id, church_id (NULL=library), name, tradition, occasion, base_rite_id, version,
       meta: {role_labels: {leader:"P", congregation:"C"}, notes}, blocks: [Block] }

Block common: { id, type, title?, condition?, toggle? }   # toggle: communion|baptism|...

Block types v1:
  heading{text} · rubric{text} · dialogue{lines:[{role: leader|congregation|instruction|none, text}]}
  literal_text{text, style: unison|prayer|plain}
  hymn_slot{slot: gathering|sermon|communion|sending|custom, render: ref|lyrics|notation}
  reading_slot{slot: first|psalm|second|gospel|custom, render: full|ref}
  psalm{source: slot|literal, style: responsive|unison}
  proper_slot{kind: prayer_of_day|confession|offering_prayer|preface|post_communion|blessing|dismissal|...,
              fallback: text_ref}                          # text_ref → church text library
  notation{piece: kyrie|sanctus|agnus_dei|..., text_fallback: text_ref}  # LP renders the text
  music_item{kind: prelude|offertory|postlude|choral}
  module_ref{module_id}                                    # occasion modules

Reserved now, UI later: prayer_list, week_calendar, serving_list, staff_directory, announcement_text

Condition: { seasons?: [...], feasts?: [...], toggles?: {communion:true}, invert?: bool }
```

Semantic roles render via church `role_labels`; documents differ by renderer style, not rite
(bulletin renders `notation` as images; large-print renders `text_fallback`).

### Calendar providers

```
CalendarProvider.resolve(date, church) -> LiturgicalDay {
  date, day_name, season, color, cycles: {rcl:"C", narrative:4, lcms_1yr:true...},
  propers: {first, psalm, second, gospel citations, preface_kind...}, overlays: [...] }
```

Providers: `sns` (today, unchanged) · `rcl_local` (owned tables seeded from Vanderbilt) ·
`narrative`, `lcms_1yr` (hand-transcribed owned tables) · `manual` (sermon-series mode).
Per-week override wins. House seasonal customs move from season.py into per-church
`seasonal_rules`, evaluated as block Conditions.

### Content sources

```
ContentSource: get_passage(cite, translation) · get_proper_text(kind, day)
             · get_hymn(collection, number) · capabilities() · entitled(church)
```

Registry per church: `sns` · `public_domain` (ELLC, WEB/KJV, Open Hymnal) · `net_bible` ·
`esv` · `church_library` · `manual`. Per-slot preference order, entitlement-checked, cached.
Entitlement rule generalizes: no source serves an unentitled church.

### Storage (migrations 008+)

rites · rite_modules · church_texts (persistent text library) · seasonal_rules ·
lectionaries (scheme, cycle_key, date_key, day_name, propers jsonb). form_data grows
rite_id + toggles; past_runs unchanged.

### Never changes

Renderer owns typography/pagination/auto-tighten/imposition/5-document family. Weekly wizard
flow untouched in every phase. No block exposes fonts/margins/layout.

## Workstreams

| WS | Deliverable | Size | Deps | Hard gate |
|---|---|---|---|---|
| LWS-0a | Parity harness: golden text-layer/page-count extracts for 4 config variants of the fixture Sunday; sensitivity-proven; CI-runnable | S | — | Detects a 1-line template change; green on main |
| LWS-0b | Rite schema + storage + loader; current ELW ordo transcribed to a library rite (no renderer change) | M | 0a | Round-trip; line-by-line transcription review vs both templates |
| LWS-0c | Renderer block dispatch; bulletin.html derived from rite data | L | 0b | Layout suite + parity harness unchanged (escape hatch: owner ratifies PDFs) |
| LWS-0d | LP/leader/pulpit from same rite; duplicate ordo deleted; season.py customs → seasonal_rules | M–L | 0c | Same gates per document; house-customs table out of code |
| LWS-1 | Church text library; settings 6–10; rite picker + per-service toggles | M | 0d | Custom text persists across weeks; full-credential browser gate |
| LWS-2 | Rite editor (structured only); ~10 starter rites; occasion modules; block preview | M–L | 1 | Editor round-trip; non-author church adopts starter + generates; UI gate |
| LWS-3 | rcl_local + manual mode + Narrative + LCMS-1yr transcriptions + overlay + per-week override | M | 0d (∥2) | rcl_local matches S&S across 3 years of fixtures; no-S&S church generates via manual |
| LWS-4 | Content-source registry; PD library; NET/ESV adapters; per-slot preference | M–L | 3 | Zero-subscription church generates a complete bulletin |
| LWS-5 | Import wizard (.docx/.pdf → LLM segmentation → confidence-flagged draft rite) | M | 2,4 | ≥8/11 corpus bulletins produce usable drafts; never silent |
| LWS-6 | Calendar-niche onboarding; licensing helper (hymn tags, footers, OneLicense/CCLI report export) | S–M | 3,4 | Narrative-Lectionary church onboards sans S&S and prints |
| LWS-7 | Announcements blocks UI (structured lists only) | M | 2 | No freeform layout; corpus-shaped fixtures within page budgets |
| LWS-8 | LCMS: LSB starter rites, ESV default, hymn upload; LSB probe gated on ToS | M | 4+ToS | LSB rite renders in house style; entitlement enforced |

Dependency shape: `0a→0b→0c→0d→1→2→5` with `0d→3→4→{5,6,8}` in parallel after 0d; `2→7`.

## Delegation

- **Orchestrator (Fable, main session):** briefs, review, merges, full-credential gates, parity ratification.
- **Opus agents:** 0b/0c/0d engine+renderer, 2 editor, 4 registry, 5 import.
- **Sonnet agents:** 0a harness, 1, 3 provider code, 6, scripture adapters, docs.
- **Sonnet/Haiku + second-pass verification:** lectionary/PD/starter-rite data transcription
  (liturgical data errors are Sunday-morning-visible — always source-diff verified).

**Standing guardrails** (platform set + new): no .env, no push, no pinned-layout changes outside
the escape-hatch process; per-agent test DBs; worktree pinning verified as first action;
renderer-touching briefs must run the parity harness and attach output verbatim; data
transcriptions need second-pass source verification before merge.

## Verification

Parity harness first; existing suites authoritative (570+ fast, 18 layout, credentialed browser
gates run by orchestrator only); new suites per phase (schema round-trip, provider conformance,
editor round-trip, import-corpus regression). Escape hatch: surviving parity gaps → before/after
PDF pair → owner eyeball → deliberate re-baseline recorded in the commit.

## Owner gates

Now: approve → LWS-0a/0b briefs. End 0c/0d: ratify parity PDFs if needed. During 2: taste pass
on starter rites/editor. Before 6: pricing + Augsburg letter timing. Before 8: LSB ToS go/no-go.

## RE-BASELINED ROADMAP — July 20, 2026 (supersedes the LWS-0..8 table below, now historical)

The original LWS-0..8 table (bottom of this doc) predates three owner steers; this section is the
current authoritative plan reconciled to what shipped and where the goals moved.

### Status of the original plan
- **Foundation LWS-0a–0d: DONE** (parity harness, rite schema, all documents render from rite data,
  duplicate ordo deleted, seasonal customs → data).
- **LWS-1: mostly done** (church text library, rite picker, per-service toggles). *Settings 6–10
  deferred* — needs credentialed S&S atom verification (orchestrator task).
- **LWS-2: rescoped** — rite editor + CRUD + export/import DONE; starter rites cut from "~10
  cross-tradition" to **ELCA-only** (Holy Communion, Service of the Word, Morning/Evening/Night
  Prayer + baptism module). SotW + daily offices are DRAFTS awaiting owner ELW verification.
- **LWS-3: partial** — calendar seam + `sns`/`manual` providers DONE (LWS-3a). `rcl_local` NOT
  built; Narrative/LCMS-1yr deferred by design (other-calendar content).
- **LWS-4: reshaped → CS-1/CS-2** — entitlement-gated content-source layer (CS-1) + S&S pull-live
  (CS-2) DONE; PD-text layer (`pd_text.py`) added. NET/ESV adapters dropped in favor of
  NRSVUE-via-S&S entitlement.
- **LWS-5 (import wizard), LWS-6 (onboarding + licensing helper), LWS-7 (announcements UI): not
  started.** **LWS-8 (LCMS): deprioritized** (other-tradition).
- **Added beyond the plan:** flexible calendar/rite architecture (doc 08), the copyright/PD-vs-
  licensed layer + corrections (doc 10 + CS-1/CS-2), NRSVUE placement (doc 11), rite export/import,
  and the known-good preservation snapshot (`docs/reference/`, tag `known-good-setup-2026-07-20`).

### Governing goals (the shift)
1. **Flexible system first** — pluggable rites + calendars, no ELCA/RCL assumptions in core.
2. **ELCA / S&S parity for content** — go deep only where we know the domain.
3. **Do NOT build content or decide for other traditions** — architect so others can add them.

### Product-fit constraint (owner, July 20 2026): userbase is ~100% USA Protestant
Bounds goal #3's "other traditions" to the USA Protestant set (ELCA, LCMS, Episcopal/Anglican,
UMC, Presbyterian, evangelical/non-denominational). Consequences:
- **Roman Catholic is DEFINITIVELY out of scope** (not just deprioritized) — Catholic Ordinary-Time
  forward-numbering, the weekday I/II cycle, NABRE, and USCCB per-parish lectionary licensing are
  NOT design requirements. Simplifies the calendar-flexibility surface.
- **Copyright is US-only** — the UK Crown-Patent 1662-BCP caveat (doc 10) is moot.
- **Scripture translations that matter:** NRSV/NRSVUE (mainline), ESV (LCMS/evangelical), KJV/WEB
  (public-domain floor). No NABRE.
- **Season vocabulary is bounded** — Western 7 + Gesima/pre-Lent (LCMS historic) + Season of
  Creation overlay + "none" (non-lectionary). RB-1's string-id season model is right-sized for this
  (bounded extensibility, not arbitrary world-tradition openness).
Flexibility is still worthwhile: USA Protestant traditions still diverge in rite (Communion / Word /
Reformed / free-church) and calendar (RCL / LCMS 1-year / Narrative / none).

### Forward workstreams, in priority order
**Cluster A — finish the flexibility spine (leads):**
- **RB-1 Complete season generalization** — season identity becomes a string id carried through
  `get_seasonal_config`/`fill_seasonal_defaults`, the rite-condition context, and the renderer's
  season-driven atoms. RCL/Western ids == today's `LiturgicalSeason.value`s → OUTPUT-NEUTRAL (parity
  4/4 is the gate). Unblocks non-RCL seasons (gesima/creation) existing at all. *The biggest
  remaining flexibility gap — a half-finished loose end from LWS-3a.*
- **RB-2 `rcl_local` calendar provider** — real RCL 3-year data (Vanderbilt-seeded owned tables) +
  Easter computus (python-dateutil), producing `LiturgicalDay`. Proves the calendar seam with a real
  second provider and gets ELCA calendar resolution in-house (less S&S dependency). Gate: day-names
  + citations match S&S across the fixture set.

**Cluster B — close ELCA / S&S parity:**
- **RB-3 child-rite + section-container engine extension** — the structural capability for
  Funeral+Committal (linked rites) and multi-section services. Parity unchanged.
- **RB-4 author Funeral + Marriage rites** (drafts, on RB-3) — CS content model (PD scaffold +
  entitlement pull + VAR slots), owner verifies against ELW.
- **Owner task:** verify the SotW + daily-office DRAFTS against a physical ELW.

**Parked / on-demand (architecture ready; build when chosen):** CS-2 pull-map population (map real
atom-codes — credentialed, orchestrator); import wizard (LWS-5); licensing helper (LWS-6);
announcements UI (LWS-7); settings 6–10. **Other-tradition content (LSB/BCP/Catholic, Narrative/
LCMS-1yr calendars): architecture-ready, deliberately NOT built.**

## GOVERNING PRIORITY — July 20, 2026 (owner)

Ordered priorities for all remaining work:
1. **Build a FLEXIBLE system** — this matters most. Rites and calendars as genuinely pluggable
   extension points, no ELCA/RCL assumptions baked into core types. Architecture-flexibility work
   outranks new content.
2. **ELCA / Sundays & Seasons PARITY for content** — go deep only where we actually know the
   domain (ELCA + what S&S provides). This is the content we build.
3. **Do NOT build content or make design decisions for OTHER traditions** (LSB/BCP/Catholic/etc.)
   — we don't know them well enough to decide for them. The flexible system must let people who DO
   know them add them later; we don't pre-bake their choices.

Reprioritized next work (flexibility-first, all serving #1 and/or #2; none building other-tradition
content): (a) content-source registry + entitlement [flexibility + makes the PD-vs-licensed split
from doc 10 real]; (b) complete the season generalization end-to-end (carry the open SeasonId
through get_seasonal_config / fill_seasonal_defaults / rite conditions — currently only the
LiturgicalDay type is opened, the rest still uses the closed enum); (c) child-rite / section-
container engine extension [flexibility AND unblocks ELCA funeral/wedding, which S&S covers =
parity]; (d) rcl_local provider [proves the provider model + ELCA calendar in-house]. Explicitly
NOT: authoring LSB/BCP/Catholic rites.

## Scope decision — July 20, 2026 (owner)

**CONTENT/DATA is ELCA/RCL-first; ARCHITECTURE is flexible/non-RCL-ready NOW** (owner steer,
same day — see `08-flexible-calendar-rite-architecture.md`, the governing design). We author NO
non-ELCA rites yet (LSB/BCP deferred) and transcribe NO non-RCL lectionary data yet (Catholic,
Narrative, LCMS-1yr deferred) — BUT the calendar `CalendarProvider`/`LiturgicalDay` types and the
rite model are engineered shape-agnostic from the start (open cycles/propers dicts; season as a
provider-defined id, not the closed RCL enum; provider resolution method pluggable) so each
deferred calendar/rite is later a "implement provider + supply data" or "author rite JSON" task
with zero core rework. Opening the types must not change any ELCA value (parity is still the gate).
The ELCA slice is to be calendar-complete: RCL propers resolvable in-house (LWS-3b = rcl_local
with real RCL 3-year data, Vanderbilt-seeded owned tables), so ELCA rites work without S&S doing
the calendar math. Owner is the liturgical-domain reviewer for the ELCA starter rites.
Engineering guardrail: agents must NOT fabricate liturgical text — new ELCA rites are derived
from the existing reviewed ordo (e.g. Service of the Word = Holy Communion minus the meal) or
built from public-domain/sourced text with owner taste review; net-new composed liturgy waits.

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

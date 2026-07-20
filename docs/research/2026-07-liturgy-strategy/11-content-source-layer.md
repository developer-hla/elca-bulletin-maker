# Content-Source Layer — S&S Verification + Design

July 20, 2026 · Answers the owner's "should we pull from S&S?" with an empirical probe of what
S&S actually exposes (done live with the licensed Ascension credential, read-only), then designs
the multi-source content layer. Governing priority: flexibility first; ELCA/S&S parity for content;
pull licensed text from S&S rather than bundle it.

## Part A — What S&S actually exposes (verified live, July 20 2026)

Probed `members.sundaysandseasons.com` with the Ascension license. Top-level areas: **PLANNER,
LIBRARY, MUSIC, PREACHING, VISUALS, NRSVUE BIBLE**, plus per-day resource tabs.

| Area | Endpoint | Content | Scrapeable? | We pull it? |
|---|---|---|---|---|
| **Day Texts** | `/Home/DayTexts/{date}/{eventDateId}` | The dated **PROPERS**: intro, confession, prayer of the day, gospel acclamation, readings/psalm/gospel (incl. semicontinuous alternates), prayers of intercession, offering prayer, invitation to communion, prayer after communion, blessing, dismissal, commemorations | **Yes** — server-rendered HTML `<h3>`-delimited (has `/Home/Download?view=DayTexts`) | **Yes, today** |
| Day Resources | `/Home/DayResources/...` | Commentary (overview, ideas, children's message, lectionary notes) | Yes | No (not liturgy) |
| **Music** | `/Music/...`, `/Music/Search` | Hymns + service-music **notation** (the setting ordinary — Kyrie/Sanctus etc. — as atom-coded images) | Yes (form-POST search) | **Yes** (hymns + setting images) |
| **Library** | `/Library` → `/Home/Search` | The reproducible-content library — where liturgy **orders**, **settings**, and **occasional services** (funeral/marriage/daily office) text most likely lives | **Partially** — a Kendo-UI (2014) **client-side/AJAX search app**; server-side query params returned the shell, not results. Retrieval needs reverse-engineering the search AJAX endpoint (not done in this probe) | No |
| **Planner** | `/Planner` | The worship-plan **builder** — assemble a service, then **export to Word** | Ordo assembly exists but **exports to Word, not structured data** | No |
| Bible | `/Bible` | NRSVUE text | Yes | Indirectly (readings come via DayTexts) |

### The decisive findings
1. **The ORDINARY liturgy TEXT (Kyrie/Sanctus/Agnus Dei/creeds/Great Thanksgiving wording) is NOT
   in DayTexts.** DayTexts is propers-only (verified: its `<h3>` sections are exactly the dated
   items). The ordinary lives in the **Library** (reproducible text, behind the JS search) and/or
   is embedded in **Music** notation images. Today we get the ordinary as (a) bundled text in
   `static_text.py` and (b) setting notation images. So **pulling the ordinary text from S&S is
   possible in principle (it's the church's licensed content, same site/session) but requires
   integrating the Library search — more work than the DayTexts scraping we already do, and its
   retrieval endpoint is not yet reverse-engineered.**
2. **Occasion-service text (funeral/marriage/daily office) is in the Library too** — same
   JS-search access path, same caveat.
3. **The ordo/structure is NOT available as clean data** — the Planner only exports to Word. This
   re-confirms the architecture: **structure stays ours; only content comes from S&S.**

### Honesty on what's unverified
I did not reverse-engineer the Library search AJAX endpoint this session, so "we can pull the
ordinary/occasion text from S&S" is **feasible-but-unproven** — a spike to nail the Library
retrieval is the first task before committing to pull-the-ordinary. DayTexts propers pull is proven
(in production). PD fallback text is in hand (`pd_text.py`). Politeness/entitlement rules from the
existing S&S integration carry over.

## Part B — The content-source layer design

### The problem it solves
Content that fills a rite comes from several places with different licensing:
- **Propers** (dated) — S&S, per church's license. *Pulled today.*
- **Ordinary ELW text** (Kyrie/Sanctus/creeds/prayers) — AF-copyrighted; **currently BUNDLED in
  `static_text.py` and shipped to everyone** (fine for licensed Ascension, a copyright problem for
  other churches). Should resolve via the church's S&S license, with PD fallback for the unlicensed.
- **Public-domain text** (canticles, traditional versicles) — `pd_text.py`; bundle freely.
- **Church's own saved text** — `church_texts` (LWS-1).
- **Manual paste** — per service.

### The abstraction
```
ContentSource (per church, registered by capability):
  resolve(request: ContentRequest, church) -> ContentResult | None
  entitled(church) -> bool
  capabilities() -> set[ContentKind]

ContentRequest: { kind, key, date?, params }
  kind ∈ {proper, ordinary, passage, hymn, occasion_text}
  key  = slot/text-catalog key (e.g. "ordinary.kyrie", "proper.prayer_of_day", "pd.magnificat")

Sources (in resolution priority, per slot):
  1. church_override   — this service's inline edit (never persisted beyond the run)
  2. church_library    — church_texts saved presets (LWS-1)
  3. sns               — the church's licensed S&S pull (propers today; ordinary/occasion after the
                         Library spike), cached in sns_cache; entitled() = has validated S&S link
  4. public_domain     — pd_text.py / bundled PD; entitled() = always
  5. (empty/placeholder + a rubric note) — never fabricate
```

### Resolution
`resolve_text(church, slot)` walks the priority list, returns the first source that yields content
AND is `entitled`. So: a licensed church gets its S&S/ELW wording; an unlicensed church falls
through to the PD text; either can be overridden by the church's own library or a per-service edit.
Caching: S&S results go through the existing `sns_cache` (content_service.py already does this for
propers). The rite engine's blocks already express this as `text_ref` (PD/existing) + `proper_slot`
/`fallback`/`text_fallback` — the layer just makes the fallback chain source-aware and
entitlement-gated instead of "static text always."

### Entitlement — the correction this enables
Move the AF-copyrighted constants in `static_text.py` behind the `sns`/entitlement source: a
licensed church resolves them (pulled or, pragmatically, served-from-bundle-gated-by-entitlement —
see below); an unlicensed church gets the `pd_text.py` equivalent. `pd_text.py` (PD) always
bundles. This is the single fix for the "we ship copyrighted ELW text to everyone" latent issue.

### Pull-live vs bundle-gated (a real sub-decision, flagged for owner)
Two ways to give a licensed church its ELW wording, same legal outcome:
- **Pull-live from S&S** (the owner's instinct): purest — S&S is source of truth, we stop
  maintaining ELW text copies — but needs the Library-search spike, and adds a scrape dependency
  for text that never changes (the ordinary is stable).
- **Bundle-gated**: keep the ELW text in the repo but SERVE it only to entitled churches (gate the
  existing `static_text.py`), PD to the rest. Robust, no new scraping, but we still hold copies.
- **Recommendation:** do bundle-gated FIRST (it fixes the copyright exposure immediately with no
  new scraping and no behavior change for Ascension), and treat pull-live as an enhancement after
  the Library spike proves retrieval. Both are the same ContentSource interface; only the `sns`
  source's implementation differs. Owner decides whether pull-live is worth the scrape.

### Flexibility payoff
The layer is source-agnostic and tradition-agnostic: a future provider (another publisher, another
church's PD corpus, a real API if one ever appears) is just another `ContentSource` in the registry
with its own `entitled()`/`capabilities()`. No core change. This is the content half of the
"flexible system" priority (the calendar half is the CalendarProvider seam from LWS-3a).

## Phasing
- **CS-1 (fixes the copyright exposure, no new scraping):** ContentSource interface + registry;
  `public_domain` + `sns`(bundle-gated over today's static_text) + `church_library` sources;
  entitlement-gated resolution; wire the rite engine's fallback chain through it. Ascension output
  unchanged (parity gate). This is the priority piece.
- **CS-2 (the pull spike):** reverse-engineer the Library search; implement `sns` ordinary/occasion
  TEXT pull (cached); flip the `sns` source from bundle-gated to pull-live if the owner wants it.
- **CS-3:** manual-source UI for no-license churches; per-slot source preference surfaced in the
  wizard/editor.

Gates throughout: parity 4/4 (Ascension byte-identical), credentialed generation, per-source
conformance tests, entitlement tests (unlicensed church gets PD, never AF text).

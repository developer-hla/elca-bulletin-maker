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

### Scripture translation — NRSV / NRSVUE (owner preference, July 20 2026)
Owner wants NRSV/NRSVUE where possible. It slots into the same entitlement model:
- **NRSVUE is the ENTITLED scripture translation, delivered via the church's S&S license.** NRSV/
  NRSVUE is copyrighted (NCC/Friendship Press) with NO self-serve API (see doc 05), so it can only
  come through S&S (which serves its DayTexts readings + `/Bible` in NRSVUE). **The Sunday READINGS
  we already pull from S&S are NRSVUE — licensed churches already get NRSVUE scripture today.**
- **PD fallback for scripture-derived content = KJV / WEB** (WEB has an explicit PD dedication).
  This is what the daily-office KJV canticles are: the unlicensed-church fallback, not the primary.
- So for scripture-kind content the resolver's entitled source = NRSVUE-via-S&S, PD source = KJV/WEB.
  Readings already resolve this way (via `content_service`); pulling NRSVUE for the daily-office
  canticles/psalms (vs today's bundled KJV) is a **CS-2** enhancement (needs the S&S scripture pull).
- Possible extra path for non-S&S churches (flag for legal, not relied on): NRSVUE grants free
  print use up to 500 verses in a church's own non-salable bulletin with attribution — but that is
  the *church's* reproduction right, not our software's bundling right; only pursue if counsel
  confirms the tool acts as the church's agent. Default remains NRSVUE-via-S&S / PD fallback.

### Flexibility payoff
The layer is source-agnostic and tradition-agnostic: a future provider (another publisher, another
church's PD corpus, a real API if one ever appears) is just another `ContentSource` in the registry
with its own `entitled()`/`capabilities()`. No core change. This is the content half of the
"flexible system" priority (the calendar half is the CalendarProvider seam from LWS-3a).

## CS-2 spike results (July 20 2026 — Library reverse-engineering)

**Verdict: pull-live from S&S is FEASIBLE.** The ordinary/occasion liturgy text is all present in
the Library, entitlement-gated, on our existing authenticated session.

- **The Library is a resource TREE**, navigated by `GET /Library/_Children?parentAtomId={N}` (each
  node's `data-ajax-url`). No free-text search needed for our purpose — it's browsable.
- **Organized by source-book collection** (top-level atomIds): ELW=9396, LBW=110, WOV=118,
  ACS=333320, TFF=116, LLC=111 (Spanish), plus resource collections (lectionary/psalm, S&S
  resources, other, children's bulletins). So S&S covers ELW + several ELCA-family books + Spanish.
- **The content we need is there as nodes**: under a collection — Holy Communion, Holy Baptism,
  Daily Prayer, Life Passages (Marriage/Burial), Lent & the Three Days, and explicit leaves like
  "Service of the Word", "Marriage Service Elements", "Burial of the Dead", "Apostles' Creed",
  "Nicene Creed", "Occasional Services for the Assembly", "Pastoral Care".
- **Each content leaf carries a stable `data-atom-code`** (e.g. `lbwApostlesCreed`) and offers
  **"Download this item" + "Copy to clipboard"** — i.e. S&S itself provides a text export of each
  item. That is the pull hook.
- **Not yet pinned:** the exact content-fetch request behind the copy/download action. Guessed URL
  patterns 404'd; `/Home/Download` exists but 500'd on my params (wrong shape, not absent). The
  clean way to nail it is a **Playwright session that clicks the copy/download action and captures
  the actual XHR** (method + path + params) — a bounded implementation step, not a research
  unknown. That capture is the first task of building CS-2's pull.
- **Politeness:** the tree + per-item fetch is more requests than DayTexts; cache aggressively in
  `sns_cache` (the ordinary/occasion text is stable — fetch once per church per item, reuse).

**Implication:** the owner's pull-from-S&S instinct is sound and buildable. CS-2 = (1) capture the
copy/download endpoint via Playwright, (2) add an `sns` ContentSource method to fetch an item by
atom-code (cached, entitlement-gated), (3) flip the relevant `sns` source resolution from
bundle-gated to pull-live, keeping the PD fallback for the unentitled. NRSVUE canticles/psalms come
the same way (S&S serves NRSVUE). This stays behind the CS-1 interface — only the `sns` source impl
changes; parity/entitlement gates unchanged.

## CS-2 endpoint CAPTURED (July 20 2026) — pull is proven, exact request in hand

The copy/preview action fires `doGenericModalGet("/File/Preview", {atomCode})` (found in the
genericModal bundle); download is `/File/Download?atomId=X&atomCode=Y`. **Confirmed working:**
- **`GET /File/Preview?atomCode=<atomCode>`** → the item's text as HTML. Verified live:
  `lbwApostlesCreed` → the Apostles' Creed, `lbwNiceneCreed` → the Nicene Creed.
- **Response shape:** `<div class="body"><p><div [style="text-indent: Nem"]><strong>LINE</strong>
  </div>...</p>...</div>` — indentation via `text-indent` = liturgical stanza indent.
- **Not-found shape:** HTTP **200** with plain body `"Atom not found with code: <code>"` (~38 bytes,
  no `.body` div) — the fetcher MUST detect this and treat as None, not as content.
- **Entitlement = the login** (the church's own S&S session); unentitled churches can't reach it.
- **Atom-codes** are stable per item (`lbwApostlesCreed`…); collections: ELW=9396, LBW=110, WOV=118,
  ACS=333320, TFF=116. Discovering the full key→atom-code map for target content is incremental
  credentialed browsing (orchestrator's job); the mechanism works for any code.

### CS-2 build design (parity-safe — FILLS GAPS, does not flip the parity-locked Sunday ordinary)
1. **Pull method** (in `sns/` — e.g. `content_service.fetch_preview(atom_code) -> Optional[str]`):
   GET `/File/Preview?atomCode=`, detect the "Atom not found" body → None, clean the HTML preserving
   stanza structure, **cache in `sns_cache`** keyed by atom-code (stable text → long TTL).
2. **Injection, not import** (layering): `ContentContext` gains an optional `sns_fetch:
   Callable[[str], Optional[str]]`, injected by the web/generate layer from the church's client.
   `core/content_source.resolve_text` stays web-free; for a slot that declares an `atom_code` AND an
   entitled context with `sns_fetch`, it pulls (cached) — sitting above the PD fallback.
3. **Gap-fill only:** do NOT assign atom-codes to the existing bundled Sunday ordinary keys (that
   would replace our transcription/house text with S&S text and break parity + risk overriding house
   customizations — a separate owner-ratified decision). Pull serves keys we currently can only
   placeholder (occasion services, ELW/NRSVUE daily-office canticles, etc.), where an entitled church
   gets real S&S text instead of a placeholder. Demonstrate end-to-end with a pull-keyed slot + mock.
4. NRSVUE canticles/psalms arrive the same way (S&S serves NRSVUE); map those keys to their atoms.

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

---
## Product-fit note (July 20 2026): USA Protestant only
Userbase is ~100% USA Protestant (see 07). Scripture translations in scope: NRSV/NRSVUE (mainline,
entitled via S&S), ESV (LCMS/evangelical), KJV/WEB (PD fallback). NABRE/Catholic sources are out of
scope. The entitlement model is unchanged; there is simply no Catholic-publisher branch to design for.

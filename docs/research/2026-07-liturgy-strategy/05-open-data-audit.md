# Open Liturgical Data & Tooling — Build-vs-Borrow Audit (July 2026)

Web research by research agents (lectionary-data sub-report merged in). URLs inline.

## 1. Lectionary data

**RCL — best-covered, citations only:**
- **Vanderbilt** (lectionary.library.vanderbilt.edu): full 3-year cycle + daily lectionary. Machine-readable: `weekly.ics`/`daily.ics` (live, rolls forward ~2 years), RSS, per-year XLSX/DOCX/PDF exports; embedded JS data blob on every page. No JSON API. License: CCT/Augsburg citations "freely used for non-profit purposes"; NRSV text restrictions separate. Actively maintained.
- **LectServe** (lectserve.com): live JSON API (`/today`, `/sunday`, `/date/…`, `?lect=rcl|acna`), backed by `marmanold/Date-Lectionary` (Perl, BSD-2). One-person hobby project, low velocity since ~2020 — continuity risk.
- **GitHub/PyPI/npm:** `stanlemon/lectionary-js` (MIT, hand-maintained JSON, covers BOTH 1-year historic and 3-year RCL — notable); `garethjmsaunders/sec-digital-calendar` (CSV, GPL-3.0, 3 years + daily office, actively updated); `catholic-mass-readings` (Apache-2.0 USCCB *scraper* — code license ≠ text license). Nothing bundles pericope text.
- **lectio-api.org: DEAD** (DNS gone — verified directly). **calapi.inadiutorium.cz: ALIVE** (verified directly) — JSON "Church Calendar API" by the calendarium-romanum author; HTTP-only hobby hosting; reference/bootstrap, not a production dependency.

**Catholic (USCCB):** no API; **written license agreement with annual per-parish fee required** for regular bulletin reproduction of readings, regardless of quote length. Legally the riskiest lectionary. https://www.usccb.org/committees/divine-worship/policies/copyright-permissions-requirements

**LCMS one-year historic:** weakest-covered — LCMS publishes PDF/Word summaries only; Word to Worship has HTML tables; `stanlemon/lectionary-js` partially models it. **Hand-encode once** (~57 entries).

**Narrative Lectionary:** PDF-only from Luther Seminary (workingpreacher.org), no structured source anywhere. Fixed 4-year table — **one-time transcription**.

## 2. Liturgical calendar computation

- **Computus solved:** `python-dateutil` `easter()` (Julian/Orthodox/Western). Zero work.
- **romcal** (JS/TS, MIT): most mature reference architecture — rank/precedence resolver over declarative calendar data tables. Stable release 2020-stale. **Extract the data tables + hand-write a small Python resolver on its rank+override pattern; don't port the code.**
- **LiturgicalCalendarAPI** (PHP, Apache-2.0, active): full precedence engine, JSON/ICS output — consumable as a data source.
- **`liturgical-calendar` (PyPI)**: Python port targeting Church of England; active; Python≥3.11 but pure-python (backport mechanical); **license undeclared — verify repo LICENSE before vendoring**. No TEC/1979-BCP engine exists; vendor engine + hand-built TEC table.
- **Pattern to copy:** numeric rank per celebration + explicit override function for known conflicts (solemnity-on-Advent-Sunday transfers).

## 3. Open liturgical text / schema projects

- **Venite (github.com/gbj/venite, MIT) — the standout prior art.** Publishes `@venite/ldf`, the "Liturgy Document Format": every element extends `LiturgicalDocument` with `type` ∈ `liturgy | heading | option | refrain | rubric | text | responsive | bible-reading | psalm | meditation | image | parallel`. Key models: `ResponsivePrayer` lines `{label, text, response, optional}` (the call-response primitive); `Psalm` with antiphon/gloria metadata; `Option` (choose-one alternatives with selected index); `Condition` (gate blocks on day/season/feast/weekday/date-range/preference — the "rite adapts to the day" answer); `LiturgicalDay` carrying a `year` map keyed by lectionary-cycle name (one day, multiple cycle positions simultaneously). Sibling repos: hymnal-api, bible-api. **Author disavows the codebase — adopt the schema design, not the code.**
- **Divinum Officium:** active, Perl, idiosyncratic plain-text data format, no LICENSE file — not a schema to adopt.
- **Open Hymnal Project:** domain squatted; recovered via Wayback — see preservation note below. Best structured PD tune corpus (ABC notation) found anywhere.
- **OSIS:** Bible-markup XML, not order-of-service; no maintained liturgy-flavored fork found. Venite LDF is the only mature "liturgy markup" prior art.

## 4. Scripture APIs & bulletin licensing

| Translation | Fit | Bulletin-print license | API |
|---|---|---|---|
| ESV | LCMS/evangelical | ≤500 verses free; bulletins explicitly named; "(ESV)" | api.esv.org, 5k queries/day free; ToS has doctrine/non-commercial clauses — churches should hold their own keys |
| NET | cross-tradition | Best-in-class: any form incl. bulletins, "(NET)", no cap short of a whole book | Yes — push-button safe |
| WEB | universal floor | True public domain | Static data widely mirrored |
| KJV | traditional | PD in US | Static data |
| NRSV/NRSVue | mainline (ELCA/PCUSA/UMC) | Gratis ≤500 verses in bulletins/orders of service | **No confirmed self-serve API — the automation gap most worth resolving** (Friendship Press/NCC conversation) |
| NABRE | Catholic | **Paid annual per-parish USCCB license for bulletin readings** | None — cannot borrow |

## 5. Hymn data

- **Hymnary.org:** largest corpus, structured internally, **no API/bulk export** (bot-blocked; unofficial scrapers exist as evidence of absence). Reuse terms unpublished.
- **Open Hymnal:** ABC tune + ThML text corpus, "freely distributable"/PD — **domain squatted; recovered from Wayback and preserved locally** at `/Users/malloryashmore/asc_luth/research-archive/open-hymnal/` (2014.06 + 2011.10 ABC archives, ThML XML, PDFs, license-page evidence; integrity-verified; see MANIFEST.md).
- **CPDL:** choral scores, per-piece license tags, not congregational-hymnal-shaped.
- Structured PD text+tune generally scarce; text abundant but unsegmented (Gutenberg hymnal scans).

## Build-vs-borrow verdicts

| Capability | Best resource | Approach |
|---|---|---|
| RCL citations | Vanderbilt ICS/XLSX (+ sec-digital-calendar CSV) | **Consume as data**, own the table |
| Catholic calendar | romcal tables / LiturgicalCalendarAPI | **Port data, build small resolver** (if ever needed) |
| LCMS 1-year | LCMS PDFs + lectionary-js partial | **Build (one-time transcription)** |
| Narrative Lectionary | Luther Seminary PDFs | **Build (one-time transcription)** |
| Feast precedence engine | romcal pattern | **Port logic (small, hand-written)** |
| Anglican/Episcopal calendar | `liturgical-calendar` PyPI | **Port engine, swap in TEC data; verify license** |
| Computus | python-dateutil | **Consume as-is** |
| Order-of-service schema | Venite LDF | **Adopt schema design, own implementation** |
| PD liturgical texts | ELLC/ICET common texts | **Consume (public domain)** |
| PD hymn tunes | Open Hymnal ABC (preserved locally) | **Consume as data** |
| Scripture (mainline) | NRSV print / NET API | Consume; NRSV automation needs a licensing call |
| Scripture (LCMS) | ESV API | Consume via API |
| Scripture (Catholic) | — | Cannot borrow (USCCB fees) |

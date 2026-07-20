# Competitive Landscape — Liturgy/Bulletin Tools (July 2026)

Web research by a research agent. Confidence flags preserved; several products have almost no public review footprint (itself a finding).

## 1. Sundays & Seasons (Augsburg Fortress, ELCA)
Content-assembly and licensing gateway, **not a bulletin generator**. Vendor's own workflow: select date/base liturgy → edit plan → download → "**Format your finished bulletin or projection in your own application (like Microsoft Word or PowerPoint).**" Bundles AF Liturgies License. Standard vs Deluxe (music download, add-ons). Pricing unverified (~$249–799/yr by attendance, JS-gated). No native PDF; all final typography manual, weekly. No indexed reviews/complaints found anywhere — the pain is structural, confirmed by vendor copy.

## 2. Lutheran Service Builder (Concordia/CPH, LCMS)
Strongest incumbent. Real "Bulletin view" auto-filled from planning view; saved bulletin-format presets (font/size/margins/page/folding — "plan to bulletin in one click"); pastor/congregation/large-print variants; concurrent multi-device planning. **Still ends at "export to a word processor for printing."** Two licenses: Liturgy (bundled) + Hymn (separate paid, usage-tracked). Verified pricing: $500/$650/$800/$950 first year by attendance tier; renewals $250–700. No public complaint trail found; predecessor desktop product sunset 2022.

## 3. RitePlanning (Church Publishing, Episcopal)
Step-wizard document workflow; "Save as Template" auto-updates propers weekly; multi-user. **The moat is the licensing bundle**: BCP, Book of Occasional Services, Lesser Feasts & Fasts, NRSV, Hymnal 1982, LEVAS II. Tiers: Standard (hymn texts) vs Deluxe (texts+tunes+permissions). Pricing unverified. No first-person complaints found (evidence gap, not satisfaction). Structural note: **1979 BCP text is public domain**; Hymnal 1982 music is not (OneLicense ~$185/yr start) — an Episcopal competitor must integrate licensing, restrict to PD, or bundle.

## 4. Venite.app + open-source liturgy data
Free Episcopal Daily Office + bulletin generation (docx export), solo-developed; 4.8/5 (91 ratings); Patreon ~$109/mo — hobbyist scale. Its **Liturgy Document Format (LDF)** is MIT and public; maintainer disavows the codebase ("old and brittle... wouldn't recommend as a starting point"). Other data: LectServe (hobby JSON API), Vanderbilt RCL (scrape/ICS source), dailyoffice.app (rich but all-rights-reserved). **No dependable maintained open lectionary API exists** — build/own the calendar logic.

## 5. Planning Center Services
Category leader for worship-team scheduling; atomic unit is a timestamped "Plan" (rundown, not liturgy). Deep song tooling + CCLI SongSelect import. **Print = report generator** ("clunky"); "bulletin" in PC-speak = a Publishing add-on *web page* ($15–32/mo), not print. Zero bundled content licensing. Liturgical fit weak — "Service Type: Liturgical" is a folder label; purpose-built denominational substitutes exist precisely because PC doesn't cover licensed liturgy. Pricing free→~$239/mo modular. Complaints: general usability/learning curve.

## 6. Proclaim (Faithlife) & ProPresenter (Renewed Vision)
Projection-first, confirmed **screens only, no print/bulletin output**. Proclaim: cloud slides, SongSelect/Hymnbase autofill, local API, pricing undisclosed. ProPresenter: $29/mo Standard per seat; $59/mo Campus (20 seats).

## 7. WorshipPlanning.com, Ministry Scheduler Pro, DIY
- **WorshipPlanning.com**: worship-flow builder + volunteer scheduling; **zero bulletin/print output**; $15/$25/$50/$100/mo tiers; thin review base (4.4/5, 20 reviews).
- **Ministry Scheduler Pro** (Rotunda): pure volunteer scheduling, Catholic-parish skew; **zero bulletin output**; $50–65/mo; complaints: "old and outdated interface," "frustrating to do even basic tasks," desktop-install friction; still 4.6/5.
- **DIY Word/Publisher/Canva**: persists because free/familiar/flexible. Active template ecosystem (Warner Press, Concordia Supply, Publisher template packs; new AI entrant FaithStack claiming 30–90 min/Sunday saved — vendor figure). **What breaks: typo culture** — a recognized joke genre (proofreadingservices.com collection; dedicated Facebook group); root cause per a named-author account: no time to check "before hitting Send to Print"; prescribed fix (3-person proofreading team) confirms rushed single-person review is the norm.

## Synthesis

### Landscape table

| Tool | Liturgy flexibility | Licensing | Print quality | Volunteer ease | Multi-tradition | Price |
|---|---|---|---|---|---|---|
| Sundays & Seasons | Medium (ELCA only) | AF bundled | **Low — hand-formatted in Word** | Low | No | ~$249–799/yr (unverified) |
| Lutheran Service Builder | Med-high (LSB, format presets) | Liturgy bundled; hymns separate | Medium — presets, still Word finish | Medium | No | $500–950 y1 / $250–700 renewal |
| RitePlanning | Medium (BCP wizard) | Strong bundle | Unknown | Unknown | No | Unverified |
| Venite.app | Low-med | Free/PD BCP | Basic (.docx) | High, hobbyist risk | No | Free |
| Planning Center | Low (rundown) | None (BYO) | Low (report dump) | Medium, steep curve | Agnostic, liturgy-blind | Free–$239/mo |
| Proclaim/ProPresenter | Low (slides) | None (BYO) | N/A screens | Medium | Agnostic | $29–59/mo |
| WorshipPlanning/MSP | None | None | **None** | Medium | Agnostic | $15–65/mo |
| DIY Word/Canva | Total | None | Variable, typo-prone | Low (hours weekly) | Total, zero support | Free |

### Gaps nobody fills
1. **Churches that rotate settings/liturgies** — incumbents lock to one denomination's liturgy or have no liturgical awareness.
2. **Alternative-lectionary / non-RCL churches** — nothing serves them in one tool.
3. **Beautiful PRINT output** — the sharpest, most consistently confirmed gap: nobody ships finished typeset print as the terminal output.
4. **Low-training-volunteer usability** — incumbents have learning curves; DIY shifts QC onto under-resourced staff.

### Pricing norms
Scheduling-only $15–65/mo; denominational content subscriptions ≈ $20–65/mo-equivalent; ProPresenter $29–59/mo. **Target band: $30–75/mo attendance-scaled** for a tool solving content + finished print.

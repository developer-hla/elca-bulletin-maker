# Liturgical Practice Variability — Domain Research (July 2026)

Web research by a research agent; URLs cited inline. Condensed only for formatting.

## 1. Service structure across traditions

**Universal deep structure:** Gathering → Word → (Meal/Eucharist) → Sending. Everything else is variation in vocabulary, granularity, and which slots are populated.

- **ELCA (ELW):** 10 numbered settings of Holy Communion (musical idiom varies; skeleton shared), plus daily-office rites (Morning/Evening Prayer, Compline) with more-fixed ordos. https://en.wikipedia.org/wiki/Evangelical_Lutheran_Worship
- **LCMS (LSB):** FIVE Divine Service settings. 1 & 2 share text (different music); 3 preserves the 1888 Common Service; 4 & 5 simpler/hymn-based. **"Switching settings" is a stable menu a congregation adopts (default + seasonal alternate), not a weekly rotation rule.** Design implication: default setting = per-service override, not calendar-locked. https://blog.cph.org/worship/the-divine-service-in-lutheran-service-book
- **Episcopal (1979 BCP):** Rite I (traditional language) vs Rite II (contemporary); structurally near-identical; Enriching Our Worship = supplemental series alongside Rite II. https://www.episcopalchurch.org/glossary/rite-1-rite-2/
- **Roman Catholic:** cleanest Ordinary (fixed) / Proper (varies by day) split; also the "Common" (per-category-of-saint) middle layer. Customization comparatively low (GIRM-governed). https://www.usccb.org/prayer-and-worship/the-mass/order-of-mass
- **UMC:** four-movement "basic pattern" (Entrance / Proclamation & Response / Thanksgiving & Communion / Sending Forth); Book of Worship offers resources, not mandated text. https://www.umcdiscipleship.org/book-of-worship/an-order-of-sunday-worship-using-the-basic-pattern
- **PC(USA):** four-fold Gathering/Word/Eucharist/Sending; **communion often monthly/quarterly** — the whole Eucharist block is conditional, not just variable. https://pcusa.org/order-worship-faqs
- **Non-lectionary free churches:** sermon-series/topical planning, zero external calendar; need the entire calendar engine bypassable with manual per-week content as a first-class path. https://network.crcna.org/topic/leadership/pastors/something-other-lectionary

**Design takeaway:** model services as ordered slots tagged fixed (ordinary) / calendar-variable (proper) / occasion-variable (rite type). A "setting" = a bundle of fixed-slot texts+music, selectable per-service.

## 2. Call-response formatting conventions

- Lutheran: **P:/C:** dominant (some ELCA use A: for Assembly).
- Episcopal/Anglican: **Celebrant/People** spelled out; Officiant for offices; Deacon for dismissal. Bulletins print responses in full so congregants don't juggle the BCP. https://www.ecfvp.org/blogs/2384/bulletin-vs-prayer-book
- Catholic: **Priest/All** (USCCB); some use Presider/Assembly.
- Generic ecumenical: **L:/P:** — "P" means opposite things across traditions (Pastor vs People). **Role labels must be per-church configuration over semantic roles.**
- **Bold-for-congregation** widely replaces/supplements letter codes.
- **Rubrics** historically red, now usually italic — a distinct semantic content type (instruction vs spoken text). https://en.wikipedia.org/wiki/Rubric
- **℣/℟ versicle symbols** (U+2123/U+211F) in office/litany contexts.
- Chanted texts: mostly "(sung)" or tone numbers; inline pointing/notation is the exception (stretch feature).

## 3. Alternative calendars & lectionaries

- **RCL:** 3-year A/B/C from Advent; post-Pentecost **Propers number backward from Advent** (last = Proper 29). https://lectionary.library.vanderbilt.edu/faq/
- **Catholic Ordinary Time:** same Sundays, forward-consecutive numbering; readings largely the same texts, different labels; separate weekday Year I/II axis.
- **One-year historic lectionary:** LCMS option (not universal within LCMS — congregations choose 1-year vs 3-year Series A/B/C). https://www.lcms.org/worship/lectionary-summaries
- **Narrative Lectionary:** Luther Seminary, 4-year cycle, **September–May**, one primary preaching text per week (structurally different props-per-week shape); 480+ congregations across 30+ denominations. https://www.workingpreacher.org/home-narrative-lectionary
- **Season of Creation:** Sept 1–Oct 4 overlay on any base lectionary. https://seasonofcreation.com/
- **Occasional services:** Ash Wednesday/Holy Week = date-triggered propers; weddings/funerals = event-triggered rites with no calendar date.

**Design takeaway:** pluggable lectionary scheme per church; numbering-vs-date resolution tables (same Sunday, different names); overlay mechanism; occasion-type track; full manual bypass.

## 4. Content sourcing landscape

| Tradition | S&S-equivalent |
|---|---|
| ELCA | sundaysandseasons.com (Augsburg Fortress) |
| LCMS | Lutheran Service Builder (CPH) — >1/3 of LCMS congregations |
| WELS | NPH Service Builder |
| Episcopal | RitePlanning (Church Publishing) — bundles BCP, BOS, LFF, NRSV, Hymnal 1982, LEVAS II |
| Catholic | OCP / GIA / Liturgical Press missalette subscriptions |

**Licensing floor:**
- **ELLC/ICET common texts** (Lord's Prayer, creeds, Gloria, Sanctus, Magnificat, Nunc Dimittis, Te Deum, Kyrie…) are **public domain** — exactly the "ordinary" blocks a rite library needs. http://www.icelweb.org/copyright.htm
- Older BCPs effectively public domain (1979 US BCP freely reproducible).
- **NRSV: explicit gratis use for church bulletins** up to 500 verses, "(NRSV)" attribution. Scripture reprinting is NOT the licensing bottleneck. https://bible.oremus.org/nrsvae/permiss.html
- **Hymn/music licensing is the real friction:** CCLI (contemporary) vs OneLicense (traditional/liturgical publishers); many churches need both; reprint legality is per-song → per-hymn license tagging is the licensing feature worth building. https://ccli.com/us/en/differences

## 5. The pain (firsthand accounts)

- Bulletin prep framed as consuming "an entire workday each week." https://churchjuice.com/blog/church-bulletins-are-awful
- Copy-paste/typo errors are a recognized genre (compiled blooper lists). https://www.patheos.com/blogs/ponderanew/2018/03/15/62-terrible-church-bulletin-mistakes/
- Print locks in errors; last-minute changes structurally hard. https://usebltn.com/digital-bulletins/
- Space fights over late announcements; governance never formalized.
- **Workforce fragility:** the church-secretary role is disappearing; the producer is increasingly a part-time volunteer non-specialist — tooling must reduce required liturgical/copyright expertise. https://churchanswers.com/blog/seven-reasons-church-secretary-position-disappearing/
- Licensing anxiety over-weighted relative to scripture (free); concentrates on hymns.
- Reddit-specific firsthand threads not surfaced by search (unconfirmed-findable, not negative evidence).

## Cross-cutting design implication

Four independently-configurable axes: (1) **Rite/Ordo**, (2) **Setting** (fixed-slot texts+music, per-service selectable), (3) **Calendar/Lectionary scheme** (swappable + overlayable), (4) **Role/typography convention**. Traditions differ enormously in content and vocabulary, far less in shape.

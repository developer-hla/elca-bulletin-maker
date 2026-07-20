# Real Bulletin Structure — Field Corpus (July 2026)

11 real, dated (2023–2026) bulletin PDFs fetched from live church websites and parsed end-to-end across 6 traditions (4 ELCA/LCMS Lutheran, 3 Episcopal, 1 Catholic worship aid, 2 UMC, 2 PC(USA)). WELS/ACNA could not be sampled (gap noted). Full URL list at bottom.

## Catalog (condensed)

| Church / Tradition | Date | Pages | Notes |
|---|---|---|---|
| Elk River Lutheran (ELCA) | 2023-07-23 | 8 | Liturgy = 1 of 8 pages; hymns by number only; rest is announcements/prayer list/kids' sheet |
| Augustana Lutheran, Portland (ELCA) | 2026-01-11 | 4 | Full lyrics inline; readings by citation; jazz service |
| Trinity Lutheran, Columbia MO (LCMS) | 2025-07-27 | 24 | Lutheran Service Builder output; full scripture text; notation images for all sung ordinary; creed with per-phrase verse footnotes; 4-page newsletter insert |
| St. George's Episcopal, Fredericksburg (Rite II) | 2025-08-10 | 20 | Full lyrics + some notation; land acknowledgment; categorized prayer list |
| St. Stephen's Episcopal, Richmond (Rite II) | 2025-05-18 | 8 | Bishop visitation: confirmation + vestment-dedication modules grafted onto base ordo; 1 page = ~90-name prayer list |
| St. Philip's Episcopal, Palatine (Rite I) | 2025-10-05 | 24 | Elizabethan text, Willan notation, birthdays, 2-week calendar, visitor explainer |
| Saint Michael Parish (Catholic worship aid) | Christmas 2025 | 12 | Same Roman ordo ×4 Mass times, only music varies; ZERO announcements (separate parish bulletin exists) |
| UMC Shrub Oak NY | 2025-12-21 | 9 | L:/P: dialogue; Advent candle ritual; heavy announcements |
| Myers Park UMC, Charlotte | 2025-08-24 | 8 | Concert-program style music notes; ASL noted; ~7 announcement paragraphs |
| Basking Ridge PC(USA) | 2025-03-09 | 4 | Litany confession; ~30-event week calendar |
| Faith Presbyterian, Sun City AZ | 2025-07-27 | 8 | Large-print format; plain language; scam-warning notice |

## Block-type vocabulary

**Universal (all 6 traditions):** heading · rubric (italic stage direction) · dialogue (leader/people, however labeled) · hymn-ref · reading (ref or full) · sermon-block · freeform-prayer · announcement-block · welcome-note · serving-list · staff-directory · giving-block (QR).

**Most-but-not-all:** hymn-lyrics (full text) · prayer-list · calendar-block.

**Tradition-concentrated:** notation-image (LCMS/Episcopal/Catholic; absent in UMC/Presbyterian samples) · eucharistic-prayer block (sacramental traditions/communion Sundays) · psalm-responsive with pointing (Episcopal/Catholic/LCMS) · creed-with-verse-footnotes (LSB software artifact) · birthdays/anniversaries (small-mid congregations) · children's-worksheet (1 occurrence) · **special-occasion-insert modules** (every tradition — pluggable module on a base ordo, not separate templates).

## Ordo diversity

**Within-tradition variance is LOW — almost entirely tone/music, not structure.** Two very different ELCA churches share the same ~15-element skeleton; LCMS skeleton variance ≈ 0 by design (software-generated from shared hymnal); both UMC samples follow the published 4-part pattern element-for-element; both Presbyterian samples share the Reformed skeleton despite opposite vibes.

**Between-tradition variance concentrates in one seam: whether communion happens weekly** (the whole Eucharist macro-block present/absent). Role-label conventions cluster by tradition but are presentational.

**Verdict: ~10 starter templates cover the large majority**, plus a library of pluggable occasion modules (baptism/confirmation, episcopal visitation, Advent candles, Christmas/Holy Week, multi-service-time variants) layered onto any base.

## The announcements problem

Non-liturgical content is routinely **30–75% of a real bulletin by page volume** (Elk River ~75%; UMC ~50–55%; Episcopal ~25–45%; Presbyterian ~40–50%; LCMS ~30–35%). Exception: Catholic **worship aids** are liturgy-only because parishes print a separate announcement bulletin (often ad-supported via LPi).

Scope implication: liturgy-only is a legitimate real-world document type (Catholic model), but diverges from "what most churches hand out." If the promise is "recreate your bulletin," structured announcement blocks (prayer list, calendar, serving list, staff directory, freeform) are unavoidable; if "generate your order of service," current scope is honest — but must be framed explicitly.

## Import feasibility

- **None of the 11 were scans** — all machine-generated with extractable text (InDesign, Publisher, Word, Lutheran Service Builder, RitePlanning). Sample skews web-savvy; analog-leaning parishes remain an OCR risk pool.
- Liturgy body text overwhelmingly **single-column**; announcements are where multi-column/tables/photos live — the hard-to-parse content is exactly what a liturgy importer ignores.
- Tractable signals: closed vocabulary of section headings ("PROCESSIONAL HYMN", "THE COLLECT", "GOSPEL", "BENEDICTION"); regex-able role-letter dialogue; consistent hymn-line pattern.
- Trip-ups: notation images (skip staff, keep lyric lines); tables scrambling reading order; creed verse-footnotes needing cleanup; multi-service-time variants ("one skeleton, N time-keyed variants").
- **Verdict: "upload last week's bulletin → drafted rite" is tractable** via an LLM segmentation pass with human confirmation; assume file upload, never URL fetch (several church URLs 404'd during research).

## URLs analyzed

1. https://www.elkriverlutheran.org/uploads/2/1/5/0/21506420/8.30_worship_bulletin_2023.07.23.pdf
2. https://augustana.org/wp-content/uploads/2026/01/January-11-2026-Sunday-bulletin-jazz-lead.pdf
3. https://www.trinity-lcms.org/wp-content/uploads/2025/07/2025-7-27.Pentecost-7-DS1.pdf
4. https://www.stgeorgesepiscopal.net/wp-content/uploads/2025/08/Proper-14-08102025-1000_Final.pdf
5. https://ststephensrva.org/wp-content/uploads/2025/05/Easter-5-May-18-900-am-FINAL.pdf
6. https://stphilipspalatine.org/files/2025.10.5-Rite-I-Bulletin-Pentecost.pdf
7. https://saintmichaelparish.org/wp-content/uploads/2025/12/WA-12-24-25-Christmas-DT.pdf
8. https://umcso.com/wp-content/uploads/2025/12/Worship-Bulletin-for-December-21-2025.pdf
9. https://myersparkumc.org/wp-content/uploads/2025/08/8-24-2025-Online-Bulletin.pdf
10. https://brpc.org/wp-content/uploads/2025/03/FINAL-weekly-bulletin-March-9-2025.pdf
11. https://scfaith.org/wp-content/uploads/2025/07/Bulletin-July-27-2025-Web.pdf

Partial: St. Aidan Catholic (image/ad-dense, text layer present); WELS 2018 sample folder (unreadable); several dead links encountered (assume upload-based import).

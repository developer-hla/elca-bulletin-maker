# S&S/ELW Verification of Draft Daily-Office Rites

July 21, 2026 · Verification pass comparing the DRAFT rite JSONs
(`elw_morning_prayer.json`, `elw_evening_prayer.json`, `elw_night_prayer.json`,
`elw_service_of_the_word.json`) against the AUTHORITATIVE Sundays & Seasons
(S&S) HTML saved at `/Users/malloryashmore/.claude/jobs/9ff3b560/tmp/sns_verify/`.
S&S is Augsburg Fortress's own platform, so its liturgy text and ordo *is* ELW
— this pass replaces a manual physical-book check. No code, rite, or test
files were edited; this is a findings-only report. No S&S credentials or
network access were used — the four saved HTML files plus the draft JSONs
were the only inputs.

Short incipits and element names are cited below to identify what's being
compared; AF-copyrighted running text is deliberately NOT reproduced at
length.

---

## Prioritized corrections needed

1. **Spurious "Kyrie" block in all three Daily Offices.** Matins, Vespers,
   and Compline drafts each insert a standalone `dialogue` block titled
   "KYRIE" (the ancient threefold "Lord, have mercy / Christ, have mercy /
   Lord, have mercy") inside "Prayers." **None of the three S&S ordos have a
   discrete Kyrie in this form or position.** It looks carried over from the
   Sunday Communion rite without basis. (Vespers does contain a *litany*
   whose responses are "Lord, have mercy" repeated after each of 7
   petitions — structurally quite different from a bare 3-line Kyrie — see
   #2.)

2. **All three offices are missing the actual "Prayers" body.** The
   S&S-authoritative content that fills "Prayers" — Matins' "P: The Lord be
   with you / C: And also with you / P: Let us pray" opening plus its
   thanksgiving-and-intercession petition set; Vespers' full "In peace, let
   us pray to the Lord... Lord, have mercy" litany (7 petitions); Compline's
   opening verse "Hear my prayer, O Lord; listen to my cry..." — is absent
   from all three drafts. Each draft jumps straight from the "PRAYERS"
   heading to Kyrie/Lord's-Prayer/collect, i.e. the actual intercessory
   content of the office is currently unmodeled. This is the single
   largest structural gap found.

3. **Vespers: Phos Hilaron is bundled as the fixed light-canticle text, but
   S&S's actual default in that position is the prose "Thanksgiving for
   Light"** ("We give you thanks, O God, for in the beginning you called
   light into being…"). Phos Hilaron/"O Gracious Light" appears in the S&S
   ordo only as *one of eight* optional "Hymn of Light" musical settings
   (ELW #231, alongside #229, #230, #560–563), not as the ordo's mandatory
   prose element. Recommend adding the Thanksgiving for Light as the actual
   default and re-labeling Phos Hilaron as one alternative among several,
   or clearly documenting the substitution as a deliberate house choice.

4. **Matins and Evening Prayer `blessing` proper_slot has no PD fallback at
   all** ("No PD fallback bundled" — renders blank for a church with no S&S
   entitlement). Compline has a fallback but it's a mismatched reuse (see
   #9); the Service of the Word already has a proper dedicated fallback
   (`elw.aaronic_blessing`). Recommend giving Matins/Vespers a PD-appropriate
   blessing fallback for consistency (S&S's own Matins blessing text —
   "Almighty God, the Father, ☩ the Son, and the Holy Spirit, bless and
   preserve us" — is a short, traditional-form Trinitarian blessing that may
   be no more copyright-sensitive than the already-bundled
   `elw.aaronic_blessing`; a legal/owner check would settle it).

5. **Matins is missing the "Alleluia"** element — S&S has an explicit
   `elw_matins_alleluia_m: Alleluia.` line right after the opening
   dialogue+doxology, omitted in Lent. One word, trivially PD, easy add.

6. **Optional office hymn ("Song") missing/misplaced.** S&S places an
   optional assembly hymn between Psalmody and the Reading in all three
   offices (plus Compline has an additional optional "Night Hymn" before
   Confession). Vespers and Compline drafts have no `hymn_slot` at all;
   Matins has one (`office_hymn`) but it's placed *after* the Benedictus
   (gospel canticle) instead of between Psalmody and the Reading.

7. **`collect` proper_slot modeling mismatch.** All three offices model the
   post-Lord's-Prayer collect as `kind: "prayer_of_day"` (day/lectionary-
   variable, resolved from S&S's daily propers). But S&S's actual content in
   that position is a small **fixed** set of alternative office prayers —
   3 options for Matins, 3 for Vespers, 6 for Compline — none tied to the
   day's appointed collect. Worth reconsidering whether this should be a
   different `proper_slot` kind, or a set of `literal_text` options, rather
   than a per-day variable slot.

8. **Compline confession — worth a second provenance look.** ELW's own
   Option B ("I confess to God Almighty, before the whole company of
   heaven…") is a traditional confiteor-form text, textually closer to
   ancient/historic confession wording than our substituted 1662 BCP
   General Confession. Doc 10's flag #3 ("no verified PD English; 1662 is a
   working substitute, not verbatim") may be worth revisiting now that a
   concrete ELW-side candidate is identified — not a code change, just an
   owner/legal question.

9. **Compline blessing fallback reuses the exact opening text.** The
   `blessing` block's fallback is `pd.compline_open` — the same text used
   for the *opening* dialogue. S&S's two actual Compline blessing options
   ("Almighty and merciful God, Father ☩ Son and Holy Spirit, bless,
   preserve, and keep us…" / "Now in peace I will lie down and sleep…") are
   both distinct from the opening line. Minor text-quality issue, not
   fatal (the fallback isn't liturgically wrong, just not a faithful analog
   to either S&S option).

10. **Minor/documentation: Matins reading-response note.** The `reading`
    block's note names "Here endeth the reading" as the response phrase;
    S&S's actual two options are "The word of the Lord." and "Word of God,
    word of life." This is only in a `note` field (not rendered text) but
    is inaccurate documentation worth fixing.

11. **Minor: Matins' two-part opening vs. S&S's one-part dialogue.** Our
    draft uses two separate traditional BCP versicles ("O Lord, open thou
    our lips" + "O God, make speed to save us") plus a separate Gloria
    Patri block, where S&S's Matins ordo has one self-contained "Dialogue
    and Doxology" unit (option A or B, each already including its own
    embedded doxology). Not wrong — both are genuine historic Morning-
    Office elements — but it's a different decomposition of the same
    moment, not a 1:1 structural match. ("Make speed to save us" is
    historically the opening versicle for the *other* hours, not Matins
    specifically, in the BCP lineage — using it in Matins as well as
    Vespers is a minor traditional-office inconsistency, not an ELW error.)

12. **Low priority / explicitly optional: Matins is missing "Thanksgiving
    for Baptism"** as an alternate/additional ending "especially on
    Sundays." Substantial S&S content (roughly half the file) models an
    alternate baptismal-remembrance ending in place of, or alongside, the
    plain Blessing. Not a principal/required element; flagged for
    completeness only.

13. **Low priority: no Gathering-position "Thanksgiving for Baptism"
    alternative to Confession** modeled in the Service of the Word (a rare
    ELW variant, distinct from the mid-service Holy Baptism module_ref that
    replaces the Creed). Not covered by our doc 09 ordo either; flagged for
    completeness only.

---

## Confidence note on HTML parsing

No `BeautifulSoup`/`lxml` was available in this environment; I wrote a small
stdlib-only `HTMLParser` extractor that flattens block-level tags,
tagging headings and preserving div/class markers, then read the resulting
text top-to-bottom.

- **matins.html / vespers.html / compline.html — HIGH confidence.** These
  are rich, clearly-sequential liturgical scripts: full dialogue/canticle
  text, rubrics, and hymnal atom-codes (`elw_matins_*_m`, `elw_vespers_*_m`,
  `elw_compline_*_m`) appear interleaved in an evident service order, with
  no `<table>` tags or multi-column layout markers. I'm confident in both
  element identity and sequence for these three files.
- **service_of_word.html — LOW-MEDIUM confidence on sequence, HIGH on
  section membership.** This file has no dialogue text, no rubrics beyond
  one-paragraph blurbs, and no hymnal atom-codes — categorically different
  from the office files. Checking which HTML elements were bold (`<strong>`)
  revealed that ELW's own "central" (bold) items and "supportive"
  (non-bold) items are *grouped together* in the raw markup rather than
  interleaved in liturgical order — e.g. a literal top-to-bottom reading
  would place "Greeting" *after* "Kyrie" and "Canticle of Praise," which
  contradicts both universal ELW practice and our own doc 09 ordo (Gathering
  song → Greeting → Kyrie → Gloria → Prayer of the Day). This is strong
  evidence the source page is a grouped/diagram-style "Pattern for Worship"
  overview, not a linear script, so its DOM order was **not** treated as
  authoritative for fine-grained sequencing — only for confirming which
  elements exist and which section (Gathering/Word/Meal/Sending) each
  belongs to.
- I had no rendered screenshot or original CSS; all comparisons are from
  raw-HTML-derived text.

---

## Matins (Morning Prayer) — `elw_morning_prayer.json` ↔ `matins.html`

### Ordo alignment

| # | S&S element (ELW Morning Prayer) | Our block | Status |
|---|---|---|---|
| 1 | Dialogue and Doxology (opt. A/B, doxology embedded) | `opening_versicle_lips` + `opening_versicle_speed` + `gloria_patri` (3 blocks) | Present, different decomposition (see #11) |
| 2 | Alleluia (omitted in Lent) | — | **MISSING** (#5) |
| 3 | Psalmody (invitatory options + psalm, Ps 95/63/67/100…) | `psalm` (psalm, slot/responsive) | Present |
| 4 | Song (optional hymn, after Psalmody) | `office_hymn` (present but placed after Benedictus) | **MISPLACED** (#6) |
| 5 | Readings (+ response + reflection) | `reading` (reading_slot) | Present |
| 6 | Scriptural responsory (opt. A/B) | `responsory` (rubric only, no text) | Present as rubric — reasonable given [LIC] |
| 7 | Gospel Canticle: Benedictus (Song of Zechariah) | `benedictus` (PD KJV) | Present, correct canticle for this office |
| 8 | Prayers: "Lord be with you/Let us pray" + petitions | — | **MISSING** (#2) |
| 9 | (n/a — no Kyrie in S&S ordo) | `kyrie` (dialogue) | **NOT IN S&S ORDO** (#1) |
| 10 | Lord's Prayer (intro options + text) | `lords_prayer` (PD traditional) | Present |
| 11 | Closing office prayer (3 fixed alternatives) | `collect` (proper_slot, kind=prayer_of_day) | Present but modeled as day-variable, not fixed-alternative (#7) |
| 12 | Blessing | `blessing` (proper_slot, no fallback) | Present, but blank without entitlement (#4) |
| 13 | (optional) Thanksgiving for Baptism | — | Missing, low priority (#12) |

### Text provenance check

- Opening versicles / Gloria Patri: [PD] 1662/1928 BCP, correctly flagged as
  the traditional substitute for ELW's contemporary combined dialogue.
- Benedictus: [PD] KJV, correctly the canticle for Morning Prayer ("the song
  of Zechariah" per S&S) — no canticle mismatch.
- Responsory and collect/blessing: correctly left as [LIC]/[VAR] rubric or
  proper_slot rather than bundling ELW's copyrighted wording — sound
  provenance choice, aside from the fixed-vs-variable modeling question
  (#7) and the missing fallback (#4).

### Correctness issues

See prioritized list #1, #2, #4, #5, #6, #7, #10, #11, #12 above — all
Matins-relevant items are cross-referenced there to avoid duplication.

---

## Evening Prayer (Vespers) — `elw_evening_prayer.json` ↔ `vespers.html`

### Ordo alignment

| # | S&S element (ELW Evening Prayer) | Our block | Status |
|---|---|---|---|
| 1 | Dialogue (Service of Light, opt. A–F seasonal) | `service_of_light_rubric` (neutral paraphrase, [LIC] text omitted) | Present, reasonable |
| 2 | Hymn of Light (optional, 8 options incl. #231 "O Gracious Light" = Phos Hilaron) | — (Phos Hilaron instead placed as fixed canticle, see below) | **MODELED DIFFERENTLY** (#3) |
| 3 | Thanksgiving for Light (fixed prose prayer — the actual default in this position) | — | **MISSING** (#3) — our `phos_hilaron` block stands in its place |
| 4 | Psalmody (Ps 141 example given in full, or Ps 121/other) | `psalm` (title "Psalm 141") | Present, matches |
| 5 | Song (optional hymn, after Psalmody) | — | **MISSING** (#6) |
| 6 | Readings (+ response + reflection) | `reading` (reading_slot) | Present |
| 7 | Scriptural responsory (opt. A/B) | `responsory` (rubric only) | Present as rubric |
| 8 | Gospel Canticle: Magnificat (Song of Mary) | `magnificat` (PD KJV) | Present, correct canticle |
| 9 | Prayers: full litany ("In peace, let us pray to the Lord… Lord, have mercy" ×7) + closing prayer | — | **MISSING** (#2) |
| 10 | (n/a — litany's "Lord, have mercy" is embedded in the petitions, not a standalone Kyrie block) | `kyrie` (dialogue) | **NOT A MATCH FOR S&S'S FORM** (#1) |
| 11 | Lord's Prayer | `lords_prayer` (PD traditional) | Present |
| 12 | Closing prayer (3 fixed alternatives, after the litany) | `collect` (proper_slot, kind=prayer_of_day) | Present but modeled as day-variable (#7) |
| 13 | Blessing (opt. A/B) | `blessing` (proper_slot, no fallback) | Present, but blank without entitlement (#4) |

### Text provenance check

- Magnificat: [PD] KJV, correct canticle for Evening Prayer ("the song of
  Mary") — no mismatch.
- Phos Hilaron: [PD] Bridges 1899 — legitimate historic Vespers text, but
  per S&S's specific ordo it occupies the wrong structural slot (see #3);
  this is the one place where a PD choice is structurally, not just
  textually, different from the authoritative ordo.
- Service-of-Light dialogue and responsory correctly left as [LIC]
  rubric-only, sound provenance choice.

### Correctness issues

See #1, #2, #3, #4, #6, #7 above.

---

## Night Prayer (Compline) — `elw_night_prayer.json` ↔ `compline.html`

### Ordo alignment

| # | S&S element (ELW Night Prayer) | Our block | Status |
|---|---|---|---|
| 1 | Dialogue (opening versicle + sung option A/B) | `opening` (PD "quiet night" versicle) | Present |
| 2 | Night Hymn (optional, before Confession) | — | **MISSING** (#6) |
| 3 | Confession and Forgiveness (opt. A contemporary / opt. B traditional-form) | `confession` (PD 1662 General Confession, substitute) | Present, provenance nuance (#8) |
| 4 | Psalmody (Ps 4/33/34/91/130/134/136, one or more) | `psalm` (psalm, slot/responsive) | Present |
| 5 | Song (optional hymn, after Psalmody) | — | **MISSING** (#6) |
| 6 | Reading (one of 8 short options) | `reading` (reading_slot) | Present |
| 7 | Responsory ("Into your hands, O Lord, I commend my spirit") | `responsory` (dialogue, PD "into thy hands") | Present, good match |
| 8 | Gospel Canticle: Nunc Dimittis (Song of Simeon) | `nunc_dimittis` (PD KJV) | Present, correct canticle |
| 9 | Prayers: opening verse "Hear my prayer, O Lord…" + one of 6 fixed prayers | — | **MISSING** (#2) |
| 10 | (n/a — no Kyrie in S&S ordo) | `kyrie` (dialogue) | **NOT IN S&S ORDO** (#1) |
| 11 | Lord's Prayer | `lords_prayer` (PD traditional) | Present |
| 12 | (the 6 fixed prayers above, folded into "Prayers") | `collect` (proper_slot, kind=prayer_of_day) | Present but modeled as day-variable (#7) |
| 13 | Blessing (opt. A/B, both distinct from the opening text) | `blessing` (proper_slot, fallback=pd.compline_open) | Present, but fallback reuses the opening text rather than either S&S option (#9) |

### Text provenance check

- Nunc Dimittis: [PD] KJV, correct canticle for Night Prayer ("the song of
  Simeon") — no mismatch.
- Responsory "Into thy hands": good PD match to S&S's actual responsory
  text/reference (Ps 31:5), best provenance alignment of any responsory
  across the three offices.
- Confession: see #8 — S&S's own Option B is closer to traditional
  confiteor wording than the 1662 substitute; worth a second look, not an
  error.
- Opening/blessing: see #9 — reused text, minor quality issue.

### Correctness issues

See #1, #2, #6, #7, #8, #9 above.

---

## Service of the Word — `elw_service_of_the_word.json` ↔ `service_of_word.html`

### The `elw_hcPattern` / "Pattern for Worship" caveat

The saved `service_of_word.html` is titled **"Holy Communion: Pattern for
Worship"** — confirmed by the page's own `<h3>` heading. It is **not** a
distinct "Service of the Word" liturgy script; ELW/S&S does not appear to
publish one as a standalone page (our own doc 09 already models Service of
the Word as "Holy Communion minus the Meal," which this file's structure
supports). Its content is a compact overview:

- Four macro-sections (GATHERING / WORD / MEAL / SENDING) with one-line
  element names and a one-paragraph explanatory blurb per section.
- No dialogue text, no rubrics, no hymnal atom-codes.
- Elements are marked "central" via `<strong>` — bold: Greeting, Prayer of
  the Day, First Reading, Psalm, Second Reading, Gospel Acclamation, Gospel,
  Sermon, Hymn of the Day, Prayers of Intercession, Offering, Setting the
  Table, Great Thanksgiving (+ sub-parts), Words of Institution, Lord's
  Prayer, Communion, Blessing. Not bold (i.e. "supportive"/optional per
  ELW's own classification): Confession and Forgiveness, Thanksgiving for
  Baptism, Gathering Song, Hymn or Psalm, Kyrie, Canticle of Praise, Creed,
  Peace, Offering Prayer, Communion Song, Prayer after Communion, Sending of
  Communion, Sending Song, Dismissal.

**Is it a usable authority for our Service of the Word draft?** Partially,
and only at the section level (see the confidence note above for why the
in-section order was not trusted). What it DOES support:

- The Gathering→Word section membership and element list matches our SotW
  draft element-for-element: Confession→Gathering Hymn→Greeting→Kyrie→
  Canticle of Praise→Prayer of the Day→First Reading→Psalm→Second Reading→
  Gospel Acclamation→Gospel→Sermon→Hymn of the Day→Creed→Prayers of
  Intercession→Peace all appear, correctly grouped under Gathering/Word.
- That Kyrie and Canticle of Praise are legitimately part of this ordo (in
  contrast to the Daily Offices, where they are not) — no issue here.

**What it does NOT support — the residual open questions, unresolved by
this source:**

- The outline's "Offering," "Setting the Table," and "Lord's Prayer" all
  sit inside MEAL, on the assumption the Meal is always celebrated. The
  page is silent on how a Word-only truncation should be re-shaped — it
  neither confirms nor denies our draft's two explicit judgment calls
  (retaining the Offering; relocating the Lord's Prayer to right after the
  Offering, before the Blessing). Those remain owner/liturgist judgment
  calls, exactly as the rite's own `meta.notes` already says — this
  verification pass found no S&S evidence either way.
- Fine text-level accuracy (exact wording of Confession, Kyrie, Greeting,
  etc.) cannot be checked against this file at all, since it contains none
  of that text; verifying those would require either the actual Sunday
  Communion S&S page (not fetched in this job) or a physical/PDF ELW check.

**Verdict:** the derivation (Service of the Word = Holy Communion minus the
Meal) holds up at every level this file can check. The two structural
judgment calls the draft already flags remain open and are not something
this pass can resolve — recommend the owner confirm them against the pew
edition, or a fuller S&S fetch of the Holy Communion setting itself.

### Text provenance / correctness issues

None found beyond the two already-flagged, already-documented owner
judgment calls above. No new corrections identified for this rite from this
source.

---

## Summary by service

| Service | High-confidence corrections | Provenance-only notes | hcPattern-style caveat |
|---|---|---|---|
| Matins | Kyrie doesn't belong; Prayers body missing; Alleluia missing; hymn misplaced; blessing fallback blank; collect modeling | Two-part opening vs. one-part S&S dialogue; reading-response note wording | n/a — full script available, high confidence |
| Vespers | Kyrie doesn't belong; Prayers body (litany) missing; Phos Hilaron in wrong slot; hymn missing; blessing fallback blank; collect modeling | — | n/a — full script available, high confidence |
| Compline | Kyrie doesn't belong; Prayers body missing; hymn/night-hymn missing; collect modeling | Confession Option B closer to PD than assumed; blessing fallback reuses opening text | n/a — full script available, high confidence |
| Service of the Word | None found | Offering/Lord's-Prayer relocation remain unverified (owner call) | Source is a summary "Pattern" page, not a script — section-level only, in-section order not trusted |

---

## Ambiguous / unresolved items

1. Whether the Daily Office `collect` should really be day/lectionary-variable
   (as modeled) or a small fixed set of alternative prayers (as S&S shows) —
   this is a modeling question for the owner/architect, not something this
   pass can settle definitively, since some congregations do substitute the
   day's collect in daily prayer even though S&S's page shows fixed options.
2. Whether ELW's Compline confession Option B legally qualifies as public
   domain or close enough to it — a legal/owner question, not resolvable
   from the HTML alone (flagged, not decided).
3. The Service of the Word's Offering-retention and Lord's-Prayer-relocation
   judgment calls — genuinely unverifiable from any S&S source pulled in
   this job; would need a fuller Holy Communion S&S fetch or the pew
   edition itself.
4. Whether the S&S "Pattern for Worship" page's DOM order (bold items
   grouped separately from non-bold items) reflects an actual two-column
   layout in the source, or some other non-linear structure — I could not
   confirm without a rendered screenshot; I treated it conservatively as
   unreliable for sequencing either way.

# Public-Domain Liturgical Text Sourcing (+ Holy Week/Advent provenance)

July 20, 2026 · Pass 2, feeding the daily-office / Holy Week / Advent authoring. **Corrects two
sourcing assumptions with legal significance — read the corrections first.** Confidence: canticle
PD status and the manifest are fetch-verified against Wikipedia/ebible.org; a few items flagged
[VERIFY] need a final legal spot-check. Not legal advice.

## Two corrections that change what we can bundle

1. **The 1979 BCP is NOT public domain** (published 1979, ~49 yrs inside the 95-yr US term; no PD
   dedication found). Congregations photocopy it under informal tolerance, but that is not a legal
   basis for bundling into distributed software. **Use the 1662 English BCP or 1928 US BCP** (both
   now outside the term) as the PD substitutes. Treat all 1979-BCP contemporary wording as [LIC].
2. **ELLC "Praying Together" (1988) common texts are NOT public domain** — they carry "© ELLC,
   used by permission." That permission covers *liturgical reproduction in worship* (a church's
   bulletin) but NOT bundling into commercial/distributed software. This is the family of
   contemporary-English texts ELW uses (the "My soul proclaims…" Magnificat, the modern creeds,
   Sanctus, etc.). **Flag ELLC/ELW contemporary wording as [LIC]; bundle the Coverdale/KJV/1662
   traditional equivalents instead.**

**Consequence:** a daily office/rite built from BUNDLE-able PD text is a *traditional-language*
office (1662/KJV canticles), which is NOT verbatim ELW's contemporary wording. The both/and that
fits our entitlement model: **bundle the traditional PD text as the default/fallback; resolve
ELW's contemporary wording via the church's own Augsburg license when entitled.** A church with no
license still gets a complete (traditional-language) service; a licensed church gets ELW's exact
wording.

**Latent issue this surfaces (track for LWS-4/entitlement):** our EXISTING `static_text.py`
bundles ELW/ELLC-wording texts (Nicene Creed, Kyrie, Sanctus, etc.) unconditionally. That is fine
for the single *licensed* Ascension deployment, but bundling them to *other* churches without
entitlement is the same copyright problem. The entitlement model must eventually gate these too.

## [PD-BUNDLE] manifest — safe to include full text (proposed catalog keys)

| Key | Content | PD source |
|---|---|---|
| `pd.magnificat_bcp1662` / `pd.magnificat_kjv` | Magnificat (Luke 1:46-55) | 1662 BCP / KJV 1611 |
| `pd.benedictus_bcp1662` / `pd.benedictus_kjv` | Benedictus (Luke 1:68-79) | 1662 BCP / KJV |
| `pd.nunc_dimittis_bcp` / `pd.nunc_dimittis_kjv` | Nunc Dimittis (Luke 2:29-32) | 1549/1662 BCP / KJV |
| `pd.phos_hilaron_bridges` | "O Gladsome Light, O Grace" | Robert Bridges, 1899 |
| `pd.phos_hilaron_keble` | "Hail, Gladdening Light" | John Keble, 1834 |
| `pd.te_deum_bcp1662` | Te Deum | 1662 BCP |
| `pd.versicle_open_lips` | "O Lord, open thou our lips…" | Ps 51:15, 1662/1928 BCP |
| `pd.versicle_make_speed` | "O God, make speed to save us…" | Ps 70:1, 1662/1928 BCP |
| `pd.gloria_patri` | "Glory be to the Father…" | traditional doxology |
| `pd.compline_open` | "The Lord Almighty grant us a quiet night…" | 1928 BCP Compline |
| `pd.general_confession_bcp` | General Confession | 1662/1928 BCP |
| `pd.into_thy_hands` | "Into thy hands, O Lord…" | Ps 31:5, 1928 BCP |
| `pd.creed_apostles_traditional` | Apostles' Creed (traditional) | 1662/1928 BCP |
| `pd.sanctus_traditional` | "Holy, holy, holy, Lord God of hosts…" | traditional BCP |
| `pd.ash_wed_formula` | "Remember that you are dust…" / "Repent and believe…" | Gen 3:19 / Mark 1:15 KJV |
| `pd.footwashing_antiphon` | "A new commandment I give unto you…" | John 13:34 KJV |
| `pd.o_antiphons_neale` | "O come, O come, Emmanuel" verses | J.M. Neale, 1851 |
| `pd.scripture_*` | all readings/psalms/Words of Institution/Passion | KJV 1611 or WEB (explicit PD dedication, ebible.org) |

Full verified texts for the canticles/versicles are in the agent transcript; transcribe from
there (sourced), owner verifies.

## [LIC] — resolve via the church's ELW/Augsburg entitlement (never bundle)
ELW/ELLC contemporary canticles & creeds & Sanctus; ELW Phos Hilaron ("O gracious Light…");
contemporary opening versicles ("O God, come to my assistance…"); Ash Wednesday Invitation to
Lenten Discipline + Litany of Penitence (ELW wording); Good Friday Solemn Collects + modern
Reproaches/Adoration wording; the Exsultet (ALL modern English translations — ICEL/ELW/LSB/1979);
"Ubi caritas" singable English (Westendorf 1960); any S&S/ELW Advent-wreath scripts.

## [VAR] — variable/proper (lectionary readings, Collect of the Day, preface, local intercessions,
locally-composed Advent-wreath text, sermon).

## Holy Week / Advent structure notes (provenance highlights)
- **Palm Sunday** (overlay): procession + Passion — scripture [PD via KJV/WEB]; blessing-of-palms wording [LIC].
- **Ash Wednesday** (distinct): imposition formula [PD scripture]; Invitation + Litany of Penitence [LIC].
- **Maundy Thursday** (distinct): footwashing antiphon [PD]; stripping w/ Ps 22 [PD]; Ubi caritas English [LIC].
- **Good Friday** (distinct): ancient Reproaches/Adoration core is PD (Latin/Greek) but **all usable
  modern English translations are [LIC]** — the older 1662 PD collects contain superseded/offensive
  content. **Recommendation: commission fresh original English translations we own**, rather than
  reuse copyrighted or use the objectionable-PD wording. Owner decision.
- **Easter Vigil** (distinct, needs the child-rite/section engine extension): Service of Light +
  **Exsultet** (ancient Latin PD; all modern English [LIC] — same commission-fresh recommendation);
  Readings [PD scripture] + collects [LIC]; Baptism (traditional Apostles' Creed [PD]); Communion.
- **Advent wreath**: NO standard denominational text (Wichern 1839 devotional origin). Build the
  default from PD Isaiah verses + a simple rubric + (optionally) fresh owned prayer wording; ELW/S&S
  wreath scripts are [LIC]. The O Antiphons ("O come, O come, Emmanuel", Neale 1851) are [PD].
- Advent seasonal adjustments (no Gloria, Advent canticle) are practice/rubric — already handled by
  our seasonal-customs layer; ELW's specific Advent-canticle wording is [LIC].

## Flagged for owner/legal verification (do not treat as settled)
1. 1979 BCP status (confirm with Church Publishing before ANY 1979 wording is bundled).
2. Whether ELLC ever grants a commercial-bundling license (none found — only free liturgical reuse).
3. Compline Confiteor — no verified PD English; 1662 General Confession is a working substitute, not verbatim.
4. Good Friday Reproaches & Exsultet — no confirmed PD English; commission-fresh is the recommended path.
5. "Ubi caritas" — no PD singable English translation confirmed.
6. 1662 BCP UK Crown-Patent printing restriction — treated as not applicable to US bundling; confirm with counsel if serving UK churches.

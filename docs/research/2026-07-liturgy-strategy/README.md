# Liturgy-Tool Strategy Research — July 2026

Ideation-phase research for generalizing the ELCA bulletin maker into a flexible,
multi-tradition liturgy tool (rites-as-data, pluggable calendars/content sources,
publisher-account clearinghouse). Produced by parallel research agents, synthesized
in `00-strategy.html` (also published as a Claude artifact:
https://claude.ai/code/artifact/0897f010-0dbd-4936-bbaa-39ebf5279d9f).

| File | Contents |
|---|---|
| `00-strategy.html` | The synthesized strategy: thesis, four-axis model, design concept, directions + recommendation, clearinghouse pillar, feature bets, announcements fork, phased build plan (LWS-0..6), risks |
| `01-codebase-audit.md` | Where liturgical/ELCA assumptions live in this repo, file:line, chokepoints ranked by blast radius |
| `02-domain-research.md` | Service-structure variability across traditions, call-response conventions, alternative calendars/lectionaries, content sourcing + licensing, bulletin-production pain |
| `03-bulletin-corpus.md` | Empirical survey of 11 real church bulletins across 6 traditions: block vocabulary, ordo diversity, the announcements problem, import feasibility |
| `04-competitive-landscape.md` | Sundays & Seasons, Lutheran Service Builder, RitePlanning, Planning Center, Proclaim/ProPresenter, scheduling tools, DIY workflow; landscape table, gaps, pricing norms |
| `05-open-data-audit.md` | Machine-readable lectionary data, calendar-computation libraries, Venite LDF prior art, scripture APIs + licensing, hymn data; build-vs-borrow verdicts |
| `06-provider-postures.md` | Per-provider API/ToS/integration findings: Catholic publishers (closed), CCLI partner-API precedent (retired), OneLicense (manual-only) |

Related: the preserved Open Hymnal public-domain corpus (ABC notation + ThML XML,
license evidence, ~18 MB) lives at `/Users/malloryashmore/asc_luth/research-archive/open-hymnal/`
(kept outside the repo for size; see its MANIFEST.md).

Pending at time of writing: the consolidated S&S / Lutheran Service Builder /
RitePlanning ToS detail report (a research agent was still finishing); its
essential findings are summarized in `06-provider-postures.md` and the strategy doc.

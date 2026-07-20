# Content-Provider API / ToS / Integration Postures (July 2026)

Findings from targeted research agents on the "clearinghouse" pillar (church links its own
publisher subscriptions; we assemble/print from any of them). The S&S / Lutheran Service
Builder / RitePlanning ToS-detail consolidation was still in flight when this was written;
their capability profiles are in `04-competitive-landscape.md`. Update this file when the
consolidated report lands.

## Operating rules (owner-endorsed posture)

Permissionless-by-default with guardrails:
1. Every provider fetch uses the church's OWN paid credentials.
2. **The entitlement rule is non-negotiable**: content never flows to a church without its
   own subscription (already enforced in code for S&S). This is the line between
   "integration tool" and "piracy vector."
3. Fetch politely, cache aggressively (load providers less than a human clicking through).
4. Treat every provider as breakable: cache + graceful degradation + manual paste fallback.
5. Respond cooperatively if contacted; partnership letters framed as "your subscribers love
   this," sent when useful, not as permission gates.
6. Realistic risk = provider breakage and church-account suspension, not courtrooms.

## Catholic publishers — CLOSED (verified from primary sources)

- **OCP / Liturgy.com**: no API/export (print + email-outline only). ToS verbatim: "You agree
  not to 'crawl,' 'scrape,' or 'spider' any part of our website or to reverse engineer…"
  Content sharing restricted; accounts capped. Verdict: blocked.
- **GIA** (absorbed WLP in 2020): no API/export; GIAPlanner is web-only. No published Terms
  of Use at all (no explicit prohibition, but nothing to rely on); copyright policy delegates
  reprint rights to OneLicense. Verdict: unclear/blocked; treat WLP as GIA.
- **LPi / 4LPi**: not a content source — a competing ad-supported bulletin-production
  service. Data flows INTO LPi (parishes upload finished bulletins). ToS bars building
  products from their content. Realistic relationship: parishes upload OUR PDFs to LPi
  Express (no integration needed).
- Industry-wide, the only integration point is **ONE LICENSE**, which is rights-REPORTING,
  not content delivery.
- Combined with USCCB's paid-per-parish lectionary licensing (see 05): **Catholic segment
  out of scope.**

## CCLI / SongSelect — Partner API existed, now RETIRED (verified)

- Planning Center's SongSelect integration is real: OAuth-style account linking against
  CCLI's identity service; imports lyrics/ChordPro/chord charts; requires the church's own
  paid SongSelect subscription; deactivates after 60 idle days.
- CCLI ran a public "SongSelect Partner API" (OAuth2/OIDC + PKCE, Azure APIM keys, rate
  limits 100/10s) — Postman doc carries the notice: **"CCLI has retired the SongSelect API
  Partner Program and is no longer accepting new API partners."** No successor found.
- Multi-partner precedent confirmed: Planning Center, WorshipTools, Elvanto, Subsplash
  (grandfathered).
- Implication: **no sanctioned programmatic path today**; hymn music = user-mediated file
  import (churches upload what they're licensed for). The precedent ("what Planning Center
  has") is a concrete partnership ask at scale.

## OneLicense — nothing (verified)

Manual Select → Report → Support website workflow; account downloads of licensed
music/text files; **no API, developer, or partner program of any kind found**.
Opportunity inversion: we can GENERATE the church's OneLicense/CCLI usage report from
generation history — a loved feature with zero legal exposure.

## Protestant liturgy publishers (capability profiles in 04; ToS detail pending)

- **Sundays & Seasons (ELCA)**: no API; web UI; we integrate in production today via
  church-owned credentials + encrypted vault + entitlement-gated cache. Continue.
- **Lutheran Service Builder (CPH/LCMS)**: no API found; the strongest incumbent product.
  Phase-target for credential-linked probing under the same rules, pending ToS read.
- **RitePlanning (Church Publishing/Episcopal)**: no API found; 1979 BCP being public
  domain shrinks what we'd even need from them. Later segment.

# Hosted-mode hardening notes

What the app does to be safe to host, and the one open question to
settle before offering a public URL to other congregations.

## Credential handling (by design)

- Each congregation signs in with **its own Sundays & Seasons
  subscription**. Credentials pass through to S&S at login and are
  never written anywhere; the S&S session cookie lives only in the
  per-session `SundaysClient` in memory.
- Sessions expire after 8 hours of inactivity; expiry closes the S&S
  client and deletes any generated-PDF temp directories.
- Nothing user-specific persists across container restarts (see
  `hosted-deploy.md`).

## Hosted mode switches (`BULLETIN_HOSTED=1`)

- Session cookie marked `Secure` (HTTPS-only).
- Login rate limiting: 10 attempts per address per 5 minutes, HTTP 429
  after that — S&S account protection, not just server protection.

## Sundays & Seasons terms of use (reviewed July 2026)

The public [privacy and terms](https://www.sundaysandseasons.com/privacy-and-terms/)
page **does not address** automated/programmatic access, account access
by tools acting on a subscriber's behalf, or third-party services —
neither permitting nor prohibiting them. The Annual License each
subscriber holds is precisely for reproducing S&S liturgical content in
their congregation's bulletins, which is all this tool does, and it
does so under each congregation's own login.

**Recommendation:** self-hosting for your own congregation is the same
access pattern as using the website. Before advertising a shared hosted
URL to other congregations, email Augsburg Fortress support, describe
the tool (each congregation authenticates with its own subscription;
content is only ever rendered into that congregation's bulletins), and
ask for written confirmation. Until then, prefer pointing other
congregations at `uv tool install` so each runs its own copy.

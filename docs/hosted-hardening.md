# Hosted-mode hardening notes

What the app does to be safe to host, and the one open question to
settle before offering a public URL beyond your own congregation.

## Account & credential model (July 2026)

- Users sign in with **app accounts** (email + password, scrypt-hashed).
  Volunteers never see or handle the Sundays & Seasons password.
- Each church's S&S credential is linked once by an admin and stored
  **encrypted at rest** (Fernet) in the SQLite database. The encryption
  key is `$BULLETIN_SECRET_KEY` (hosted) or an auto-generated keyfile at
  `~/.bulletin-maker/secret.key` (local). Losing the key does not lose
  data — the church just re-links its S&S account.
- The credential is decrypted only in memory, per session, to log into
  S&S on the church's behalf. It is validated against S&S *before* it
  is ever stored.
- Registration is gated: the first church registers freely (local first
  run); after that new churches require `$BULLETIN_REGISTRATION_CODE`.
  Members join with their church's invite code. With no code set, the
  instance is closed to new churches — the "just our church" posture.

## Hosted mode switches (`BULLETIN_HOSTED=1`)

- Session cookie marked `Secure` (HTTPS-only).
- Rate limiting on login, registration, join, and S&S-link attempts:
  10 per address per 5 minutes, HTTP 429 after that.

## Sessions & isolation

- Sessions expire after 8 hours of inactivity; expiry closes the S&S
  client and deletes generated-PDF temp directories.
- All content is church-scoped in the database (past runs, profile,
  S&S link); the test suite asserts cross-church isolation.

## Operational cautions

- **Back up `app.db`** (or its volume) — it now holds accounts and the
  encrypted S&S links. `secret.key` / `$BULLETIN_SECRET_KEY` must stay
  stable across restarts or every church re-links.
- There is no self-service password reset; an operator assists (by
  deleting/recreating the user row) until one is built.

## Sundays & Seasons terms of use (reviewed July 2026)

The public [privacy and terms](https://www.sundaysandseasons.com/privacy-and-terms/)
page **does not address** automated/programmatic access, account access
by tools acting on a subscriber's behalf, or third-party services —
neither permitting nor prohibiting them. The Annual License each
subscriber holds is precisely for reproducing S&S liturgical content in
their congregation's bulletins, which is all this tool does, and it
does so under each congregation's own linked subscription.

**Recommendation:** hosting for your own congregation is the same
access pattern as using the website. Before opening registration to
other congregations (i.e., before setting a registration code and
sharing it), email Augsburg Fortress support, describe the tool (each
church links its own subscription; content is only rendered into that
church's bulletins), and ask for written confirmation.

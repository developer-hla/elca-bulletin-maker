# Authentication & sessions

This describes the durable session model and the email-based auth token
flows exposed by the web adapter (`src/bulletin_maker/web/`).

## Sessions

Sessions are durable and survive process restarts.

- On login (register, join, `POST /api/session`, or magic-link consume) the
  server mints a random token, stores only its `sha256` hash in the
  `sessions` table, and sets it in the `bulletin_session` cookie
  (`HttpOnly`, `SameSite=Lax`, `Secure` when `BULLETIN_HOSTED=1`).
- Expiry is sliding: 30 days, refreshed on authenticated use. To avoid a DB
  write on every request, `last_seen`/`expires_at` are only refreshed when
  `last_seen` is older than ~1 hour.
- `DELETE /api/session` (logout) deletes the session row and clears the
  cookie.
- Expired rows are pruned opportunistically when a new session is created.
- Runtime state that cannot be persisted lives in process memory: the shared
  Sundays & Seasons client is cached per church; the fetched day, hymn-lyrics
  cache, and in-flight generation jobs are cached per session. This state is
  rebuilt lazily after a restart.

## Auth token flows

Tokens are random (`secrets.token_urlsafe`), single-use, and stored only as a
`sha256` hash in the `auth_tokens` table. Issuance never reveals whether an
account exists (no enumeration). Rate limiting per `email+IP` is active when
`BULLETIN_HOSTED=1`.

| Purpose | Lifetime | Link |
| --- | --- | --- |
| `reset` (password reset) | 30 minutes | `{APP_BASE_URL}/#reset={token}` |
| `magic` (magic sign-in)  | 30 minutes | `{APP_BASE_URL}/#magic={token}` |
| `verify` (email verify)  | 7 days     | `{APP_BASE_URL}/#verify={token}` |

### Endpoints

- `POST /api/auth/forgot` `{email}` — always returns `{"success": true}`.
  If the account exists, emails a password-reset link.
- `POST /api/auth/reset` `{token, new_password}` — sets the password,
  invalidates **all** of the user's sessions and outstanding reset tokens.
  `400` if the token is invalid/expired/used; `422` if the password is too
  short.
- `POST /api/auth/magic` `{email}` — always returns `{"success": true}`.
  If the account exists, emails a sign-in link.
- `POST /api/auth/magic/consume` `{token}` — creates a session and returns
  the same shape as `POST /api/session`. `400` if invalid/expired/used.
- `GET /api/auth/verify?token=...` or `POST /api/auth/verify` `{token}` —
  marks the email verified. `400` if invalid/expired/used.

Email verification tokens are issued and emailed automatically on register
and join. Verification is soft: unverified users can still use the app.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | Base URL used to build email links. |
| `EMAIL_PROVIDER` | `console` | Email backend: `console` (logs the message; used in dev/tests) or `resend`. |
| `RESEND_API_KEY` | — | Required when `EMAIL_PROVIDER=resend`. |
| `EMAIL_FROM` | — | From address; required when `EMAIL_PROVIDER=resend`. |

The `console` backend logs each message. Under pytest it also captures
messages in `bulletin_maker.web.email.sent_for_tests`. The `resend` backend
`POST`s to `https://api.resend.com/emails` and fails fast if
`RESEND_API_KEY` or `EMAIL_FROM` is missing.

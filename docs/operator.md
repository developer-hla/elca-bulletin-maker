# Operator Console

The operator console is the service owner's cross-church admin panel. It is
gated by a per-user `operator` flag (migration `006_operator.sql`) and lives
under `/api/operator/*` plus an in-app panel reachable from the **Operator**
link in the header (shown only to operators).

## Granting the operator flag

There is no self-service path — the first operator is granted by hand against
the database:

```sql
UPDATE users SET operator = true WHERE email = 'owner@example.org';
```

An operator can be any existing user. The flag is on the user, not the church,
so an operator keeps console access regardless of which church they belong to.
Revoke by setting the column back to `false`.

## Endpoints

All endpoints require an operator session; a non-operator (member, plain admin,
or anonymous) receives `403` (or `401` if not signed in).

| Method & path | Purpose |
| --- | --- |
| `GET /api/operator/churches` | Roster: per church `{id, name, plan, disabled, member_count, sns_linked, last_generate_at, generates_this_month}`. |
| `POST /api/operator/churches/{id}/disable` | Suspend a church (`churches.disabled = true`). |
| `POST /api/operator/churches/{id}/enable` | Lift the suspension. |
| `POST /api/operator/users/{id}/reset-password` | Send the standard password-reset email to that user. |
| `GET /api/operator/jobs` | Latest ~50 generation jobs across all churches, with an error snippet on failures. |
| `GET /api/operator/cache` | `sns_cache` stats: `{entries, oldest_fetched_at, newest_fetched_at, by_kind}` (kind = key prefix before `:`). |
| `GET /api/operator/audit` | Latest ~100 audit events. |

The roster and every other response report `sns_linked` as a boolean only. The
S&S username, the encrypted password blob, and password hashes are never
included in any operator response.

## What "disable" does

Disabling a church sets `churches.disabled = true`. Enforcement lives where
identity is resolved:

- **Login** (`POST /api/session`) is refused with `401` and the message
  "This account is suspended — contact support."
- **In-flight sessions** are refused the same way — `whoami` (`GET /api/session`)
  and any endpoint behind `require_user` return `401` on the next request.

Operators are exempt: an operator can always sign in and use the console even
if their own church is disabled. Enabling the church restores access
immediately; no session cleanup is required because the checks are evaluated
per request.

## Audit semantics

`audit_log` records who did what, when. Each row is
`{actor_user_id, church_id, action, detail_jsonb, at}`; the audit endpoint joins
in the actor's email and church name for display. Recorded actions:

| Action | Written when |
| --- | --- |
| `church_registered` | A new church registers. |
| `member_joined` | A member joins with an invite code. |
| `sns_linked` | An admin links (or re-links) the church's S&S account. Detail is empty — no credential is ever stored in the log. |
| `church_disabled` / `church_enabled` | An operator toggles a church's status. |
| `password_reset` | An operator triggers a reset email for a user. |

Audit writes are best-effort side effects of the primary action and never
contain secrets.

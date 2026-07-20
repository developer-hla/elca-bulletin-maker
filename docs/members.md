# Church members (admin)

Endpoints for a church admin to manage their own church's roster, invite
code, and usage. All are **admin-only** (`require_admin`) and strictly
scoped to the caller's church — an admin can never read or mutate another
church's rows. Queries live in `web/members.py`; the endpoints are in
`web/server.py`. The Settings panel surfaces these in an admin-only
"Members" card and the invite card.

## Endpoints

- `GET /api/church/members` — the church's roster:
  `[{id, email, display_name, role, email_verified, created_at, is_you}]`,
  ordered by `created_at`. `is_you` marks the requesting admin.
- `DELETE /api/church/members/{user_id}` — remove a member of the admin's
  church. Refused with `422` if:
  - the target is the church's **last admin** ("You can't remove the last
    admin."), or
  - the target is **yourself** ("You can't remove yourself.").

  `404` if `user_id` is not a member of the caller's church. On success the
  removed user's sessions are invalidated (`store.invalidate_user`) so they
  are signed out immediately. `jobs.user_id` has no cascade, so the member's
  jobs are set to `NULL` before the user row is deleted; sessions and
  auth_tokens cascade.
- `POST /api/church/invite/send` `{email}` — emails the church's invite code
  and a `APP_BASE_URL/#join=<code>` link to `email`. `422` if the address is
  not a valid email. Rate-limited per (email, IP) when `BULLETIN_HOSTED=1`.
- `POST /api/church/invite/regenerate` — rotates the invite code to a new
  `secrets.token_urlsafe(9)` value, stores it, and returns
  `{invite_code}`. The old code stops working for `POST /api/join`
  immediately.
- `GET /api/church/usage` — `{generates_this_month, member_count}`.
  `generates_this_month` counts rows in `jobs` for the church since the
  start of the current UTC calendar month (same source as plan limits);
  `member_count` counts the church's users.

## Rules

- Admin-only: non-admins get `403` on every endpoint above.
- Church-scoped: every query filters by the caller's `church_id`.
- The last remaining admin cannot be removed, and no one can remove
  themselves — a church always keeps at least one admin.

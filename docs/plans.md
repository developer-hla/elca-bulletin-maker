# Plans & limits

Every church row carries a `plan` (text, `NOT NULL DEFAULT 'free'`). The
limits for a plan live in the `plans` table:

```sql
CREATE TABLE plans (
    plan        text PRIMARY KEY,
    limits_jsonb jsonb NOT NULL DEFAULT '{}'
);
```

The `free` plan is seeded with `'{}'` — no limits, so today's behaviour is
unchanged and every gate is a no-op.

## `limits_jsonb` schema

An object whose keys cap specific actions. **An absent key means that action
is unlimited.** Recognised keys:

| Key                   | Type | Meaning                                                  |
|-----------------------|------|----------------------------------------------------------|
| `max_users`           | int  | Most user accounts a church may have.                    |
| `generates_per_month` | int  | Most bulletin generations per calendar month (UTC).      |

Example (a hypothetical paid tier):

```json
{ "max_users": 10, "generates_per_month": 50 }
```

The schema is extensible: new keys are additive and any key a plan omits stays
unlimited. Adding a new *action* means adding a check function in
`src/bulletin_maker/web/plans.py` and a gate call in `server.py`.

## Enforcement

`plans.check_limit(church, action)` (in `src/bulletin_maker/web/plans.py`)
reads the church's plan row and raises `PlanLimitError` on violation.
`server.py` maps that to **HTTP 403** with body
`{"error": <message>, "error_type": "plan_limit"}` via a single app-level
exception handler. Gates are called at the top of:

- `POST /api/join` — action `"join"`, checks `max_users`.
- `POST /api/generate` — action `"generate"`, checks `generates_per_month`.

### How counts are measured

- **Users** — `SELECT COUNT(*) FROM users WHERE church_id = …`.
- **Generations** — `SELECT COUNT(*) FROM jobs WHERE church_id = … AND
  created_at >= <first of this UTC month>`.

**Why `jobs` and not `past_runs`?** `jobs` is one row per generation with a
`created_at` timestamp — the honest record of "a bulletin was generated."
`past_runs` is a capped, per-service-date deduplicated *history* (see
`db.MAX_PAST_RUNS`, and its per-`service_date` DELETE), so it would badly
undercount a month's activity. Note: the current `server.py` keeps live job
state in memory and does not yet persist rows to the `jobs` table, so the
generation count is scaffolding-accurate — it becomes live once job
persistence lands in a separate workstream.

## Creating a paid plan by hand (until billing exists)

There is no billing UI yet. To grant a church a paid plan manually:

```sql
INSERT INTO plans (plan, limits_jsonb)
VALUES ('parish', '{"max_users": 10, "generates_per_month": 50}');

UPDATE churches SET plan = 'parish' WHERE id = <church_id>;
```

Removing a limit key (or setting the plan back to `free`) restores unlimited
behaviour for that action.

## Billing scaffold — what stays untouched

Migration `005_billing_scaffold.sql` adds one nullable column,
`churches.billing_customer_id text`, as a Stripe-shaped placeholder for a
payment-provider customer id. That is the **entire** billing surface today:

- No Stripe SDK, no webhooks, no payment endpoints.
- Nothing reads or writes `billing_customer_id` yet.
- Plan rows and `churches.plan` are edited by hand (see above).

A real billing workstream later wires `billing_customer_id` to a provider,
adds checkout/webhook endpoints, and automates plan assignment. Until then,
none of that code exists and plans are managed purely in SQL.

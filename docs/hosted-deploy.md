# Hosted deployment

The Dockerfile at the repo root runs the same FastAPI app as the local
`bulletin-maker` command. **Note:** the image has not been built on the
development machine (no Docker available) — build it in CI or on first
deploy and smoke-test `/api/instance` before announcing a URL.

Before hosting for anyone beyond your own congregation, read
`docs/hosted-hardening.md` (credential vault, registration gating, and
the Sundays & Seasons terms-of-use question).

## Persistence is now REQUIRED

Since the accounts rework, the app stores accounts, church profiles,
and encrypted S&S links in PostgreSQL (`$DATABASE_URL`, default
`postgresql://localhost/bulletin_maker`). The schema is applied
automatically from `migrations/*.sql` on first connection. A container
with no database behind it loses everything on restart. Point
`DATABASE_URL` at a managed Postgres:

1. **A managed Postgres** (Neon, Supabase, Cloud SQL) with `DATABASE_URL`
   set to its connection string — the connection survives container
   restarts and scale-to-zero, or
2. any small always-on host running its own Postgres.

A serverless Postgres such as **Neon** pairs well with a scale-to-zero
container: both idle to nothing and the data still persists. The database
needs the `citext` extension (`CREATE EXTENSION IF NOT EXISTS citext;`);
migrations create everything else.

Set `BULLETIN_SECRET_KEY` explicitly in either case — if the key is
auto-generated inside an ephemeral container, every restart invalidates
the stored S&S links.

## Google Cloud Run sketch

```bash
gcloud run deploy bulletin-maker \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --set-env-vars BULLETIN_HOSTED=1,DATABASE_URL=YOUR_POSTGRES_URL,BULLETIN_SECRET_KEY=YOUR_GENERATED_KEY
```

- Memory: 1 GiB — Chromium needs headroom; 512 MiB is too tight.
- Generate the key once with:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and keep it in a secret manager, not the shell history.
- Put the Postgres connection string (`DATABASE_URL`) in a secret manager
  too — it carries the database password. Neon's pooled connection string
  works well here at one-church scale.

## Hugging Face Spaces (free CPU tier, no card)

Docker-type Space with the root Dockerfile; set the app port to 8080
and point `DATABASE_URL` at an external managed Postgres (e.g. Neon).
Free Spaces have ephemeral disks, so a local database would not survive
restarts — an external `DATABASE_URL` is what makes the platform usable
beyond a demo.

## Environment variables

| Variable | Purpose |
|---|---|
| `PORT` | Listen port (injected by Cloud Run; defaults to 8080) |
| `BULLETIN_HOSTED` | Set to `1` over HTTPS — Secure cookies + auth rate limiting |
| `DATABASE_URL` | PostgreSQL connection string; defaults to `postgresql://localhost/bulletin_maker` |
| `BULLETIN_SECRET_KEY` | Fernet key for the S&S credential vault — must stay stable |
| `BULLETIN_REGISTRATION_CODE` | When set, new churches can register with this code; unset = closed after the first church |
| `BULLETIN_PROFILE` | Optional TOML seed profile for the first church (defaults to the bundled Ascension profile) |

## What still doesn't persist (by design)

Sessions (login state), generation jobs, and produced PDFs are memory /
tmpfs only and vanish on restart — users just sign in again and
regenerate. No document content is ever written to durable storage.

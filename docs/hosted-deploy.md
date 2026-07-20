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
and encrypted S&S links in SQLite (`$BULLETIN_DB`, default
`~/.bulletin-maker/app.db`). A scale-to-zero container with no volume
loses everything on restart. Two workable shapes:

1. **Cloud Run + a mounted volume** (GCS FUSE volume mount or a
   Filestore mount) with `BULLETIN_DB` pointed into it, or
2. any small always-on host (the free-tier VM class) where the disk
   simply persists.

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
  --add-volume name=data,type=cloud-storage,bucket=YOUR_BUCKET \
  --add-volume-mount volume=data,mount-path=/data \
  --set-env-vars BULLETIN_HOSTED=1,BULLETIN_DB=/data/app.db,BULLETIN_SECRET_KEY=YOUR_GENERATED_KEY
```

- Memory: 1 GiB — Chromium needs headroom; 512 MiB is too tight.
- Generate the key once with:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and keep it in a secret manager, not the shell history.
- SQLite over GCS FUSE is fine at one-church scale (single writer,
  weekly usage); revisit if multiple congregations join.

## Hugging Face Spaces (free CPU tier, no card)

Docker-type Space with the root Dockerfile; set the app port to 8080
and add a persistent storage upgrade (free Spaces have ephemeral disks —
without persistent storage this platform only suits demos).

## Environment variables

| Variable | Purpose |
|---|---|
| `PORT` | Listen port (injected by Cloud Run; defaults to 8080) |
| `BULLETIN_HOSTED` | Set to `1` over HTTPS — Secure cookies + auth rate limiting |
| `BULLETIN_DB` | SQLite path; point at the persistent volume |
| `BULLETIN_SECRET_KEY` | Fernet key for the S&S credential vault — must stay stable |
| `BULLETIN_REGISTRATION_CODE` | When set, new churches can register with this code; unset = closed after the first church |
| `BULLETIN_PROFILE` | Optional TOML seed profile for the first church (defaults to the bundled Ascension profile) |

## What still doesn't persist (by design)

Sessions (login state), generation jobs, and produced PDFs are memory /
tmpfs only and vanish on restart — users just sign in again and
regenerate. No document content is ever written to durable storage.

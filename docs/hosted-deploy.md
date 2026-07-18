# Hosted deployment

The Dockerfile at the repo root runs the same FastAPI app as the local
`bulletin-maker` command. Two free-tier, scale-to-zero options are
documented below. **Note:** the image has not been built on the
development machine (no Docker available) — build it in CI or on first
deploy and smoke-test `/api/profile` before announcing a URL.

Before hosting for anyone beyond your own congregation, read
`docs/hosted-hardening.md` (credential handling, rate limits, and the
Sundays & Seasons terms-of-use question).

## Google Cloud Run (free tier; needs a credit card on file)

```bash
gcloud run deploy bulletin-maker \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --set-env-vars BULLETIN_HOSTED=1
```

- Scale-to-zero: you pay nothing while idle; the free tier comfortably
  covers a congregation's weekly usage.
- Memory: 1 GiB — Chromium needs headroom; 512 MiB is too tight.
- Cold starts are a few seconds (container boot + first Chromium launch).

## Hugging Face Spaces (free CPU tier, no card)

1. Create a Docker-type Space.
2. Push this repo (the root Dockerfile is picked up automatically).
3. Set the Space port to 8080 in the Space settings (or add
   `app_port: 8080` to the Space README frontmatter).

- Free Spaces sleep after inactivity and wake on request — fine for
  weekly bulletin work.

## Environment variables

| Variable | Purpose |
|---|---|
| `PORT` | Listen port (injected by Cloud Run; defaults to 8080) |
| `BULLETIN_HOSTED` | Set to `1` when serving over HTTPS — marks the session cookie `Secure` and enables login rate limiting |
| `BULLETIN_PROFILE` | Optional path to a congregation profile TOML baked into the image (defaults to the bundled Ascension profile) |

## What the container does NOT persist

Sessions (S&S login cookies), generation jobs, and downloaded PDFs live
in memory / tmpfs and vanish on scale-to-zero. Past runs land in the
container's `~/.bulletin-maker`, which is also ephemeral — hosted users
should treat Past Runs as best-effort. This is intentional: no user
credentials or content are ever written to durable storage.

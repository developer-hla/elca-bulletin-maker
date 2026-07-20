# Durable jobs and artifact storage

Bulletin generation runs in a background thread, but its **state** and the
**generated PDFs** are stored durably so nothing is lost when the server
restarts.

## Jobs

Job state lives in the PostgreSQL `jobs` table (`web/jobstore.py`), not in
process memory:

- `POST /api/generate` inserts a `running` job and dispatches a worker thread.
- The worker appends progress entries and writes the final status, results,
  and errors back to the row.
- `GET /api/jobs/{job_id}` reads the row **church-scoped** — a job belongs to
  a church, and any member of that church may poll it.

Progress entries keep the exact shape the SPA polls:

```json
{"step": "scripture", "detail": "Rendering scripture", "pct": 50}
```

### Restart semantics

On startup the app runs `jobstore.recover_stale_jobs()`, which flips every job
still `queued`/`running` (left mid-flight by the crash/restart) to `failed`
with a human message:

> The server restarted while this bulletin was generating. Please generate
> again.

Generated files, however, survive a restart: they are streamed back from the
artifact store through the same authorized endpoints, so a download link keeps
working after a restart as long as the artifact has not expired.

## Artifacts

Each produced PDF is uploaded to an object store and recorded in the
`artifacts` table. Downloads always stream through the authorized endpoints
(`GET /api/jobs/{job_id}/files/{key}` and `/api/jobs/{job_id}/zip`) — there
are no public URLs and no redirects.

### Object key layout

```
{church_id}/{job_id}/{doc_key}/{filename}
```

### Backends

Selected by the `ARTIFACT_STORE` environment variable:

| `ARTIFACT_STORE` | Backend | Configuration |
| --- | --- | --- |
| `local` (default) | Files on disk | `BULLETIN_ARTIFACT_DIR` (default `~/.bulletin-maker/artifacts`) |
| `s3` | S3-compatible object store via boto3 | `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |

When `ARTIFACT_STORE=s3` is selected, all four `S3_*` variables are required;
a missing one fails fast at startup.

Install the S3 dependency with `pip install -e '.[s3]'` (adds `boto3`).

### Cloudflare R2

R2 is S3-compatible. Point the same variables at your R2 account:

- `S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`
- `S3_BUCKET=<your-bucket>`
- `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` — an R2 API token's credentials.

## TTL and cleanup

Artifacts expire 7 days after creation (`expires_at`). Expired objects and
rows are reclaimed by `purge_expired_artifacts()`, which is called
opportunistically whenever a new job is created.

For a scheduled sweep (e.g. cron), run:

```
python -m bulletin_maker.web.artifacts --purge
```

# Ops Runbook

For the tired operator at 7am on a Sunday. Every command below is meant to be
copy-pasted. Where a value is site-specific it is written as a shell variable
you set first.

Assumptions: you have shell access to the host running the app, the app is
started with `bulletin-maker` (or `uvicorn bulletin_maker.web.server:create_app`),
and `$DATABASE_URL` points at the live Postgres (e.g.
`postgresql://user:pass@host:5432/bulletin_maker`).

---

## 1. Is it up? (health check)

### Liveness endpoint

`GET /api/instance` is unauthenticated and touches the database (it counts
churches), so a `200` with JSON means both the web process and Postgres are
answering.

```sh
BASE_URL=https://your-host        # or http://127.0.0.1:8355 locally
curl -fsS "$BASE_URL/api/instance" && echo
```

Expected:

```json
{"success": true, "has_churches": true, "registration_open": false}
```

- Non-200 / connection refused -> the web process is down or unreachable.
- 500 -> the process is up but the database is not (see the logs below).

The response also carries an `X-Request-Id` header; include it when reporting a
problem so it can be grepped out of the logs:

```sh
curl -fsS -D - "$BASE_URL/api/instance" -o /dev/null | grep -i x-request-id
```

### Operator console (in-app)

Sign in as an operator account and use the console for a live jobs/error feed:

- `GET /api/operator/jobs` — recent generation jobs and their status.
- `GET /api/operator/audit` — recent audit events (registrations, links, etc.).
- `GET /api/operator/cache` — S&S cache stats.

These are the fastest way to see whether bulletin generation is failing for a
specific church without shell access.

---

## 2. Where the logs go

The app logs **warnings and errors only** (routine success is not logged). The
format is chosen by the `BULLETIN_LOG_JSON` environment variable.

### Local (developer machine)

`BULLETIN_LOG_JSON` unset or `0` -> human-readable lines on the console where
`bulletin-maker` is running:

```
2026-07-19 22:07:13,557 WARNING bulletin_maker.web.server: S&S account linked for church 'St. Test Lutheran'
```

There is no log file locally; logs go to the terminal (stderr). Scroll back in
that window, or run the app under `tee`:

```sh
bulletin-maker 2>&1 | tee -a ~/bulletin-maker.log
```

### Hosted

Set `BULLETIN_LOG_JSON=1`. Each log line becomes one JSON object, which the
platform's log collector (journald, Docker, Fly, etc.) can index:

```json
{"ts": "2026-07-19T22:07:13.557+00:00", "level": "WARNING", "logger": "bulletin_maker.web.server", "message": "S&S account linked for church ...", "request_id": "d55e83b6bfda", "church_id": 12, "user_id": 4}
```

Every request-scoped record carries `request_id`; authenticated records also
carry `church_id` and `user_id`; generation-worker records carry `job_id` and
`church_id`. To trace one request end to end, grep the id:

```sh
journalctl -u bulletin-maker | grep d55e83b6bfda        # systemd
docker logs bulletin-maker 2>&1 | grep d55e83b6bfda      # docker
```

Unhandled request errors are logged as `ERROR` with the request id and a
traceback, and the client receives the generic
`{"detail": {"error": "...", "error_type": "internal"}}` 500 body.

If `$SENTRY_DSN` is set, errors are also reported to Sentry (environment from
`$BULLETIN_ENV`, release = package version, tracing disabled). If the DSN is
unset, Sentry is completely dormant — nothing is sent and the SDK is not even
imported.

---

## 3. Backups

### How they run

`python -m bulletin_maker.web.backup` dumps `$DATABASE_URL` with
`pg_dump -Fc` (Postgres custom format) and uploads it through the app's
artifact store under the key `backups/<UTC timestamp>.dump`. It then prunes
old backups, keeping the newest `$BULLETIN_BACKUP_KEEP` (default 14). The
process exits non-zero on any failure so cron will complain.

`pg_dump` is located in this order: `$PG_DUMP`, then `pg_dump` on `PATH`, then
`/opt/homebrew/opt/postgresql@16/bin/pg_dump`.

Suggested cron line — daily at 02:15, keeping 14 days, appending output to a
log so a failure leaves a trace:

```cron
15 2 * * * cd /srv/bulletin-maker && DATABASE_URL='postgresql://user:pass@host/bulletin_maker' BULLETIN_BACKUP_KEEP=14 ARTIFACT_STORE=s3 S3_ENDPOINT_URL=... S3_BUCKET=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... /srv/bulletin-maker/venv/bin/python -m bulletin_maker.web.backup >> /var/log/bulletin-backup.log 2>&1
```

(Backups are deliberately **not** recorded in the `artifacts` database table —
a database backup must never depend on the database being up.)

### Where they live

- **Local store** (`ARTIFACT_STORE=local`, the default): under
  `$BULLETIN_ARTIFACT_DIR/backups/` (default
  `~/.bulletin-maker/artifacts/backups/`).
- **S3 / R2** (`ARTIFACT_STORE=s3`): in `s3://$S3_BUCKET/backups/`.

### List existing backups

```sh
python -m bulletin_maker.web.backup --list
```

Prints one line per backup: object key, size in MB, and UTC timestamp, oldest
first. The newest is the last line.

---

## 4. Restore procedure

You need: the same environment variables the app uses (`$DATABASE_URL`,
`ARTIFACT_STORE` and its credentials), and `pg_restore` / `createdb` from the
Postgres client tools. Work through these in order.

**Step 0 — pick the backup to restore.**

```sh
python -m bulletin_maker.web.backup --list
BACKUP_KEY=backups/20260719T021500Z.dump      # copy the key you want
```

**Step 1 — download the dump to a local file** (works for both local and R2
stores, via the same store abstraction the app uses):

```sh
python -c "from bulletin_maker.web.artifacts import get_store; open('/tmp/restore.dump','wb').write(get_store().open_stream('$BACKUP_KEY').read())"
ls -lh /tmp/restore.dump      # sanity: non-zero size
```

**Step 2 — create the target database.** Restore into a *fresh* database to
avoid colliding with live data. Set `RESTORE_DB` and derive an admin URL
(same server, `postgres` maintenance DB) for `createdb`:

```sh
RESTORE_DB=bulletin_maker_restore
ADMIN_URL='postgresql://user:pass@host:5432/postgres'
createdb -d "$ADMIN_URL" "$RESTORE_DB"
# The schema uses the citext extension; add it before restoring:
psql -d "postgresql://user:pass@host:5432/$RESTORE_DB" -c 'CREATE EXTENSION IF NOT EXISTS citext;'
```

**Step 3 — restore the dump.** Custom-format dumps are restored with
`pg_restore`. Use `--no-owner` (the restoring role owns everything) and
`--clean --if-exists` so a re-run is idempotent:

```sh
RESTORE_URL="postgresql://user:pass@host:5432/$RESTORE_DB"
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname "$RESTORE_URL" /tmp/restore.dump
```

A few `does not exist, skipping` notices on a fresh database are normal.
`pg_restore` exits non-zero on real errors — check the exit status:

```sh
echo "pg_restore exit: $?"
```

**Step 4 — check migrations are current.** The app applies its plain-SQL
migrations on startup. Confirm the restored schema is at the latest migration
before pointing the app at it:

```sh
psql -d "$RESTORE_URL" -c 'SELECT max(version) FROM schema_migrations;'
psql -d "$RESTORE_URL" -c '\dt'      # sanity: churches, users, jobs, artifacts, sessions all present
```

If `max(version)` is behind the code, boot the app once against this DB (Step 5)
— startup will apply any pending migrations.

**Step 5 — boot the server against the restored DB.**

```sh
DATABASE_URL="$RESTORE_URL" bulletin-maker
# or, headless:
DATABASE_URL="$RESTORE_URL" uvicorn --factory bulletin_maker.web.server:create_app --host 127.0.0.1 --port 8355
```

**Step 6 — smoke check.**

```sh
curl -fsS http://127.0.0.1:8355/api/instance && echo
```

Expect `{"success": true, "has_churches": true, ...}`. Then sign in through the
web UI and confirm the church list / recent runs look right.

**Step 7 — cut over.** Once verified, either rename `$RESTORE_DB` to the live
name or repoint the app's `$DATABASE_URL` at `$RESTORE_DB`, then restart the
production process. Keep the old database around until you are confident.

---

## 5. Deferred to WS-9 (needs a live deployment)

These three items require production infrastructure and are intentionally out
of scope for this workstream:

1. **UptimeRobot monitor** on `GET /api/instance` — external ping every 1–5
   minutes with alerting to the on-call channel.
2. **Billing budget alert** — a cloud-provider budget/spend alert so an
   unexpected cost spike is caught early.
3. **Secret provisioning** — set `$SENTRY_DSN` (turns on error reporting) and
   the R2 credentials (`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`,
   `S3_SECRET_ACCESS_KEY`) in the production environment so backups and
   artifacts land in R2.

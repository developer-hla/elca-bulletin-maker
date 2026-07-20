"""Durable generation jobs backed by the PostgreSQL ``jobs`` table.

Job state (status, streamed progress entries, results, errors) lives in
Postgres so it survives a server restart and can be polled by any member
of the owning church. The generation worker thread appends progress and
finishes the job here; the web layer reads it back church-scoped.

Progress entries keep the exact shape the SPA polls:
``{"step": key, "detail": text, "pct": int}``.
"""

from __future__ import annotations

from typing import Optional

from psycopg.types.json import Jsonb

from bulletin_maker.web import db

STALE_STATUSES = ("queued", "running")


def create_job(job_id: str, church_id: int, user_id: Optional[int],
               form_data: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, church_id, user_id, status, form_data_jsonb)"
            " VALUES (%s, %s, %s, 'running', %s)",
            (job_id, church_id, user_id, Jsonb(form_data)),
        )


def append_progress(job_id: str, entry: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET progress_jsonb = progress_jsonb || %s"
            " WHERE id = %s",
            (Jsonb([entry]), job_id),
        )


def finish_job(job_id: str, status: str, results: dict, errors: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = %s, results_jsonb = %s, errors_jsonb = %s"
            " WHERE id = %s",
            (status, Jsonb(results), Jsonb(errors), job_id),
        )


def get_job(job_id: str, church_id: int) -> Optional[dict]:
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE id = %s AND church_id = %s",
            (job_id, church_id),
        ).fetchone()


def recover_stale_jobs(message: str) -> int:
    """Mark every job left running by a crash/restart as failed."""
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'failed', errors_jsonb = %s"
            " WHERE status = ANY(%s)",
            (Jsonb({"job": message}), list(STALE_STATUSES)),
        )
        return cur.rowcount

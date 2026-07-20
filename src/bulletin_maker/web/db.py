"""PostgreSQL store for churches, users, and church-scoped past runs.

One database at $DATABASE_URL (default postgresql://localhost/bulletin_maker).
Plain psycopg 3, no ORM. Schema lives in migrations/*.sql and is applied
lazily on first connection per database URL.

The church row owns everything congregation-scoped: the profile (JSON,
same fields as CongregationProfile), the encrypted S&S credential, and
the invite code members use to join.

JSON columns are jsonb. psycopg returns them as parsed Python objects, so
profile_json is re-serialized to a JSON string on read to preserve the
contract callers rely on (server.py does json.loads(church["profile_json"])).
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DEFAULT_DATABASE_URL = "postgresql://localhost/bulletin_maker"
MAX_PAST_RUNS = 20
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_lock = threading.Lock()
_migrated_urls: set = set()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _connect_raw() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


def connect() -> psycopg.Connection:
    _ensure_migrated()
    return _connect_raw()


# ── Migrations ───────────────────────────────────────────────────────

def _migration_files() -> list:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(int(f.name.split("_", 1)[0]), f) for f in files]


def run_migrations() -> None:
    with _connect_raw() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version int PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())")
        conn.commit()
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {r["version"] for r in rows}
        for version, path in _migration_files():
            if version in applied:
                continue
            sql = path.read_text()
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,))


def _ensure_migrated() -> None:
    url = database_url()
    if url in _migrated_urls:
        return
    with _lock:
        if url in _migrated_urls:
            return
        run_migrations()
        _migrated_urls.add(url)


def reset_for_tests() -> None:
    """Force the next connection to re-check/apply migrations (test fixture)."""
    _migrated_urls.clear()


# ── Row shaping ──────────────────────────────────────────────────────

def _church_dict(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    row["profile_json"] = json.dumps(row["profile_json"])
    return row


# ── Churches ─────────────────────────────────────────────────────────

def church_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM churches").fetchone()["n"]


def create_church(name: str, profile: dict) -> dict:
    invite_code = secrets.token_urlsafe(9)
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO churches (name, invite_code, profile_json)"
            " VALUES (%s, %s, %s) RETURNING *",
            (name, invite_code, Jsonb(profile)),
        ).fetchone()
        return _church_dict(row)


def get_church(church_id: int, conn: Optional[psycopg.Connection] = None) -> Optional[dict]:
    own = conn is None
    if own:
        conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM churches WHERE id = %s", (church_id,)).fetchone()
        return _church_dict(row)
    finally:
        if own:
            conn.close()


def get_church_by_invite(invite_code: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM churches WHERE invite_code = %s",
            (invite_code,)).fetchone()
        return _church_dict(row)


def update_church_profile(church_id: int, profile: dict) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE churches SET profile_json = %s WHERE id = %s",
            (Jsonb(profile), church_id))


def set_sns_link(church_id: int, username: str, password_enc: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE churches SET sns_username = %s, sns_password_enc = %s"
            " WHERE id = %s",
            (username, password_enc, church_id))


# ── Users ────────────────────────────────────────────────────────────

def create_user(church_id: int, email: str, password_hash: str,
                display_name: str, role: str = "member") -> dict:
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO users (church_id, email, password_hash,"
            " display_name, role) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (church_id, email.strip(), password_hash, display_name, role),
        ).fetchone()
        return row


def get_user_by_email(email: str) -> Optional[dict]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = %s",
            (email.strip(),)).fetchone()


def get_user(user_id: int) -> Optional[dict]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


# ── Past runs (church-scoped) ────────────────────────────────────────

def save_past_run(church_id: int, form_data: dict, metadata: dict) -> str:
    now = datetime.now()
    run_id = now.strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)
    service_date = form_data.get("date", "")
    with connect() as conn:
        conn.execute(
            "DELETE FROM past_runs WHERE church_id = %s AND service_date = %s",
            (church_id, service_date))
        conn.execute(
            "INSERT INTO past_runs (id, church_id, service_date, timestamp,"
            " metadata_json, form_data_json) VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, church_id, service_date, now,
             Jsonb(metadata), Jsonb(form_data)),
        )
        conn.execute(
            "DELETE FROM past_runs WHERE church_id = %s AND id NOT IN ("
            " SELECT id FROM past_runs WHERE church_id = %s"
            " ORDER BY timestamp DESC LIMIT %s)",
            (church_id, church_id, MAX_PAST_RUNS),
        )
    return run_id


def list_past_runs(church_id: int) -> list:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, service_date, metadata_json FROM past_runs"
            " WHERE church_id = %s ORDER BY timestamp DESC",
            (church_id,)).fetchall()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"].isoformat(),
            "date": r["service_date"],
            "metadata": r["metadata_json"],
        }
        for r in rows
    ]


def get_past_run(church_id: int, run_id: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM past_runs WHERE church_id = %s AND id = %s",
            (church_id, run_id)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "timestamp": row["timestamp"].isoformat(),
        "metadata": row["metadata_json"],
        "form_data": row["form_data_json"],
    }


def delete_past_run(church_id: int, run_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM past_runs WHERE church_id = %s AND id = %s",
            (church_id, run_id))
        return cur.rowcount > 0

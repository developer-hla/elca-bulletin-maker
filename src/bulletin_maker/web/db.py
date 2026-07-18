"""SQLite store for churches, users, and church-scoped past runs.

One file at ~/.bulletin-maker/app.db (override with $BULLETIN_DB for
tests and hosted volumes). Plain sqlite3, WAL mode, no ORM.

The church row owns everything congregation-scoped: the profile (JSON,
same fields as CongregationProfile), the encrypted S&S credential, and
the invite code members use to join.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS churches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    profile_json TEXT NOT NULL,
    sns_username TEXT NOT NULL DEFAULT '',
    sns_password_enc TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    church_id INTEGER NOT NULL REFERENCES churches(id),
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS past_runs (
    id TEXT NOT NULL,
    church_id INTEGER NOT NULL REFERENCES churches(id),
    service_date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    form_data_json TEXT NOT NULL,
    PRIMARY KEY (church_id, id)
);
"""

MAX_PAST_RUNS = 20

_lock = threading.Lock()


def db_path() -> Path:
    override = os.environ.get("BULLETIN_DB")
    if override:
        return Path(override)
    return Path.home() / ".bulletin-maker" / "app.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().isoformat()


# ── Churches ─────────────────────────────────────────────────────────

def church_count() -> int:
    with _lock, connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM churches").fetchone()[0]


def create_church(name: str, profile: dict) -> dict:
    invite_code = secrets.token_urlsafe(9)
    with _lock, connect() as conn:
        cur = conn.execute(
            "INSERT INTO churches (name, invite_code, profile_json, created_at)"
            " VALUES (?, ?, ?, ?)",
            (name, invite_code, json.dumps(profile), _now()),
        )
        return get_church(cur.lastrowid, conn)


def get_church(church_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    own = conn is None
    if own:
        conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM churches WHERE id = ?", (church_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def get_church_by_invite(invite_code: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM churches WHERE invite_code = ?",
            (invite_code,)).fetchone()
        return dict(row) if row else None


def update_church_profile(church_id: int, profile: dict) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "UPDATE churches SET profile_json = ? WHERE id = ?",
            (json.dumps(profile), church_id))


def set_sns_link(church_id: int, username: str, password_enc: str) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "UPDATE churches SET sns_username = ?, sns_password_enc = ?"
            " WHERE id = ?",
            (username, password_enc, church_id))


# ── Users ────────────────────────────────────────────────────────────

def create_user(church_id: int, email: str, password_hash: str,
                display_name: str, role: str = "member") -> dict:
    with _lock, connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (church_id, email, password_hash,"
            " display_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (church_id, email.strip(), password_hash, display_name,
             role, _now()),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_user_by_email(email: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.strip(),)).fetchone()
        return dict(row) if row else None


def get_user(user_id: int) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


# ── Past runs (church-scoped) ────────────────────────────────────────

def save_past_run(church_id: int, form_data: dict, metadata: dict) -> str:
    now = datetime.now()
    run_id = now.strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)
    service_date = form_data.get("date", "")
    with _lock, connect() as conn:
        conn.execute(
            "DELETE FROM past_runs WHERE church_id = ? AND service_date = ?",
            (church_id, service_date))
        conn.execute(
            "INSERT INTO past_runs (id, church_id, service_date, timestamp,"
            " metadata_json, form_data_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, church_id, service_date, now.isoformat(),
             json.dumps(metadata), json.dumps(form_data)),
        )
        conn.execute(
            "DELETE FROM past_runs WHERE church_id = ? AND id NOT IN ("
            " SELECT id FROM past_runs WHERE church_id = ?"
            " ORDER BY timestamp DESC LIMIT ?)",
            (church_id, church_id, MAX_PAST_RUNS),
        )
    return run_id


def list_past_runs(church_id: int) -> list:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, service_date, metadata_json FROM past_runs"
            " WHERE church_id = ? ORDER BY timestamp DESC",
            (church_id,)).fetchall()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "date": r["service_date"],
            "metadata": json.loads(r["metadata_json"]),
        }
        for r in rows
    ]


def get_past_run(church_id: int, run_id: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM past_runs WHERE church_id = ? AND id = ?",
            (church_id, run_id)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "metadata": json.loads(row["metadata_json"]),
        "form_data": json.loads(row["form_data_json"]),
    }


def delete_past_run(church_id: int, run_id: str) -> bool:
    with _lock, connect() as conn:
        cur = conn.execute(
            "DELETE FROM past_runs WHERE church_id = ? AND id = ?",
            (church_id, run_id))
        return cur.rowcount > 0

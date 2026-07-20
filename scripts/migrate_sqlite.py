"""One-time importer: copy churches/users/past_runs from the legacy
SQLite app.db into PostgreSQL at $DATABASE_URL.

Usage:
    DATABASE_URL=postgresql://localhost/bulletin_maker \\
        python scripts/migrate_sqlite.py /path/to/app.db

Preserves primary-key ids and fixes the bigserial sequences afterward.
Refuses to run if the target Postgres already has any churches, so it
can't clobber a live database.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from bulletin_maker.web import db


def _load_json(value):
    return json.loads(value) if isinstance(value, str) else value


def _copy_churches(sqlite_conn: sqlite3.Connection, pg: psycopg.Connection) -> int:
    rows = sqlite_conn.execute("SELECT * FROM churches").fetchall()
    for r in rows:
        pg.execute(
            "INSERT INTO churches (id, name, invite_code, profile_json,"
            " sns_username, sns_password_enc, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (r["id"], r["name"], r["invite_code"],
             Jsonb(_load_json(r["profile_json"])),
             r["sns_username"], r["sns_password_enc"], r["created_at"]),
        )
    return len(rows)


def _copy_users(sqlite_conn: sqlite3.Connection, pg: psycopg.Connection) -> int:
    rows = sqlite_conn.execute("SELECT * FROM users").fetchall()
    for r in rows:
        pg.execute(
            "INSERT INTO users (id, church_id, email, password_hash,"
            " display_name, role, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (r["id"], r["church_id"], r["email"], r["password_hash"],
             r["display_name"], r["role"], r["created_at"]),
        )
    return len(rows)


def _copy_past_runs(sqlite_conn: sqlite3.Connection, pg: psycopg.Connection) -> int:
    rows = sqlite_conn.execute("SELECT * FROM past_runs").fetchall()
    for r in rows:
        pg.execute(
            "INSERT INTO past_runs (id, church_id, service_date, timestamp,"
            " metadata_json, form_data_json)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (r["id"], r["church_id"], r["service_date"], r["timestamp"],
             Jsonb(_load_json(r["metadata_json"])),
             Jsonb(_load_json(r["form_data_json"]))),
        )
    return len(rows)


def _fix_sequences(pg: psycopg.Connection) -> None:
    pg.execute(
        "SELECT setval(pg_get_serial_sequence('churches', 'id'),"
        " GREATEST((SELECT COALESCE(MAX(id), 0) FROM churches), 1))")
    pg.execute(
        "SELECT setval(pg_get_serial_sequence('users', 'id'),"
        " GREATEST((SELECT COALESCE(MAX(id), 0) FROM users), 1))")


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    sqlite_path = Path(argv[1])
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    db.run_migrations()

    with db.connect() as pg:
        existing = pg.execute("SELECT COUNT(*) AS n FROM churches").fetchone()["n"]
        if existing:
            raise SystemExit(
                f"Refusing to import: target already has {existing} churches.")

        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            churches = _copy_churches(sqlite_conn, pg)
            users = _copy_users(sqlite_conn, pg)
            past_runs = _copy_past_runs(sqlite_conn, pg)
        finally:
            sqlite_conn.close()

        _fix_sequences(pg)

    print(f"Imported {churches} churches, {users} users, "
          f"{past_runs} past runs into {db.database_url()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

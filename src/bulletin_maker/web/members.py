"""Church-membership queries for the admin Members panel.

Admin-only operations over a single church's roster: listing members,
removing one, regenerating the invite code, emailing the invite, and the
monthly usage counters. All queries are church-scoped so one church's admin
can never read or mutate another church's rows.

Uses db.connect() directly (db.py stays closed to new queries). The monthly
generation count mirrors plans.py — one row per generation in the ``jobs``
table, counted from the start of the current UTC calendar month.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from bulletin_maker.web import db, email

INVITE_CODE_BYTES = 9
DEFAULT_APP_BASE_URL = "http://127.0.0.1:8000"


def _app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", DEFAULT_APP_BASE_URL)


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def list_members(church_id: int) -> list:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, email, display_name, role, email_verified, created_at"
            " FROM users WHERE church_id = %s ORDER BY created_at, id",
            (church_id,)).fetchall()
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "display_name": r["display_name"],
            "role": r["role"],
            "email_verified": r["email_verified"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


def get_member(church_id: int, user_id: int) -> Optional[dict]:
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, role FROM users WHERE id = %s AND church_id = %s",
            (user_id, church_id)).fetchone()


def admin_count(church_id: int) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM users"
            " WHERE church_id = %s AND role = 'admin'",
            (church_id,)).fetchone()["n"]


def delete_member(church_id: int, user_id: int) -> None:
    """Remove a church member. ``jobs.user_id`` has no cascade, so NULL it
    first; sessions and auth_tokens cascade on the user delete."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET user_id = NULL WHERE user_id = %s", (user_id,))
        conn.execute(
            "DELETE FROM users WHERE id = %s AND church_id = %s",
            (user_id, church_id))


def regenerate_invite(church_id: int) -> str:
    invite_code = secrets.token_urlsafe(INVITE_CODE_BYTES)
    with db.connect() as conn:
        conn.execute(
            "UPDATE churches SET invite_code = %s WHERE id = %s",
            (invite_code, church_id))
    return invite_code


def member_count(church_id: int) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE church_id = %s",
            (church_id,)).fetchone()["n"]


def generates_this_month(church_id: int) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE church_id = %s"
            " AND created_at >= %s",
            (church_id, _month_start())).fetchone()["n"]


def send_invite(church: dict, to_email: str) -> None:
    join_url = f"{_app_base_url()}/#join={church['invite_code']}"
    body = (
        f"You've been invited to help make bulletins for {church['name']} "
        "with Bulletin Maker.\n\n"
        "Open this link to create your account:\n"
        f"{join_url}\n\n"
        "Or go to the sign-in screen, choose \"Join with an invite code,\" "
        f"and enter this code:\n{church['invite_code']}\n"
    )
    email.send_email(to_email, "You're invited to Bulletin Maker", body)

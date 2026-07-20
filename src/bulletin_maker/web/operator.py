"""Cross-church operator console: roster, jobs, cache, and the audit log.

The service owner grants a user the ``operator`` flag (migration 006). This
module holds the read queries the console renders and the ``audit`` helper the
web layer calls to record noteworthy actions. Every query here is deliberately
credential-free: the S&S username/password blobs and password hashes are never
selected, so the console can never leak them.

Church-disabled enforcement lives in the web layer (require_user / login);
this module only flips the ``churches.disabled`` flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from psycopg.types.json import Jsonb

from bulletin_maker.web import db

JOBS_LIMIT = 50
AUDIT_LIMIT = 100
ERROR_SNIPPET_MAX = 200

ACTION_CHURCH_REGISTERED = "church_registered"
ACTION_MEMBER_JOINED = "member_joined"
ACTION_SNS_LINKED = "sns_linked"
ACTION_CHURCH_DISABLED = "church_disabled"
ACTION_CHURCH_ENABLED = "church_enabled"
ACTION_PASSWORD_RESET = "password_reset"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def audit(actor_user_id: Optional[int], church_id: Optional[int],
          action: str, detail: Optional[dict] = None) -> None:
    """Append one row to the audit log. Never store S&S credentials here."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (actor_user_id, church_id, action,"
            " detail_jsonb) VALUES (%s, %s, %s, %s)",
            (actor_user_id, church_id, action, Jsonb(detail or {})),
        )


def set_church_disabled(church_id: int, disabled: bool) -> bool:
    """Flip churches.disabled. Returns False when no such church exists."""
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE churches SET disabled = %s WHERE id = %s",
            (disabled, church_id))
        return cur.rowcount > 0


def church_roster() -> list:
    """Per-church summary for the console. Exposes sns_linked as a bool
    only — never the S&S username or any credential."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.name, c.plan, c.disabled,"
            " (c.sns_username <> '') AS sns_linked,"
            " (SELECT COUNT(*) FROM users u WHERE u.church_id = c.id)"
            "   AS member_count,"
            " (SELECT MAX(j.created_at) FROM jobs j WHERE j.church_id = c.id)"
            "   AS last_generate_at,"
            " (SELECT COUNT(*) FROM jobs j WHERE j.church_id = c.id"
            "   AND j.created_at >= %s) AS generates_this_month"
            " FROM churches c ORDER BY c.name",
            (_month_start(),)).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "plan": r["plan"],
            "disabled": r["disabled"],
            "member_count": r["member_count"],
            "sns_linked": bool(r["sns_linked"]),
            "last_generate_at": _iso(r["last_generate_at"]),
            "generates_this_month": r["generates_this_month"],
        }
        for r in rows
    ]


def _error_snippet(errors: Optional[dict]) -> str:
    if not errors:
        return ""
    joined = "; ".join(str(v) for v in errors.values())
    return joined[:ERROR_SNIPPET_MAX]


def latest_jobs(limit: int = JOBS_LIMIT) -> list:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT j.id, c.name AS church_name, j.status, j.created_at,"
            " j.errors_jsonb FROM jobs j"
            " JOIN churches c ON c.id = j.church_id"
            " ORDER BY j.created_at DESC LIMIT %s",
            (limit,)).fetchall()
    return [
        {
            "id": r["id"],
            "church_name": r["church_name"],
            "status": r["status"],
            "created_at": _iso(r["created_at"]),
            "error": _error_snippet(r["errors_jsonb"])
            if r["status"] == "failed" else "",
        }
        for r in rows
    ]


def cache_stats() -> dict:
    with db.connect() as conn:
        totals = conn.execute(
            "SELECT COUNT(*) AS entries, MIN(fetched_at) AS oldest,"
            " MAX(fetched_at) AS newest FROM sns_cache").fetchone()
        by_kind = conn.execute(
            "SELECT split_part(cache_key, ':', 1) AS kind, COUNT(*) AS n"
            " FROM sns_cache GROUP BY kind ORDER BY kind").fetchall()
    return {
        "entries": totals["entries"],
        "oldest_fetched_at": _iso(totals["oldest"]),
        "newest_fetched_at": _iso(totals["newest"]),
        "by_kind": {r["kind"]: r["n"] for r in by_kind},
    }


def latest_audit(limit: int = AUDIT_LIMIT) -> list:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.id, a.actor_user_id, a.church_id, a.action,"
            " a.detail_jsonb, a.at, u.email AS actor_email,"
            " c.name AS church_name FROM audit_log a"
            " LEFT JOIN users u ON u.id = a.actor_user_id"
            " LEFT JOIN churches c ON c.id = a.church_id"
            " ORDER BY a.at DESC, a.id DESC LIMIT %s",
            (limit,)).fetchall()
    return [
        {
            "id": r["id"],
            "actor_email": r["actor_email"],
            "church_name": r["church_name"],
            "action": r["action"],
            "detail": r["detail_jsonb"],
            "at": _iso(r["at"]),
        }
        for r in rows
    ]

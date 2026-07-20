"""Plan limit enforcement for church-scoped actions.

Each church row carries a ``plan`` (default ``'free'``). A plan's limits
live in ``plans.limits_jsonb`` — an object whose keys cap specific actions.
An absent key means that action is unlimited, so the free plan (seeded with
``'{}'``) enforces nothing and every gate is a no-op.

Recognised limit keys:
  * ``max_users`` — most user accounts a church may have.
  * ``generates_per_month`` — most bulletin generations per calendar month.

Generation counting reads the ``jobs`` table rather than ``past_runs``:
``jobs`` is one row per generation with a ``created_at`` timestamp, whereas
``past_runs`` is a capped, per-date deduplicated history (see db.MAX_PAST_RUNS)
that would badly undercount. See docs/plans.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from bulletin_maker.web import db

MAX_USERS = "max_users"
GENERATES_PER_MONTH = "generates_per_month"

ACTION_GENERATE = "generate"
ACTION_JOIN = "join"


class PlanLimitError(Exception):
    """A church has hit a limit its plan imposes on the attempted action."""


def check_limit(church: dict, action: str) -> None:
    """Raise PlanLimitError if ``church`` may not perform ``action``.

    A no-op when the church's plan sets no limit on the action.
    """
    check = _CHECKS.get(action)
    if check is None:
        raise ValueError(f"Unknown plan action: {action!r}")
    with db.connect() as conn:
        limits = _plan_limits(church, conn)
        if not limits:
            return
        check(church, limits, conn)


def _plan_limits(church: dict, conn: psycopg.Connection) -> dict:
    plan = church.get("plan") or "free"
    row = conn.execute(
        "SELECT limits_jsonb FROM plans WHERE plan = %s", (plan,)).fetchone()
    if row is None:
        return {}
    return row["limits_jsonb"] or {}


def _check_max_users(church: dict, limits: dict,
                     conn: psycopg.Connection) -> None:
    max_users = limits.get(MAX_USERS)
    if max_users is None:
        return
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE church_id = %s",
        (church["id"],)).fetchone()["n"]
    if count >= max_users:
        raise PlanLimitError(
            f"This church has reached its member limit ({max_users}). "
            "An admin can upgrade the plan to add more members.")


def _check_generates_per_month(church: dict, limits: dict,
                               conn: psycopg.Connection) -> None:
    limit = limits.get(GENERATES_PER_MONTH)
    if limit is None:
        return
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE church_id = %s"
        " AND created_at >= %s",
        (church["id"], _month_start())).fetchone()["n"]
    if count >= limit:
        raise PlanLimitError(
            f"This church has reached its monthly bulletin limit ({limit}). "
            "The count resets at the start of next month.")


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


_CHECKS = {
    ACTION_JOIN: _check_max_users,
    ACTION_GENERATE: _check_generates_per_month,
}

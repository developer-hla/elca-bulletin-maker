"""Per-church seasonal house-customs overrides (LWS-0d scaffold).

Thin persistence layer over the ``seasonal_rules`` table from migration 009.
The table is empty/unused today — this module only proves the seam a later
workstream (LWS-1+) will wire into ``fill_seasonal_defaults`` resolution.
Until then, every church resolves seasonal customs purely from the bundled
data file (see ``renderer/season.py``), so ``get_church_seasonal_overrides``
always returns ``{}`` for a church with no rows.
"""

from __future__ import annotations

from typing import Dict

from bulletin_maker.web import db


def get_church_seasonal_overrides(church_id: int) -> Dict[str, dict]:
    """Return this church's seasonal-rules overrides, keyed by season.

    Empty dict when the church has no rows (today's only case) — bundled
    defaults apply unchanged.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT season, rules FROM seasonal_rules WHERE church_id = %s",
            (church_id,),
        ).fetchall()
    return {row["season"]: row["rules"] for row in rows}

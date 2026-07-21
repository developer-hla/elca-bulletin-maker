"""Per-church liturgical-text library storage (LWS-1).

Thin persistence layer over the ``church_texts`` table from migration 010.
Follows the established db pattern: psycopg 3, ``dict_row``, per-call
``db.connect()``, jsonb via ``Jsonb``. db.py itself is untouched.

Every query is church-scoped by construction — ``get_text``/``delete_text``
take ``church_id`` and match it in the ``WHERE`` clause, so one church can
never read or remove another's saved text by guessing an id. Admin-gating
for writes lives at the endpoint layer (server.py), not here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from psycopg.types.json import Jsonb

from bulletin_maker.web import db

ALLOWED_KINDS = (
    "confession", "offering_prayer", "prayer_after_communion",
    "blessing", "dismissal", "prayer_of_day",
    # A per-church custom text for one canonical_slot occasion section
    # (funeral / marriage). ``name`` is the section_key, ``body`` a plain
    # string — NOT structured, so it is absent from STRUCTURED_KINDS.
    "occasion_section",
)
STRUCTURED_KINDS = frozenset({"confession", "dismissal"})

OCCASION_SECTION_KIND = "occasion_section"


def _row_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "church_id": row["church_id"],
        "kind": row["kind"],
        "name": row["name"],
        "body": row["body"],
        "created_at": row["created_at"].isoformat(),
    }


def list_texts(church_id: int, kind: Optional[str] = None) -> List[dict]:
    """This church's saved texts, optionally filtered to one ``kind``."""
    query = "SELECT * FROM church_texts WHERE church_id = %s"
    params: tuple = (church_id,)
    if kind is not None:
        query += " AND kind = %s"
        params = (church_id, kind)
    query += " ORDER BY kind, name"
    with db.connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def texts_by_kind(church_id: int) -> Dict[str, List[dict]]:
    """This church's saved texts grouped by kind, for the option catalog."""
    grouped: Dict[str, List[dict]] = {}
    for row in list_texts(church_id):
        grouped.setdefault(row["kind"], []).append(row)
    return grouped


def section_overrides(church_id: int) -> Dict[str, str]:
    """This church's saved canonical_slot overrides as ``{section_key: text}``.

    Each ``occasion_section`` row stores the section_key in ``name`` and the
    plain override text in ``body``; this shape is exactly the ``church_texts``
    dict the content source consults first at resolution.  The dict is keyed
    only by occasion section_keys, so it can never shadow a Sunday / office key.
    """
    rows = list_texts(church_id, OCCASION_SECTION_KIND)
    return {row["name"]: row["body"] for row in rows}


def save_text(church_id: int, kind: str, name: str, body) -> dict:
    """Insert or update a saved text by its (church, kind, name) identity.

    Re-saving the same name replaces the body — that is how a church
    updates a preset rather than accumulating duplicates.
    """
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO church_texts (church_id, kind, name, body)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (church_id, kind, name) DO UPDATE SET"
            "   body = EXCLUDED.body"
            " RETURNING *",
            (church_id, kind, name, Jsonb(body)),
        ).fetchone()
    return _row_to_dict(row)


def get_text(church_id: int, text_id: int) -> Optional[dict]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM church_texts WHERE id = %s AND church_id = %s",
            (text_id, church_id),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def delete_text(church_id: int, text_id: int) -> bool:
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM church_texts WHERE id = %s AND church_id = %s",
            (text_id, church_id))
        return cur.rowcount > 0

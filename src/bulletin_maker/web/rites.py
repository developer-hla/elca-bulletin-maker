"""Storage for rites and rite modules (LWS-0b).

Thin persistence layer over the ``rites`` / ``rite_modules`` tables from
migration 008.  Follows the established db pattern: psycopg 3, ``dict_row``,
per-call ``db.connect()``, jsonb via ``Jsonb``.  db.py itself is untouched;
all rite queries live here.

Save semantics: every ``save_rite`` / ``save_module`` UPSERTs by ``id`` and
bumps ``version`` on update (a fresh insert keeps the object's version).
Loads reconstruct the dataclass via ``from_dict``, so a round-trip preserves
the object's dict exactly (only ``version`` changes, and only on re-save).

``list_rites(church_id)`` returns that church's rites *plus* all library
rites (church_id NULL), library first — the intended visibility rule.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from psycopg.types.json import Jsonb

from bulletin_maker.core.rite import Rite, RiteModule, condition_applies
from bulletin_maker.web import db


# ── Row shaping ───────────────────────────────────────────────────────


def _row_to_rite(row: dict) -> Rite:
    meta = row.get("meta") or {}
    return Rite.from_dict(
        {
            "id": row["id"],
            "church_id": row["church_id"],
            "name": row["name"],
            "tradition": row["tradition"],
            "occasion": row["occasion"],
            "base_rite_id": row["base_rite_id"],
            "version": row["version"],
            "meta": meta,
            "blocks": row["blocks"] or [],
        }
    )


def _row_to_module(row: dict) -> RiteModule:
    meta = row.get("meta") or {}
    return RiteModule.from_dict(
        {
            "id": row["id"],
            "church_id": row["church_id"],
            "name": row["name"],
            "version": row["version"],
            "meta": meta,
            "blocks": row["blocks"] or [],
        }
    )


# ── Rites ─────────────────────────────────────────────────────────────


def save_rite(rite: Rite) -> Rite:
    """Insert or update ``rite`` by id; bump version on update.

    Returns the stored rite (with the persisted version and updated_at
    reflected on a re-loaded object).
    """
    d = rite.to_dict()
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO rites"
            " (id, church_id, name, tradition, occasion, base_rite_id,"
            "  version, blocks, meta)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (id) DO UPDATE SET"
            "   church_id = EXCLUDED.church_id,"
            "   name = EXCLUDED.name,"
            "   tradition = EXCLUDED.tradition,"
            "   occasion = EXCLUDED.occasion,"
            "   base_rite_id = EXCLUDED.base_rite_id,"
            "   blocks = EXCLUDED.blocks,"
            "   meta = EXCLUDED.meta,"
            "   version = rites.version + 1,"
            "   updated_at = now()"
            " RETURNING *",
            (
                d["id"],
                d["church_id"],
                d["name"],
                d["tradition"],
                d["occasion"],
                d["base_rite_id"],
                d["version"],
                Jsonb(d["blocks"]),
                Jsonb(d["meta"]),
            ),
        ).fetchone()
    return _row_to_rite(row)


def get_rite(rite_id: str) -> Optional[Rite]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM rites WHERE id = %s", (rite_id,)
        ).fetchone()
    return _row_to_rite(row) if row is not None else None


def list_rites(church_id: Optional[int] = None) -> List[Rite]:
    """Return ``church_id``'s rites plus all library rites (NULL first).

    With ``church_id`` None, returns library rites only.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rites"
            " WHERE church_id IS NULL OR church_id = %s"
            " ORDER BY church_id NULLS FIRST, occasion, name",
            (church_id,),
        ).fetchall()
    return [_row_to_rite(r) for r in rows]


def delete_rite(rite_id: str) -> bool:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM rites WHERE id = %s", (rite_id,))
        return cur.rowcount > 0


# ── Editor helpers (LWS-2) ────────────────────────────────────────────


def fork_rite(
    source: Rite,
    church_id: int,
    name: Optional[str] = None,
    base_rite_id: Optional[str] = None,
) -> Rite:
    """Return a new, unsaved church-owned copy of ``source``.

    A fresh ``id``, ``church_id`` set to the caller's church, ``version`` 1,
    and a "Copy of …" name.  Blocks and metadata are carried over verbatim via
    a ``from_dict``/``to_dict`` round trip, so the copy is structurally
    identical and independently editable.  ``base_rite_id`` records provenance;
    it must reference a *persisted* rite (the bundled library rites live only in
    JSON, so a library fork passes ``None``) to satisfy the table's foreign key.
    """
    payload = source.to_dict()
    payload["id"] = "rite_" + uuid.uuid4().hex
    payload["church_id"] = church_id
    payload["version"] = 1
    payload["base_rite_id"] = base_rite_id
    payload["name"] = name or ("Copy of " + source.name)
    return Rite.from_dict(payload)


def prepare_import(payload: Dict[str, Any], church_id: int) -> Rite:
    """Return a new, unsaved church-owned Rite parsed from an imported file.

    Mirrors :func:`fork_rite`'s ownership reset: a fresh ``id``, ``church_id``
    set to the caller's church, and ``version`` 1, so an import can never
    overwrite an existing row or claim another church's id. ``base_rite_id``
    is dropped (the source id may belong to another church, or to no
    persisted row at all — a bundled library file has no row to link to), so
    it is always ``None`` on import, same as a library fork. Raises
    :class:`bulletin_maker.core.rite.RiteSchemaError` if ``payload`` is
    structurally invalid; the caller runs ``validate_rite`` afterward.
    """
    payload = dict(payload)
    payload["id"] = "rite_" + uuid.uuid4().hex
    payload["church_id"] = church_id
    payload["version"] = 1
    payload["base_rite_id"] = None
    return Rite.from_dict(payload)


def import_name_collides(name: str, occasion: str, church_id: int) -> bool:
    """Whether ``church_id`` already owns a rite with this ``name``/``occasion``.

    Mirrors the DB's uniqueness rule (``COALESCE(church_id, 0), occasion,
    name``) so an import can rename before it collides at insert time.
    """
    return any(
        r.name == name and r.occasion == occasion
        for r in list_rites(church_id)
        if r.church_id == church_id
    )


def visible_block_ids(rite: Rite, context: Dict[str, Any]) -> List[str]:
    """Block ids kept for a given ``{season, feasts, toggles}`` context.

    Mirrors the renderer's filter (``rite_resolver``): a block is visible when
    it is enabled and its condition applies.  Used by the editor preview.
    """
    return [
        block.id
        for block in rite.blocks
        if block.enabled and condition_applies(block.condition, context)
    ]


def rite_run_count(rite_id: str) -> int:
    """How many stored past runs reference ``rite_id`` (delete guard)."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM past_runs"
            " WHERE form_data_json ->> 'rite_id' = %s",
            (rite_id,),
        ).fetchone()
    return row["n"]


# ── Modules ───────────────────────────────────────────────────────────


def save_module(module: RiteModule) -> RiteModule:
    """Insert or update ``module`` by id; bump version on update."""
    d = module.to_dict()
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO rite_modules (id, church_id, name, version, blocks, meta)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (id) DO UPDATE SET"
            "   church_id = EXCLUDED.church_id,"
            "   name = EXCLUDED.name,"
            "   blocks = EXCLUDED.blocks,"
            "   meta = EXCLUDED.meta,"
            "   version = rite_modules.version + 1,"
            "   updated_at = now()"
            " RETURNING *",
            (
                d["id"],
                d["church_id"],
                d["name"],
                d["version"],
                Jsonb(d["blocks"]),
                Jsonb(d["meta"]),
            ),
        ).fetchone()
    return _row_to_module(row)


def get_module(module_id: str) -> Optional[RiteModule]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM rite_modules WHERE id = %s", (module_id,)
        ).fetchone()
    return _row_to_module(row) if row is not None else None


def list_modules(church_id: Optional[int] = None) -> List[RiteModule]:
    """Return ``church_id``'s modules plus all library modules (NULL first)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rite_modules"
            " WHERE church_id IS NULL OR church_id = %s"
            " ORDER BY church_id NULLS FIRST, name",
            (church_id,),
        ).fetchall()
    return [_row_to_module(r) for r in rows]

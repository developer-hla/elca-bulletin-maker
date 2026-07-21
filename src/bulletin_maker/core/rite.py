"""Rite schema — typed, serializable liturgy data (LWS-0b).

A ``Rite`` is the structured form of a service order: an ordered list of
typed ``Block`` s that a renderer (LWS-0c/0d, not this workstream) will
iterate instead of the ~500 lines of hardcoded Jinja that live in
``renderer/templates/html/bulletin.html`` today.

This module is deliberately renderer-free.  It owns:

* the dataclasses (``Rite``, ``RiteModule``, ``Block``, ``Condition``,
  ``RoleLabels``),
* strict ``to_dict`` / ``from_dict`` with fail-fast validation (an unknown
  block ``type`` or an unknown payload field raises and names the offender),
* ``validate_rite`` for referential sanity (``module_ref`` resolvable,
  ``text_ref`` present in the catalog, conditions well-formed), and
* ``condition_applies`` — a pure evaluator for block ``Condition`` s.

Block ``condition`` semantics (see ``Condition``):
    {seasons?: [...], feasts?: [...], toggles?: {name: bool}, invert?: bool}
Empty condition = always applies.  Multiple fields AND together.  ``invert``
flips the final result.

Python 3.9 compatible: ``from __future__ import annotations`` throughout,
``Optional[...]`` (never ``X | None``), no match statements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

# ── Errors ────────────────────────────────────────────────────────────


class RiteError(ValueError):
    """Base class for rite schema/validation errors."""


class RiteSchemaError(RiteError):
    """Structural error while parsing a rite/block dict (fail fast).

    Always names the offending field(s)/type so the caller can fix the data.
    """


class RiteValidationError(RiteError):
    """Referential error(s) found by :func:`validate_rite`.

    Carries the full list of problems on ``.errors``.
    """

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# ── Vocabulary ────────────────────────────────────────────────────────

# Semantic dialogue roles (mapped to church role_labels at render time).
DIALOG_ROLES: FrozenSet[str] = frozenset(
    {"leader", "congregation", "instruction", "none"}
)

# CongregationProfile-driven content markers (rendered from the profile,
# never from the text catalog).  "cover" is the composite cover page.
KNOWN_PROFILE_REFS: FrozenSet[str] = frozenset(
    {"cover", "welcome_message", "standing_instructions", "copyright_paragraphs"}
)

LITERAL_STYLES: FrozenSet[str] = frozenset({"unison", "prayer", "plain"})

HYMN_SLOTS: FrozenSet[str] = frozenset(
    {"gathering", "sermon", "communion", "sending", "custom"}
)
HYMN_RENDERS: FrozenSet[str] = frozenset({"ref", "lyrics", "notation"})

READING_SLOTS: FrozenSet[str] = frozenset(
    {"first", "psalm", "second", "gospel", "custom"}
)
READING_RENDERS: FrozenSet[str] = frozenset({"full", "ref"})

PSALM_SOURCES: FrozenSet[str] = frozenset({"slot", "literal"})
PSALM_STYLES: FrozenSet[str] = frozenset({"responsive", "unison"})

PROPER_KINDS: FrozenSet[str] = frozenset(
    {
        "prayer_of_day",
        "confession",
        "offering_prayer",
        "preface",
        "post_communion",
        "blessing",
        "dismissal",
        "prayers_of_intercession",
    }
)

NOTATION_PIECES: FrozenSet[str] = frozenset(
    {
        "kyrie",
        "glory_to_god",
        "this_is_the_feast",
        "gospel_acclamation",
        "great_thanksgiving",
        "preface",
        "sanctus",
        "memorial_acclamation",
        "amen",
        "offertory_hymn",
        "agnus_dei",
        "nunc_dimittis",
    }
)

MUSIC_KINDS: FrozenSet[str] = frozenset(
    {"prelude", "offertory", "postlude", "choral"}
)

# A ``canonical_slot`` names its content by a stable ``section_key`` — an
# arbitrary identifier (not a closed enum), so a rite can key any canonical
# section the church's licensed source fills at render time.  The format is the
# same identifier shape used for variable keys: a letter/underscore followed by
# word characters.
SECTION_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ── Per-service variables (RB-3b) ─────────────────────────────────────
#
# A rite may declare ``meta.variables`` — fields a volunteer fills per service
# (a deceased's name, a couple's names, a date).  Block text references them
# with a DOUBLE-brace placeholder ``{{key}}``; the value is substituted at
# render time.  Double braces deliberately do NOT collide with baptism's
# single-brace ``{name}`` per-candidate substitution (a different mechanism)
# nor with any hymn/creed formatting.
#
# A key is an identifier: a letter/underscore followed by word characters.
# Optional whitespace inside the braces is tolerated (``{{ key }}``).
VARIABLE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

VARIABLE_TYPES: FrozenSet[str] = frozenset({"text", "date", "names"})


def iter_variable_placeholders(text: str) -> List[str]:
    """Return the variable keys referenced by ``{{key}}`` placeholders in ``text``."""
    if not text:
        return []
    return VARIABLE_PLACEHOLDER_RE.findall(text)


def substitute_variables(text: str, variables: Dict[str, str]) -> str:
    """Replace every ``{{key}}`` in ``text`` with its per-service value.

    An unfilled placeholder — a key with no value, or an empty value — renders
    the bracketed hint ``[key]`` instead of vanishing, so a volunteer sees at
    a glance what is still missing rather than getting silently-wrong output.
    Text with no placeholders is returned unchanged (parity no-op).
    """
    if not text:
        return text

    def _replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        value = variables.get(key)
        if value:
            return str(value)
        return "[%s]" % key

    return VARIABLE_PLACEHOLDER_RE.sub(_replace, text)


# ── Block type registry ───────────────────────────────────────────────


@dataclass(frozen=True)
class BlockTypeSpec:
    """Declares the payload contract for one block ``type``.

    ``fields`` is the ordered tuple of *all* allowed payload field names
    (everything outside the common {id,type,title,condition,toggle,note}).
    ``required`` must all be present.  ``one_of`` lists groups where exactly
    one member must be present.  ``enums`` constrains field values.
    ``reserved`` types parse but are flagged unusable by ``validate_rite``.
    """

    type: str
    fields: Tuple[str, ...] = ()
    required: FrozenSet[str] = frozenset()
    one_of: Tuple[Tuple[str, ...], ...] = ()
    enums: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    reserved: bool = False


_SPECS: Dict[str, BlockTypeSpec] = {
    s.type: s
    for s in [
        BlockTypeSpec("heading", ("text",), frozenset({"text"})),
        BlockTypeSpec("rubric", ("text",), frozenset({"text"})),
        BlockTypeSpec(
            "dialogue",
            ("lines", "text_ref"),
            one_of=(("lines", "text_ref"),),
        ),
        BlockTypeSpec(
            "literal_text",
            ("text", "text_ref", "profile_ref", "style"),
            one_of=(("text", "text_ref", "profile_ref"),),
            enums={"style": LITERAL_STYLES},
        ),
        BlockTypeSpec(
            "hymn_slot",
            ("slot", "render"),
            frozenset({"slot", "render"}),
            enums={"slot": HYMN_SLOTS, "render": HYMN_RENDERS},
        ),
        BlockTypeSpec(
            "reading_slot",
            ("slot", "render"),
            frozenset({"slot", "render"}),
            enums={"slot": READING_SLOTS, "render": READING_RENDERS},
        ),
        BlockTypeSpec(
            "psalm",
            ("source", "style"),
            frozenset({"source", "style"}),
            enums={"source": PSALM_SOURCES, "style": PSALM_STYLES},
        ),
        BlockTypeSpec(
            "proper_slot",
            ("kind", "fallback"),
            frozenset({"kind"}),
            enums={"kind": PROPER_KINDS},
        ),
        BlockTypeSpec(
            "canonical_slot",
            ("section_key", "fallback"),
            frozenset({"section_key"}),
        ),
        BlockTypeSpec(
            "notation",
            ("piece", "text_fallback"),
            frozenset({"piece"}),
            enums={"piece": NOTATION_PIECES},
        ),
        BlockTypeSpec(
            "music_item",
            ("kind",),
            frozenset({"kind"}),
            enums={"kind": MUSIC_KINDS},
        ),
        BlockTypeSpec("module_ref", ("module_id",), frozenset({"module_id"})),
        # ── Reserved (announcements family): defined now, UI in LWS-7 ──
        BlockTypeSpec("prayer_list", reserved=True),
        BlockTypeSpec("week_calendar", reserved=True),
        BlockTypeSpec("serving_list", reserved=True),
        BlockTypeSpec("staff_directory", reserved=True),
        BlockTypeSpec("announcement_text", reserved=True),
    ]
}

BLOCK_TYPES: FrozenSet[str] = frozenset(_SPECS)
RESERVED_BLOCK_TYPES: FrozenSet[str] = frozenset(
    t for t, s in _SPECS.items() if s.reserved
)

_COMMON_BLOCK_KEYS: FrozenSet[str] = frozenset(
    {"id", "type", "title", "condition", "toggle", "note", "enabled"}
)


# ── Condition ─────────────────────────────────────────────────────────


@dataclass
class Condition:
    """When a block applies.

    All present fields AND together; an all-empty condition always applies.
    ``invert`` flips the final result.
    """

    seasons: Optional[List[str]] = None
    feasts: Optional[List[str]] = None
    toggles: Optional[Dict[str, bool]] = None
    invert: bool = False

    def is_empty(self) -> bool:
        return (
            self.seasons is None
            and self.feasts is None
            and self.toggles is None
            and not self.invert
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.seasons is not None:
            out["seasons"] = list(self.seasons)
        if self.feasts is not None:
            out["feasts"] = list(self.feasts)
        if self.toggles is not None:
            out["toggles"] = dict(self.toggles)
        if self.invert:
            out["invert"] = True
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        if not isinstance(data, dict):
            raise RiteSchemaError(
                "condition must be an object, got %r" % type(data).__name__
            )
        unknown = set(data) - {"seasons", "feasts", "toggles", "invert"}
        if unknown:
            raise RiteSchemaError(
                "condition has unknown field(s): %s" % ", ".join(sorted(unknown))
            )
        seasons = data.get("seasons")
        if seasons is not None:
            if not isinstance(seasons, list) or not all(
                isinstance(s, str) for s in seasons
            ):
                raise RiteSchemaError("condition.seasons must be a list of strings")
        feasts = data.get("feasts")
        if feasts is not None:
            if not isinstance(feasts, list) or not all(
                isinstance(s, str) for s in feasts
            ):
                raise RiteSchemaError("condition.feasts must be a list of strings")
        toggles = data.get("toggles")
        if toggles is not None:
            if not isinstance(toggles, dict) or not all(
                isinstance(k, str) and isinstance(v, bool)
                for k, v in toggles.items()
            ):
                raise RiteSchemaError(
                    "condition.toggles must be an object of {name: bool}"
                )
        invert = data.get("invert", False)
        if not isinstance(invert, bool):
            raise RiteSchemaError("condition.invert must be a boolean")
        return cls(
            seasons=list(seasons) if seasons is not None else None,
            feasts=list(feasts) if feasts is not None else None,
            toggles=dict(toggles) if toggles is not None else None,
            invert=invert,
        )


def condition_applies(
    condition: Optional[Condition], context: Dict[str, Any]
) -> bool:
    """Evaluate ``condition`` against a render ``context``.

    ``context`` carries ``season`` (str), ``feasts`` (list of str), and
    ``toggles`` (dict name->bool); all optional.  ``None`` condition or an
    all-empty condition always applies.  Present fields AND together;
    ``invert`` flips the final result.
    """
    if condition is None:
        return True
    ctx_season = context.get("season")
    ctx_feasts = set(context.get("feasts") or [])
    ctx_toggles = context.get("toggles") or {}

    result = True
    if condition.seasons is not None:
        result = result and (ctx_season in condition.seasons)
    if condition.feasts is not None:
        result = result and bool(ctx_feasts.intersection(condition.feasts))
    if condition.toggles is not None:
        for name, want in condition.toggles.items():
            if bool(ctx_toggles.get(name, False)) != bool(want):
                result = False
                break

    return (not result) if condition.invert else result


# ── RoleLabels ────────────────────────────────────────────────────────


@dataclass
class RoleLabels:
    """Church-specific labels for the two speaking roles."""

    leader: str = "P"
    congregation: str = "C"

    def to_dict(self) -> Dict[str, str]:
        return {"leader": self.leader, "congregation": self.congregation}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleLabels":
        if not isinstance(data, dict):
            raise RiteSchemaError("role_labels must be an object")
        unknown = set(data) - {"leader", "congregation"}
        if unknown:
            raise RiteSchemaError(
                "role_labels has unknown field(s): %s"
                % ", ".join(sorted(unknown))
            )
        return cls(
            leader=data.get("leader", "P"),
            congregation=data.get("congregation", "C"),
        )


# ── RiteVariable ──────────────────────────────────────────────────────


@dataclass
class RiteVariable:
    """A field a volunteer fills per service, substituted into block text.

    ``key`` is the placeholder id used as ``{{key}}`` in block text; ``label``
    is the human prompt shown in the wizard; ``type`` picks the wizard input
    control (``text`` / ``date`` / ``names``); ``required`` flags whether the
    volunteer must fill it.
    """

    key: str
    label: str
    type: str = "text"
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiteVariable":
        if not isinstance(data, dict):
            raise RiteSchemaError("rite variable must be an object")
        allowed = {"key", "label", "type", "required"}
        unknown = set(data) - allowed
        if unknown:
            raise RiteSchemaError(
                "rite variable has unknown field(s): %s"
                % ", ".join(sorted(unknown))
            )
        key = data.get("key")
        if not isinstance(key, str) or not VARIABLE_PLACEHOLDER_RE.fullmatch(
            "{{%s}}" % key
        ):
            raise RiteSchemaError(
                "rite variable 'key' must be an identifier, got %r" % (key,)
            )
        label = data.get("label")
        if not isinstance(label, str) or not label:
            raise RiteSchemaError(
                "rite variable %r missing non-empty string 'label'" % key
            )
        var_type = data.get("type", "text")
        if var_type not in VARIABLE_TYPES:
            raise RiteSchemaError(
                "rite variable %r has invalid type %r (allowed: %s)"
                % (key, var_type, ", ".join(sorted(VARIABLE_TYPES)))
            )
        required = data.get("required", True)
        if not isinstance(required, bool):
            raise RiteSchemaError(
                "rite variable %r 'required' must be a boolean" % key
            )
        return cls(key=key, label=label, type=var_type, required=required)


def _variables_from_meta(meta: Dict[str, Any]) -> List[RiteVariable]:
    raw = meta.get("variables")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RiteSchemaError("rite meta 'variables' must be a list")
    variables = [RiteVariable.from_dict(v) for v in raw]
    keys = [v.key for v in variables]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise RiteSchemaError(
            "rite meta 'variables' has duplicate key(s): %s" % ", ".join(dupes)
        )
    return variables


# ── Block ─────────────────────────────────────────────────────────────


def _validate_dialog_lines(lines: Any) -> None:
    if not isinstance(lines, list) or not lines:
        raise RiteSchemaError("dialogue.lines must be a non-empty list")
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            raise RiteSchemaError("dialogue.lines[%d] must be an object" % i)
        unknown = set(line) - {"role", "text"}
        if unknown:
            raise RiteSchemaError(
                "dialogue.lines[%d] has unknown field(s): %s"
                % (i, ", ".join(sorted(unknown)))
            )
        role = line.get("role", "none")
        if role not in DIALOG_ROLES:
            raise RiteSchemaError(
                "dialogue.lines[%d].role %r not in %s"
                % (i, role, sorted(DIALOG_ROLES))
            )
        if "text" not in line or not isinstance(line["text"], str):
            raise RiteSchemaError("dialogue.lines[%d].text must be a string" % i)


def _validate_section_key(section_key: Any) -> None:
    if not isinstance(section_key, str) or not SECTION_KEY_RE.fullmatch(section_key):
        raise RiteSchemaError(
            "canonical_slot 'section_key' must be an identifier "
            "(letter/underscore + word chars), got %r" % (section_key,)
        )


def _validate_block_payload(block_type: str, payload: Dict[str, Any]) -> None:
    """Fail fast if ``payload`` violates the type's :class:`BlockTypeSpec`."""
    spec = _SPECS[block_type]

    allowed = set(spec.fields)
    unknown = set(payload) - allowed
    if unknown:
        raise RiteSchemaError(
            "block type %r has unknown field(s): %s (allowed: %s)"
            % (block_type, ", ".join(sorted(unknown)), ", ".join(sorted(allowed)))
        )

    missing = spec.required - set(payload)
    if missing:
        raise RiteSchemaError(
            "block type %r missing required field(s): %s"
            % (block_type, ", ".join(sorted(missing)))
        )

    for group in spec.one_of:
        present = [f for f in group if f in payload]
        if len(present) != 1:
            raise RiteSchemaError(
                "block type %r requires exactly one of {%s}; found %s"
                % (block_type, ", ".join(group), present or "none")
            )

    for fname, allowed_values in spec.enums.items():
        if fname in payload and payload[fname] not in allowed_values:
            raise RiteSchemaError(
                "block type %r field %r has invalid value %r (allowed: %s)"
                % (
                    block_type,
                    fname,
                    payload[fname],
                    ", ".join(sorted(allowed_values)),
                )
            )

    if block_type == "dialogue" and "lines" in payload:
        _validate_dialog_lines(payload["lines"])

    if block_type == "canonical_slot":
        _validate_section_key(payload["section_key"])


@dataclass
class Block:
    """One typed element of a rite (see module docstring for the type list).

    Common fields mirror §2.1: ``id``, ``type``, ``title?``, ``condition?``,
    ``toggle?`` (plus a ``note`` for human annotations, since JSON has no
    comments).  Type-specific payload lives in ``data``.
    """

    id: str
    type: str
    title: Optional[str] = None
    condition: Optional[Condition] = None
    toggle: Optional[str] = None
    note: Optional[str] = None
    enabled: bool = True
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in _SPECS:
            raise RiteSchemaError(
                "unknown block type %r (known: %s)"
                % (self.type, ", ".join(sorted(BLOCK_TYPES)))
            )
        _validate_block_payload(self.type, self.data)

    @property
    def reserved(self) -> bool:
        return _SPECS[self.type].reserved

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id, "type": self.type}
        if self.title is not None:
            out["title"] = self.title
        if self.toggle is not None:
            out["toggle"] = self.toggle
        # Emitted only when disabled so an enabled block (the default, and
        # every library block) serializes byte-identically to before.
        if not self.enabled:
            out["enabled"] = False
        if self.condition is not None and not self.condition.is_empty():
            out["condition"] = self.condition.to_dict()
        if self.note is not None:
            out["note"] = self.note
        # Payload in declared spec order for stable, reviewable output.
        for fname in _SPECS[self.type].fields:
            if fname in self.data:
                out[fname] = self.data[fname]
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        if not isinstance(data, dict):
            raise RiteSchemaError("block must be an object")
        if "id" not in data or not isinstance(data["id"], str):
            raise RiteSchemaError("block missing string 'id'")
        if "type" not in data or not isinstance(data["type"], str):
            raise RiteSchemaError(
                "block %r missing string 'type'" % data.get("id")
            )
        block_type = data["type"]
        if block_type not in _SPECS:
            raise RiteSchemaError(
                "block %r has unknown type %r (known: %s)"
                % (data["id"], block_type, ", ".join(sorted(BLOCK_TYPES)))
            )
        payload = {k: v for k, v in data.items() if k not in _COMMON_BLOCK_KEYS}
        condition = None
        if "condition" in data:
            condition = Condition.from_dict(data["condition"])
        title = data.get("title")
        if title is not None and not isinstance(title, str):
            raise RiteSchemaError("block %r 'title' must be a string" % data["id"])
        toggle = data.get("toggle")
        if toggle is not None and not isinstance(toggle, str):
            raise RiteSchemaError("block %r 'toggle' must be a string" % data["id"])
        note = data.get("note")
        if note is not None and not isinstance(note, str):
            raise RiteSchemaError("block %r 'note' must be a string" % data["id"])
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise RiteSchemaError(
                "block %r 'enabled' must be a boolean" % data["id"]
            )
        return cls(
            id=data["id"],
            type=block_type,
            title=title,
            condition=condition,
            toggle=toggle,
            note=note,
            enabled=enabled,
            data=payload,
        )


# ── Rite & RiteModule ─────────────────────────────────────────────────


def _blocks_to_dicts(blocks: List[Block]) -> List[Dict[str, Any]]:
    return [b.to_dict() for b in blocks]


def _blocks_from_dicts(raw: Any) -> List[Block]:
    if not isinstance(raw, list):
        raise RiteSchemaError("'blocks' must be a list")
    return [Block.from_dict(b) for b in raw]


@dataclass
class RiteModule:
    """A reusable, occasion-scoped fragment (e.g. Holy Baptism).

    Referenced from a rite by a ``module_ref`` block.  Stored in the
    ``rite_modules`` table; ``church_id`` NULL = library module.
    """

    id: str
    name: str
    blocks: List[Block] = field(default_factory=list)
    church_id: Optional[int] = None
    version: int = 1
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "church_id": self.church_id,
            "name": self.name,
            "version": self.version,
            "meta": {"notes": self.notes},
            "blocks": _blocks_to_dicts(self.blocks),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiteModule":
        if not isinstance(data, dict):
            raise RiteSchemaError("module must be an object")
        allowed = {"id", "church_id", "name", "version", "meta", "blocks"}
        unknown = set(data) - allowed
        if unknown:
            raise RiteSchemaError(
                "module has unknown top-level field(s): %s"
                % ", ".join(sorted(unknown))
            )
        if "id" not in data or not isinstance(data["id"], str):
            raise RiteSchemaError("module missing string 'id'")
        if "name" not in data or not isinstance(data["name"], str):
            raise RiteSchemaError("module %r missing string 'name'" % data["id"])
        meta = data.get("meta") or {}
        if not isinstance(meta, dict):
            raise RiteSchemaError("module 'meta' must be an object")
        meta_unknown = set(meta) - {"notes"}
        if meta_unknown:
            raise RiteSchemaError(
                "module meta has unknown field(s): %s"
                % ", ".join(sorted(meta_unknown))
            )
        return cls(
            id=data["id"],
            name=data["name"],
            blocks=_blocks_from_dicts(data.get("blocks", [])),
            church_id=data.get("church_id"),
            version=data.get("version", 1),
            notes=meta.get("notes", ""),
        )


@dataclass
class Rite:
    """A full service order as structured data (see module docstring)."""

    id: str
    name: str
    blocks: List[Block] = field(default_factory=list)
    tradition: str = ""
    occasion: str = ""
    church_id: Optional[int] = None  # NULL = library rite
    base_rite_id: Optional[str] = None
    version: int = 1
    role_labels: RoleLabels = field(default_factory=RoleLabels)
    notes: str = ""
    variables: List[RiteVariable] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "role_labels": self.role_labels.to_dict(),
            "notes": self.notes,
        }
        # Emitted only when non-empty so a rite that declares no variables
        # (every existing/default rite) serializes byte-identically to before.
        if self.variables:
            meta["variables"] = [v.to_dict() for v in self.variables]
        return {
            "id": self.id,
            "church_id": self.church_id,
            "name": self.name,
            "tradition": self.tradition,
            "occasion": self.occasion,
            "base_rite_id": self.base_rite_id,
            "version": self.version,
            "meta": meta,
            "blocks": _blocks_to_dicts(self.blocks),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rite":
        if not isinstance(data, dict):
            raise RiteSchemaError("rite must be an object")
        allowed = {
            "id",
            "church_id",
            "name",
            "tradition",
            "occasion",
            "base_rite_id",
            "version",
            "meta",
            "blocks",
        }
        unknown = set(data) - allowed
        if unknown:
            raise RiteSchemaError(
                "rite has unknown top-level field(s): %s"
                % ", ".join(sorted(unknown))
            )
        if "id" not in data or not isinstance(data["id"], str):
            raise RiteSchemaError("rite missing string 'id'")
        if "name" not in data or not isinstance(data["name"], str):
            raise RiteSchemaError("rite %r missing string 'name'" % data["id"])
        meta = data.get("meta") or {}
        if not isinstance(meta, dict):
            raise RiteSchemaError("rite 'meta' must be an object")
        meta_unknown = set(meta) - {"role_labels", "notes", "variables"}
        if meta_unknown:
            raise RiteSchemaError(
                "rite meta has unknown field(s): %s"
                % ", ".join(sorted(meta_unknown))
            )
        role_labels = (
            RoleLabels.from_dict(meta["role_labels"])
            if "role_labels" in meta
            else RoleLabels()
        )
        return cls(
            id=data["id"],
            name=data["name"],
            blocks=_blocks_from_dicts(data.get("blocks", [])),
            tradition=data.get("tradition", ""),
            occasion=data.get("occasion", ""),
            church_id=data.get("church_id"),
            base_rite_id=data.get("base_rite_id"),
            version=data.get("version", 1),
            role_labels=role_labels,
            notes=meta.get("notes", ""),
            variables=_variables_from_meta(meta),
        )


# ── Referential validation ────────────────────────────────────────────


def _text_refs_in_block(block: Block) -> List[str]:
    """Return the text-catalog keys a block references, if any."""
    refs: List[str] = []
    d = block.data
    if block.type == "literal_text" and "text_ref" in d:
        refs.append(d["text_ref"])
    elif block.type == "dialogue" and "text_ref" in d:
        refs.append(d["text_ref"])
    elif block.type == "proper_slot" and "fallback" in d:
        refs.append(d["fallback"])
    elif block.type == "canonical_slot" and "fallback" in d:
        refs.append(d["fallback"])
    elif block.type == "notation" and "text_fallback" in d:
        refs.append(d["text_fallback"])
    return refs


def _placeholder_keys_in_block(block: Block) -> List[str]:
    """Return the variable keys a block's inline text references via ``{{key}}``.

    Only inline text is scanned — ``heading.text``, ``rubric.text``,
    ``literal_text.text``, and each ``dialogue.lines[].text`` — the exact fields
    where per-service substitution is applied.  Catalog-resolved text
    (``text_ref`` / ``fallback``) is static and never carries placeholders.
    """
    d = block.data
    keys: List[str] = []
    if block.type in ("heading", "rubric") and "text" in d:
        keys.extend(iter_variable_placeholders(d["text"]))
    elif block.type == "literal_text" and "text" in d:
        keys.extend(iter_variable_placeholders(d["text"]))
    elif block.type == "dialogue" and "lines" in d:
        for line in d["lines"]:
            keys.extend(iter_variable_placeholders(line.get("text", "")))
    return keys


def _collect_block_errors(
    block: Block,
    where: str,
    catalog: FrozenSet[str],
    module_ids: FrozenSet[str],
    variable_keys: FrozenSet[str],
    errors: List[str],
) -> None:
    for key in _placeholder_keys_in_block(block):
        if key not in variable_keys:
            errors.append(
                "%s: block %r uses undeclared variable placeholder {{%s}} "
                "(declared: %s)"
                % (where, block.id, key, ", ".join(sorted(variable_keys)) or "none")
            )
    if block.reserved:
        errors.append(
            "%s: block %r uses reserved type %r (not usable until its UI ships)"
            % (where, block.id, block.type)
        )
    for ref in _text_refs_in_block(block):
        if ref not in catalog:
            errors.append(
                "%s: block %r references unknown text key %r"
                % (where, block.id, ref)
            )
    if block.type == "literal_text" and "profile_ref" in block.data:
        pref = block.data["profile_ref"]
        if pref not in KNOWN_PROFILE_REFS:
            errors.append(
                "%s: block %r references unknown profile field %r (known: %s)"
                % (where, block.id, pref, ", ".join(sorted(KNOWN_PROFILE_REFS)))
            )
    if block.type == "module_ref":
        mid = block.data.get("module_id")
        if mid not in module_ids:
            errors.append(
                "%s: block %r references unknown module %r"
                % (where, block.id, mid)
            )


def collect_rite_errors(
    rite: Rite,
    *,
    catalog: Optional[FrozenSet[str]] = None,
    modules: Optional[Dict[str, RiteModule]] = None,
) -> List[str]:
    """Return a list of referential problems (empty list = valid).

    Checks: reserved block types are flagged; every ``text_ref`` resolves in
    ``catalog``; every ``profile_ref`` is a known profile field; every
    ``module_ref`` resolves in ``modules``; referenced modules' own blocks
    are validated too.  ``catalog`` defaults to the text-catalog keys.
    """
    if catalog is None:
        from bulletin_maker.core.text_catalog import text_keys

        catalog = text_keys()
    modules = modules or {}
    module_ids = frozenset(modules)
    variable_keys = frozenset(v.key for v in rite.variables)

    errors: List[str] = []
    seen_ids: Dict[str, int] = {}
    for block in rite.blocks:
        seen_ids[block.id] = seen_ids.get(block.id, 0) + 1
        _collect_block_errors(
            block, "rite %r" % rite.id, catalog, module_ids,
            variable_keys, errors,
        )
    dupes = sorted(bid for bid, n in seen_ids.items() if n > 1)
    if dupes:
        errors.append(
            "rite %r has duplicate block id(s): %s"
            % (rite.id, ", ".join(dupes))
        )

    # Validate the blocks of every module referenced by this rite.
    referenced = {
        b.data.get("module_id")
        for b in rite.blocks
        if b.type == "module_ref"
    }
    for mid in sorted(m for m in referenced if m in modules):
        module = modules[mid]
        for block in module.blocks:
            # Modules may themselves ref modules; pass the same id set.  A
            # module's placeholders are validated against the embedding rite's
            # declared variables (the rite owns the variable declarations).
            _collect_block_errors(
                block, "module %r" % mid, catalog, module_ids,
                variable_keys, errors,
            )
    return errors


def validate_rite(
    rite: Rite,
    *,
    catalog: Optional[FrozenSet[str]] = None,
    modules: Optional[Dict[str, RiteModule]] = None,
) -> None:
    """Raise :class:`RiteValidationError` if ``rite`` has referential errors.

    See :func:`collect_rite_errors` for the checks performed.
    """
    errors = collect_rite_errors(rite, catalog=catalog, modules=modules)
    if errors:
        raise RiteValidationError(errors)

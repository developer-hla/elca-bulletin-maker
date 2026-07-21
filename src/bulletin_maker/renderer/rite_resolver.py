"""Resolve a document's ordered, condition-filtered rite blocks (LWS-0c/0d).

Each document (bulletin, large print, leader guide) is rendered by iterating the
library rite (``elw_sunday_communion``) block by block, in order, keeping only
the blocks whose ``condition`` applies to the current service.  Order and
conditions come from the rite — one shared source; the per-block markup and the
``.flow-group`` pagination grouping stay with each document's template
(``templates/html/bulletin.html``, ``templates/html/large_print.html``).

This module owns two renderer-side concerns:

* expanding the ``ServiceConfig`` enums into the derived boolean toggles the
  rite conditions use (``canticle`` -> ``canticle_glory_to_god`` /
  ``canticle_this_is_the_feast``; ``creed_type`` -> ``creed_nicene`` /
  ``creed_apostles``; ``eucharistic_form`` -> ``eucharistic_extended``), and
* the flow-group membership — which consecutive blocks a document keeps
  together on a page (``break-inside: avoid``).  This is per-document
  pagination, not rite structure, so each document supplies its own groups.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union

from bulletin_maker.core.content_source import ContentContext, resolve_text
from bulletin_maker.core.library import (
    HOLY_BAPTISM_MODULE_ID,
    SUNDAY_COMMUNION_RITE_ID,
    load_modules,
    load_rite,
)
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.rite import (
    Block,
    Rite,
    RiteModule,
    RoleLabels,
    condition_applies,
    substitute_variables,
)
from bulletin_maker.core.text_catalog import get_text
from bulletin_maker.renderer.static_text import DialogRole
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_THIS_IS_THE_FEAST,
)

# A resolved render unit is either a bare block id (str) — dispatched by id in
# the document template, exactly as before — or an *embedded* block dict tagged
# ``{"embedded": True, ...}``, dispatched generically by ``type`` via the
# ``render_block`` template macro.  Embedded units only ever arise from
# expanding a generic ``module_ref`` (see ``_collect``); a rite whose only
# module_ref is baptism (a macro-rendered module) yields only bare ids, so its
# output is byte-identical to before.
Unit = Union[str, Dict[str, Any]]


class RiteEmbedError(RuntimeError):
    """A ``module_ref`` could not be embedded (cycle, too deep, or unknown)."""


# Modules with a bespoke, byte-frozen macro renderer in the templates stay
# id-dispatched: their ``module_ref`` emits the block id (e.g. "baptism" ->
# ``m.baptism_rite(...)``) untouched.  Every *other* module_ref is expanded
# generically into its blocks, rendered by type.  This is what keeps existing
# rites byte-identical — the only library module_ref is baptism.
MACRO_RENDERED_MODULES = frozenset({HOLY_BAPTISM_MODULE_ID})

# Recursion guard for nested module_refs (cycle detection also applies).
_MAX_EMBED_DEPTH = 8

# Map a text-catalog dialogue role (DialogRole.value) to a rite schema role.
_SCHEMA_ROLE_OF: Dict[str, str] = {
    DialogRole.PASTOR.value: "leader",
    DialogRole.CONGREGATION.value: "congregation",
    DialogRole.INSTRUCTION.value: "instruction",
    DialogRole.NONE.value: "none",
}

# Renderer-side pagination: consecutive blocks a document wraps in a single
# ``.flow-group`` so they stay together across a page break.  Each tuple mirrors
# the ``<div class="flow-group">`` runs of the corresponding pre-refactor
# template exactly; the groupings differ per document.
_BULLETIN_FLOW_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("gathering_chimes", "prelude", "choral_call_to_worship", "welcome_spoken"),
    ("greeting", "kyrie"),
    ("prayer_of_day",),
    ("sermon_seated_rubric", "sermon", "sermon_hymn"),
    ("creed_nicene", "creed_apostles"),
    ("prayers_of_intercession",),
    ("peace",),
    ("offering", "offertory"),
    ("offering_prayer",),
    ("preface", "congregation_sings_sanctus", "sanctus"),
    ("invitation_to_communion", "invitation_seated_rubric"),
    ("post_communion_stand_rubric", "post_communion_blessing"),
    ("prayer_after_communion", "blessing"),
    ("announcements", "sending_hymn", "dismissal", "postlude", "copyright"),
)

# Large print (and the leader guide, which shares this template) groups
# differently from the bulletin: the sermon hymn is not grouped with the
# sermon, the great-thanksgiving/sanctus run is ungrouped, the nunc dimittis is
# its own group, and there is no copyright block (large print ends at the
# postlude).  Mirrors ``large_print.html`` exactly.
_LARGE_PRINT_FLOW_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("gathering_chimes", "prelude", "choral_call_to_worship", "welcome_spoken"),
    ("sermon_seated_rubric", "sermon"),
    ("prayers_of_intercession",),
    ("peace",),
    ("offering", "offertory"),
    ("offering_prayer",),
    ("invitation_to_communion", "invitation_seated_rubric"),
    ("post_communion_stand_rubric", "post_communion_blessing"),
    ("nunc_dimittis",),
    ("prayer_after_communion", "blessing"),
    ("announcements", "sending_hymn", "dismissal", "postlude"),
)


def _flow_group_index(groups: Tuple[Tuple[str, ...], ...]) -> Dict[str, int]:
    return {
        block_id: index
        for index, group in enumerate(groups)
        for block_id in group
    }


_BULLETIN_FLOW_GROUP_OF: Dict[str, int] = _flow_group_index(_BULLETIN_FLOW_GROUPS)
_LARGE_PRINT_FLOW_GROUP_OF: Dict[str, int] = _flow_group_index(_LARGE_PRINT_FLOW_GROUPS)


@lru_cache(maxsize=None)
def _rite_by_id(rite_id: str) -> Rite:
    return load_rite(rite_id)


def _resolve_rite(config: ServiceConfig) -> Rite:
    """The rite driving this service — the picked ``rite_id``, or the
    bundled ELW Sunday Communion rite when the field is unset (every
    pre-picker service, and any service left on the default)."""
    return _rite_by_id(config.rite_id or SUNDAY_COMMUNION_RITE_ID)


def build_condition_context(
    config: ServiceConfig, season_id: str,
) -> Dict[str, Any]:
    """Expand a resolved ServiceConfig into the rite condition context.

    Returns ``{season, feasts, toggles}`` as consumed by
    :func:`bulletin_maker.core.rite.condition_applies`.  ``season_id`` is the
    season-identity string a rite ``condition.seasons`` list matches against;
    the three enum config fields become derived booleans (see module docstring).
    """
    toggles = {
        "show_confession": bool(config.show_confession),
        "greeting": bool(config.show_greeting),
        "kyrie": bool(config.include_kyrie),
        "canticle_glory_to_god": config.canticle == CANTICLE_GLORY_TO_GOD,
        "canticle_this_is_the_feast": config.canticle == CANTICLE_THIS_IS_THE_FEAST,
        "baptism": bool(config.include_baptism),
        "creed_nicene": config.creed_type == "nicene",
        "creed_apostles": config.creed_type == "apostles",
        "eucharistic_extended": config.eucharistic_form == "extended",
        "memorial_acclamation": bool(config.include_memorial_acclamation),
        "nunc_dimittis": bool(config.show_nunc_dimittis),
    }
    return {"season": season_id, "feasts": [], "toggles": toggles}


@lru_cache(maxsize=None)
def _library_modules() -> Dict[str, RiteModule]:
    return load_modules()


def _dialogue_lines(
    data: Dict[str, Any], variables: Dict[str, str],
) -> List[Dict[str, str]]:
    """Normalize a dialogue block's lines to ``[{role, text}]`` schema roles.

    Inline ``lines`` are already schema-shaped (and get ``{{key}}`` variable
    substitution); a ``text_ref`` resolves to catalog ``(DialogRole, text)``
    tuples — static text, no substitution — mapped back to the schema roles.
    """
    if "lines" in data:
        return [
            {
                "role": line.get("role", "none"),
                "text": substitute_variables(line["text"], variables),
            }
            for line in data["lines"]
        ]
    resolved = get_text(data["text_ref"])
    return [
        {"role": _SCHEMA_ROLE_OF[role.value], "text": text}
        for role, text in resolved
    ]


def _literal_text(data: Dict[str, Any], variables: Dict[str, str]) -> str:
    if "text" in data:
        return substitute_variables(data["text"], variables)
    if "text_ref" in data:
        return get_text(data["text_ref"])
    return ""


def _slot_heading(block: Block) -> str:
    if block.title:
        return block.title
    d = block.data
    label = d.get("slot") or d.get("kind") or d.get("piece") or block.type
    return str(label).replace("_", " ").upper()


def resolve_canonical_slot(block: Block, content: ContentContext) -> Any:
    """Resolve a ``canonical_slot`` block's text through the content source.

    A canonical_slot stores no canonical wording in the app: its ``section_key``
    is resolved via :func:`content_source.resolve_text`, whose priority chain is
    a church-saved custom text -> (later) a licensed S&S pull -> the entitlement
    placeholder.  With no church override and no pull wired in this layer, the
    result is :data:`content_source.ENTITLEMENT_PLACEHOLDER`.
    """
    if block.type != "canonical_slot":
        raise ValueError(
            "resolve_canonical_slot expects a canonical_slot block, got %r"
            % block.type
        )
    section_key = block.data["section_key"]
    return resolve_text(section_key, content)


def _embed_unit(
    block: Block, labels: RoleLabels, variables: Dict[str, str],
) -> Dict[str, Any]:
    """Build a type-dispatched embedded render unit from a module block.

    Inline text fields get ``{{key}}`` per-service variable substitution.
    """
    unit: Dict[str, Any] = {
        "embedded": True,
        "id": block.id,
        "type": block.type,
        "title": block.title,
    }
    if block.type in ("heading", "rubric"):
        unit["text"] = substitute_variables(block.data.get("text", ""), variables)
    elif block.type == "literal_text":
        unit["text"] = _literal_text(block.data, variables)
        unit["style"] = block.data.get("style", "plain")
    elif block.type == "dialogue":
        unit["lines"] = _dialogue_lines(block.data, variables)
        unit["leader_label"] = labels.leader
        unit["congregation_label"] = labels.congregation
    else:
        # hymn_slot / reading_slot / psalm / proper_slot / notation /
        # music_item resolve their content from renderer-side context, which is
        # not available for an arbitrary embedded module; represent the block by
        # its structural heading (per-slot content resolution is a follow-on).
        unit["heading"] = _slot_heading(block)
    return unit


def _lookup_module(
    block: Block,
    module_id: Optional[str],
    modules: Dict[str, RiteModule],
    stack: Tuple[str, ...],
) -> RiteModule:
    if module_id in stack:
        chain = " -> ".join(stack + (module_id,))
        raise RiteEmbedError("module_ref cycle detected: %s" % chain)
    if len(stack) >= _MAX_EMBED_DEPTH:
        raise RiteEmbedError(
            "module_ref nesting exceeds max depth %d (at block %r)"
            % (_MAX_EMBED_DEPTH, block.id)
        )
    module = modules.get(module_id)
    if module is None:
        raise RiteEmbedError(
            "module_ref block %r references unknown module %r"
            % (block.id, module_id)
        )
    return module


def _collect(
    blocks: List[Block],
    context: Dict[str, Any],
    modules: Dict[str, RiteModule],
    labels: RoleLabels,
    variables: Dict[str, str],
    stack: Tuple[str, ...],
    embed: bool,
) -> List[Unit]:
    """Flatten ``blocks`` (condition-filtered) into render units.

    Top-level rite blocks emit bare ids (id-dispatched, unchanged).  A
    macro-rendered ``module_ref`` (baptism) also emits its bare id.  Any other
    ``module_ref`` expands into the module's blocks, which — being embedded —
    emit type-dispatched unit dicts (recursively, with a recursion guard).
    """
    units: List[Unit] = []
    for block in blocks:
        if not block.enabled or not condition_applies(block.condition, context):
            continue
        if block.type == "module_ref":
            module_id = block.data.get("module_id")
            if module_id in MACRO_RENDERED_MODULES:
                units.append(block.id)
                continue
            module = _lookup_module(block, module_id, modules, stack)
            units.extend(
                _collect(
                    module.blocks, context, modules, labels, variables,
                    stack + (module_id,), embed=True,
                )
            )
            continue
        units.append(
            _embed_unit(block, labels, variables) if embed else block.id
        )
    return units


def _resolve_units(
    rite: Rite,
    context: Dict[str, Any],
    modules: Dict[str, RiteModule],
    variables: Optional[Dict[str, str]] = None,
) -> List[Unit]:
    return _collect(
        rite.blocks, context, modules, rite.role_labels, variables or {},
        (), embed=False,
    )


def _group(
    units: List[Unit], flow_group_of: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Wrap consecutive same-flow-group block ids; others render standalone.

    Embedded units (dicts) are always standalone and break any flow run — they
    carry no flow-group membership (that grouping is keyed by the fixed
    document block ids).
    """
    items: List[Dict[str, Any]] = []
    index = 0
    count = len(units)
    while index < count:
        unit = units[index]
        group_key = None if isinstance(unit, dict) else flow_group_of.get(unit)
        if group_key is None:
            items.append({"flow": False, "ids": [unit]})
            index += 1
            continue
        run = [unit]
        cursor = index + 1
        while (
            cursor < count
            and not isinstance(units[cursor], dict)
            and flow_group_of.get(units[cursor]) == group_key
        ):
            run.append(units[cursor])
            cursor += 1
        items.append({"flow": True, "ids": run})
        index = cursor
    return items


def resolve_bulletin_sequence(
    config: ServiceConfig,
    season_id: str,
    modules: Optional[Dict[str, RiteModule]] = None,
) -> List[Dict[str, Any]]:
    """Return the bulletin's render sequence: ordered, condition-filtered blocks.

    Each item is ``{"flow": bool, "ids": [unit, ...]}``.  A unit is a bare block
    id (str, id-dispatched) or an embedded block dict (type-dispatched via the
    ``render_block`` macro); ``flow`` items are wrapped in a ``.flow-group`` div
    by the template.  ``modules`` overrides the bundled library modules (tests).
    """
    context = build_condition_context(config, season_id)
    rite = _resolve_rite(config)
    modules = _library_modules() if modules is None else modules
    units = _resolve_units(rite, context, modules, config.variables)
    return _group(units, _BULLETIN_FLOW_GROUP_OF)


def resolve_large_print_sequence(
    config: ServiceConfig,
    season_id: str,
    modules: Optional[Dict[str, RiteModule]] = None,
) -> List[Dict[str, Any]]:
    """Return the large-print / leader-guide render sequence.

    Same rite, order, and conditions as the bulletin — only the flow-group
    pagination differs (see ``_LARGE_PRINT_FLOW_GROUPS``).  The leader guide
    shares this sequence and switches individual blocks from text to notation
    images via ``*_image_uri`` context values, per-block in the template.
    """
    context = build_condition_context(config, season_id)
    rite = _resolve_rite(config)
    modules = _library_modules() if modules is None else modules
    units = _resolve_units(rite, context, modules, config.variables)
    return _group(units, _LARGE_PRINT_FLOW_GROUP_OF)

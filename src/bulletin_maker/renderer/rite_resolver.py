"""Resolve the bulletin's ordered, condition-filtered rite blocks (LWS-0c).

The bulletin document is rendered by iterating the library rite
(``elw_sunday_communion``) block by block, in order, keeping only the blocks
whose ``condition`` applies to the current service.  Order and conditions come
from the rite; the per-block markup and the ``.flow-group`` pagination grouping
stay with the renderer (``templates/html/bulletin.html``).

This module owns two renderer-side concerns:

* expanding the ``ServiceConfig`` enums into the derived boolean toggles the
  rite conditions use (``canticle`` -> ``canticle_glory_to_god`` /
  ``canticle_this_is_the_feast``; ``creed_type`` -> ``creed_nicene`` /
  ``creed_apostles``; ``eucharistic_form`` -> ``eucharistic_extended``), and
* the flow-group membership — which consecutive blocks the bulletin keeps
  together on a page (``break-inside: avoid``).  This is pagination, not rite
  structure.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Tuple

from bulletin_maker.core.library import SUNDAY_COMMUNION_RITE_ID, load_rite
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.rite import Rite, condition_applies
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_THIS_IS_THE_FEAST,
)

# Renderer-side pagination: consecutive blocks the bulletin wraps in a single
# ``.flow-group`` so they stay together across a page break.  Mirrors the
# ``<div class="flow-group">`` runs of the pre-refactor bulletin.html exactly.
_FLOW_GROUPS: Tuple[Tuple[str, ...], ...] = (
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

_FLOW_GROUP_OF: Dict[str, int] = {
    block_id: index
    for index, group in enumerate(_FLOW_GROUPS)
    for block_id in group
}


@lru_cache(maxsize=1)
def _bulletin_rite() -> Rite:
    return load_rite(SUNDAY_COMMUNION_RITE_ID)


def build_condition_context(
    config: ServiceConfig, season: LiturgicalSeason,
) -> Dict[str, Any]:
    """Expand a resolved ServiceConfig into the rite condition context.

    Returns ``{season, feasts, toggles}`` as consumed by
    :func:`bulletin_maker.core.rite.condition_applies`.  The three enum fields
    become derived booleans (see module docstring).
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
    return {"season": season.value, "feasts": [], "toggles": toggles}


def _visible_block_ids(context: Dict[str, Any]) -> List[str]:
    rite = _bulletin_rite()
    return [
        block.id
        for block in rite.blocks
        if condition_applies(block.condition, context)
    ]


def _group(block_ids: List[str]) -> List[Dict[str, Any]]:
    """Wrap consecutive same-flow-group block ids; others render standalone."""
    items: List[Dict[str, Any]] = []
    index = 0
    count = len(block_ids)
    while index < count:
        block_id = block_ids[index]
        group_key = _FLOW_GROUP_OF.get(block_id)
        if group_key is None:
            items.append({"flow": False, "ids": [block_id]})
            index += 1
            continue
        run = [block_id]
        cursor = index + 1
        while cursor < count and _FLOW_GROUP_OF.get(block_ids[cursor]) == group_key:
            run.append(block_ids[cursor])
            cursor += 1
        items.append({"flow": True, "ids": run})
        index = cursor
    return items


def resolve_bulletin_sequence(
    config: ServiceConfig, season: LiturgicalSeason,
) -> List[Dict[str, Any]]:
    """Return the bulletin's render sequence: ordered, condition-filtered blocks.

    Each item is ``{"flow": bool, "ids": [block_id, ...]}``; ``flow`` items are
    wrapped in a ``.flow-group`` div by the template.
    """
    context = build_condition_context(config, season)
    return _group(_visible_block_ids(context))

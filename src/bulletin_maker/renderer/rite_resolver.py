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
from typing import Any, Dict, List, Tuple

from bulletin_maker.core.library import SUNDAY_COMMUNION_RITE_ID, load_rite
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.rite import Rite, condition_applies
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_THIS_IS_THE_FEAST,
)

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


@lru_cache(maxsize=1)
def _sunday_communion_rite() -> Rite:
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
    rite = _sunday_communion_rite()
    return [
        block.id
        for block in rite.blocks
        if condition_applies(block.condition, context)
    ]


def _group(
    block_ids: List[str], flow_group_of: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Wrap consecutive same-flow-group block ids; others render standalone."""
    items: List[Dict[str, Any]] = []
    index = 0
    count = len(block_ids)
    while index < count:
        block_id = block_ids[index]
        group_key = flow_group_of.get(block_id)
        if group_key is None:
            items.append({"flow": False, "ids": [block_id]})
            index += 1
            continue
        run = [block_id]
        cursor = index + 1
        while cursor < count and flow_group_of.get(block_ids[cursor]) == group_key:
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
    return _group(_visible_block_ids(context), _BULLETIN_FLOW_GROUP_OF)


def resolve_large_print_sequence(
    config: ServiceConfig, season: LiturgicalSeason,
) -> List[Dict[str, Any]]:
    """Return the large-print / leader-guide render sequence.

    Same rite, order, and conditions as the bulletin — only the flow-group
    pagination differs (see ``_LARGE_PRINT_FLOW_GROUPS``).  The leader guide
    shares this sequence and switches individual blocks from text to notation
    images via ``*_image_uri`` context values, per-block in the template.
    """
    context = build_condition_context(config, season)
    return _group(_visible_block_ids(context), _LARGE_PRINT_FLOW_GROUP_OF)

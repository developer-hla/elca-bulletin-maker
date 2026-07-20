"""Tests for the rite condition context (RB-1 season-id generalization).

The rite resolver builds the condition-evaluation context that
``core.rite.condition_applies`` matches a block's ``Condition.seasons``
against.  RB-1 makes that context carry the season IDENTITY as a string id,
so a rite condition matches on the id (and a non-RCL provider's new id would
flow through) rather than depending on the closed ``LiturgicalSeason`` enum.
"""

from __future__ import annotations

from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.rite import Condition, condition_applies
from bulletin_maker.renderer.rite_resolver import build_condition_context
from bulletin_maker.renderer.season import LiturgicalSeason


def _config() -> ServiceConfig:
    return ServiceConfig(date="2026-2-22", date_display="February 22, 2026")


def test_context_season_is_the_id_string():
    context = build_condition_context(_config(), "lent")
    assert context["season"] == "lent"


def test_condition_matches_on_id_string():
    context = build_condition_context(_config(), LiturgicalSeason.LENT.value)
    lent_only = Condition(seasons=["lent"])
    advent_only = Condition(seasons=["advent"])
    assert condition_applies(lent_only, context) is True
    assert condition_applies(advent_only, context) is False


def test_unknown_provider_season_id_flows_through_to_conditions():
    # A future provider's season id the closed enum never heard of still
    # reaches the condition context verbatim and matches a rite authored
    # for it — no enum wall between the provider and the rite.
    context = build_condition_context(_config(), "gesima")
    assert context["season"] == "gesima"
    gesima_block = Condition(seasons=["gesima"])
    assert condition_applies(gesima_block, context) is True

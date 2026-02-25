"""Liturgical season detection and seasonal content configuration.

Detects season from S&S DayContent title and provides season-specific
configuration for document generation (which liturgical elements appear,
which forms are used, etc.).
"""

from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass


class LiturgicalSeason(Enum):
    ADVENT = "advent"
    CHRISTMAS = "christmas"
    EPIPHANY = "epiphany"
    LENT = "lent"
    EASTER = "easter"
    PENTECOST = "pentecost"       # Ordinary Time after Pentecost
    CHRISTMAS_EVE = "christmas_eve"


@dataclass
class SeasonalConfig:
    """What liturgical elements are present/which forms are used for a season."""
    has_kyrie: bool                # Kyrie present (omitted in Large Print regardless)
    canticle: str                  # "glory_to_god", "this_is_the_feast", or "none"
    creed_default: str             # "apostles" or "nicene"
    eucharistic_form: str          # "short", "poetic", or "extended"
    has_memorial_acclamation: bool # Memorial Acclamation in eucharistic prayer


# Season -> config mapping (from bulletin-format-notes.md)
_SEASON_CONFIGS = {
    LiturgicalSeason.ADVENT: SeasonalConfig(
        has_kyrie=True,
        canticle="glory_to_god",
        creed_default="apostles",
        eucharistic_form="poetic",
        has_memorial_acclamation=False,
    ),
    LiturgicalSeason.CHRISTMAS: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
    ),
    LiturgicalSeason.EPIPHANY: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
    ),
    LiturgicalSeason.LENT: SeasonalConfig(
        has_kyrie=True,
        canticle="none",
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
    ),
    LiturgicalSeason.EASTER: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
    ),
    LiturgicalSeason.PENTECOST: SeasonalConfig(
        has_kyrie=True,
        canticle="glory_to_god",
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
    ),
    LiturgicalSeason.CHRISTMAS_EVE: SeasonalConfig(
        has_kyrie=False,
        canticle="none",
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
    ),
}


def detect_season(title: str) -> LiturgicalSeason:
    """Detect liturgical season from S&S DayContent title.

    Examples:
        "First Sunday in Lent, Year A" -> LENT
        "Second Sunday of Advent, Year A" -> ADVENT
        "Lectionary 32, Year C" -> PENTECOST (Ordinary Time)
        "Baptism of Our Lord" -> EPIPHANY
        "Christmas Eve" -> CHRISTMAS_EVE
    """
    t = title.lower()

    if "christmas eve" in t:
        return LiturgicalSeason.CHRISTMAS_EVE
    if "advent" in t:
        return LiturgicalSeason.ADVENT
    if "christmas" in t:
        return LiturgicalSeason.CHRISTMAS
    if "epiphany" in t or "baptism of" in t:
        return LiturgicalSeason.EPIPHANY
    if "lent" in t or "ash wednesday" in t:
        return LiturgicalSeason.LENT
    if "easter" in t:
        return LiturgicalSeason.EASTER
    # "Lectionary N" or "Pentecost N" = Ordinary Time
    if "lectionary" in t or "pentecost" in t:
        return LiturgicalSeason.PENTECOST
    # Transfiguration falls in Epiphany season
    if "transfiguration" in t:
        return LiturgicalSeason.EPIPHANY

    # Default to Pentecost/Ordinary
    return LiturgicalSeason.PENTECOST


def get_seasonal_config(season: LiturgicalSeason) -> SeasonalConfig:
    """Get the liturgical configuration for a season."""
    return _SEASON_CONFIGS[season]

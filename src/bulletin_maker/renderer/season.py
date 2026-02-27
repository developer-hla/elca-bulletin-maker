"""Liturgical season detection and seasonal content configuration.

Detects season from S&S DayContent title and provides season-specific
configuration for document generation (which liturgical elements appear,
which forms are used, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bulletin_maker.sns.models import ServiceConfig


class LiturgicalSeason(Enum):
    ADVENT = "advent"
    CHRISTMAS = "christmas"
    EPIPHANY = "epiphany"
    LENT = "lent"
    EASTER = "easter"
    PENTECOST = "pentecost"       # Ordinary Time after Pentecost
    CHRISTMAS_EVE = "christmas_eve"


class PrefaceType(Enum):
    """All sung preface variants available in Setting Two.

    Each member's value is the key used in file stems (preface_{value}.jpg)
    and serialized to/from the UI.
    """
    # Seasonal
    ADVENT = "advent"
    CHRISTMAS = "christmas"
    EPIPHANY = "epiphany"
    LENT = "lent"
    EASTER = "easter"
    SUNDAYS = "sundays"           # Ordinary Time
    PENTECOST = "pentecost"
    # Occasional
    APOSTLES = "apostles"
    ASCENSION = "ascension"
    FUNERAL = "funeral"
    HEALING = "healing"
    HOLY_TRINITY = "holy_trinity"
    HOLY_WEEK = "holy_week"
    MARRIAGE = "marriage"
    SAINTS = "saints"
    TRANSFIGURATION = "transfiguration"
    WEEKDAYS = "weekdays"

    @property
    def label(self) -> str:
        return _PREFACE_LABELS[self]

    @property
    def group(self) -> str:
        return "seasonal" if self in _SEASONAL_PREFACES else "occasional"


_PREFACE_LABELS: dict[PrefaceType, str] = {
    PrefaceType.ADVENT: "Advent",
    PrefaceType.CHRISTMAS: "Christmas",
    PrefaceType.EPIPHANY: "Epiphany",
    PrefaceType.LENT: "Lent",
    PrefaceType.EASTER: "Easter",
    PrefaceType.SUNDAYS: "Sundays (Ordinary Time)",
    PrefaceType.PENTECOST: "Pentecost",
    PrefaceType.APOSTLES: "Apostles",
    PrefaceType.ASCENSION: "Ascension",
    PrefaceType.FUNERAL: "Funeral",
    PrefaceType.HEALING: "Healing",
    PrefaceType.HOLY_TRINITY: "Holy Trinity",
    PrefaceType.HOLY_WEEK: "Holy Week",
    PrefaceType.MARRIAGE: "Marriage",
    PrefaceType.SAINTS: "Saints",
    PrefaceType.TRANSFIGURATION: "Transfiguration",
    PrefaceType.WEEKDAYS: "Weekdays",
}

_SEASONAL_PREFACES: frozenset[PrefaceType] = frozenset({
    PrefaceType.ADVENT,
    PrefaceType.CHRISTMAS,
    PrefaceType.EPIPHANY,
    PrefaceType.LENT,
    PrefaceType.EASTER,
    PrefaceType.SUNDAYS,
    PrefaceType.PENTECOST,
})


@dataclass
class SeasonalConfig:
    """What liturgical elements are present/which forms are used for a season."""
    has_kyrie: bool                # Kyrie present (omitted in Large Print regardless)
    canticle: str                  # "glory_to_god", "this_is_the_feast", or "none"
    creed_default: str             # "apostles" or "nicene"
    eucharistic_form: str          # "short", "poetic", or "extended"
    has_memorial_acclamation: bool # Memorial Acclamation in eucharistic prayer
    preface: PrefaceType           # Default preface for this season
    show_confession: bool = True   # False for Christmas Eve
    show_nunc_dimittis: bool = True  # True always (user can override)


# Season -> config mapping (from bulletin-format-notes.md)
_SEASON_CONFIGS = {
    LiturgicalSeason.ADVENT: SeasonalConfig(
        has_kyrie=True,
        canticle="glory_to_god",
        creed_default="apostles",
        eucharistic_form="poetic",
        has_memorial_acclamation=False,
        preface=PrefaceType.ADVENT,
    ),
    LiturgicalSeason.CHRISTMAS: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.CHRISTMAS,
    ),
    LiturgicalSeason.EPIPHANY: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.EPIPHANY,
    ),
    LiturgicalSeason.LENT: SeasonalConfig(
        has_kyrie=False,
        canticle="none",
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.LENT,
    ),
    LiturgicalSeason.EASTER: SeasonalConfig(
        has_kyrie=True,
        canticle="this_is_the_feast",
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.EASTER,
    ),
    LiturgicalSeason.PENTECOST: SeasonalConfig(
        has_kyrie=True,
        canticle="glory_to_god",
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
        preface=PrefaceType.SUNDAYS,
    ),
    LiturgicalSeason.CHRISTMAS_EVE: SeasonalConfig(
        has_kyrie=False,
        canticle="none",
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
        preface=PrefaceType.CHRISTMAS,
        show_confession=False,
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


def get_preface_options() -> dict[str, list[dict[str, str]]]:
    """Return preface options grouped by seasonal/occasional.

    Built from PrefaceType — this is the single source of truth for the UI.
    """
    groups: dict[str, list[dict[str, str]]] = {"seasonal": [], "occasional": []}
    for preface in PrefaceType:
        groups[preface.group].append({"key": preface.value, "label": preface.label})
    return groups


def get_seasonal_config(season: LiturgicalSeason) -> SeasonalConfig:
    """Get the liturgical configuration for a season."""
    return _SEASON_CONFIGS[season]


def fill_seasonal_defaults(config: ServiceConfig, season: LiturgicalSeason) -> None:
    """Fill any None liturgical-choice fields on config from the season defaults.

    Mutates ``config`` in place.  Only touches fields that are None;
    values already set by the user/wizard are left unchanged.
    """
    seasonal = _SEASON_CONFIGS[season]

    if config.creed_type is None:
        config.creed_type = seasonal.creed_default
    if config.include_kyrie is None:
        config.include_kyrie = seasonal.has_kyrie
    if config.canticle is None:
        config.canticle = seasonal.canticle
    if config.eucharistic_form is None:
        config.eucharistic_form = seasonal.eucharistic_form
    if config.include_memorial_acclamation is None:
        config.include_memorial_acclamation = seasonal.has_memorial_acclamation
    if config.preface is None:
        config.preface = seasonal.preface
    if config.show_confession is None:
        config.show_confession = seasonal.show_confession
    if config.show_nunc_dimittis is None:
        config.show_nunc_dimittis = seasonal.show_nunc_dimittis

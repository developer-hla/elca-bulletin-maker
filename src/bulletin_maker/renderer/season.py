"""Liturgical season detection and seasonal content configuration.

Detects season from S&S DayContent title and provides season-specific
configuration for document generation (which liturgical elements appear,
which forms are used, etc.).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from bulletin_maker.exceptions import BulletinError

if TYPE_CHECKING:
    from bulletin_maker.core.models import ServiceConfig


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
    canticle: str                  # CANTICLE_GLORY_TO_GOD, CANTICLE_THIS_IS_THE_FEAST, or CANTICLE_NONE
    creed_default: str             # "apostles" or "nicene"
    eucharistic_form: str          # "short" or "extended"
    has_memorial_acclamation: bool # Memorial Acclamation in eucharistic prayer
    preface: PrefaceType           # Default preface for this season
    show_confession: bool = True   # False for Christmas Eve
    show_greeting: bool = True     # True for all current seasons (override per-service)
    show_nunc_dimittis: bool = True  # True always (user can override)


# Season house-customs data (LWS-0d): per-congregation policy, bundled as
# data rather than hardcoded so a future per-church override (seasonal_rules,
# see web/seasonal_rules.py) has something to override. Values here must
# stay identical to the pre-LWS-0d hardcoded dict — this is an
# output-neutral refactor, not a policy change.
_SEASONAL_CUSTOMS_FILE = Path(__file__).resolve().parent / "data" / "seasonal_customs.json"


def _load_seasonal_customs(path: Path) -> dict[LiturgicalSeason, SeasonalConfig]:
    """Parse the bundled seasonal-customs data file into SeasonalConfig objects.

    Fails fast (BulletinError) if any LiturgicalSeason member has no entry
    in the data file.
    """
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    customs: dict[LiturgicalSeason, SeasonalConfig] = {}
    for season in LiturgicalSeason:
        if season.value not in raw:
            raise BulletinError(
                f"Missing seasonal customs for season {season.value!r} in {path}"
            )
        entry = raw[season.value]
        customs[season] = SeasonalConfig(
            has_kyrie=entry["has_kyrie"],
            canticle=entry["canticle"],
            creed_default=entry["creed_default"],
            eucharistic_form=entry["eucharistic_form"],
            has_memorial_acclamation=entry["has_memorial_acclamation"],
            preface=PrefaceType(entry["preface"]),
            show_confession=entry["show_confession"],
            show_greeting=entry["show_greeting"],
            show_nunc_dimittis=entry["show_nunc_dimittis"],
        )
    return customs


_SEASONAL_CUSTOMS = _load_seasonal_customs(_SEASONAL_CUSTOMS_FILE)


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
    return _SEASONAL_CUSTOMS[season]


def fill_seasonal_defaults(config: ServiceConfig, season: LiturgicalSeason) -> None:
    """Fill any None liturgical-choice fields on config from the season defaults.

    Mutates ``config`` in place.  Only touches fields that are None;
    values already set by the user/wizard are left unchanged.
    """
    seasonal = _SEASONAL_CUSTOMS[season]

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
        config.preface = PrefaceType.SUNDAYS
    if config.show_confession is None:
        config.show_confession = seasonal.show_confession
    if config.show_greeting is None:
        config.show_greeting = seasonal.show_greeting
    if config.show_nunc_dimittis is None:
        config.show_nunc_dimittis = seasonal.show_nunc_dimittis

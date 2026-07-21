"""Config variants of the fixture Sunday for the LWS-0a parity harness.

Four variants of the same recorded S&S day (``lectionary16_2026-07-19.json``,
shared with ``tests/test_layout_regression.py``) chosen to exercise the
conditional paths in the renderer templates:

    regular  — exactly what the layout suite renders today.
    baptism  — baptism toggle on, with candidate names.
    lenten   — kyrie off, canticle none, extended eucharistic prayer,
               nicene creed: mirrors what ``fill_seasonal_defaults``
               produces for LiturgicalSeason.LENT.
    festival — canticle "this_is_the_feast", memorial acclamation sung,
               nicene creed — explicit overrides layered on the fixture's
               native (Ordinary Time) season.

Each variant is a fully-resolved (DayContent, ServiceConfig, season)
triple ready to hand to ``generate_documents()``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.renderer.season import (
    LiturgicalSeason,
    detect_season,
    fill_seasonal_defaults,
)
from bulletin_maker.sns.models import (
    CANTICLE_THIS_IS_THE_FEAST,
    DayContent,
    HymnLyrics,
    Reading,
)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures" / "day_content" / "lectionary16_2026-07-19.json"
)


class Variant(NamedTuple):
    name: str
    day: DayContent
    config: ServiceConfig
    season: str


def load_fixture() -> tuple[DayContent, dict[str, HymnLyrics]]:
    """Load the recorded S&S day shared with the layout regression suite."""
    fx = json.loads(FIXTURE.read_text())
    day_data = dict(fx["day"])
    day_data["readings"] = [Reading(**r) for r in day_data["readings"]]
    day = DayContent(**day_data)
    hymns = {slot: HymnLyrics(**data) for slot, data in fx["hymns"].items()}
    return day, hymns


def _base_config(hymns: dict[str, HymnLyrics]) -> ServiceConfig:
    return ServiceConfig(
        date="2026-07-19",
        date_display="July 19, 2026",
        gathering_hymn=hymns["gathering"],
        sermon_hymn=hymns["sermon"],
        communion_hymn=hymns["communion"],
        sending_hymn=hymns["sending"],
        prelude_title="All Glory Be to God on High",
        prelude_composer="Johann Pachelbel",
        offertory_title="Seek Ye First",
        offertory_composer="Karen Lafferty",
        postlude_title="Savior, Again to Your Dear Name",
    )


def _regular(day: DayContent, hymns: dict[str, HymnLyrics]) -> Variant:
    config = _base_config(hymns)
    season = detect_season(day.title).value
    fill_seasonal_defaults(config, season)
    return Variant("regular", day, config, season)


def _baptism(day: DayContent, hymns: dict[str, HymnLyrics]) -> Variant:
    config = _base_config(hymns)
    season = detect_season(day.title).value
    fill_seasonal_defaults(config, season)
    config.include_baptism = True
    config.variables = {
        "baptism_candidate_names": "Jordan Alexis Rivera, Micah Thomas Rivera"
    }
    return Variant("baptism", day, config, season)


def _lenten(day: DayContent, hymns: dict[str, HymnLyrics]) -> Variant:
    """Kyrie off, canticle none, extended EP, nicene creed — pure LENT
    seasonal defaults, on the fixture's own readings/hymns."""
    config = _base_config(hymns)
    season = LiturgicalSeason.LENT.value
    fill_seasonal_defaults(config, season)
    return Variant("lenten", day, config, season)


def _festival(day: DayContent, hymns: dict[str, HymnLyrics]) -> Variant:
    """This Is the Feast, sung memorial acclamation, nicene creed —
    explicit overrides layered on the fixture's native season."""
    config = _base_config(hymns)
    season = detect_season(day.title).value
    fill_seasonal_defaults(config, season)
    config.canticle = CANTICLE_THIS_IS_THE_FEAST
    config.creed_type = "nicene"
    config.include_memorial_acclamation = True
    config.memorial_acclamation_mode = "sung"
    return Variant("festival", day, config, season)


def build_variants() -> list[Variant]:
    day, hymns = load_fixture()
    return [
        _regular(day, hymns),
        _baptism(day, hymns),
        _lenten(day, hymns),
        _festival(day, hymns),
    ]


VARIANTS: list[Variant] = build_variants()
VARIANT_NAMES: tuple[str, ...] = tuple(v.name for v in VARIANTS)

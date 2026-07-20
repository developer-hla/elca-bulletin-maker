"""Round-trip/parity tests for the seasonal house-customs data layer (LWS-0d).

season.py used to hardcode a Season -> SeasonalConfig dict; those values now
live in renderer/data/seasonal_customs.json, loaded once at import time.
This is an output-neutral refactor: the expected values below are hardcoded
from the CURRENT (pre-LWS-0d) season.py so any drift between the data file
and the historical Python dict fails loudly here.

The storage tests need the same Postgres test DB the rest of the suite uses
(``BULLETIN_TEST_DATABASE_URL``); the loader tests are pure and need no DB.
"""

from __future__ import annotations

import json
import os

import pytest

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.season import (
    LiturgicalSeason,
    PrefaceType,
    SeasonalConfig,
    _load_seasonal_customs,
    get_seasonal_config,
)
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_NONE,
    CANTICLE_THIS_IS_THE_FEAST,
)
from bulletin_maker.web import db, seasonal_rules

# Expected values transcribed from the pre-LWS-0d hardcoded _SEASON_CONFIGS
# dict in season.py — the ground truth this refactor must not disturb.
EXPECTED = {
    LiturgicalSeason.ADVENT: SeasonalConfig(
        has_kyrie=True,
        canticle=CANTICLE_GLORY_TO_GOD,
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
        preface=PrefaceType.ADVENT,
    ),
    LiturgicalSeason.CHRISTMAS: SeasonalConfig(
        has_kyrie=True,
        canticle=CANTICLE_THIS_IS_THE_FEAST,
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.CHRISTMAS,
    ),
    LiturgicalSeason.EPIPHANY: SeasonalConfig(
        has_kyrie=True,
        canticle=CANTICLE_THIS_IS_THE_FEAST,
        creed_default="apostles",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.EPIPHANY,
    ),
    LiturgicalSeason.LENT: SeasonalConfig(
        has_kyrie=False,
        canticle=CANTICLE_NONE,
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.LENT,
    ),
    LiturgicalSeason.EASTER: SeasonalConfig(
        has_kyrie=True,
        canticle=CANTICLE_THIS_IS_THE_FEAST,
        creed_default="nicene",
        eucharistic_form="extended",
        has_memorial_acclamation=True,
        preface=PrefaceType.EASTER,
    ),
    LiturgicalSeason.PENTECOST: SeasonalConfig(
        has_kyrie=True,
        canticle=CANTICLE_GLORY_TO_GOD,
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
        preface=PrefaceType.SUNDAYS,
    ),
    LiturgicalSeason.CHRISTMAS_EVE: SeasonalConfig(
        has_kyrie=False,
        canticle=CANTICLE_NONE,
        creed_default="apostles",
        eucharistic_form="short",
        has_memorial_acclamation=False,
        preface=PrefaceType.CHRISTMAS,
        show_confession=False,
    ),
}


# ── Bundled data matches the historical hardcoded values exactly ───────


@pytest.mark.parametrize("season", list(LiturgicalSeason))
def test_get_seasonal_config_matches_historical_values(season):
    assert get_seasonal_config(season) == EXPECTED[season]


def test_every_liturgical_season_is_covered():
    assert set(EXPECTED) == set(LiturgicalSeason)


# ── Loader fails fast on incomplete data ────────────────────────────────


def test_loader_fails_fast_on_missing_season(tmp_path):
    incomplete = {
        season.value: {
            "has_kyrie": True,
            "canticle": "none",
            "creed_default": "apostles",
            "eucharistic_form": "short",
            "has_memorial_acclamation": False,
            "preface": "sundays",
            "show_confession": True,
            "show_greeting": True,
            "show_nunc_dimittis": True,
        }
        for season in LiturgicalSeason
        if season is not LiturgicalSeason.LENT
    }
    bad_file = tmp_path / "incomplete_seasonal_customs.json"
    bad_file.write_text(json.dumps(incomplete))

    with pytest.raises(BulletinError) as exc:
        _load_seasonal_customs(bad_file)
    assert "lent" in str(exc.value)


# ── Per-church override seam (empty today) ──────────────────────────────

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL", "postgresql://localhost/bulletin_maker_test"
)


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    db.reset_for_tests()
    with db.connect() as conn:
        conn.execute("TRUNCATE seasonal_rules, churches RESTART IDENTITY CASCADE")


def test_get_church_seasonal_overrides_empty_for_church_with_no_rules():
    church = db.create_church("Test Church", {"name": "Test Church"})
    assert seasonal_rules.get_church_seasonal_overrides(church["id"]) == {}

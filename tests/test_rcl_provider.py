"""Tests for the RCL calendar provider (LWS-3b / RB-2).

The provider *computes* the Revised Common Lectionary temporal day from a
date (Western Easter computus + the Advent anchor), so these tests pin its
output against a table of KNOWN liturgical days spanning several years.

How the expected values were derived (not from the provider itself):

* Western Easter dates come from the church's own algorithm and were spot
  checked against ``dateutil.easter.easter`` (2023-04-09, 2024-03-31,
  2025-04-20, 2026-04-05).
* Moveable days anchor off Easter by the standard offsets: Ash Wednesday
  Easter-46, Palm Sunday Easter-7, Ascension Easter+39, Pentecost
  Easter+49, Holy Trinity Easter+56.
* Advent I is the fourth Sunday before Christmas Day; Christ the King is the
  Sunday before Advent I (= "Lectionary 34"). "Lectionary N" for an ordinary
  Sunday after Pentecost is N counted back by weeks from Christ the King —
  equivalently the RCL Proper whose fixed date window the Sunday falls in
  (Lectionary 16 = the Sunday of July 17-23, so 2026-07-19 = Lectionary 16,
  which is exactly the S&S fixture title in tests/fixtures/day_content/).
* Lectionary year: the year that begins in Advent of calendar year Y is
  A when Y % 3 == 0, B when Y % 3 == 1, C when Y % 3 == 2 — pinned to the
  anchors Advent 2022 = A, Advent 2024 = C, Advent 2025 = A, and to the
  fixture (the liturgical year of 2026-07-19 began Advent 2025 = Year A).
* "First Sunday in Lent, Year A" == 2026-02-22 is the very example in
  ``core.naming.extract_day_name``'s docstring, independently fixing the
  Ash Wednesday / Lent math for 2026.

Reading citations (propers) are intentionally empty for this phase.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bulletin_maker.core.calendar import (
    CALENDAR_PROVIDER_KEYS,
    DEFAULT_CALENDAR_PROVIDER,
    get_calendar_provider,
)
from bulletin_maker.core.naming import extract_day_name
from bulletin_maker.core.rcl_calendar import RclCalendarProvider
from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.season import detect_season

FIXTURE = (
    Path(__file__).parent
    / "fixtures" / "day_content" / "lectionary16_2026-07-19.json"
)

# (date, expected lectionary year, expected season id, expected day_name)
KNOWN_DAYS = [
    # --- Advent (year-cycle anchors) ---
    ("2022-11-27", "A", "advent", "First Sunday of Advent"),
    ("2025-11-30", "A", "advent", "First Sunday of Advent"),
    ("2024-12-01", "C", "advent", "First Sunday of Advent"),
    ("2025-12-07", "A", "advent", "Second Sunday of Advent"),
    # --- Christmas ---
    ("2025-12-24", "A", "christmas_eve", "Christmas Eve"),
    ("2025-12-25", "A", "christmas", "Nativity of Our Lord"),
    # --- Epiphany ---
    ("2026-01-06", "A", "epiphany", "Epiphany of Our Lord"),
    ("2026-01-11", "A", "epiphany", "Baptism of Our Lord"),
    ("2023-01-22", "A", "epiphany", "Third Sunday after Epiphany"),
    ("2026-02-15", "A", "epiphany", "Transfiguration of Our Lord"),
    # --- Lent (2026-02-22 fixed by naming.py docstring) ---
    ("2026-02-18", "A", "lent", "Ash Wednesday"),
    ("2026-02-22", "A", "lent", "First Sunday in Lent"),
    ("2026-03-01", "A", "lent", "Second Sunday in Lent"),
    ("2026-03-29", "A", "lent", "Sunday of the Passion"),
    # --- Easter ---
    ("2026-04-05", "A", "easter", "Resurrection of Our Lord"),
    ("2026-04-12", "A", "easter", "Second Sunday of Easter"),
    ("2026-04-26", "A", "easter", "Fourth Sunday of Easter"),
    ("2026-05-14", "A", "easter", "Ascension of Our Lord"),
    # --- Time after Pentecost ---
    ("2026-05-24", "A", "pentecost", "Day of Pentecost"),
    ("2026-05-31", "A", "pentecost", "The Holy Trinity"),
    ("2026-06-07", "A", "pentecost", "Lectionary 10"),
    ("2026-07-19", "A", "pentecost", "Lectionary 16"),  # the S&S fixture Sunday
    ("2025-07-20", "C", "pentecost", "Lectionary 16"),
    ("2024-09-15", "B", "pentecost", "Lectionary 24"),
    ("2026-11-22", "A", "pentecost", "Christ the King"),
    ("2024-11-24", "B", "pentecost", "Christ the King"),
]


@pytest.fixture
def provider() -> RclCalendarProvider:
    return RclCalendarProvider()


@pytest.mark.parametrize("date,year,season_id,day_name", KNOWN_DAYS)
def test_known_days(provider, date, year, season_id, day_name):
    day = provider.resolve(date)
    assert day.day_name == day_name
    assert day.season.id == season_id
    assert day.cycles == {"rcl": year}


@pytest.mark.parametrize("date,year", [
    ("2022-11-27", "A"),  # Advent 2022 begins Year A
    ("2024-12-01", "C"),  # Advent 2024 begins Year C
    ("2025-11-30", "A"),  # Advent 2025 begins Year A
    ("2023-12-03", "B"),  # Advent 2023 begins Year B (completes the cycle)
])
def test_year_cycle_anchors(provider, date, year):
    assert provider.resolve(date).cycles["rcl"] == year


def test_propers_are_empty_by_design(provider):
    for date, *_ in KNOWN_DAYS:
        assert provider.resolve(date).propers == {}


def test_season_id_stays_in_the_rcl_western_vocabulary(provider):
    rcl_western_ids = {
        "advent", "christmas", "christmas_eve",
        "epiphany", "lent", "easter", "pentecost",
    }
    for date, *_ in KNOWN_DAYS:
        assert provider.resolve(date).season.id in rcl_western_ids


def test_matches_sns_fixture_day():
    """The computed day for the fixture Sunday reproduces what the S&S path
    (extract_day_name + detect_season on the S&S title) yields."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    title = fixture["day"]["title"]
    expected_name = extract_day_name(title)
    expected_season = detect_season(title).value

    day = RclCalendarProvider().resolve("2026-07-19")

    assert day.day_name == expected_name  # "Lectionary 16"
    assert day.season.id == expected_season  # "pentecost"
    assert day.cycles == {"rcl": "A"}  # title says "Year A"


def test_registered_and_opt_in():
    assert "rcl" in CALENDAR_PROVIDER_KEYS
    assert isinstance(get_calendar_provider("rcl"), RclCalendarProvider)
    assert DEFAULT_CALENDAR_PROVIDER == "sns"  # rcl never becomes the default


def test_bad_date_fails_loudly(provider):
    with pytest.raises(BulletinError):
        provider.resolve("July 19, 2026")


def test_ignores_extra_context(provider):
    """resolve() computes from the date alone; a stray day=... kwarg (the
    server passes one uniformly) is ignored, not an error."""
    day = provider.resolve("2026-07-19", day=object())
    assert day.day_name == "Lectionary 16"

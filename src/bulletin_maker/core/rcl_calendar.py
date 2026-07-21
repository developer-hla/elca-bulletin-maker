"""RCL calendar provider (LWS-3b / RB-2): computes the Revised Common
Lectionary temporal day from a date, no lookup table and no network.

Where :class:`~bulletin_maker.core.calendar.SnsCalendarProvider` classifies
an already-fetched S&S ``DayContent`` (string-matching its title), this
provider *computes* the liturgical day from the calendar date alone: it
anchors every moveable observance off Western Easter
(:func:`dateutil.easter.easter`) and off Christmas Day, then names the day
by the standard RCL temporal cycle and reports the three-year A/B/C
lectionary position. It is the second real provider on the calendar seam
and gives ELCA calendar identity in-house.

Scope — the TEMPORAL cycle only. Every season-driven Sunday (Advent →
Christ the King) and the principal feasts that anchor it (Christmas Eve,
Nativity of Our Lord, Epiphany, Baptism of Our Lord, Transfiguration, Ash
Wednesday, Maundy Thursday, Good Friday, Sunday of the Passion,
Resurrection of Our Lord, Ascension, Day of Pentecost, The Holy Trinity,
Christ the King) are resolved with the day names S&S uses. Sanctoral /
fixed lesser festivals and the festivals often transferred to a Sunday
(Reformation, All Saints, Name of Jesus, Presentation, Holy Cross, etc.)
are OUT of scope: those Sundays resolve to their ordinary temporal identity
(a "Lectionary N" Sunday), a deliberate future extension, not this phase.

Propers (reading citations) are intentionally EMPTY for RB-2
(``propers == {}``). The RCL reading dataset carries a separate
copyright/licensing question, and churches entitled to S&S already receive
citations from S&S; supplying them here is a later workstream. This
provider proves the day-name / season / three-year-cycle computation.

Weekdays that are not one of the named feasts inherit the identity of their
liturgical week's anchoring Sunday when that Sunday shares their season,
and otherwise fall back to the season label — churches use this provider
for Sundays and principal feasts, so weekday resolution is best-effort.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Tuple

from dateutil.easter import easter

from bulletin_maker.core.calendar import (
    CalendarProvider,
    LiturgicalDay,
    SeasonId,
)
from bulletin_maker.exceptions import BulletinError

SUNDAY = 6  # date.weekday(): Monday=0 .. Sunday=6

DAYS_ASH_BEFORE_EASTER = 46
DAYS_MAUNDY_BEFORE_EASTER = 3
DAYS_GOOD_FRIDAY_BEFORE_EASTER = 2
DAYS_PALM_BEFORE_EASTER = 7
DAYS_ASCENSION_AFTER_EASTER = 39
DAYS_PENTECOST_AFTER_EASTER = 49
DAYS_TRINITY_AFTER_EASTER = 56

ADVENT_WEEKS = 4
CHRIST_THE_KING_LECTIONARY = 34

CHRISTMAS_DAY = 25
CHRISTMAS_EVE_DAY = 24
EPIPHANY_MONTH = 1
EPIPHANY_DAY = 6
FIRST_BAPTISM_WINDOW_DAY = 7  # Baptism of Our Lord = first Sunday on/after Jan 7

LECTIONARY_YEARS = "ABC"  # indexed by (Advent-start calendar year) % 3

_ORDINALS = (
    "First", "Second", "Third", "Fourth", "Fifth",
    "Sixth", "Seventh", "Eighth", "Ninth", "Tenth",
)

_SEASON_LABELS: Dict[str, str] = {
    "advent": "Advent",
    "christmas": "Christmas",
    "christmas_eve": "Christmas Eve",
    "epiphany": "Epiphany",
    "lent": "Lent",
    "easter": "Easter",
    "pentecost": "Time after Pentecost",
}

_SEASON_COLORS: Dict[str, str] = {
    "advent": "blue",
    "christmas": "white",
    "christmas_eve": "white",
    "epiphany": "green",
    "lent": "purple",
    "easter": "white",
    "pentecost": "green",
}


def _season(season_id: str) -> SeasonId:
    return SeasonId(
        id=season_id,
        label=_SEASON_LABELS[season_id],
        color=_SEASON_COLORS[season_id],
    )


def _ordinal(n: int) -> str:
    return _ORDINALS[n - 1]


def _parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise BulletinError(
            "rcl calendar provider needs an ISO date (YYYY-MM-DD); got %r"
            % date_str
        ) from None


def _sunday_on_or_before(d: date) -> date:
    return d - timedelta(days=(d.weekday() - SUNDAY) % 7)


def _sunday_on_or_after(d: date) -> date:
    return d + timedelta(days=(SUNDAY - d.weekday()) % 7)


def _advent_start(year: int) -> date:
    last_advent_sunday = _sunday_on_or_before(date(year, 12, CHRISTMAS_EVE_DAY))
    return last_advent_sunday - timedelta(weeks=ADVENT_WEEKS - 1)


def _lectionary_year(d: date) -> str:
    advent_year = d.year if d >= _advent_start(d.year) else d.year - 1
    return LECTIONARY_YEARS[advent_year % 3]


def _named_feast(d: date, easter_day: date) -> Tuple[str, SeasonId]:
    """Return the (name, season) for a principal feast that can fall on a
    weekday, or ``("", ...)`` when ``d`` is not one of them."""
    if d == date(d.year, 12, CHRISTMAS_EVE_DAY):
        return "Christmas Eve", _season("christmas_eve")
    if d == date(d.year, 12, CHRISTMAS_DAY):
        return "Nativity of Our Lord", _season("christmas")
    if d == date(d.year, EPIPHANY_MONTH, EPIPHANY_DAY):
        return "Epiphany of Our Lord", _season("epiphany")
    if d == easter_day - timedelta(days=DAYS_ASH_BEFORE_EASTER):
        return "Ash Wednesday", _season("lent")
    if d == easter_day - timedelta(days=DAYS_MAUNDY_BEFORE_EASTER):
        return "Maundy Thursday", _season("lent")
    if d == easter_day - timedelta(days=DAYS_GOOD_FRIDAY_BEFORE_EASTER):
        return "Good Friday", _season("lent")
    if d == easter_day + timedelta(days=DAYS_ASCENSION_AFTER_EASTER):
        return "Ascension of Our Lord", _season("easter")
    return "", _season("pentecost")


def _advent_sunday(d: date, advent_start: date, season: SeasonId) -> str:
    week = (d - advent_start).days // 7 + 1
    return f"{_ordinal(week)} Sunday of Advent"


def _christmas_sunday(d: date, first_christmas_sunday: date) -> str:
    week = (d - first_christmas_sunday).days // 7 + 1
    return f"{_ordinal(week)} Sunday of Christmas"


def _epiphany_sunday(d: date, baptism: date, transfiguration: date) -> str:
    if d == baptism:
        return "Baptism of Our Lord"
    if d == transfiguration:
        return "Transfiguration of Our Lord"
    week = (d - baptism).days // 7 + 1
    return f"{_ordinal(week)} Sunday after Epiphany"


def _lent_sunday(d: date, first_lent_sunday: date, palm_sunday: date) -> str:
    if d == palm_sunday:
        return "Sunday of the Passion"
    week = (d - first_lent_sunday).days // 7 + 1
    return f"{_ordinal(week)} Sunday in Lent"


def _easter_sunday(d: date, easter_day: date) -> str:
    week = (d - easter_day).days // 7 + 1
    return f"{_ordinal(week)} Sunday of Easter"


def _pentecost_sunday(d: date, trinity: date, christ_the_king: date) -> str:
    if d == trinity:
        return "The Holy Trinity"
    if d == christ_the_king:
        return "Christ the King"
    weeks_before_king = (christ_the_king - d).days // 7
    return f"Lectionary {CHRIST_THE_KING_LECTIONARY - weeks_before_king}"


class RclCalendarProvider(CalendarProvider):
    """Computes the RCL temporal day from a date (Easter computus + Advent).

    Contract: ``season.id`` is always one of the RCL/Western season ids the
    ELCA path already uses (``advent``, ``christmas``, ``christmas_eve``,
    ``epiphany``, ``lent``, ``easter``, ``pentecost``), so it composes with
    the seasonal-customs and rite-condition system unchanged. ``cycles``
    carries the three-year position as ``{"rcl": "A"|"B"|"C"}``. ``propers``
    is empty by design for this phase (see the module docstring).
    """

    key = "rcl"

    def resolve(self, date: str, **_context: Any) -> LiturgicalDay:
        d = _parse_date(date)
        day_name, season = self._classify(d)
        return LiturgicalDay(
            date=date,
            day_name=day_name,
            season=season,
            cycles={"rcl": _lectionary_year(d)},
            propers={},
        )

    def _classify(self, d: date) -> Tuple[str, SeasonId]:
        easter_day = easter(d.year)
        feast_name, feast_season = _named_feast(d, easter_day)
        if feast_name:
            return feast_name, feast_season
        return self._temporal_day(d, easter_day)

    def _temporal_day(self, d: date, easter_day: date) -> Tuple[str, SeasonId]:
        advent_start = _advent_start(d.year)
        if d >= advent_start:
            return self._advent_or_christmas(d, advent_start)

        epiphany = date(d.year, EPIPHANY_MONTH, EPIPHANY_DAY)
        if d < epiphany:
            return self._christmastide(d)

        ash_wednesday = easter_day - timedelta(days=DAYS_ASH_BEFORE_EASTER)
        if d < ash_wednesday:
            return self._time_after_epiphany(d, easter_day, ash_wednesday)

        if d < easter_day:
            return self._lent(d, easter_day, ash_wednesday)

        if d == easter_day:
            return "Resurrection of Our Lord", _season("easter")

        pentecost = easter_day + timedelta(days=DAYS_PENTECOST_AFTER_EASTER)
        if d < pentecost:
            season = _season("easter")
            if d.weekday() == SUNDAY:
                return _easter_sunday(d, easter_day), season
            return self._weekday(d, season)

        if d == pentecost:
            return "Day of Pentecost", _season("pentecost")

        return self._time_after_pentecost(d, easter_day, advent_start)

    def _advent_or_christmas(self, d: date, advent_start: date) -> Tuple[str, SeasonId]:
        if d < date(d.year, 12, CHRISTMAS_EVE_DAY):
            season = _season("advent")
            if d.weekday() == SUNDAY:
                return _advent_sunday(d, advent_start, season), season
            return self._weekday(d, season)
        season = _season("christmas")
        first_christmas_sunday = _sunday_on_or_after(
            date(d.year, 12, CHRISTMAS_DAY) + timedelta(days=1))
        if d.weekday() == SUNDAY:
            return _christmas_sunday(d, first_christmas_sunday), season
        return self._weekday(d, season)

    def _christmastide(self, d: date) -> Tuple[str, SeasonId]:
        season = _season("christmas")
        previous_christmas = date(d.year - 1, 12, CHRISTMAS_DAY)
        first_christmas_sunday = _sunday_on_or_after(
            previous_christmas + timedelta(days=1))
        if d.weekday() == SUNDAY:
            return _christmas_sunday(d, first_christmas_sunday), season
        return self._weekday(d, season)

    def _time_after_epiphany(self, d: date, easter_day: date,
                             ash_wednesday: date) -> Tuple[str, SeasonId]:
        season = _season("epiphany")
        if d.weekday() != SUNDAY:
            return self._weekday(d, season)
        baptism = _sunday_on_or_after(
            date(d.year, EPIPHANY_MONTH, FIRST_BAPTISM_WINDOW_DAY))
        transfiguration = _sunday_on_or_before(ash_wednesday)
        return _epiphany_sunday(d, baptism, transfiguration), season

    def _lent(self, d: date, easter_day: date,
              ash_wednesday: date) -> Tuple[str, SeasonId]:
        season = _season("lent")
        if d.weekday() != SUNDAY:
            return self._weekday(d, season)
        first_lent_sunday = _sunday_on_or_after(
            ash_wednesday + timedelta(days=1))
        palm_sunday = easter_day - timedelta(days=DAYS_PALM_BEFORE_EASTER)
        return _lent_sunday(d, first_lent_sunday, palm_sunday), season

    def _time_after_pentecost(self, d: date, easter_day: date,
                              advent_start: date) -> Tuple[str, SeasonId]:
        season = _season("pentecost")
        if d.weekday() != SUNDAY:
            return self._weekday(d, season)
        trinity = easter_day + timedelta(days=DAYS_TRINITY_AFTER_EASTER)
        christ_the_king = advent_start - timedelta(weeks=1)
        return _pentecost_sunday(d, trinity, christ_the_king), season

    def _weekday(self, d: date, season: SeasonId) -> Tuple[str, SeasonId]:
        anchor_sunday = _sunday_on_or_before(d)
        anchor_name, anchor_season = self._classify(anchor_sunday)
        if anchor_season.id == season.id:
            return anchor_name, season
        return season.label or season.id, season


# Self-register into the calendar provider registry. At module bottom so
# RclCalendarProvider is fully defined; setdefault keeps it idempotent. By this
# point `calendar` is fully imported in both orders (rcl-first: our top-level
# import of calendar already completed it; calendar-first: it triggered our
# import only after finishing). See calendar._ensure_providers_loaded.
from bulletin_maker.core import calendar as _calendar  # noqa: E402
_calendar._PROVIDERS.setdefault("rcl", RclCalendarProvider())

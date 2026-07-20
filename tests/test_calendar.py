"""Tests for the calendar provider seam (LWS-3a).

Covers: the sns provider is output-neutral (same season/day_name detect_season
and extract_day_name would produce today, given the same DayContent), the
manual provider builds a LiturgicalDay from supplied input with no network
access, and provider selection via the church profile default.
"""

from __future__ import annotations

import pytest

from bulletin_maker.core.calendar import (
    CALENDAR_PROVIDER_KEYS,
    NEUTRAL_SEASON,
    ManualCalendarProvider,
    SeasonId,
    SnsCalendarProvider,
    get_calendar_provider,
    liturgical_season_of,
)
from bulletin_maker.core.naming import extract_day_name
from bulletin_maker.core.profile import CongregationProfile, profile_from_dict
from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.season import LiturgicalSeason, detect_season
from bulletin_maker.sns.models import DayContent, Reading

REPRESENTATIVE_TITLES = [
    "First Sunday of Advent, Year A",
    "Christmas Day",
    "First Sunday in Lent, Year A",
    "Resurrection of Our Lord - Easter Day",
    "Lectionary 32, Year C",
    "Baptism of Our Lord",  # a festival day
    "Sunday, July 19, 2026 Lectionary 16, Year A",  # full S&S title format
]


def _day(title: str, readings=None) -> DayContent:
    return DayContent(
        date="2026-7-19", title=title, introduction="",
        confession_html="", prayer_of_the_day_html="", gospel_acclamation="",
        readings=readings or [],
    )


class TestSnsCalendarProviderIsOutputNeutral:
    """The sns provider must yield exactly what detect_season/extract_day_name
    produce today — a church on this provider generates byte-identically."""

    @pytest.mark.parametrize("title", REPRESENTATIVE_TITLES)
    def test_season_matches_detect_season(self, title):
        day = _day(title)
        liturgical_day = SnsCalendarProvider().resolve(day.date, day=day)
        assert liturgical_day.season.id == detect_season(title).value

    @pytest.mark.parametrize("title", REPRESENTATIVE_TITLES)
    def test_liturgical_season_of_recovers_the_enum(self, title):
        day = _day(title)
        liturgical_day = SnsCalendarProvider().resolve(day.date, day=day)
        assert liturgical_season_of(liturgical_day) == detect_season(title)

    @pytest.mark.parametrize("title", REPRESENTATIVE_TITLES)
    def test_day_name_matches_extract_day_name(self, title):
        day = _day(title)
        liturgical_day = SnsCalendarProvider().resolve(day.date, day=day)
        assert liturgical_day.day_name == extract_day_name(title)

    def test_propers_come_from_reading_citations(self):
        readings = [
            Reading(label="First Reading", citation="Isaiah 44:6-8",
                    intro="", text_html=""),
            Reading(label="First Reading (alternate)",
                    citation="Wisdom 12:13, 16-19", intro="", text_html=""),
            Reading(label="Psalm", citation="Psalm 86:11-17",
                    intro="", text_html=""),
            Reading(label="Second Reading", citation="Romans 8:12-25",
                    intro="", text_html=""),
            Reading(label="Gospel", citation="Matthew 13:24-30, 36-43",
                    intro="", text_html=""),
        ]
        day = _day("Sunday, July 19, 2026 Lectionary 16, Year A", readings)
        liturgical_day = SnsCalendarProvider().resolve(day.date, day=day)
        assert liturgical_day.propers == {
            "first": "Isaiah 44:6-8",
            "psalm": "Psalm 86:11-17",
            "second": "Romans 8:12-25",
            "gospel": "Matthew 13:24-30, 36-43",
        }

    def test_requires_a_day_content(self):
        with pytest.raises(BulletinError):
            SnsCalendarProvider().resolve("2026-07-19")

    def test_get_calendar_provider_returns_sns(self):
        provider = get_calendar_provider("sns")
        assert isinstance(provider, SnsCalendarProvider)
        assert provider.key == "sns"


class TestManualCalendarProvider:
    """No lectionary, no network: built entirely from supplied input."""

    def test_builds_from_day_name_only(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Sermon Series: Sunday 3")
        assert liturgical_day.date == "2026-07-19"
        assert liturgical_day.day_name == "Sermon Series: Sunday 3"
        assert liturgical_day.propers == {}

    def test_default_season_is_neutral(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Sermon Series: Sunday 3")
        assert liturgical_day.season == NEUTRAL_SEASON
        assert liturgical_day.season.id == "none"

    def test_accepts_explicit_liturgical_season_override(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Lenten Teaching Series 2",
            season=LiturgicalSeason.LENT)
        assert liturgical_day.season == SeasonId(id="lent")
        assert liturgical_season_of(liturgical_day) == LiturgicalSeason.LENT

    def test_accepts_explicit_string_season(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Custom Series", season="epiphany_series_3")
        assert liturgical_day.season.id == "epiphany_series_3"

    def test_accepts_optional_citations(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Sermon Series: Sunday 3",
            propers={"first": "Romans 8:1-11"})
        assert liturgical_day.propers == {"first": "Romans 8:1-11"}

    def test_requires_day_name(self):
        with pytest.raises(BulletinError):
            ManualCalendarProvider().resolve("2026-07-19")

    def test_no_network_access(self, monkeypatch):
        """Building a manual LiturgicalDay must never touch the network —
        simulate that by making socket creation blow up and confirming
        resolve() still succeeds."""
        import socket

        def _forbidden(*args, **kwargs):
            raise AssertionError("manual provider must not open a socket")

        monkeypatch.setattr(socket, "socket", _forbidden)
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Sermon Series: Sunday 3")
        assert liturgical_day.day_name == "Sermon Series: Sunday 3"

    def test_get_calendar_provider_returns_manual(self):
        provider = get_calendar_provider("manual")
        assert isinstance(provider, ManualCalendarProvider)
        assert provider.key == "manual"


class TestGetCalendarProvider:
    def test_unknown_key_raises(self):
        with pytest.raises(BulletinError):
            get_calendar_provider("rcl_local")

    def test_known_keys(self):
        assert CALENDAR_PROVIDER_KEYS == {"sns", "manual"}


class TestLiturgicalSeasonOf:
    def test_raises_for_neutral_season(self):
        liturgical_day = ManualCalendarProvider().resolve(
            "2026-07-19", day_name="Sermon Series: Sunday 3")
        with pytest.raises(BulletinError):
            liturgical_season_of(liturgical_day)


class TestProfileCalendarProviderSelection:
    """calendar_provider is a per-church profile field, defaulting to sns —
    the sanctioned per-church extension point, same shape as
    liturgical_setting/paper_size."""

    def test_default_is_sns(self):
        profile = CongregationProfile(
            church_name="Test", address_lines=(), service_time="",
            welcome_message="", standing_instructions="")
        assert profile.calendar_provider == "sns"

    def test_profile_from_dict_defaults_to_sns(self):
        profile = profile_from_dict({"church_name": "Test"})
        assert profile.calendar_provider == "sns"

    def test_profile_from_dict_honors_explicit_value(self):
        profile = profile_from_dict(
            {"church_name": "Test", "calendar_provider": "manual"})
        assert profile.calendar_provider == "manual"

    def test_selection_resolves_to_the_right_provider(self):
        profile = profile_from_dict(
            {"church_name": "Test", "calendar_provider": "manual"})
        provider = get_calendar_provider(profile.calendar_provider)
        assert isinstance(provider, ManualCalendarProvider)

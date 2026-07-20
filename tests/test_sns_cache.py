"""Tests for the S&S content cache, service layer, and Thursday prefetch."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from psycopg.types.json import Jsonb

from bulletin_maker.exceptions import BulletinError, ContentNotFoundError
from bulletin_maker.sns.content_service import (
    ContentService,
    SubscriptionRequiredError,
    cache_get,
    cache_put,
)
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading
from bulletin_maker.sns import prefetch
from bulletin_maker.web import db, security

TEST_DATABASE_URL = "postgresql://localhost/bulletin_maker_test"

_TRUNCATE = (
    "TRUNCATE churches, users, past_runs, sessions, auth_tokens, jobs,"
    " artifacts, sns_cache, audit_log RESTART IDENTITY CASCADE"
)


def _day() -> DayContent:
    readings = [
        Reading(label=label, citation=f"{label[:4]} 1:1", intro="intro",
                text_html="<p>text</p>")
        for label in ("First Reading", "Psalm", "Second Reading", "Gospel")
    ]
    return DayContent(
        date="2026-7-19",
        title="Sunday, July 19, 2026 Lectionary 16, Year A",
        introduction="intro", confession_html="<div>c</div>",
        prayer_of_the_day_html="<p>p</p>", gospel_acclamation="ga",
        readings=readings, prayers_html="<p>prayers</p>",
        offering_prayer_html="o", prayer_after_communion_html="pac",
        blessing_html="b", dismissal_html="d",
    )


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    db.reset_for_tests()
    with db.connect() as conn:
        conn.execute(_TRUNCATE)


class TestSerialization:

    def test_day_content_roundtrip(self):
        day = _day()
        restored = DayContent.from_dict(day.to_dict())
        assert restored == day
        assert all(isinstance(r, Reading) for r in restored.readings)

    def test_reading_roundtrip(self):
        reading = Reading("Gospel", "John 3:16", "intro", "<p>text</p>")
        assert Reading.from_dict(reading.to_dict()) == reading

    def test_hymn_lyrics_roundtrip(self):
        lyrics = HymnLyrics(
            number="ELW 504", title="A Mighty Fortress",
            verses=["1\tline", "2\tline"], refrain="ref",
            copyright="PD", verse_label="Verses 1-2")
        assert HymnLyrics.from_dict(lyrics.to_dict()) == lyrics


class TestCacheStore:

    def test_put_then_get(self):
        cache_put("day:2026-7-19", {"hello": "world"})
        assert cache_get("day:2026-7-19") == {"hello": "world"}

    def test_miss_returns_none(self):
        assert cache_get("day:nope") is None

    def test_expired_entry_is_a_miss(self):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO sns_cache (cache_key, payload_jsonb, fetched_at,"
                " ttl_seconds) VALUES (%s, %s, now() - interval '10 days', %s)",
                ("day:old", None, 604800))
        # payload NULL -> miss regardless; also test a stale non-null payload
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO sns_cache (cache_key, payload_jsonb, fetched_at,"
                " ttl_seconds) VALUES (%s, %s, now() - interval '10 days', %s)",
                ("day:stale", Jsonb({"x": 1}), 604800))
        assert cache_get("day:old") is None
        assert cache_get("day:stale") is None

    def test_put_overwrites_and_refreshes(self):
        cache_put("day:k", {"v": 1})
        cache_put("day:k", {"v": 2})
        assert cache_get("day:k") == {"v": 2}


class TestContentService:

    def _service(self, client, entitled=True):
        return ContentService(entitled=entitled, client_provider=lambda: client)

    def test_miss_fetches_and_caches(self):
        client = MagicMock()
        client.get_day_texts.return_value = _day()
        service = self._service(client)

        result = service.get_day_content("2026-7-19")
        assert result == _day()
        client.get_day_texts.assert_called_once_with("2026-7-19")
        assert cache_get("day:2026-7-19") is not None

    def test_hit_does_not_touch_client(self):
        client = MagicMock()
        client.get_day_texts.return_value = _day()
        service = self._service(client)
        service.get_day_content("2026-7-19")

        client2 = MagicMock()
        service2 = self._service(client2)
        result = service2.get_day_content("2026-7-19")
        assert result == _day()
        client2.get_day_texts.assert_not_called()

    def test_force_refresh_bypasses_cache(self):
        client = MagicMock()
        client.get_day_texts.return_value = _day()
        service = self._service(client)
        service.get_day_content("2026-7-19")
        service.get_day_content("2026-7-19", force_refresh=True)
        assert client.get_day_texts.call_count == 2

    def test_passage_roundtrips_through_cache(self):
        client = MagicMock()
        client.search_passage.return_value = "<p>passage</p>"
        service = self._service(client)
        assert service.get_passage("John 3:16") == "<p>passage</p>"

        client2 = MagicMock()
        service2 = self._service(client2)
        assert service2.get_passage("John 3:16") == "<p>passage</p>"
        client2.search_passage.assert_not_called()

    def test_hymn_lyrics_cached(self):
        lyrics = HymnLyrics(number="ELW 504", title="A Mighty Fortress",
                            verses=["1\tline"], copyright="PD")
        client = MagicMock()
        client.fetch_hymn_lyrics.return_value = lyrics
        service = self._service(client)
        assert service.get_hymn_lyrics("ELW", "504", "7/19/2026") == lyrics

        client2 = MagicMock()
        service2 = self._service(client2)
        assert service2.get_hymn_lyrics("ELW", "504", "7/19/2026") == lyrics
        client2.fetch_hymn_lyrics.assert_not_called()

    def test_content_not_found_propagates(self):
        client = MagicMock()
        client.fetch_hymn_lyrics.side_effect = ContentNotFoundError("no words")
        service = self._service(client)
        with pytest.raises(ContentNotFoundError):
            service.get_hymn_lyrics("ELW", "999", "7/19/2026")

    def test_unentitled_never_reads_cache_or_client(self):
        cache_put("day:2026-7-19", _day().to_dict())
        client = MagicMock()
        service = self._service(client, entitled=False)
        with pytest.raises(SubscriptionRequiredError):
            service.get_day_content("2026-7-19")
        client.get_day_texts.assert_not_called()


class TestPrefetch:

    def test_coming_sunday_from_thursday(self):
        thursday = date(2026, 7, 16)
        assert prefetch.coming_sunday(thursday) == date(2026, 7, 19)

    def test_coming_sunday_from_sunday_is_next_week(self):
        sunday = date(2026, 7, 19)
        assert prefetch.coming_sunday(sunday) == date(2026, 7, 26)

    def _add_church(self, name, username):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO churches (name, invite_code, profile_json,"
                " sns_username, sns_password_enc) VALUES (%s, %s, '{}', %s, %s)",
                (name, name, username, "enc" if username else ""))

    def test_run_warms_only_linked_churches(self, monkeypatch):
        self._add_church("Linked", "linked@sns.org")
        self._add_church("Unlinked", "")

        client = MagicMock()
        client.get_day_texts.return_value = _day()
        monkeypatch.setattr(prefetch, "SundaysClient", lambda: client)
        monkeypatch.setattr(security, "decrypt_secret", lambda s: "pw")

        failures = prefetch.run(date(2026, 7, 16))
        assert failures == 0
        client.login.assert_called_once_with("linked@sns.org", "pw")
        assert cache_get("day:2026-7-19") is not None

    def test_per_church_error_does_not_abort(self, monkeypatch):
        self._add_church("Bad", "bad@sns.org")
        self._add_church("Good", "good@sns.org")

        def fake_warm(church, api_date):
            if church["sns_username"] == "bad@sns.org":
                raise BulletinError("login failed")
            cache_put(f"day:{api_date}", _day().to_dict())

        monkeypatch.setattr(prefetch, "warm_church", fake_warm)

        failures = prefetch.run(date(2026, 7, 16))
        assert failures == 1
        assert cache_get("day:2026-7-19") is not None

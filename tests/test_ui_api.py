"""Tests for the UI API bridge (bulletin_maker.ui.api).

Tests cover credential management, form data handling, and error wrapping
without requiring a live S&S connection or pywebview window.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bulletin_maker.ui.api import BulletinAPI


# ── BulletinAPI ───────────────────────────────────────────────────────


class TestLogin:
    def test_success(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        api._client = mock_client

        result = api.login("user@test.com", "pass123")

        assert result["success"] is True
        assert result["username"] == "user@test.com"
        mock_client.login.assert_called_once_with("user@test.com", "pass123")

    def test_auth_error_returns_failure(self):
        from bulletin_maker.exceptions import AuthError

        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.login.side_effect = AuthError("bad creds")
        api._client = mock_client

        result = api.login("bad", "creds")
        assert result["success"] is False
        assert "bad creds" in result["error"]


class TestLogout:
    def test_clears_client_state(self):
        api = BulletinAPI()
        api._client = MagicMock()
        api._hymn_cache["test"] = {"number": "1"}

        result = api.logout()

        assert result["success"] is True
        assert api._client is None
        assert api._day is None
        assert api._hymn_cache == {}


class TestFetchDayContent:
    def test_returns_error_without_client_login(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.get_day_texts.side_effect = Exception("not logged in")
        api._client = mock_client

        result = api.fetch_day_content("2026-02-22", "February 22, 2026")
        assert result["success"] is False

    def test_successful_fetch_returns_season_info(self):
        from bulletin_maker.sns.models import DayContent, Reading

        api = BulletinAPI()
        mock_client = MagicMock()
        day = DayContent(
            date="2026-2-22",
            title="Sunday, February 22, 2026 First Sunday in Lent, Year A",
            introduction="test",
            confession_html="<p>conf</p>",
            prayer_of_the_day_html="<p>prayer</p>",
            gospel_acclamation="alleluia",
            readings=[
                Reading("First Reading", "Genesis 2:15-17", "", "<p>text</p>"),
                Reading("Psalm", "Psalm 32", "", "<p>text</p>"),
            ],
        )
        mock_client.get_day_texts.return_value = day
        api._client = mock_client

        result = api.fetch_day_content("2026-02-22", "February 22, 2026")
        assert result["success"] is True
        assert result["season"] == "lent"
        assert "First Sunday in Lent" in result["day_name"]
        assert len(result["readings"]) == 2
        assert result["defaults"]["creed_type"] == "nicene"  # Lent default


class TestSearchHymn:
    def test_no_results_returns_error(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.search_hymn.return_value = []
        api._client = mock_client

        result = api.search_hymn("999", "ELW")
        assert result["success"] is False

    def test_success_returns_title(self):
        from bulletin_maker.sns.models import HymnResult

        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.search_hymn.return_value = [
            HymnResult(atom_id="123", title="Amazing Grace",
                       words_atom_id="456"),
        ]
        api._client = mock_client

        result = api.search_hymn("779", "ELW")
        assert result["success"] is True
        assert result["title"] == "Amazing Grace"
        assert result["has_words"] is True


class TestGenerateAll:
    def test_error_when_no_day_content(self):
        api = BulletinAPI()
        api._day = None
        result = api.generate_all({})
        assert result["success"] is False
        assert "No content fetched" in result["error"]

    def test_builds_service_config_from_form_data(self):
        """Verify generate_all constructs ServiceConfig correctly
        (we mock the actual generation to avoid needing Playwright)."""
        from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading

        api = BulletinAPI()
        api._day = DayContent(
            date="2026-2-22",
            title="Sunday, February 22, 2026 First Sunday in Lent, Year A",
            introduction="test",
            confession_html="",
            prayer_of_the_day_html="",
            gospel_acclamation="",
            readings=[
                Reading("First Reading", "Genesis 2:15-17", "", "<p>text</p>"),
            ],
            prayers_html="<p>prayers</p>",
        )

        # Cache a hymn
        api._hymn_cache["ELW_335"] = {
            "number": "ELW 335",
            "title": "Jesus, Keep Me Near the Cross",
            "verses": ["verse1", "verse2"],
            "refrain": "refrain text",
            "copyright": "PD",
        }

        form_data = {
            "date": "2026-02-22",
            "date_display": "February 22, 2026",
            "creed_type": "nicene",
            "include_kyrie": False,
            "canticle": "none",
            "eucharistic_form": "extended",
            "include_memorial_acclamation": True,
            "gathering_hymn": {"number": "335", "collection": "ELW", "title": "Jesus, Keep Me Near the Cross"},
            "sermon_hymn": None,
            "communion_hymn": None,
            "sending_hymn": None,
            "output_dir": "/tmp/test_output",
        }

        # Mock generation functions to avoid Playwright dependency
        # These are imported inside generate_all from bulletin_maker.renderer
        with patch("bulletin_maker.renderer.html_renderer.render_to_pdf") as mock_rtp, \
             patch("bulletin_maker.renderer.html_renderer.render_with_shrink") as mock_rws, \
             patch("bulletin_maker.renderer.generate_bulletin") as mock_bull, \
             patch("bulletin_maker.renderer.generate_pulpit_prayers") as mock_pray, \
             patch("bulletin_maker.renderer.generate_pulpit_scripture") as mock_scrip, \
             patch("bulletin_maker.renderer.generate_large_print") as mock_lp:

            mock_bull.return_value = (Path("/tmp/test_output/bulletin.pdf"), 5)
            mock_pray.return_value = Path("/tmp/test_output/prayers.pdf")
            mock_scrip.return_value = Path("/tmp/test_output/scripture.pdf")
            mock_lp.return_value = Path("/tmp/test_output/lp.pdf")

            result = api.generate_all(form_data)

        assert result["success"] is True
        assert "bulletin" in result["results"]
        assert "prayers" in result["results"]
        assert "scripture" in result["results"]
        assert "large_print" in result["results"]

        # Verify the ServiceConfig was built correctly
        call_args = mock_bull.call_args
        config = call_args[1].get("config") if "config" in (call_args[1] or {}) else call_args[0][1]
        assert config.creed_type == "nicene"
        assert config.include_kyrie is False
        assert config.gathering_hymn is not None
        assert config.gathering_hymn.title == "Jesus, Keep Me Near the Cross"
        assert len(config.gathering_hymn.verses) == 2


class TestOpenOutputFolder:
    def test_nonexistent_folder_returns_error(self, tmp_path):
        api = BulletinAPI()
        result = api.open_output_folder(str(tmp_path / "nope"))
        assert result["success"] is False

    @patch("bulletin_maker.ui.api.subprocess.Popen")
    @patch("bulletin_maker.ui.api.platform.system", return_value="Darwin")
    def test_opens_existing_folder(self, mock_sys, mock_popen, tmp_path):
        api = BulletinAPI()
        result = api.open_output_folder(str(tmp_path))
        assert result["success"] is True
        mock_popen.assert_called_once()


class TestCleanup:
    def test_closes_client(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        api._client = mock_client

        api.cleanup()
        mock_client.close.assert_called_once()
        assert api._client is None

    def test_noop_when_no_client(self):
        api = BulletinAPI()
        api.cleanup()  # Should not raise

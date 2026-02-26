"""Tests for the UI API bridge (bulletin_maker.ui.api).

Tests cover credential management, form data handling, error wrapping,
progress callbacks, window-dependent methods, and generation error paths
without requiring a live S&S connection or pywebview window.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading
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
    def test_returns_error_on_bulletin_error(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.get_day_texts.side_effect = BulletinError("not logged in")
        api._client = mock_client

        result = api.fetch_day_content("2026-02-22", "February 22, 2026")
        assert result["success"] is False
        assert "not logged in" in result["error"]

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
        assert result["defaults"]["preface"] == "lent"


class TestGetPrefaceOptions:
    def test_returns_preface_groups(self):
        api = BulletinAPI()
        result = api.get_preface_options()
        assert result["success"] is True
        assert "seasonal" in result["prefaces"]
        assert "occasional" in result["prefaces"]


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
             patch("bulletin_maker.renderer.generate_large_print") as mock_lp, \
             patch("bulletin_maker.renderer.generate_leader_guide") as mock_lg:

            mock_bull.return_value = (Path("/tmp/test_output/bulletin.pdf"), 5)
            mock_pray.return_value = Path("/tmp/test_output/prayers.pdf")
            mock_scrip.return_value = Path("/tmp/test_output/scripture.pdf")
            mock_lp.return_value = Path("/tmp/test_output/lp.pdf")
            mock_lg.return_value = Path("/tmp/test_output/leader_guide.pdf")

            result = api.generate_all(form_data)

        assert result["success"] is True
        assert "bulletin" in result["results"]
        assert "prayers" in result["results"]
        assert "scripture" in result["results"]
        assert "large_print" in result["results"]
        assert "leader_guide" in result["results"]

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


# ── H14: Error path tests for generate_all() ────────────────────────


class TestGenerateAllErrors:
    def _make_api_with_day(self):
        """Create a BulletinAPI with minimal DayContent set."""
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
        return api

    def test_missing_date_field(self):
        api = self._make_api_with_day()
        result = api.generate_all({"date_display": "February 22, 2026"})
        assert result["success"] is False
        assert "Missing required fields" in result["error"]

    def test_missing_date_display_field(self):
        api = self._make_api_with_day()
        result = api.generate_all({"date": "2026-02-22"})
        assert result["success"] is False
        assert "Missing required fields" in result["error"]

    def test_partial_generation_failure(self, tmp_path):
        """One document fails, others succeed — errors dict populated."""
        api = self._make_api_with_day()

        form_data = {
            "date": "2026-02-22",
            "date_display": "February 22, 2026",
            "output_dir": str(tmp_path),
        }

        with patch("bulletin_maker.renderer.generate_bulletin") as mock_bull, \
             patch("bulletin_maker.renderer.generate_pulpit_prayers") as mock_pray, \
             patch("bulletin_maker.renderer.generate_pulpit_scripture") as mock_scrip, \
             patch("bulletin_maker.renderer.generate_large_print") as mock_lp, \
             patch("bulletin_maker.renderer.generate_leader_guide") as mock_lg:

            mock_bull.side_effect = RuntimeError("Playwright crashed")
            mock_pray.return_value = Path(tmp_path / "prayers.pdf")
            mock_scrip.return_value = Path(tmp_path / "scripture.pdf")
            mock_lp.return_value = Path(tmp_path / "lp.pdf")
            mock_lg.return_value = Path(tmp_path / "leader_guide.pdf")

            result = api.generate_all(form_data)

        assert result["success"] is False
        assert "bulletin" in result["errors"]
        assert "Playwright crashed" in result["errors"]["bulletin"]
        assert "prayers" in result["results"]
        assert "scripture" in result["results"]
        assert "large_print" in result["results"]
        assert "leader_guide" in result["results"]

    def test_all_generation_steps_fail(self, tmp_path):
        api = self._make_api_with_day()

        form_data = {
            "date": "2026-02-22",
            "date_display": "February 22, 2026",
            "output_dir": str(tmp_path),
        }

        with patch("bulletin_maker.renderer.generate_bulletin") as mock_bull, \
             patch("bulletin_maker.renderer.generate_pulpit_prayers") as mock_pray, \
             patch("bulletin_maker.renderer.generate_pulpit_scripture") as mock_scrip, \
             patch("bulletin_maker.renderer.generate_large_print") as mock_lp, \
             patch("bulletin_maker.renderer.generate_leader_guide") as mock_lg:

            mock_bull.side_effect = RuntimeError("fail 1")
            mock_pray.side_effect = RuntimeError("fail 2")
            mock_scrip.side_effect = RuntimeError("fail 3")
            mock_lp.side_effect = RuntimeError("fail 4")
            mock_lg.side_effect = RuntimeError("fail 5")

            result = api.generate_all(form_data)

        assert result["success"] is False
        assert len(result["errors"]) == 5
        assert result["results"] == {}


# ── M18: Window-dependent method tests ───────────────────────────────


class TestChooseOutputDirectory:
    def test_no_window_returns_error(self):
        api = BulletinAPI()
        api._window = None
        result = api.choose_output_directory()
        assert result["success"] is False
        assert "Window not available" in result["error"]

    def test_returns_selected_folder(self):
        api = BulletinAPI()
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = ["/Users/test/output"]
        api._window = mock_window

        result = api.choose_output_directory()
        assert result["success"] is True
        assert result["path"] == "/Users/test/output"

    def test_no_selection_returns_error(self):
        api = BulletinAPI()
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = []
        api._window = mock_window

        result = api.choose_output_directory()
        assert result["success"] is False


class TestChooseCoverImage:
    def test_no_window_returns_error(self):
        api = BulletinAPI()
        api._window = None
        result = api.choose_cover_image()
        assert result["success"] is False
        assert "Window not available" in result["error"]

    def test_returns_selected_file(self):
        api = BulletinAPI()
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = ["/Users/test/cover.jpg"]
        api._window = mock_window

        result = api.choose_cover_image()
        assert result["success"] is True
        assert result["path"] == "/Users/test/cover.jpg"

    def test_no_selection_returns_error(self):
        api = BulletinAPI()
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = None
        api._window = mock_window

        result = api.choose_cover_image()
        assert result["success"] is False


# ── M19: Progress callback tests ─────────────────────────────────────


class TestPushProgress:
    def test_sends_json_to_window(self):
        api = BulletinAPI()
        mock_window = MagicMock()
        api._window = mock_window

        api._push_progress("bulletin", "Generating...", 50)

        mock_window.evaluate_js.assert_called_once()
        js_call = mock_window.evaluate_js.call_args[0][0]
        assert "updateProgress(" in js_call
        # Verify the JSON is valid
        json_str = js_call.replace("updateProgress(", "").rstrip(")")
        payload = json.loads(json_str)
        assert payload["step"] == "bulletin"
        assert payload["detail"] == "Generating..."
        assert payload["pct"] == 50

    def test_noop_without_window(self):
        api = BulletinAPI()
        api._window = None
        # Should not raise
        api._push_progress("test", "detail", 0)


# ── M20: Expanded fetch_day_content() tests ──────────────────────────


class TestFetchDayContentErrors:
    def test_invalid_date_format(self):
        api = BulletinAPI()
        api._client = MagicMock()

        result = api.fetch_day_content("not-a-date", "Bad Date")
        assert result["success"] is False
        assert "Invalid date format" in result["error"]

    def test_bulletin_error_from_client(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        mock_client.get_day_texts.side_effect = BulletinError("S&S returned HTTP 500")
        api._client = mock_client

        result = api.fetch_day_content("2026-02-22", "February 22, 2026")
        assert result["success"] is False
        assert "HTTP 500" in result["error"]

    def test_no_readings_still_succeeds(self):
        api = BulletinAPI()
        mock_client = MagicMock()
        day = DayContent(
            date="2026-2-22",
            title="Sunday, February 22, 2026 First Sunday in Lent, Year A",
            introduction="test",
            confession_html="",
            prayer_of_the_day_html="",
            gospel_acclamation="",
            readings=[],
        )
        mock_client.get_day_texts.return_value = day
        api._client = mock_client

        result = api.fetch_day_content("2026-02-22", "February 22, 2026")
        assert result["success"] is True
        assert result["readings"] == []

    def test_title_without_year_prefix(self):
        """DayContent with unusual title still returns day_name."""
        api = BulletinAPI()
        mock_client = MagicMock()
        day = DayContent(
            date="2026-12-24",
            title="Christmas Eve",
            introduction="",
            confession_html="",
            prayer_of_the_day_html="",
            gospel_acclamation="",
            readings=[],
        )
        mock_client.get_day_texts.return_value = day
        api._client = mock_client

        result = api.fetch_day_content("2026-12-24", "December 24, 2026")
        assert result["success"] is True
        assert result["day_name"] == "Christmas Eve"

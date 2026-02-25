"""Integration tests — end-to-end flow with mocked HTTP responses.

Verifies: login → get_day_texts → search_hymn → fetch_hymn_lyrics
using realistic HTML stubs without a live S&S connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent


# ── Realistic HTML stubs ─────────────────────────────────────────────

LOGIN_PAGE_HTML = """
<html><body>
<form action="/Account/Login" method="post">
<input name="__RequestVerificationToken" value="test-csrf-token-123" type="hidden">
<input name="UserName" type="text">
<input name="Password" type="password">
</form>
</body></html>
"""

LOGIN_SUCCESS_HTML = """
<html><body>
<div>Welcome back, testuser</div>
<a href="/Account/LogOff">Log Off</a>
<a href="/Planner">Planner</a>
</body></html>
"""

DAY_TEXTS_HTML = """
<div id="rightcolumn">
<h2>Sunday, February 22, 2026 First Sunday in Lent, Year A</h2>
<h3>Introduction</h3>
<p>Today's texts speak of temptation.</p>
<h3>Confession and Forgiveness</h3>
<p>In the name of the Father...</p>
<h3>Prayer of the Day</h3>
<p>Lord God, our strength, the struggle between good and evil...</p>
<h3>First Reading: Genesis 2:15-17; 3:1-7</h3>
<div class="reading_intro"><em>The first temptation</em></div>
<div><p><sup>15</sup>The <sc>Lord</sc> God took the man...</p></div>
<h3>Psalm: Psalm 32</h3>
<div class="reading_intro"><em>Happy are they</em></div>
<div><p><sup>1</sup>Happy are they whose transgressions are forgiven...</p></div>
<h3>Second Reading: Romans 5:12-19</h3>
<div class="reading_intro"><em>Grace through one man</em></div>
<div><p><sup>12</sup>Just as sin came into the world...</p></div>
<h3>Gospel Acclamation</h3>
<p>Return to the Lord, your God.</p>
<h3>Gospel: Matthew 4:1-11</h3>
<div class="reading_intro"><em>The temptation of Jesus</em></div>
<div><p><sup>1</sup>Then Jesus was led up by the Spirit...</p></div>
<h3>Prayers of Intercession</h3>
<div class="body"><div>Open our hearts, Lord.</div><div><strong>Your mercy is great.</strong></div></div>
<h3>Offering Prayer</h3>
<p>Blessed are you, O God...</p>
<h3>Invitation to Communion</h3>
<p>Taste and see that the Lord is good.</p>
<h3>Prayer after Communion</h3>
<p>Gracious God, in you we live and move...</p>
<h3>Blessing</h3>
<p>The Lord bless you and keep you.</p>
<h3>Dismissal</h3>
<p>Go in peace. Serve the Lord.</p>
<div class="content-download">
"""

SEARCH_RESULTS_HTML = """
<html><body>
<form action="/Music/Search" method="post">
<input name="__RequestVerificationToken" value="csrf" type="hidden">
<input name="Search.HymnSongNumber" value="">
<input name="Search.Categories[0].SongBooks[0].Active" type="checkbox" value="true">
</form>
<table>
<tr>
<td>ELW 335</td>
<td data-title="Jesus, Keep Me Near the Cross" data-atom-id="55001">
<a data-atom-id="55010" title="Download">Harmony</a>
<a data-atom-id="55011" title="Download">Melody</a>
<a data-atom-id="55012" title="Download">Words</a>
</td>
</tr>
</table>
</body></html>
"""

MUSIC_FORM_HTML = """
<html><body>
<form action="/Music/Search" method="post">
<input name="__RequestVerificationToken" value="music-csrf" type="hidden">
<input name="Search.HymnSongNumber" value="">
<input name="Search.Categories[0].SongBooks[0].Active" type="checkbox" value="true">
<input name="Search.Categories[0].SongBooks[1].Active" type="checkbox" value="false">
</form>
</body></html>
"""


# ── Tests ────────────────────────────────────────────────────────────


class TestClientIntegration:
    """End-to-end client flow with mocked HTTP."""

    def _make_response(self, text: str = "", content: bytes = b"",
                       status_code: int = 200, url: str = ""):
        resp = MagicMock()
        resp.text = text
        resp.content = content or text.encode()
        resp.status_code = status_code
        resp.url = url
        resp.raise_for_status = MagicMock()
        return resp

    def test_login_and_fetch_day_texts(self):
        """Login then fetch DayTexts — verifies full parse pipeline."""
        client = SundaysClient()
        responses = [
            self._make_response(LOGIN_PAGE_HTML),      # GET /Account/Login
            self._make_response(LOGIN_SUCCESS_HTML),    # POST /Account/Login
            self._make_response(DAY_TEXTS_HTML),        # GET /Home/DayTexts/...
        ]
        client.client.request = MagicMock(side_effect=responses)

        client.login("user@test.com", "pass123")
        assert client._logged_in is True

        day = client.get_day_texts("2026-2-22")
        assert isinstance(day, DayContent)
        assert "First Sunday in Lent" in day.title
        assert len(day.readings) == 4  # First, Psalm, Second, Gospel
        assert day.readings[0].label == "First Reading"
        assert day.readings[0].citation == "Genesis 2:15-17; 3:1-7"
        assert day.readings[1].label == "Psalm"
        assert day.readings[3].label == "Gospel"
        assert "temptation" in day.introduction.lower()
        assert day.prayers_html != ""

    def test_search_hymn_parses_results(self):
        """Search hymn — verifies search form + result parsing."""
        client = SundaysClient()
        client._logged_in = True

        responses = [
            self._make_response(MUSIC_FORM_HTML),       # GET /Music
            self._make_response(SEARCH_RESULTS_HTML),    # POST /Music/Search
        ]
        client.client.request = MagicMock(side_effect=responses)

        results = client.search_hymn("335", "ELW")
        assert len(results) == 1
        assert results[0].title == "Jesus, Keep Me Near the Cross"
        assert results[0].atom_id == "55001"
        assert results[0].words_atom_id == "55012"
        assert results[0].harmony_atom_id == "55010"

    def test_full_login_fetch_search_flow(self):
        """Full pipeline: login → fetch → search without errors."""
        client = SundaysClient()
        responses = [
            self._make_response(LOGIN_PAGE_HTML),       # login GET
            self._make_response(LOGIN_SUCCESS_HTML),     # login POST
            self._make_response(DAY_TEXTS_HTML),         # DayTexts
            self._make_response(MUSIC_FORM_HTML),        # GET /Music
            self._make_response(SEARCH_RESULTS_HTML),    # POST /Music/Search
        ]
        client.client.request = MagicMock(side_effect=responses)

        client.login("user@test.com", "pass123")
        day = client.get_day_texts("2026-2-22")
        results = client.search_hymn("335", "ELW")

        assert client._logged_in
        assert len(day.readings) == 4
        assert len(results) == 1
        assert results[0].title == "Jesus, Keep Me Near the Cross"

"""Tests for the RTF lyrics parser using real S&S fixture files."""

from __future__ import annotations

from pathlib import Path

import pytest

from bulletin_maker.exceptions import ParseError
from bulletin_maker.sns.rtf_parser import parse_rtf_lyrics

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rtf"

ELW335_PATH = FIXTURES / "ELW335.rtf"
ELW504_PATH = FIXTURES / "ELW504.rtf"
ELW512_PATH = FIXTURES / "ELW512.rtf"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── ELW 335: numbered verses + refrain ─────────────────────────────


class TestNumberedWithRefrain:
    """ELW 335 — Jesus, Keep Me Near the Cross."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.lyrics = parse_rtf_lyrics(_read(ELW335_PATH), hymn_number="335")

    def test_title(self):
        assert self.lyrics.title == "Jesus, Keep Me Near the Cross"

    def test_number(self):
        assert self.lyrics.number == "ELW 335"

    def test_verse_count(self):
        assert len(self.lyrics.verses) == 4

    def test_first_verse_starts_with_number(self):
        assert self.lyrics.verses[0].startswith("1\t")

    def test_first_verse_content(self):
        v1 = self.lyrics.verses[0]
        assert "Jesus, keep me near the cross" in v1
        assert "Calv\u2019ry\u2019s mountain" in v1 or "Calv'ry's mountain" in v1

    def test_refrain_present(self):
        assert self.lyrics.refrain
        assert "In the cross" in self.lyrics.refrain
        assert "rest beyond the river" in self.lyrics.refrain

    def test_later_verses_have_refrain_marker(self):
        for v in self.lyrics.verses[1:]:
            assert "Refrain" in v, f"Verse missing Refrain marker: {v[:40]}..."

    def test_copyright(self):
        assert "Fanny J. Crosby" in self.lyrics.copyright


# ── ELW 504: numbered verses, no refrain ───────────────────────────


class TestNumberedNoRefrain:
    """ELW 504 — A Mighty Fortress Is Our God."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.lyrics = parse_rtf_lyrics(_read(ELW504_PATH), hymn_number="504")

    def test_title(self):
        assert self.lyrics.title == "A Mighty Fortress Is Our God"

    def test_number(self):
        assert self.lyrics.number == "ELW 504"

    def test_verse_count(self):
        assert len(self.lyrics.verses) == 4

    def test_no_refrain(self):
        assert self.lyrics.refrain == ""

    def test_verses_are_numbered(self):
        for i, v in enumerate(self.lyrics.verses, 1):
            assert v.startswith(f"{i}\t"), f"Verse {i} should start with '{i}\\t'"

    def test_copyright_has_symbol(self):
        assert "\u00a9" in self.lyrics.copyright

    def test_copyright_content(self):
        assert "Martin Luther" in self.lyrics.copyright
        assert "Augsburg Fortress" in self.lyrics.copyright

    def test_no_boilerplate(self):
        assert "Duplication" not in self.lyrics.copyright


# ── ELW 512: unnumbered, no refrain ────────────────────────────────


class TestUnnumbered:
    """ELW 512 — Lord, Let My Heart Be Good Soil."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.lyrics = parse_rtf_lyrics(_read(ELW512_PATH), hymn_number="512")

    def test_title(self):
        assert self.lyrics.title == "Lord, Let My Heart Be Good Soil"

    def test_number(self):
        assert self.lyrics.number == "ELW 512"

    def test_has_verses(self):
        assert len(self.lyrics.verses) >= 1

    def test_no_refrain(self):
        assert self.lyrics.refrain == ""

    def test_no_verse_numbers(self):
        for v in self.lyrics.verses:
            assert not v[0].isdigit(), f"Unnumbered hymn has digit prefix: {v[:20]}"

    def test_content(self):
        all_text = "\n".join(self.lyrics.verses)
        assert "Lord, let my heart be good soil" in all_text

    def test_copyright(self):
        assert "Handt Hanson" in self.lyrics.copyright
        assert "\u00a9" in self.lyrics.copyright


# ── Edge cases ──────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_raises(self):
        with pytest.raises(ParseError, match="empty"):
            parse_rtf_lyrics("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ParseError, match="empty"):
            parse_rtf_lyrics("   \n\t  ")

    def test_no_hymn_number(self):
        lyrics = parse_rtf_lyrics(_read(ELW512_PATH))
        assert lyrics.number == ""
        assert lyrics.title  # title should still parse

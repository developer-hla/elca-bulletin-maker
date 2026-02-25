"""Tests for Jinja2 template filters."""

from __future__ import annotations

from bulletin_maker.renderer.filters import creed_line, hymn_text, nl2br, setup_jinja_env


class TestNl2br:
    def test_converts_newlines(self):
        assert nl2br("line1\nline2") == "line1<br>\nline2"

    def test_empty_string(self):
        assert nl2br("") == ""

    def test_none_returns_empty(self):
        assert nl2br(None) == ""

    def test_no_newlines(self):
        assert nl2br("no breaks") == "no breaks"

    def test_multiple_newlines(self):
        result = nl2br("a\nb\nc")
        assert result.count("<br>") == 2


class TestHymnText:
    def test_tabs_to_emsp(self):
        assert "&emsp;" in hymn_text("1\tOh come")

    def test_newlines_to_br(self):
        assert "<br>" in hymn_text("line1\nline2")

    def test_combined(self):
        result = hymn_text("1\tOh come,\n\tLord Jesus")
        assert "&emsp;" in result
        assert "<br>" in result

    def test_empty(self):
        assert hymn_text("") == ""

    def test_none(self):
        assert hymn_text(None) == ""


class TestCreedLine:
    def test_indents_leading_spaces(self):
        result = creed_line("  indented line")
        assert result.startswith("&emsp;&emsp;")
        assert "indented line" in result

    def test_no_indent_for_normal(self):
        result = creed_line("normal line")
        assert not result.startswith("&emsp;")

    def test_mixed(self):
        result = creed_line("normal\n  indented")
        lines = result.split("<br>\n")
        assert not lines[0].startswith("&emsp;")
        assert lines[1].startswith("&emsp;&emsp;")

    def test_empty(self):
        assert creed_line("") == ""

    def test_none(self):
        assert creed_line(None) == ""


class TestSetupJinjaEnv:
    def test_env_has_filters(self):
        env = setup_jinja_env()
        assert "nl2br" in env.filters
        assert "hymn_text" in env.filters
        assert "creed_line" in env.filters

    def test_env_loads_templates(self):
        env = setup_jinja_env()
        # Should be able to list available templates
        templates = env.loader.list_templates()
        assert len(templates) > 0

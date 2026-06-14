"""Tests for Jinja2 template filters."""

from __future__ import annotations

from bulletin_maker.renderer.filters import (
    creed_line,
    hymn_text,
    nl2br,
    setup_jinja_env,
    terminal_amen,
    terminal_amen_html,
)


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


class TestTerminalAmen:
    def test_splits_terminal_amen_to_bold_new_line(self):
        result = terminal_amen("The Holy Spirit. Amen.")
        assert result == "The Holy Spirit.<br>\n<strong>Amen.</strong>"

    def test_can_skip_inner_bold_when_wrapped_by_template(self):
        result = terminal_amen("to your holy name. Amen.", bold_amen=False)
        assert result == "to your holy name.<br>\nAmen."

    def test_standalone_amen_is_bold_without_blank_line(self):
        assert terminal_amen("Amen.") == "<strong>Amen.</strong>"

    def test_multiline_text_keeps_breaks_and_bolds_amen(self):
        result = terminal_amen("Lord, have mercy.\nAmen.")
        assert result == "Lord, have mercy.<br>\n<strong>Amen.</strong>"

    def test_text_without_terminal_amen_is_unchanged(self):
        text = "Amen is not at the end of this sentence."
        assert terminal_amen(text) == text

    def test_empty(self):
        assert terminal_amen("") == ""

    def test_none(self):
        assert terminal_amen(None) == ""


class TestTerminalAmenHtml:
    def test_bolds_terminal_amen_before_closing_tag(self):
        result = terminal_amen_html("<p>Through Christ our Lord. Amen.</p>")
        assert result == "<p>Through Christ our Lord.<br>\n<strong>Amen.</strong></p>"

    def test_leaves_existing_strong_amen_unchanged(self):
        html = "<p>Through Christ our Lord.<br><strong>Amen.</strong></p>"
        assert terminal_amen_html(html) == html

    def test_text_without_terminal_amen_is_unchanged(self):
        html = "<p>Amen is not at the end of this sentence.</p>"
        assert terminal_amen_html(html) == html


class TestSetupJinjaEnv:
    def test_env_has_filters(self):
        env = setup_jinja_env()
        assert "nl2br" in env.filters
        assert "hymn_text" in env.filters
        assert "creed_line" in env.filters
        assert "terminal_amen" in env.filters
        assert "terminal_amen_html" in env.filters

    def test_env_loads_templates(self):
        env = setup_jinja_env()
        # Should be able to list available templates
        templates = env.loader.list_templates()
        assert len(templates) > 0

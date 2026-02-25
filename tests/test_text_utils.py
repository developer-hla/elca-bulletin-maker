"""Tests for text_utils — HTML parsing, psalm parsing, and utility functions."""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.text_utils import (
    strip_tags,
    preprocess_html,
    html_to_runs,
    split_runs_by_paragraph,
    parse_psalm_verses,
    extract_book_name,
    RunSpec,
)


class TestStripTags:

    def test_removes_simple_tags(self):
        assert strip_tags("<p>Hello</p>") == "Hello"

    def test_removes_nested_tags(self):
        assert strip_tags("<div><strong>Bold</strong> text</div>") == "Bold text"

    def test_strips_whitespace(self):
        assert strip_tags("  <p>Hi</p>  ") == "Hi"

    def test_empty_string(self):
        assert strip_tags("") == ""

    def test_no_tags(self):
        assert strip_tags("plain text") == "plain text"


class TestPreprocessHtml:

    def test_strips_chant_pointing(self):
        html = 'word<sup class="point">|</sup>end'
        assert "|" not in preprocess_html(html)

    def test_preserves_small_caps_as_sc(self):
        html = '<span style="font-variant: small-caps">LORD</span>'
        result = preprocess_html(html)
        assert "<sc>LORD</sc>" in result

    def test_rejoins_hyphenated_words(self):
        assert "imputes" in preprocess_html("im- putes")

    def test_replaces_unicode_whitespace(self):
        result = preprocess_html("a\u2003b\u00a0c")
        assert "\u2003" not in result
        assert "\u00a0" not in result


class TestHtmlToRuns:

    def test_bold_text(self):
        runs = html_to_runs("<strong>Bold</strong> normal")
        bold_runs = [r for r in runs if r.bold]
        assert len(bold_runs) == 1
        assert bold_runs[0].text == "Bold"

    def test_italic_text(self):
        runs = html_to_runs("<em>Italic</em>")
        italic_runs = [r for r in runs if r.italic]
        assert len(italic_runs) == 1

    def test_paragraph_breaks(self):
        runs = html_to_runs("<p>One</p><p>Two</p>")
        groups = split_runs_by_paragraph(runs)
        assert len(groups) == 2

    def test_superscript_verses(self):
        runs = html_to_runs("<sup>1</sup>In the beginning", superscript_verses=True)
        sup_runs = [r for r in runs if r.superscript]
        assert len(sup_runs) >= 1

    def test_superscript_disabled(self):
        runs = html_to_runs("<sup>1</sup>Text", superscript_verses=False)
        sup_runs = [r for r in runs if r.superscript]
        assert len(sup_runs) == 0


class TestSplitRunsByParagraph:

    def test_single_paragraph(self):
        runs = [RunSpec(text="hello")]
        groups = split_runs_by_paragraph(runs)
        assert len(groups) == 1

    def test_multiple_paragraphs(self):
        runs = [
            RunSpec(text="first"),
            RunSpec(text="\n\n"),
            RunSpec(text="second"),
        ]
        groups = split_runs_by_paragraph(runs)
        assert len(groups) == 2
        assert groups[0][0].text == "first"
        assert groups[1][0].text == "second"

    def test_empty_input(self):
        assert split_runs_by_paragraph([]) == []


class TestParsePsalmVerses:

    def test_basic_psalm(self):
        html = '<div><sup>1</sup>Happy are they<br/><sup>2</sup>whose sins are forgiven</div>'
        verses = parse_psalm_verses(html)
        assert len(verses) >= 2
        assert verses[0].verse_num == "1"
        assert not verses[0].continuation

    def test_bold_congregation_verses(self):
        html = '<div><sup>1</sup>Leader line<br/><strong><sup>2</sup>Congregation line</strong></div>'
        verses = parse_psalm_verses(html)
        bold_verses = [v for v in verses if v.bold]
        assert len(bold_verses) >= 1

    def test_continuation_lines(self):
        html = '<div><sup>1</sup>First line<br/>continuation line</div>'
        verses = parse_psalm_verses(html)
        continuations = [v for v in verses if v.continuation]
        assert len(continuations) >= 1


class TestExtractBookName:

    @pytest.mark.parametrize("citation,expected", [
        ("Genesis 2:15-17; 3:1-7", "Genesis"),
        ("1 Corinthians 10:1-13", "1 Corinthians"),
        ("Psalm 32", "Psalm"),
        ("Matthew 4:1-11", "Matthew"),
        ("Song of Solomon 2:8-13", "Song of Solomon"),
    ])
    def test_extracts_book(self, citation, expected):
        assert extract_book_name(citation) == expected

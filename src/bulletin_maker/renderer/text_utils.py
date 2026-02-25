"""Pure text/HTML utilities for processing S&S content.

Provides HTML→run conversion, psalm parsing, tag stripping,
HTML preprocessing, and book name extraction.  No rendering
library dependencies — used by both the HTML renderer and tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


# ── HTML utilities ────────────────────────────────────────────────────

def strip_tags(html: str) -> str:
    """Remove all HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", html).strip()


def preprocess_html(html: str) -> str:
    """Clean up S&S HTML quirks before conversion."""
    # Strip chant pointing markers
    html = re.sub(r'<sup[^>]*class="point"[^>]*>\|</sup>', "", html)
    # Strip refrain markers
    html = re.sub(r'<span[^>]*class="refrain"[^>]*>[^<]*</span>', "", html)
    # Preserve small-caps LORD as <sc> tag
    html = re.sub(
        r'<span[^>]*font-variant:\s*small-caps[^>]*>(.*?)</span>',
        r'<sc>\1</sc>',
        html,
    )
    # Rejoin chant-hyphenated words (e.g. "im- putes" -> "imputes")
    html = re.sub(r'(\w)-\s+(\w)', r'\1\2', html)
    # Replace unicode whitespace
    html = html.replace("\u2003", " ").replace("\u00a0", " ")
    return html


def extract_book_name(citation: str) -> str:
    """Extract book name from citation like 'Genesis 2:15-17; 3:1-7' -> 'Genesis'."""
    match = re.match(r'^(.*?)\s+\d', citation)
    return match.group(1).strip() if match else citation


# ── Run specifications ───────────────────────────────────────────────

@dataclass
class RunSpec:
    """Describes a single formatted run of text."""
    text: str
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    small_caps: bool = False
    size_pt: float | None = None  # None = inherit from style


# Sentinel values for paragraph splitting
_PARA_BREAK = "\n\n"
_LINE_BREAK = "\n"


# ── HTML → RunSpec converter ─────────────────────────────────────────

class _HTMLToRunsParser(HTMLParser):
    """Converts S&S HTML into a flat list of RunSpec objects."""

    def __init__(self, superscript_verses: bool = True):
        super().__init__()
        self.runs: list[RunSpec] = []
        self.superscript_verses = superscript_verses
        self._bold = False
        self._italic = False
        self._sup = False
        self._small_caps = False
        self._in_verse_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in ("b", "strong"):
            self._bold = True
        elif tag in ("i", "em"):
            self._italic = True
        elif tag == "sup":
            attr_dict = dict(attrs)
            if "point" in (attr_dict.get("class") or ""):
                return
            self._sup = True
        elif tag == "sc":
            self._small_caps = True
        elif tag == "br":
            self.runs.append(RunSpec(text=_LINE_BREAK))
        elif tag == "span":
            attr_dict = dict(attrs)
            style = attr_dict.get("style", "")
            if "white-space" in style and "nowrap" in style:
                self._in_verse_span = True

    def handle_endtag(self, tag: str):
        if tag in ("b", "strong"):
            self._bold = False
        elif tag in ("i", "em"):
            self._italic = False
        elif tag == "sup":
            self._sup = False
        elif tag == "sc":
            self._small_caps = False
        elif tag == "p":
            self.runs.append(RunSpec(text=_PARA_BREAK))
        elif tag == "span":
            self._in_verse_span = False

    def handle_data(self, data: str):
        if not data:
            return
        text = re.sub(r'[ \t]+', ' ', data)
        if not text.strip():
            if text == " " and self.runs and self.runs[-1].text not in (_PARA_BREAK, _LINE_BREAK):
                self.runs.append(RunSpec(text=" "))
            return
        self.runs.append(RunSpec(
            text=text,
            bold=self._bold,
            italic=self._italic,
            superscript=self._sup if self.superscript_verses else False,
            small_caps=self._small_caps,
            size_pt=None,
        ))


def html_to_runs(html: str, superscript_verses: bool = True) -> list[RunSpec]:
    """Convert S&S HTML to a flat list of RunSpec objects.

    Line breaks become RunSpec(text="\\n"), paragraph breaks become
    RunSpec(text="\\n\\n").  Use split_runs_by_paragraph() to group
    them into per-paragraph lists.
    """
    html = preprocess_html(html)
    parser = _HTMLToRunsParser(superscript_verses=superscript_verses)
    parser.feed(html)

    runs = parser.runs
    while runs and runs[0].text.strip() == "":
        runs.pop(0)
    while runs and runs[-1].text.strip() == "":
        runs.pop()

    return runs


def split_runs_by_paragraph(runs: list[RunSpec]) -> list[list[RunSpec]]:
    """Split a flat run list at paragraph-break sentinels into groups."""
    groups: list[list[RunSpec]] = [[]]
    for run in runs:
        if run.text == _PARA_BREAK:
            if groups[-1]:
                groups.append([])
        else:
            groups[-1].append(run)
    if groups and not groups[-1]:
        groups.pop()
    return groups


# ── Psalm parsing ────────────────────────────────────────────────────

@dataclass
class PsalmVerse:
    """One verse or continuation line of a psalm."""
    verse_num: str | None  # None for continuation lines
    text: str
    bold: bool  # True = congregation (even-numbered)
    continuation: bool  # True = indented continuation


def parse_psalm_verses(html: str) -> list[PsalmVerse]:
    """Parse psalm HTML into a list of PsalmVerse objects."""
    html = preprocess_html(html)

    # Remove outer wrapping div
    html = re.sub(r'^<div[^>]*>', '', html)
    html = re.sub(r'</div>\s*$', '', html)

    lines = re.split(r'<br\s*/?>', html)
    verses: list[PsalmVerse] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        verse_match = re.search(r'<sup>(\d+)</sup>', line)
        is_continuation = not verse_match
        is_bold = bool(re.search(r'<strong>', line))

        clean = re.sub(r'<[^>]+>', '', line)
        clean = re.sub(r'(\w)-\s+(\w)', r'\1\2', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if not clean:
            continue

        if is_continuation:
            verses.append(PsalmVerse(
                verse_num=None,
                text=clean,
                bold=is_bold,
                continuation=True,
            ))
        else:
            verse_num = verse_match.group(1)
            clean = re.sub(r'^\s*' + re.escape(verse_num) + r'\s*', '', clean)
            verses.append(PsalmVerse(
                verse_num=verse_num,
                text=clean,
                bold=is_bold,
                continuation=False,
            ))

    return verses


# ── Psalm verse grouping ────────────────────────────────────────────

@dataclass
class PsalmVerseGroup:
    """A psalm verse with its continuation lines bundled together."""
    verse_num: str
    text: str
    bold: bool
    continuation: bool = False
    continuations: list[PsalmVerseGroup] = field(default_factory=list)


def group_psalm_verses(html: str) -> list[PsalmVerseGroup]:
    """Parse psalm HTML and group continuation lines with their parent verse."""
    raw_verses = parse_psalm_verses(html)
    groups: list[PsalmVerseGroup] = []

    for v in raw_verses:
        if v.continuation:
            if groups:
                groups[-1].continuations.append(
                    PsalmVerseGroup(
                        verse_num=v.verse_num or "",
                        text=v.text,
                        bold=v.bold,
                        continuation=True,
                    )
                )
        else:
            groups.append(PsalmVerseGroup(
                verse_num=v.verse_num or "",
                text=v.text,
                bold=v.bold,
            ))

    return groups

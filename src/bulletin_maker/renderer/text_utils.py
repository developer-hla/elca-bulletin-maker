"""Pure text/HTML utilities for processing S&S content.

Provides HTML→run conversion, psalm parsing, tag stripping,
HTML preprocessing, and book name extraction.  No rendering
library dependencies — used by both the HTML renderer and tests.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser


class DialogRole(Enum):
    """Roles in call-and-response liturgical dialog."""
    PASTOR = "P"
    CONGREGATION = "C"
    INSTRUCTION = "instruction"
    NONE = ""


# ── HTML utilities ────────────────────────────────────────────────────

def strip_tags(html: str) -> str:
    """Remove all HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", html).strip()


def clean_sns_html(html: str) -> str:
    """Strip S&S HTML to plain text for liturgical texts.

    Removes tags, decodes HTML entities, and normalizes whitespace.
    Used for offering prayer, prayer after communion, blessing, dismissal.
    """
    if not html:
        return ""
    # Replace <br> and </p><p> with newlines before stripping tags
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    # Normalize whitespace within lines but preserve newlines
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(line for line in lines if line)
    return text.strip()


def _clean_line(html_fragment: str) -> str:
    """Strip tags, decode entities, and normalise whitespace."""
    text = re.sub(r"<[^>]+>", "", html_fragment)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _detect_role_prefix(text: str) -> tuple[DialogRole | None, str]:
    """Check for an explicit P:/C:/Pastor:/Congregation: prefix.

    Returns (role, remaining_text) if found, else (None, original_text).
    """
    m = re.match(r"^(P|C|Pastor|Congregation)\s*:\s*", text)
    if not m:
        return None, text
    raw = m.group(1)
    if raw in ("C", "Congregation"):
        return DialogRole.CONGREGATION, text[m.end():].strip()
    return DialogRole.PASTOR, text[m.end():].strip()


def _classify_line(line_html: str) -> DialogRole:
    """Classify a single inner-div/line by its HTML formatting.

    - Entirely wrapped in <strong>/<b> → Congregation
    - Entirely wrapped in <em>/<i> → Instruction
    - Otherwise → Pastor
    """
    s = line_html.strip()
    # Bold-only line
    if re.match(r"^<(?:strong|b)\b[^>]*>(.*)</(?:strong|b)>\s*$", s, re.DOTALL):
        return DialogRole.CONGREGATION
    # Italic-only line
    if re.match(r"^<(?:em|i)\b[^>]*>(.*)</(?:em|i)>\s*$", s, re.DOTALL):
        return DialogRole.INSTRUCTION
    return DialogRole.PASTOR


def _process_body_lines(lines: list[str]) -> list[tuple[DialogRole, str]]:
    """Group consecutive same-role lines from a body block into entries."""
    entries: list[tuple[DialogRole, str]] = []
    cur_role: DialogRole | None = None
    cur_parts: list[str] = []

    for raw_line in lines:
        text = _clean_line(raw_line)
        if not text:
            continue
        role, text = _detect_role_prefix(text) or (None, text)
        if role is None:
            role = _classify_line(raw_line)

        if role == cur_role:
            cur_parts.append(text)
        else:
            if cur_role is not None and cur_parts:
                entries.append((cur_role, " ".join(cur_parts)))
            cur_role = role
            cur_parts = [text]

    if cur_role is not None and cur_parts:
        entries.append((cur_role, " ".join(cur_parts)))

    return entries


def parse_dialog_html(html: str) -> list[tuple[DialogRole, str]]:
    """Parse S&S dialog HTML into (DialogRole, text) tuples.

    Used for confession and dismissal call-and-response texts.
    The returned format matches what templates expect:
      - role: DialogRole enum member
      - text: the paragraph text

    S&S uses ``<div class="rubric">`` for instructions and
    ``<div class="body">`` for spoken content, with ``<strong>``
    marking congregation responses.  When those classes are absent
    the parser falls back to bold/italic heuristics and explicit
    ``P:`` / ``C:`` prefixes.
    """
    if not html:
        return []

    # S&S wraps content in class="rubric" and class="body" divs.
    # We iterate over top-level blocks and classify each one.
    has_sns_classes = 'class="rubric"' in html or 'class="body"' in html

    if has_sns_classes:
        return _parse_sns_dialog(html)

    # Fallback: split on <p> tags and use heuristics
    return _parse_generic_dialog(html)


def _extract_sns_blocks(html: str) -> list[tuple[str, str]]:
    """Extract (class, inner_html) for rubric/body div blocks.

    Handles nested ``<div>`` tags by tracking depth.
    """
    blocks: list[tuple[str, str]] = []
    opener = re.compile(r'<div\s+class="(rubric|body)"[^>]*>')

    pos = 0
    while pos < len(html):
        m = opener.search(html, pos)
        if not m:
            break
        block_class = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(html) and depth > 0:
            open_m = re.search(r"<div[\s>]", html[i:])
            close_m = re.search(r"</div>", html[i:])
            if close_m is None:
                break
            if open_m and open_m.start() < close_m.start():
                depth += 1
                i += open_m.start() + 4
            else:
                depth -= 1
                if depth == 0:
                    blocks.append((block_class, html[start:i + close_m.start()].strip()))
                i += close_m.end()
        pos = i

    return blocks


def _parse_sns_dialog(html: str) -> list[tuple[DialogRole, str]]:
    """Parse S&S-structured dialog with rubric/body class divs."""
    entries: list[tuple[DialogRole, str]] = []

    for block_class, inner in _extract_sns_blocks(html):
        if block_class == "rubric":
            text = _clean_line(inner)
            if text:
                entries.append((DialogRole.INSTRUCTION, text))
        else:
            # Body block — split into inner <div> lines
            lines = re.findall(r"<div>(.*?)</div>", inner, re.DOTALL)
            if not lines:
                # No inner divs — treat whole block as one chunk
                text = _clean_line(inner)
                if text:
                    role, text = _detect_role_prefix(text)
                    if role is None:
                        role = _classify_line(inner)
                    entries.append((role, text))
            else:
                entries.extend(_process_body_lines(lines))

    return entries


def _parse_generic_dialog(html: str) -> list[tuple[DialogRole, str]]:
    """Fallback parser: split on <p> tags, detect roles by formatting."""
    entries: list[tuple[DialogRole, str]] = []
    paragraphs = re.split(r"</?p[^>]*>", html)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        text = _clean_line(para)
        if not text:
            continue

        role, text = _detect_role_prefix(text)
        if role is None:
            role = _classify_line(para)

        entries.append((role, text))

    return entries


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

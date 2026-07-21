"""Parse a whole Sundays & Seasons service document into ordered segments.

Occasion services (Funeral, Marriage) are served by ``/File/Preview`` as a
single human-readable script — ``<div class="rubric">`` instructions,
``<div class="body">`` spoken/prayed text, ``<div class="hymnal">`` hymn
references, and ``<strong>OPTION A:</strong>`` alternative markers — with no
semantic section headings.  This module segments that script into an ordered
list of typed :class:`ServiceSegment` s so the renderer can lay it out in the
house style and interpolate per-service variables, WITHOUT the copyrighted
text ever being stored in the app: the parser runs at render time on content
pulled live from the church's own licensed S&S account.

Structural only: this module keys off markup (div class, ``OPTION`` markers),
never off the liturgical prose.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional

SEGMENT_RUBRIC = "rubric"
SEGMENT_TEXT = "text"
SEGMENT_HYMN = "hymn"
SEGMENT_OPTIONS = "options"

_CONTENT_CLASS = {
    "rubric": SEGMENT_RUBRIC,
    "body": SEGMENT_TEXT,
    "hymnal": SEGMENT_HYMN,
}

_OPTION_RE = re.compile(r"^\s*OPTION\s+([A-Z0-9]+)\s*:?\s*(.*)$", re.IGNORECASE | re.DOTALL)


@dataclass
class ServiceOption:
    """One alternative within a choice (e.g. Greeting Option A vs. B).

    ``heading`` is the short incipit S&S prints on the option marker line;
    ``body`` is the option's content (S&S renders it in a ``hymnal``-classed
    div immediately after the marker).
    """

    label: str
    heading: str = ""
    body: str = ""


@dataclass
class ServiceSegment:
    """One ordered piece of the service script."""

    kind: str
    text: str = ""
    options: List[ServiceOption] = field(default_factory=list)


class _Tokenizer(HTMLParser):
    """Flatten the document to ordered (kind, text) tokens.

    ``kind`` is one of the content-div kinds, ``"option"`` (a standalone
    ``<strong>OPTION x:</strong>`` marker), or ``"emphasis"`` (any other
    top-level ``<strong>``).  Text inside a content div — including nested
    emphasis — accumulates into that div's single token, so nesting never
    splits a body.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tokens: List[tuple] = []
        self._div_depth = 0
        self._block_kind: Optional[str] = None
        self._block_open_depth = 0
        self._strong: Optional[str] = None
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self._div_depth += 1
            cls = dict(attrs).get("class", "")
            kind = _CONTENT_CLASS.get(cls)
            if kind and self._block_kind is None:
                self._block_kind = kind
                self._block_open_depth = self._div_depth
                self._buf = []
            return
        if tag in ("strong", "b") and self._block_kind is None:
            self._strong = ""
            self._buf = []
            return
        if tag == "br":
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag == "div":
            if self._block_kind is not None and self._div_depth == self._block_open_depth:
                self._emit(self._block_kind)
                self._block_kind = None
            self._div_depth = max(0, self._div_depth - 1)
            return
        if tag in ("strong", "b") and self._strong is not None:
            self._emit_strong()

    def handle_data(self, data):
        if self._block_kind is not None or self._strong is not None:
            self._buf.append(data)

    def _text(self) -> str:
        return " ".join(html.unescape("".join(self._buf)).split())

    def _emit(self, kind: str) -> None:
        text = self._text()
        if text:
            if kind == SEGMENT_RUBRIC and _OPTION_RE.match(text):
                self.tokens.append(("option", text))
            else:
                self.tokens.append((kind, text))
        self._buf = []

    def _emit_strong(self) -> None:
        text = self._text()
        kind = "option" if _OPTION_RE.match(text) else "emphasis"
        if text:
            self.tokens.append((kind, text))
        self._strong = None
        self._buf = []


def _group(tokens: List[tuple]) -> List[ServiceSegment]:
    segments: List[ServiceSegment] = []
    i = 0
    n = len(tokens)
    while i < n:
        kind, text = tokens[i]
        if kind == "option":
            group, i = _consume_options(tokens, i)
            segments.append(group)
            continue
        if kind == "emphasis":
            segments.append(ServiceSegment(kind=SEGMENT_TEXT, text=text))
        elif kind == SEGMENT_HYMN:
            segments.append(ServiceSegment(kind=SEGMENT_HYMN, text=text))
        else:
            segments.append(ServiceSegment(kind=kind, text=text))
        i += 1
    return segments


def _label_ordinal(label: str) -> int:
    """Sort key for an option label, so a reset (A after C) ends the group."""
    return ord(label[0].upper()) if label[:1].isalpha() else -1


def _consume_options(tokens: List[tuple], start: int) -> tuple:
    options: List[ServiceOption] = []
    last_ordinal = -1
    i = start
    n = len(tokens)
    while i < n and tokens[i][0] == "option":
        match = _OPTION_RE.match(tokens[i][1])
        ordinal = _label_ordinal(match.group(1))
        if options and ordinal <= last_ordinal:
            break  # label reset (e.g. a new A after C) -> a distinct choice
        last_ordinal = ordinal
        option = ServiceOption(label=match.group(1), heading=match.group(2).strip())
        i += 1
        parts: List[str] = []
        while i < n and tokens[i][0] in (SEGMENT_HYMN, SEGMENT_TEXT):
            parts.append(tokens[i][1])
            i += 1
        option.body = "\n".join(parts)
        options.append(option)
    return ServiceSegment(kind=SEGMENT_OPTIONS, options=options), i


def parse_service(preview_html: str) -> List[ServiceSegment]:
    """Segment a ``/File/Preview`` service document into ordered pieces."""
    tokenizer = _Tokenizer()
    tokenizer.feed(preview_html)
    return _group(tokenizer.tokens)

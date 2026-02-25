"""RTF parser for Sundays & Seasons hymn lyrics.

S&S returns hymn words as RTF inside a ZIP from POST /File/Download.
This module extracts structured HymnLyrics from that RTF content.
"""

from __future__ import annotations

import re

from bulletin_maker.exceptions import ParseError
from bulletin_maker.sns.models import HymnLyrics


def parse_rtf_lyrics(
    rtf_content: str,
    hymn_number: str = "",
    collection: str = "ELW",
) -> HymnLyrics:
    """Parse S&S RTF hymn content into a HymnLyrics object.

    Args:
        rtf_content: Raw RTF string from S&S ZIP download.
        hymn_number: Hymn number (e.g. "335") for the number field.
        collection: Hymnal collection prefix (default "ELW").

    Returns:
        HymnLyrics with title, verses, optional refrain, and copyright.

    Raises:
        ParseError: If rtf_content is empty or too large.
    """
    if not rtf_content or not rtf_content.strip():
        raise ParseError("RTF content is empty")

    MAX_RTF_SIZE = 500_000  # 500 KB — hymn RTFs are typically <50 KB
    if len(rtf_content) > MAX_RTF_SIZE:
        raise ParseError(f"RTF content too large ({len(rtf_content)} bytes)")

    title = _extract_title(rtf_content)
    has_refrain = bool(re.search(r"\{\\i[^}]*?Refrain", rtf_content))

    text = _strip_rtf(rtf_content)
    body, copyright_text = _split_body_copyright(text, title)
    verses, refrain = _parse_stanzas(body, has_refrain)

    number = f"{collection} {hymn_number}" if hymn_number else ""

    return HymnLyrics(
        number=number,
        title=title,
        verses=verses,
        refrain=refrain,
        copyright=copyright_text,
    )


# ── Internal helpers ────────────────────────────────────────────────


def _extract_title(rtf: str) -> str:
    """Extract title from RTF ``\\title`` metadata."""
    m = re.search(r"\{\\title\s+([^}]+)\}", rtf)
    return m.group(1).strip() if m else ""


def _strip_rtf(rtf: str) -> str:
    """Walk RTF char-by-char and extract plain text.

    Converts ``\\par`` to newline, ``\\tab`` to tab, decodes hex escapes,
    and skips all RTF control words and ``{\\*...}`` destination groups.
    """
    # Skip header (font table, stylesheet, info, etc.) — body starts
    # at the first \pard command.
    body_match = re.search(r"\\pard\b", rtf)
    if body_match:
        rtf = rtf[body_match.start() :]

    # Pre-decode \'XY hex escapes (Windows-1252 code page)
    def _hex_replace(m: re.Match) -> str:
        code = int(m.group(1), 16)
        cp1252 = {
            0x92: "\u2019",  # right single quote
            0x93: "\u201c",  # left double quote
            0x94: "\u201d",  # right double quote
            0x96: "\u2013",  # en dash
            0xA9: "\u00a9",  # copyright symbol
        }
        if code in cp1252:
            return cp1252[code]
        if code > 0x10FFFF:
            return ""  # invalid Unicode code point
        return chr(code)

    rtf = re.sub(r"\\'([0-9a-fA-F]{2})", _hex_replace, rtf)

    result: list[str] = []
    i = 0
    n = len(rtf)
    depth = 0
    skip_depth = -1  # brace depth where {\* started

    while i < n:
        ch = rtf[i]

        if ch == "{":
            depth += 1
            if i + 2 < n and rtf[i + 1] == "\\" and rtf[i + 2] == "*":
                skip_depth = depth
            i += 1
            continue

        if ch == "}":
            if depth == skip_depth:
                skip_depth = -1
            depth -= 1
            i += 1
            continue

        if skip_depth > 0:
            i += 1
            continue

        if ch == "\\":
            if i + 1 < n:
                nch = rtf[i + 1]
                if nch in "\\{}":
                    result.append(nch)
                    i += 2
                    continue
                if nch in "\r\n":
                    i += 2
                    continue
                # Control word
                m = re.match(r"([a-z]+)(-?\d+)? ?", rtf[i + 1 :])
                if m:
                    word = m.group(1)
                    i += 1 + m.end()
                    if word == "par":
                        result.append("\n")
                    elif word == "tab":
                        result.append("\t")
                    elif word == "line":
                        result.append("\n")
                    continue
            i += 1
            continue

        if ch in "\r\n":
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _split_body_copyright(text: str, title: str) -> tuple[str, str]:
    """Split extracted text into hymn body and copyright footer.

    Copyright starts at the first line beginning with ``Text:``.
    The "Duplication in any form prohibited..." boilerplate is stripped.
    """
    lines = text.split("\n")

    # Skip past the title line at the top of the extracted text.
    # Normalize whitespace for comparison since RTF extraction can
    # introduce extra spaces vs. the \title metadata.
    body_start = 0
    if title:
        norm_title = " ".join(title.split()).lower()
        for i, line in enumerate(lines):
            norm_line = " ".join(line.split()).lower()
            if norm_title in norm_line:
                body_start = i + 1
                break

    # Find where copyright begins
    copyright_start = len(lines)
    for i in range(body_start, len(lines)):
        if lines[i].strip().startswith("Text:"):
            copyright_start = i
            break

    body = "\n".join(lines[body_start:copyright_start]).strip()

    copyright_lines = []
    for line in lines[copyright_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if "Duplication in any form prohibited" in stripped:
            continue
        copyright_lines.append(stripped)
    copyright_text = "\n".join(copyright_lines)

    return body, copyright_text


def _parse_stanzas(body: str, has_refrain: bool) -> tuple[list[str], str]:
    """Parse body text into verse list and optional refrain string.

    Verse format matches the existing ``HymnLyrics`` convention:
    numbered verses keep ``N\\tline text``; continuation lines keep
    leading tabs.  Refrain hymns keep ``"  Refrain"`` at the end of
    verses 2+ (matching the manual format in ``generate_test.py``).
    """
    # Split into stanzas on blank lines
    raw_stanzas = re.split(r"\n\s*\n", body.strip())
    raw_stanzas = [s.strip() for s in raw_stanzas if s.strip()]

    verses: list[str] = []
    refrain = ""

    for stanza in raw_stanzas:
        lines = stanza.split("\n")
        first_stripped = lines[0].strip()

        # Detect the refrain stanza (label "Refrain" on its own line)
        if has_refrain and first_stripped == "Refrain":
            ref_lines = [ln.strip() for ln in lines[1:] if ln.strip()]
            refrain = "\n".join(ref_lines)
            continue

        # Build verse text: keep tab structure, collapse RTF artifacts
        verse_lines: list[str] = []
        for line in lines:
            cleaned = line.rstrip()
            if not cleaned and not verse_lines:
                continue  # skip leading blanks
            verse_lines.append(cleaned)

        # Remove trailing blank lines
        while verse_lines and not verse_lines[-1].strip():
            verse_lines.pop()

        verse_text = "\n".join(verse_lines)
        if verse_text.strip():
            verses.append(verse_text)

    return verses, refrain

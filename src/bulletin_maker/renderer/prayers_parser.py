"""Parse structured S&S prayers HTML into template-ready data."""

from __future__ import annotations

import re

from bulletin_maker.renderer.static_text import DEFAULT_PRAYERS_RESPONSE
from bulletin_maker.renderer.text_utils import preprocess_html, strip_tags


def _parse_sections(html: str) -> list[tuple[str, str]]:
    """Extract (section_type, content) pairs from prayers HTML divs."""
    sections = []
    pos = 0
    outer_match = re.match(r'\s*<div>\s*', html)
    if outer_match:
        pos = outer_match.end()

    while pos < len(html):
        section_match = re.search(r'<div class="(rubric|body)">', html[pos:])
        if not section_match:
            break
        section_type = section_match.group(1)
        section_start = pos + section_match.end()
        depth = 1
        i = section_start
        while i < len(html) and depth > 0:
            open_match = re.search(r'<div[^>]*>', html[i:])
            close_match = re.search(r'</div>', html[i:])
            if close_match is None:
                break
            open_pos = (i + open_match.start()) if open_match else len(html)
            close_pos = i + close_match.start()
            if open_pos < close_pos:
                depth += 1
                i = open_pos + len(open_match.group(0))
            else:
                depth -= 1
                if depth == 0:
                    sections.append((section_type, html[section_start:close_pos]))
                    pos = close_pos + len("</div>")
                    break
                i = close_pos + len("</div>")
        else:
            sections.append((section_type, html[section_start:]))
            break

    return sections


def _parse_petitions(inner_divs: list[str], result: dict) -> None:
    """Parse petition/response pairs from inner div contents."""
    i = 0
    while i < len(inner_divs):
        petition_text = strip_tags(inner_divs[i])
        response_text = ""
        if i + 1 < len(inner_divs) and "<strong>" in inner_divs[i + 1]:
            response_text = strip_tags(inner_divs[i + 1])
            i += 2
        else:
            i += 1
        if not petition_text:
            continue
        if response_text.lower().strip(".") == "amen":
            result["closing_text"] = petition_text
            result["closing_response"] = response_text
        else:
            result["petitions"].append({
                "text": petition_text,
                "response": response_text,
            })


def parse_prayers_html(prayers_html: str) -> dict:
    """Parse structured S&S prayers HTML into intro, petitions, and closing."""
    html = preprocess_html(prayers_html)
    result = {
        "intro": "",
        "brief_silence": False,
        "petitions": [],
        "closing_text": "",
        "closing_response": "",
    }

    sections = _parse_sections(html)
    body_index = 0

    for sec_type, content in sections:
        if sec_type == "rubric":
            text = strip_tags(content)
            if "brief silence" in text.lower():
                result["brief_silence"] = True
            continue
        inner_divs = re.findall(r'<div>(.*?)</div>', content, re.DOTALL)
        if not inner_divs:
            text = strip_tags(content)
            if body_index == 0:
                result["intro"] = text
            else:
                result["closing_text"] = text
        else:
            _parse_petitions(inner_divs, result)
        body_index += 1

    return result


def parse_prayers_response(prayers_html: str) -> str:
    """Extract congregation response phrase from prayers HTML."""
    strong_matches = re.findall(r'<strong>(.*?)</strong>', prayers_html, re.DOTALL)
    for s in strong_matches:
        text = strip_tags(s).strip()
        if text and text.lower() != "amen.":
            return text
    return DEFAULT_PRAYERS_RESPONSE

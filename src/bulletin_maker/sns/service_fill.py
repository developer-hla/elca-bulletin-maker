"""Layer-2 runtime fill: map a canonical rite section to its S&S wording.

A funeral / marriage rite is authored as a SKELETON of empty keyed
``canonical_slot`` sections (see ``core/library/elw_funeral.json`` /
``elw_marriage.json``).  At render time this module fills each named section
with the church's OWN licensed Sundays & Seasons wording, so the church gets
S&S's canonical text arranged in THEIR custom order (they reorder the slot
blocks in the rite editor).

No liturgical prose is ever stored in the app.  The whole-service document is
pulled live from the church's S&S account through ``ContentContext.sns_fetch_raw``
(the RAW ``/File/Preview`` markup the parser needs) and parsed by
:func:`bulletin_maker.sns.service_parser.parse_service` into
ordered typed segments.  :data:`SECTION_MAP` — derived by the orchestrator from
the real S&S documents — records, per section_key, the atom-code of the
whole-service rite, the ORDINAL INDEX of the segment that holds the section,
and the segment KIND expected there.  The index/kind pair is a structural
confidence check: if the segment at that index is missing or the wrong kind,
the S&S document has drifted from the mapping and the fill fails loudly
(``logger.warning`` + ``None``), so the caller renders the entitlement
placeholder rather than the wrong text.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from bulletin_maker.core.content_source import ContentContext
from bulletin_maker.sns.service_parser import (
    SEGMENT_OPTIONS,
    SEGMENT_TEXT,
    ServiceSegment,
    parse_service,
)

logger = logging.getLogger(__name__)

FUNERAL_ATOM = "elw_funeralNoCommunion"
MARRIAGE_ATOM = "elw_marriageNoCommunion"

# section_key -> (whole-service atom-code, segment index, expected segment kind).
# Indices/kinds are the orchestrator-derived structural map into the output of
# ``parse_service`` for each rite's live S&S document; they are NOT liturgical
# content.  An "options" section's text is its default option (option A) body;
# a "text" section's text is the segment's text.
SECTION_MAP: Dict[str, Tuple[str, int, str]] = {
    "funeral_greeting": (FUNERAL_ATOM, 2, SEGMENT_OPTIONS),
    "funeral_thanksgiving_for_baptism": (FUNERAL_ATOM, 4, SEGMENT_OPTIONS),
    "funeral_prayer_of_the_day": (FUNERAL_ATOM, 14, SEGMENT_OPTIONS),
    "funeral_apostles_creed": (FUNERAL_ATOM, 19, SEGMENT_TEXT),
    "funeral_commendation": (FUNERAL_ATOM, 30, SEGMENT_TEXT),
    "marriage_greeting": (MARRIAGE_ATOM, 3, SEGMENT_TEXT),
    "marriage_introduction": (MARRIAGE_ATOM, 5, SEGMENT_OPTIONS),
    "marriage_declaration_of_intention": (MARRIAGE_ATOM, 7, SEGMENT_OPTIONS),
    "marriage_prayer": (MARRIAGE_ATOM, 15, SEGMENT_OPTIONS),
    "marriage_vows": (MARRIAGE_ATOM, 23, SEGMENT_OPTIONS),
    "marriage_giving_of_rings": (MARRIAGE_ATOM, 28, SEGMENT_OPTIONS),
    "marriage_acclamation": (MARRIAGE_ATOM, 30, SEGMENT_TEXT),
    "marriage_blessing_of_couple": (MARRIAGE_ATOM, 33, SEGMENT_OPTIONS),
}

# S&S lowercase placeholder tokens: the deceased is ``name``; the couple is
# ``name and name``.  See :func:`_interpolate_names` for the (best-effort,
# documented) substitution heuristic.
_COUPLE_PLACEHOLDER_RE = re.compile(r"\bname and name\b", re.IGNORECASE)
_FUNERAL_NAME_TOKEN = re.compile(r"\bname\b(?!\s+of\b)")


@lru_cache(maxsize=64)
def _parse_cached(atom_code: str, document_html: str) -> Tuple[ServiceSegment, ...]:
    """Memoize the parse of one pulled whole-service document.

    Keyed on the document text itself, so every section of one rite parses the
    document once per render, and no church's content can be served for another
    (a different church yields different text -> a different cache entry).
    """
    return tuple(parse_service(document_html))


def _segment_at(section_key: str, context: ContentContext) -> Optional[ServiceSegment]:
    atom_code, index, expected_kind = SECTION_MAP[section_key]
    if not context.entitled or context.sns_fetch_raw is None:
        return None
    document_html = context.sns_fetch_raw(atom_code)
    if not document_html:
        logger.warning(
            "service fill: no S&S document for rite %s (section %s)",
            atom_code, section_key,
        )
        return None
    segments = _parse_cached(atom_code, document_html)
    if index >= len(segments):
        logger.warning(
            "service fill: rite %s has %d segments, section %s expects index %d "
            "(S&S document drift)", atom_code, len(segments), section_key, index,
        )
        return None
    segment = segments[index]
    if segment.kind != expected_kind:
        logger.warning(
            "service fill: rite %s section %s expected %s at index %d, found %s "
            "(S&S document drift)", atom_code, section_key, expected_kind, index,
            segment.kind,
        )
        return None
    return segment


def _segment_text(segment: ServiceSegment, expected_kind: str) -> str:
    if expected_kind == SEGMENT_OPTIONS:
        return segment.options[0].body if segment.options else ""
    return segment.text


def _interpolate_names(
    text: str, section_key: str, variables: Dict[str, str],
) -> str:
    """Substitute per-service names into S&S lowercase placeholder tokens.

    Best-effort and deliberately conservative (correctness over coverage):

    * Marriage — the exact phrase ``name and name`` becomes
      ``<partner_one> and <partner_two>``.  It is replaced only when BOTH
      partner variables are present; otherwise the token is left verbatim (and
      flagged) rather than producing a half-filled phrase.
    * Funeral — the standalone lowercase token ``name`` (the deceased) is
      replaced with ``deceased_name``, EXCEPT where it is immediately followed
      by ``of`` (guarding the common "in the name of ..." phrase).  This is a
      heuristic: it can still miss an unusual construction, so it is applied
      only within the mapped funeral sections and left unsubstituted-and-logged
      when ``deceased_name`` is absent.
    """
    if section_key.startswith("marriage_"):
        return _interpolate_couple(text, section_key, variables)
    if section_key.startswith("funeral_"):
        return _interpolate_deceased(text, section_key, variables)
    return text


def _interpolate_couple(
    text: str, section_key: str, variables: Dict[str, str],
) -> str:
    if not _COUPLE_PLACEHOLDER_RE.search(text):
        return text
    partner_one = variables.get("partner_one")
    partner_two = variables.get("partner_two")
    if not partner_one or not partner_two:
        logger.warning(
            "service fill: %s has a couple placeholder but partner names are "
            "missing; left unsubstituted", section_key,
        )
        return text
    return _COUPLE_PLACEHOLDER_RE.sub("%s and %s" % (partner_one, partner_two), text)


def _interpolate_deceased(
    text: str, section_key: str, variables: Dict[str, str],
) -> str:
    if not _FUNERAL_NAME_TOKEN.search(text):
        return text
    deceased_name = variables.get("deceased_name")
    if not deceased_name:
        logger.warning(
            "service fill: %s references the deceased but deceased_name is "
            "missing; left unsubstituted", section_key,
        )
        return text
    return _FUNERAL_NAME_TOKEN.sub(deceased_name, text)


def fill_section(section_key: str, context: ContentContext) -> Optional[str]:
    """Fill one canonical rite section from the church's licensed S&S document.

    Returns the section's canonical text (with per-service names interpolated),
    or ``None`` when the section is unmapped, the church is unentitled / has no
    pull hook, or the pull / parse / confidence check fails.  A ``None`` return
    lets the caller render the entitlement placeholder.
    """
    if section_key not in SECTION_MAP:
        return None
    segment = _segment_at(section_key, context)
    if segment is None:
        return None
    _, _, expected_kind = SECTION_MAP[section_key]
    text = _segment_text(segment, expected_kind)
    if not text:
        logger.warning(
            "service fill: section %s resolved to empty text (S&S document "
            "drift)", section_key,
        )
        return None
    return _interpolate_names(text, section_key, context.variables)

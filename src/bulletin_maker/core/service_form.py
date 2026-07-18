"""Form-data → domain conversions shared by every UI adapter.

The wizard (desktop or web) submits a plain JSON dict; these helpers
turn it into a ServiceConfig, resolving hymns through a caller-supplied
lyrics cache.
"""

from __future__ import annotations

import logging
from typing import Optional

from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.renderer.season import PrefaceType
from bulletin_maker.renderer.text_utils import DialogRole
from bulletin_maker.sns.models import HymnLyrics

logger = logging.getLogger(__name__)


def format_verse_label(selected: list) -> str:
    """Build a compact verse label like 'Verses 1, 3-5' from sorted indices."""
    if not selected:
        return ""
    nums = sorted(selected)
    ranges: list[str] = []
    start = end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(str(start) if start == end else f"{start}-{end}")
            start = end = n
    ranges.append(str(start) if start == end else f"{start}-{end}")
    label = ", ".join(ranges)
    return f"Verse {label}" if len(nums) == 1 else f"Verses {label}"


def filter_verses(
    all_verses: list,
    selected: Optional[list],
) -> tuple:
    """Filter verses by 1-based indices and build a verse label.

    Returns (filtered_verses, verse_label).  If *selected* is None or
    includes all verses, returns the original list with an empty label.
    """
    total = len(all_verses)
    if not selected or len(selected) >= total:
        return all_verses, ""
    valid = sorted(i for i in selected if 1 <= i <= total)
    if not valid or len(valid) >= total:
        return all_verses, ""
    filtered = [all_verses[i - 1] for i in valid]
    return filtered, format_verse_label(valid)


def parse_preface(value: Optional[str]) -> Optional[PrefaceType]:
    """Convert a preface string to PrefaceType, returning None on bad input."""
    if not value:
        return None
    try:
        return PrefaceType(value)
    except ValueError:
        logger.warning("Invalid preface value from UI: %r", value)
        return None


def parse_dialog_entries(raw: Optional[list]) -> Optional[list]:
    """Convert JSON dialog dicts back to (DialogRole, text) tuples."""
    if not raw:
        return None
    entries = []
    for e in raw:
        try:
            role = DialogRole(e.get("role", ""))
        except ValueError:
            role = DialogRole.NONE
        entries.append((role, e.get("text", "")))
    return entries


def build_hymn(form_data: dict, slot: str, hymn_cache: dict) -> Optional[HymnLyrics]:
    """Build a HymnLyrics from cached lyric data for a form slot."""
    hymn_data = form_data.get(slot)
    if not hymn_data:
        return None
    number = hymn_data.get("number", "")
    collection = hymn_data.get("collection", "ELW")
    cache_key = f"{collection}_{number}"
    cached = hymn_cache.get(cache_key)
    if cached:
        all_verses = cached["verses"]
        selected = hymn_data.get("selected_verses")
        verses, verse_label = filter_verses(all_verses, selected)
        return HymnLyrics(
            number=cached["number"],
            title=cached["title"],
            verses=verses,
            refrain=cached["refrain"],
            copyright=cached["copyright"],
            verse_label=verse_label,
        )
    # Minimal fallback — title only (no lyrics fetched)
    logger.warning("Hymn %s %s not in cache — large print will show title only",
                   collection, number)
    title = hymn_data.get("title", "")
    return HymnLyrics(
        number=f"{collection} {number}",
        title=title,
        verses=[],
    )


def build_service_config(form_data: dict, hymn_cache: dict) -> ServiceConfig:
    """Build a ServiceConfig from wizard form data."""
    return ServiceConfig(
        date=form_data.get("date", ""),
        date_display=form_data.get("date_display", ""),
        creed_type=form_data.get("creed_type"),
        include_kyrie=form_data.get("include_kyrie"),
        canticle=form_data.get("canticle"),
        eucharistic_form=form_data.get("eucharistic_form"),
        include_memorial_acclamation=form_data.get("include_memorial_acclamation"),
        memorial_acclamation_mode=form_data.get("memorial_acclamation_mode"),
        preface=parse_preface(form_data.get("preface")),
        show_confession=form_data.get("show_confession"),
        show_nunc_dimittis=form_data.get("show_nunc_dimittis"),
        reading_overrides=form_data.get("reading_overrides") or None,
        include_baptism=form_data.get("include_baptism", False),
        baptism_candidate_names=form_data.get("baptism_candidate_names", ""),
        confession_entries=parse_dialog_entries(
            form_data.get("confession_entries")
        ),
        offering_prayer_text=form_data.get("offering_prayer_text") or None,
        prayer_after_communion_text=form_data.get("prayer_after_communion_text") or None,
        blessing_text=form_data.get("blessing_text") or None,
        dismissal_entries=parse_dialog_entries(
            form_data.get("dismissal_entries")
        ),
        gathering_hymn=build_hymn(form_data, "gathering_hymn", hymn_cache),
        sermon_hymn=build_hymn(form_data, "sermon_hymn", hymn_cache),
        communion_hymn=build_hymn(form_data, "communion_hymn", hymn_cache),
        sending_hymn=build_hymn(form_data, "sending_hymn", hymn_cache),
        prelude_title=form_data.get("prelude_title", ""),
        prelude_composer=form_data.get("prelude_composer", ""),
        prelude_performer=form_data.get("prelude_performer", ""),
        offertory_type=form_data.get("offertory_type", "offertory"),
        offertory_title=form_data.get("offertory_title", ""),
        offertory_composer=form_data.get("offertory_composer", ""),
        offertory_performer=form_data.get("offertory_performer", ""),
        postlude_title=form_data.get("postlude_title", ""),
        postlude_composer=form_data.get("postlude_composer", ""),
        postlude_performer=form_data.get("postlude_performer", ""),
        choral_title=form_data.get("choral_title", ""),
        choral_composer=form_data.get("choral_composer", ""),
        cover_image=form_data.get("cover_image", ""),
    )

"""HTML-based document renderers using Jinja2 + Playwright.

Produces print-ready PDFs for:
  - Full with Hymns LARGE PRINT
  - Leader Guide (large print + sung notation for pastor)
  - Pulpit SCRIPTURE
  - Pulpit PRAYERS

Context builders assemble template data from S&S content + static texts.
Rendering is delegated to pdf_engine; filters/env to filters module.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bulletin_maker.exceptions import BulletinError, ContentNotFoundError
from bulletin_maker.sns.models import (
    SLOT_FIRST,
    SLOT_GOSPEL,
    SLOT_PSALM,
    SLOT_SECOND,
    DayContent,
    HymnLyrics,
    Reading,
    ServiceConfig,
)
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.renderer.image_manager import (
    get_gospel_acclamation_image,
    get_preface_image,
    get_setting_image,
)
from bulletin_maker.renderer.text_utils import (
    clean_sns_html,
    extract_book_name,
    group_psalm_verses,
    parse_dialog_html,
    preprocess_html,
    strip_tags,
)
from bulletin_maker.renderer.filters import TEMPLATE_DIR, setup_jinja_env
from bulletin_maker.renderer.pdf_engine import (
    MARGINS_BULLETIN,
    MARGINS_DEFAULT,
    MARGINS_PULPIT,
    count_pages,
    impose_booklet,
    render_to_pdf,
    render_with_shrink,
)
from bulletin_maker.renderer.prayers_parser import (
    parse_prayers_html,
    parse_prayers_response,
)
from bulletin_maker.renderer.static_text import (
    AARONIC_BLESSING,
    AGNUS_DEI,
    APOSTLES_CREED,
    BAPTISM_FLOOD_PRAYER,
    BAPTISM_FORMULA,
    BAPTISM_PRESENTATION,
    BAPTISM_PROFESSION,
    BAPTISM_RENUNCIATION,
    BAPTISM_WELCOME,
    BAPTISM_WELCOME_RESPONSE,
    CHURCH_ADDRESS,
    CHURCH_NAME,
    COME_HOLY_SPIRIT,
    CONFESSION_AND_FORGIVENESS,
    DISMISSAL,
    DISMISSAL_ENTRIES,
    EUCHARISTIC_PRAYER_CLOSING,
    EUCHARISTIC_PRAYER_EXTENDED,
    GREAT_THANKSGIVING_DIALOG,
    GREAT_THANKSGIVING_PREFACE,
    INVITATION_TO_LENT,
    LORDS_PRAYER,
    MEMORIAL_ACCLAMATION,
    NICENE_CREED,
    NUNC_DIMITTIS,
    OFFERTORY_HYMN_VERSES,
    DEFAULT_PRAYERS_RESPONSE,
    PRAYERS_INTRO,
    SANCTUS,
    STANDING_INSTRUCTIONS,
    WELCOME_MESSAGE,
    WORDS_OF_INSTITUTION,
)

logger = logging.getLogger(__name__)


# ── Image helpers ─────────────────────────────────────────────────────

def _image_to_data_uri(path: Path) -> str:
    """Convert an image file to a base64 data URI."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".tif", ".tiff"):
        from PIL import Image
        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{data}"
    elif suffix == ".png":
        data = base64.b64encode(path.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    else:
        data = base64.b64encode(path.read_bytes()).decode()
        return f"data:image/jpeg;base64,{data}"


# ── Text helpers ──────────────────────────────────────────────────────

def _extract_day_name(title: str) -> str:
    """Extract liturgical day name from S&S title.

    "Sunday, February 22, 2026 First Sunday in Lent, Year A"
    -> "First Sunday in Lent"
    """
    day_name = title
    date_match = re.search(r'\d{4}\s+(.+)', day_name)
    if date_match:
        day_name = date_match.group(1).strip()
    day_name = re.sub(r',?\s*Year\s+[ABC]$', '', day_name).strip()
    return day_name


def _format_block_quotes(html: str) -> str:
    """Wrap S&S scripture block quotes in styled divs."""
    quote_line = r'<br>\s*<span>\s*\r?\n\s{8,}[^<]+</span>'
    group_pattern = r'((?:' + quote_line + r'\s*)+)(?:<br>)?'

    def _wrap(match: re.Match) -> str:
        full = match.group(1)
        lines = re.findall(r'<span>\s*\r?\n\s{8,}([^<]+)</span>', full)
        inner = "<br>\n".join(line.strip() for line in lines)
        return f'\n<div class="block-quote">{inner}</div>\n'

    return re.sub(group_pattern, _wrap, html)


def _clean_html(html: str | None) -> str:
    """Preprocess S&S HTML for direct rendering in templates."""
    if not html:
        return ""
    html = preprocess_html(html)
    html = html.replace("<sc>", '<span class="sc">').replace("</sc>", "</span>")
    html = _format_block_quotes(html)
    return html


def _split_stanzas(text: str) -> list[str]:
    """Split text on double newlines into non-empty stanzas."""
    return [s.strip() for s in text.split("\n\n") if s.strip()]


# ── Agnus Dei stanza splitting ────────────────────────────────────────

def _split_agnus_dei() -> list[str]:
    """Split Agnus Dei text into 3 stanzas (mercy/mercy/peace)."""
    lines = AGNUS_DEI.split("\n")
    stanzas = []
    for i in range(0, len(lines), 2):
        chunk = lines[i:i + 2]
        stanzas.append("\n".join(chunk))
    return stanzas


# ── Reading data helpers ──────────────────────────────────────────────

def _get_reading(day: DayContent, keyword: str):
    """Find a reading by keyword in its label."""
    for r in day.readings:
        if keyword in r.label.lower():
            return r
    return None


def _get_reading_with_override(
    day: DayContent, config: ServiceConfig, keyword: str,
) -> Reading | None:
    """Get reading, preferring override if present."""
    if config.reading_overrides and keyword in config.reading_overrides:
        ovr = config.reading_overrides[keyword]
        if isinstance(ovr, Reading):
            return ovr
        # Dict form from UI — convert to Reading
        if isinstance(ovr, dict):
            return Reading(
                label=ovr.get("label", keyword.title() + " Reading"),
                citation=ovr.get("citation", ""),
                intro=ovr.get("intro", ""),
                text_html=ovr.get("text_html", ""),
            )
    return _get_reading(day, keyword)


def _reading_data(reading: Reading | None) -> dict | None:
    """Build template-ready dict from a Reading object."""
    if reading is None:
        return None
    return {
        "citation": reading.citation,
        "intro": strip_tags(reading.intro) if reading.intro else "",
        "text_html": _clean_html(reading.text_html),
        "book": extract_book_name(reading.citation),
    }


def _build_gospel_entry(day: DayContent) -> dict | None:
    """Build template-ready dict for the Gospel reading."""
    gospel_raw = _get_reading(day, SLOT_GOSPEL)
    if gospel_raw and gospel_raw.label.lower() == SLOT_GOSPEL:
        return _reading_data(gospel_raw)
    if gospel_raw is None:
        for r in day.readings:
            if r.label.lower() == SLOT_GOSPEL:
                return _reading_data(r)
    return None


def _build_psalm_data(day: DayContent) -> dict | None:
    """Build template-ready dict for the Psalm."""
    psalm_raw = _get_reading(day, SLOT_PSALM)
    if not psalm_raw:
        return None
    return _build_psalm_data_from_reading(psalm_raw)


def _build_psalm_data_from_reading(reading: Reading | None) -> dict | None:
    """Build template-ready dict for a Psalm from a Reading object."""
    if not reading:
        return None
    psalm_num = reading.citation.replace("Psalm", "").strip()
    return {
        "number": psalm_num,
        "intro": strip_tags(reading.intro) if reading.intro else "",
        "verses": group_psalm_verses(reading.text_html),
    }


def _build_baptism_context(config: ServiceConfig) -> dict:
    """Build template-ready dict for the Holy Baptism rite."""
    names = [n.strip() for n in config.baptism_candidate_names.split(",") if n.strip()]
    formulas = [BAPTISM_FORMULA.format(name=name) for name in names] if names else [
        BAPTISM_FORMULA.format(name="___________")
    ]
    return {
        "include_baptism": True,
        "baptism_presentation": BAPTISM_PRESENTATION,
        "baptism_renunciation": BAPTISM_RENUNCIATION,
        "baptism_profession": BAPTISM_PROFESSION,
        "baptism_flood_prayer": BAPTISM_FLOOD_PRAYER,
        "baptism_formulas": formulas,
        "baptism_welcome": BAPTISM_WELCOME,
        "baptism_welcome_response": BAPTISM_WELCOME_RESPONSE,
    }


# ── Auto-adjust profiles ─────────────────────────────────────────────


@dataclass
class AdjustProfile:
    """A set of CSS + scale overrides for bulletin auto-adjustment."""
    name: str
    css: str
    scale: float = 1.0


# Tighten: 3 tiers × 2 levels = 6 profiles (T1–T6)
# Tier 1 (spacing only): imperceptible
# Tier 2 (+ cover/break): subtle layout changes
# Tier 3 (+ typography/scale/images): visible but acceptable
BULLETIN_TIGHTEN_PROFILES = [
    # T1 — spacing only
    AdjustProfile(name="T1", css=(
        ".spacer { height: 4pt; } "
        ".spacer-sm { height: 2pt; } "
        ".section-heading { margin-top: 5pt; } "
        ".ep-break { height: 3pt; }"
    )),
    # T2 — tighter spacing + break-inside relaxed
    AdjustProfile(name="T2", css=(
        ".spacer { height: 2pt; } "
        ".spacer-sm { height: 1pt; } "
        ".section-heading { margin-top: 3pt; margin-bottom: 1pt; } "
        ".flow-group { break-inside: auto; } "
        ".ep-break { height: 2pt; }"
    )),
    # T3 — zero spacing + smaller cover
    AdjustProfile(name="T3", css=(
        ".spacer { height: 0pt; } "
        ".spacer-sm { height: 0pt; } "
        ".section-heading { margin-top: 2pt; margin-bottom: 0pt; } "
        ".flow-group { break-inside: auto; } "
        ".ep-break { height: 0pt; } "
        ".cover { min-height: 7in; }"
    )),
    # T4 — add typography: smaller font, tighter line-height
    AdjustProfile(name="T4", css=(
        ".spacer { height: 0pt; } "
        ".spacer-sm { height: 0pt; } "
        ".section-heading { margin-top: 2pt; margin-bottom: 0pt; } "
        ".flow-group { break-inside: auto; } "
        ".ep-break { height: 0pt; } "
        ".cover { min-height: 7in; } "
        "body { font-size: 10.5pt; line-height: 1.3; } "
        ".reading-intro { font-size: 8.5pt; } "
        ".reading-text { line-height: 1.3; } "
        ".psalm-verse { line-height: 1.25; }"
    )),
    # T5 — tighter typography + narrower columns + scale
    AdjustProfile(name="T5", css=(
        ".spacer { height: 0pt; } "
        ".spacer-sm { height: 0pt; } "
        ".section-heading { margin-top: 1pt; margin-bottom: 0pt; } "
        ".flow-group { break-inside: auto; } "
        ".ep-break { height: 0pt; } "
        ".cover { min-height: 6.5in; } "
        "body { font-size: 10.5pt; line-height: 1.25; orphans: 2; widows: 2; } "
        ".reading-intro { font-size: 8pt; } "
        ".reading-text { line-height: 1.25; } "
        ".psalm-verse { line-height: 1.2; } "
        ".two-col { column-gap: 0.2in; }"
    ), scale=0.97),
    # T6 — maximum tightening: smallest font, shortest cover, scaled
    AdjustProfile(name="T6", css=(
        ".spacer { height: 0pt; } "
        ".spacer-sm { height: 0pt; } "
        ".section-heading { margin-top: 1pt; margin-bottom: 0pt; } "
        ".flow-group { break-inside: auto; } "
        ".ep-break { height: 0pt; } "
        ".cover { min-height: 6in; } "
        "body { font-size: 10pt; line-height: 1.2; orphans: 2; widows: 2; } "
        ".reading-intro { font-size: 8pt; } "
        ".reading-text { line-height: 1.2; } "
        ".psalm-verse { line-height: 1.15; } "
        ".two-col { column-gap: 0.15in; } "
        ".notation-image img { max-height: 6.5in; } "
        ".ep-text { font-size: 9.5pt; }"
    ), scale=0.95),
]

# Loosen: 3 tiers × 2 levels = 6 profiles (L1–L6)
BULLETIN_LOOSEN_PROFILES = [
    # L1 — spacing only
    AdjustProfile(name="L1", css=(
        ".spacer { height: 12pt; } "
        ".spacer-sm { height: 6pt; } "
        ".section-heading { margin-top: 12pt; } "
        ".ep-break { height: 10pt; }"
    )),
    # L2 — more spacing
    AdjustProfile(name="L2", css=(
        ".spacer { height: 18pt; } "
        ".spacer-sm { height: 10pt; } "
        ".section-heading { margin-top: 16pt; } "
        ".ep-break { height: 14pt; }"
    )),
    # L3 — max spacing + taller cover
    AdjustProfile(name="L3", css=(
        ".spacer { height: 24pt; } "
        ".spacer-sm { height: 14pt; } "
        ".section-heading { margin-top: 20pt; } "
        ".ep-break { height: 18pt; } "
        ".cover { min-height: 8in; }"
    )),
    # L4 — add typography: larger font, looser line-height
    AdjustProfile(name="L4", css=(
        ".spacer { height: 24pt; } "
        ".spacer-sm { height: 14pt; } "
        ".section-heading { margin-top: 20pt; } "
        ".ep-break { height: 18pt; } "
        ".cover { min-height: 8in; } "
        "body { font-size: 11.5pt; line-height: 1.4; } "
        ".reading-text { line-height: 1.4; } "
        ".psalm-verse { line-height: 1.35; }"
    )),
    # L5 — looser typography + wider columns + scale
    AdjustProfile(name="L5", css=(
        ".spacer { height: 28pt; } "
        ".spacer-sm { height: 16pt; } "
        ".section-heading { margin-top: 22pt; } "
        ".ep-break { height: 20pt; } "
        ".cover { min-height: 8in; } "
        "body { font-size: 11.5pt; line-height: 1.45; orphans: 4; widows: 4; } "
        ".reading-text { line-height: 1.45; } "
        ".psalm-verse { line-height: 1.4; } "
        ".two-col { column-gap: 0.3in; }"
    ), scale=1.03),
    # L6 — maximum loosening: largest font, tallest cover, scaled
    AdjustProfile(name="L6", css=(
        ".spacer { height: 32pt; } "
        ".spacer-sm { height: 18pt; } "
        ".section-heading { margin-top: 24pt; } "
        ".ep-break { height: 22pt; } "
        ".cover { min-height: 8.2in; } "
        "body { font-size: 12pt; line-height: 1.5; orphans: 4; widows: 4; } "
        ".reading-text { line-height: 1.5; } "
        ".psalm-verse { line-height: 1.45; } "
        ".two-col { column-gap: 0.35in; }"
    ), scale=1.05),
]

LP_TIGHTEN_CSS = [
    (
        ".spacer { height: 12pt; } "
        ".liturgy-heading { margin-top: 8pt; } "
        ".scripture-heading { margin-top: 8pt; }"
    ),
    (
        ".spacer { height: 6pt; } "
        ".liturgy-heading { margin-top: 4pt; } "
        ".scripture-heading { margin-top: 4pt; } "
        ".flow-group { break-inside: auto; }"
    ),
    (
        ".spacer { height: 0pt; } "
        ".liturgy-heading { margin-top: 2pt; } "
        ".scripture-heading { margin-top: 2pt; } "
        ".flow-group { break-inside: auto; }"
    ),
]


def _inject_css(html: str, extra_css: str) -> str:
    """Inject CSS overrides into an HTML document's style block."""
    return html.replace("</style>", f"\n/* auto-adjust */\n{extra_css}\n</style>")


def _booklet_blanks(n: int) -> int:
    """Number of blank pages needed to pad n to a multiple of 4."""
    return (4 - n % 4) % 4


def _best_direction(pages: int) -> str:
    """Pick the closer direction to reach a multiple of 4.

    Returns "tighten" if removing pages is closer (or tied),
    "loosen" if adding pages is closer.
    """
    blanks = _booklet_blanks(pages)
    if blanks == 0:
        return "tighten"  # already perfect, doesn't matter
    pages_to_remove = pages % 4  # distance down to lower multiple
    pages_to_add = blanks         # distance up to upper multiple
    if pages_to_add < pages_to_remove:
        return "loosen"
    return "tighten"


def _auto_adjust_bulletin(
    html_string: str,
    seq_path: Path,
    bulletin_page_size: dict,
    on_progress: object | None = None,
) -> None:
    """Try CSS profiles to land the bulletin on a multiple-of-4 page count.

    Renders the baseline, tries profiles, and leaves the best result on
    disk at seq_path.  The caller does not need to re-render.

    Args:
        on_progress: Optional callable(detail_str) for UI status updates.
    """
    def _report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    _report("Rendering baseline layout...")
    render_to_pdf(
        html_string, seq_path,
        margins=MARGINS_BULLETIN, display_footer=True,
        page_size=bulletin_page_size,
    )
    pages = count_pages(seq_path)
    if not pages or pages % 4 == 0:
        _report(f"Layout fits perfectly ({pages} pages)")
        return

    blanks = _booklet_blanks(pages)
    _report(f"Baseline: {pages} pages ({blanks} blank) — adjusting...")

    best_html = html_string
    best_scale = 1.0
    best_blanks = blanks
    baseline_pages = pages
    adjusted = False

    direction = _best_direction(pages)
    if direction == "tighten":
        primary = BULLETIN_TIGHTEN_PROFILES
        secondary = BULLETIN_LOOSEN_PROFILES
    else:
        primary = BULLETIN_LOOSEN_PROFILES
        secondary = BULLETIN_TIGHTEN_PROFILES

    # Try primary direction
    for profile in primary:
        _report(f"Trying {profile.name} ({direction})...")
        candidate = _inject_css(html_string, profile.css)
        render_to_pdf(
            candidate, seq_path,
            margins=MARGINS_BULLETIN, display_footer=True,
            page_size=bulletin_page_size, scale=profile.scale,
        )
        n = count_pages(seq_path)
        if not n:
            continue
        blanks = _booklet_blanks(n)
        if blanks < best_blanks:
            best_html = candidate
            best_scale = profile.scale
            best_blanks = blanks
            adjusted = True
            logger.info("Bulletin auto-adjust %s: %d pages, %d blanks",
                        profile.name, n, blanks)
        if best_blanks == 0:
            break
        # Overshoot detection: if we passed through a multiple of 4
        # (e.g. tightened from 13 past 12 to 11), stop this direction
        if direction == "tighten" and n < baseline_pages and n % 4 != 0:
            lower = baseline_pages - (baseline_pages % 4)
            if n < lower:
                break
        elif direction == "loosen" and n > baseline_pages and n % 4 != 0:
            upper = baseline_pages + _booklet_blanks(baseline_pages)
            if n > upper:
                break

    # Try secondary direction if still not perfect
    if best_blanks > 0:
        secondary_dir = "loosen" if direction == "tighten" else "tighten"
        for profile in secondary:
            _report(f"Trying {profile.name} ({secondary_dir})...")
            candidate = _inject_css(html_string, profile.css)
            render_to_pdf(
                candidate, seq_path,
                margins=MARGINS_BULLETIN, display_footer=True,
                page_size=bulletin_page_size, scale=profile.scale,
            )
            n = count_pages(seq_path)
            if not n:
                continue
            blanks = _booklet_blanks(n)
            if blanks < best_blanks:
                best_html = candidate
                best_scale = profile.scale
                best_blanks = blanks
                adjusted = True
                logger.info("Bulletin auto-adjust %s: %d pages, %d blanks",
                            profile.name, n, blanks)
            if best_blanks == 0:
                break

    if best_blanks < _booklet_blanks(baseline_pages):
        logger.info("Bulletin auto-adjust: %d blanks -> %d blanks",
                    _booklet_blanks(baseline_pages), best_blanks)

    # Re-render the best result so it's on disk for the caller
    if adjusted:
        _report("Finalizing best layout...")
        render_to_pdf(
            best_html, seq_path,
            margins=MARGINS_BULLETIN, display_footer=True,
            page_size=bulletin_page_size, scale=best_scale,
        )


# ── Liturgical text resolution ────────────────────────────────────────

def resolve_text_defaults(config: ServiceConfig, day: DayContent) -> None:
    """Populate None liturgical text fields on config from S&S, then static.

    For each of the 5 text fields, the priority is:
      1. User-provided value on config (already set) — keep it
      2. S&S DayContent HTML (parsed to plain text) — use if available
      3. Static fallback from static_text.py — last resort
    """
    # Confession
    if config.confession_entries is None:
        if day.confession_html:
            parsed = parse_dialog_html(day.confession_html)
            if parsed:
                config.confession_entries = parsed
        if config.confession_entries is None:
            config.confession_entries = CONFESSION_AND_FORGIVENESS

    # Offering Prayer
    if config.offering_prayer_text is None:
        if day.offering_prayer_html:
            config.offering_prayer_text = clean_sns_html(day.offering_prayer_html)
        if not config.offering_prayer_text:
            config.offering_prayer_text = ""

    # Prayer After Communion
    if config.prayer_after_communion_text is None:
        if day.prayer_after_communion_html:
            config.prayer_after_communion_text = clean_sns_html(
                day.prayer_after_communion_html
            )
        if not config.prayer_after_communion_text:
            config.prayer_after_communion_text = ""

    # Blessing
    if config.blessing_text is None:
        if day.blessing_html:
            config.blessing_text = clean_sns_html(day.blessing_html)
        if not config.blessing_text:
            config.blessing_text = AARONIC_BLESSING

    # Dismissal
    if config.dismissal_entries is None:
        if day.dismissal_html:
            parsed = parse_dialog_html(day.dismissal_html)
            if parsed:
                config.dismissal_entries = parsed
        if config.dismissal_entries is None:
            config.dismissal_entries = DISMISSAL_ENTRIES


# ══════════════════════════════════════════════════════════════════════
# Context builders
# ══════════════════════════════════════════════════════════════════════

def _build_common_context(
    day: DayContent, config: ServiceConfig, season: LiturgicalSeason,
) -> dict:
    """Build context keys shared by bulletin, large print, and leader guide.

    Resolves readings, creed, prayers, GA image, cover image, and all
    liturgical content that is identical across document types.
    """
    # Readings (with override support)
    first_reading = _reading_data(_get_reading_with_override(day, config, SLOT_FIRST))
    second_reading = _reading_data(_get_reading_with_override(day, config, SLOT_SECOND))
    gospel_override = _get_reading_with_override(day, config, SLOT_GOSPEL)
    gospel_entry = _reading_data(gospel_override) if gospel_override else _build_gospel_entry(day)
    psalm_override = _get_reading_with_override(day, config, SLOT_PSALM)
    psalm_data = _build_psalm_data_from_reading(psalm_override) if (config.reading_overrides and SLOT_PSALM in config.reading_overrides) else _build_psalm_data(day)

    # Gospel Acclamation image
    ga_image_uri = ""
    try:
        path = get_gospel_acclamation_image(season)
        ga_image_uri = _image_to_data_uri(path)
    except FileNotFoundError:
        logger.warning("Gospel Acclamation image not found for season %s", season)
    except ImportError:
        logger.warning("Pillow not installed — cannot convert GA image to data URI")

    # Creed
    creed_name = "NICENE CREED" if config.creed_type == "nicene" else "APOSTLES CREED"
    creed_text = NICENE_CREED if config.creed_type == "nicene" else APOSTLES_CREED

    # Prayers response
    prayers_response = DEFAULT_PRAYERS_RESPONSE
    if day.prayers_html:
        prayers_response = parse_prayers_response(day.prayers_html)

    # Invitation to communion
    invitation_text = "Taste and see that the Lord is good."
    if day.invitation_to_communion:
        invitation_text = strip_tags(preprocess_html(day.invitation_to_communion))

    # Cover image
    cover_image_uri = ""
    if config.cover_image:
        try:
            cover_image_uri = _image_to_data_uri(Path(config.cover_image))
        except FileNotFoundError:
            logger.warning("Cover image not found: %s", config.cover_image)

    return {
        # Cover / metadata
        "church_name": CHURCH_NAME,
        "church_address": CHURCH_ADDRESS,
        "cover_image_uri": cover_image_uri,
        "date_display": config.date_display,
        "day_name": _extract_day_name(day.title),

        # Welcome
        "welcome_message": WELCOME_MESSAGE,
        "standing_instructions": STANDING_INSTRUCTIONS,

        # Confession
        "show_confession": config.show_confession,
        "confession_entries": config.confession_entries,

        # Season
        "is_lent": season == LiturgicalSeason.LENT,
        "invitation_to_lent_paragraphs": _split_stanzas(INVITATION_TO_LENT),

        # Prayer of the Day
        "prayer_of_day_html": _clean_html(day.prayer_of_the_day_html),

        # Readings
        "first_reading": first_reading,
        "psalm_data": psalm_data,
        "second_reading": second_reading,
        "ga_image_uri": ga_image_uri,
        "gospel": gospel_entry,

        # Creed / Baptism
        "include_baptism": config.include_baptism,
        "creed_name": creed_name,
        "creed_stanzas": _split_stanzas(creed_text),
        **(_build_baptism_context(config) if config.include_baptism else {}),

        # Prayers
        "prayers_response": prayers_response,

        # Offering
        "offertory_hymn_verses": OFFERTORY_HYMN_VERSES,

        # Great Thanksgiving
        "great_thanksgiving_preface": GREAT_THANKSGIVING_PREFACE,

        # Eucharistic Prayer
        "eucharistic_form": config.eucharistic_form,
        "eucharistic_prayer_first_line": EUCHARISTIC_PRAYER_EXTENDED.split("\n")[0],
        "eucharistic_prayer_lines": [
            l.strip() for l in EUCHARISTIC_PRAYER_EXTENDED.split("\n")[1:]
            if l.strip()
        ],
        "words_of_institution_paragraphs": _split_stanzas(WORDS_OF_INSTITUTION),
        "has_memorial_acclamation": config.include_memorial_acclamation,
        "memorial_acclamation": MEMORIAL_ACCLAMATION,
        "eucharistic_prayer_closing_stanzas": _split_stanzas(EUCHARISTIC_PRAYER_CLOSING),
        "come_holy_spirit": COME_HOLY_SPIRIT,

        # Lord's Prayer
        "lords_prayer_stanzas": _split_stanzas(LORDS_PRAYER),

        # Invitation to Communion
        "invitation_to_communion_text": invitation_text,

        # Closing
        "show_nunc_dimittis": config.show_nunc_dimittis,
        "offering_prayer_text": config.offering_prayer_text or "",
        "prayer_after_communion_text": config.prayer_after_communion_text or "",
        "blessing_lines": (config.blessing_text or AARONIC_BLESSING).split("\n"),
        "dismissal_entries": config.dismissal_entries or DISMISSAL_ENTRIES,
    }


def _build_large_print_context(
    day: DayContent, config: ServiceConfig, season: LiturgicalSeason,
) -> dict:
    """Build the full template context for the Large Print document."""
    ctx = _build_common_context(day, config, season)

    ga_text = ""
    if day.gospel_acclamation:
        ga_text = strip_tags(preprocess_html(day.gospel_acclamation))

    ctx.update({
        "css": (TEMPLATE_DIR / "large_print.css").read_text(),
        "choral_title": config.choral_title,
        "gathering_hymn": config.gathering_hymn,
        "ga_text_fallback": ga_text,
        "sermon_hymn": config.sermon_hymn,
        "great_thanksgiving_dialog": GREAT_THANKSGIVING_DIALOG,
        "sanctus_stanzas": _split_stanzas(SANCTUS),
        "agnus_dei_stanzas": _split_agnus_dei(),
        "communion_hymn": config.communion_hymn,
        "nunc_dimittis_lines": NUNC_DIMITTIS.split("\n"),
        "sending_hymn": config.sending_hymn,
    })
    return ctx


def _build_pulpit_scripture_context(
    day: DayContent, date_display: str, config: ServiceConfig | None = None,
) -> dict:
    """Build template context for the Pulpit Scripture document."""
    if config:
        first_reading = _reading_data(_get_reading_with_override(day, config, SLOT_FIRST))
        second_reading = _reading_data(_get_reading_with_override(day, config, SLOT_SECOND))
        psalm_override = _get_reading_with_override(day, config, SLOT_PSALM)
        psalm_data = _build_psalm_data_from_reading(psalm_override) if (config.reading_overrides and SLOT_PSALM in config.reading_overrides) else _build_psalm_data(day)
    else:
        first_reading = _reading_data(_get_reading(day, SLOT_FIRST))
        second_reading = _reading_data(_get_reading(day, SLOT_SECOND))
        psalm_data = _build_psalm_data(day)

    css = (TEMPLATE_DIR / "pulpit_scripture.css").read_text()

    return {
        "css": css,
        "date_display": date_display,
        "first_reading": first_reading,
        "psalm_data": psalm_data,
        "second_reading": second_reading,
    }


def _build_pulpit_prayers_context(
    day: DayContent,
    date_display: str,
    creed_type: str,
    creed_page_num: int | None,
) -> dict:
    """Build template context for the Pulpit Prayers document."""
    creed_name = "NICENE CREED" if creed_type.lower() == "nicene" else "APOSTLES CREED"
    creed_text = NICENE_CREED if creed_type.lower() == "nicene" else APOSTLES_CREED

    page_ref = str(creed_page_num) if creed_page_num else "_____"

    parsed_prayers = {"intro": "", "brief_silence": False, "petitions": [],
                      "closing_text": "", "closing_response": ""}
    if day.prayers_html:
        parsed_prayers = parse_prayers_html(day.prayers_html)

    css = (TEMPLATE_DIR / "pulpit_prayers.css").read_text()

    return {
        "css": css,
        "date_display": date_display,
        "creed_name": creed_name,
        "creed_page_ref": page_ref,
        "creed_stanzas": _split_stanzas(creed_text),
        "prayers_intro": PRAYERS_INTRO,
        "parsed_prayers": parsed_prayers,
    }


# ── Bulletin helpers ──────────────────────────────────────────────────

def _hymn_title_str(hymn: HymnLyrics | None) -> str:
    """Format a hymn as 'ELW 335 — Title' for title-only references."""
    if hymn is None:
        return ""
    return f"{hymn.number} \u2014 {hymn.title}"


def _safe_setting_image_uri(piece: str) -> str:
    """Try to load a setting image as data URI; return empty on failure."""
    try:
        path = get_setting_image(piece)
        return _image_to_data_uri(path)
    except (FileNotFoundError, ValueError):
        logger.warning("Setting image not found for '%s'", piece)
        return ""


def _build_bulletin_context(
    day: DayContent,
    config: ServiceConfig,
    season: LiturgicalSeason,
    *,
    communion_hymn_image_uri: str = "",
) -> dict:
    """Build template context for the standard Bulletin for Congregation."""
    ctx = _build_common_context(day, config, season)

    # Notation images for liturgical setting pieces
    kyrie_uri = _safe_setting_image_uri("kyrie") if config.include_kyrie else ""

    canticle_uri = ""
    if config.canticle == "glory_to_god":
        canticle_uri = _safe_setting_image_uri("glory_to_god")
    elif config.canticle == "this_is_the_feast":
        canticle_uri = _safe_setting_image_uri("this_is_the_feast")

    great_thanksgiving_uri = _safe_setting_image_uri("great_thanksgiving")
    sanctus_uri = _safe_setting_image_uri("sanctus")
    agnus_dei_uri = _safe_setting_image_uri("agnus_dei")
    nunc_dimittis_uri = _safe_setting_image_uri("nunc_dimittis")

    memorial_acc_uri = ""
    amen_uri = ""
    if config.include_memorial_acclamation:
        memorial_acc_uri = _safe_setting_image_uri("memorial_acclamation")
        amen_uri = _safe_setting_image_uri("amen")

    ctx.update({
        "css": (TEMPLATE_DIR / "bulletin.css").read_text(),

        # Prelude/postlude
        "prelude_title": config.prelude_title,
        "prelude_performer": config.prelude_performer,
        "postlude_title": config.postlude_title,
        "postlude_performer": config.postlude_performer,
        "choral_title": config.choral_title,

        # Notation images
        "kyrie_image_uri": kyrie_uri,
        "canticle_image_uri": canticle_uri,
        "great_thanksgiving_image_uri": great_thanksgiving_uri,
        "sanctus_image_uri": sanctus_uri,
        "agnus_dei_image_uri": agnus_dei_uri,
        "nunc_dimittis_image_uri": nunc_dimittis_uri,
        "memorial_acclamation_image_uri": memorial_acc_uri,
        "amen_image_uri": amen_uri,
        "offertory_image_uri": "",

        # Hymn titles (bulletin shows title only, not full lyrics)
        "gathering_hymn_title": _hymn_title_str(config.gathering_hymn),
        "sermon_hymn_title": _hymn_title_str(config.sermon_hymn),
        "communion_hymn_title": _hymn_title_str(config.communion_hymn),
        "communion_hymn_image_uri": communion_hymn_image_uri,
        "sending_hymn_title": _hymn_title_str(config.sending_hymn),
    })
    return ctx


def _find_creed_page(pdf_path: Path) -> int | None:
    """Scan PDF text for the creed heading and return its page number.

    Looks for "NICENE CREED" or "APOSTLES CREED" in the extracted text.
    Returns 1-based page number, or None if not found.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").upper()
            if "NICENE CREED" in text or "APOSTLES CREED" in text:
                return i + 1  # 1-based
    except ImportError:
        logger.warning("pypdf not installed — cannot scan for creed page")
    except (OSError, ValueError):
        logger.warning("Could not scan PDF for creed page: %s", pdf_path)
    return None


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def _render_large_format(
    context: dict,
    output_path: Path,
    *,
    keep_intermediates: bool = False,
    label: str,
) -> Path:
    """Shared rendering logic for large print and leader guide documents.

    Both use the same template, margins, and auto-tighten strategy.
    """
    env = setup_jinja_env()
    template = env.get_template("large_print.html")
    html_string = template.render(**context)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".lp_debug"
        debug_dir.mkdir(exist_ok=True)
        debug_name = label.lower().replace(" ", "_") + ".html"
        (debug_dir / debug_name).write_text(html_string)

    render_to_pdf(html_string, output_path, margins=MARGINS_DEFAULT, display_footer=True)

    # Auto-tighten: try progressively tighter CSS to reduce page count
    pages = count_pages(output_path)
    if pages:
        best_html = html_string
        best_pages = pages
        for level_css in LP_TIGHTEN_CSS:
            candidate = _inject_css(html_string, level_css)
            render_to_pdf(candidate, output_path, margins=MARGINS_DEFAULT,
                          display_footer=True)
            n = count_pages(output_path)
            if n and n < best_pages:
                best_html = candidate
                best_pages = n
        if best_pages < pages:
            logger.info("%s auto-tighten: %d -> %d pages", label, pages, best_pages)
        render_to_pdf(best_html, output_path, margins=MARGINS_DEFAULT,
                      display_footer=True)

    logger.info("%s PDF saved: %s", label, output_path)
    return output_path


def generate_large_print(
    day: DayContent,
    config: ServiceConfig,
    output_path: Path,
    *,
    season: LiturgicalSeason,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Full with Hymns LARGE PRINT PDF via HTML + Playwright.

    Args:
        day: S&S content for the Sunday.
        config: User-provided service configuration (already resolved).
        output_path: Where to save the final PDF (suffix forced to .pdf).
        season: The detected liturgical season.
        keep_intermediates: If True, save debug HTML alongside the PDF.

    Returns:
        Path to the saved PDF file.
    """
    resolve_text_defaults(config, day)
    ctx = _build_large_print_context(day, config, season)
    return _render_large_format(
        ctx, output_path, keep_intermediates=keep_intermediates,
        label="Large Print",
    )


def _build_leader_guide_context(
    day: DayContent, config: ServiceConfig, season: LiturgicalSeason,
) -> dict:
    """Build template context for the Leader Guide (large print + notation)."""
    ctx = _build_large_print_context(day, config, season)
    ctx["is_leader_guide"] = True

    preface_image_uri = ""
    if config.preface:
        try:
            path = get_preface_image(config.preface)
            preface_image_uri = _image_to_data_uri(path)
        except FileNotFoundError:
            logger.warning("Preface image not found: %s", config.preface)
        except ImportError:
            logger.warning("Pillow not installed — cannot convert preface image")

    ctx["preface_image_uri"] = preface_image_uri
    return ctx


def generate_leader_guide(
    day: DayContent,
    config: ServiceConfig,
    output_path: Path,
    *,
    season: LiturgicalSeason,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Leader Guide PDF — large print with sung notation.

    Identical to large print but includes preface notation images
    for the pastor's sung portions of the liturgy.

    Args:
        day: S&S content for the Sunday.
        config: User-provided service configuration (already resolved).
        output_path: Where to save the final PDF (suffix forced to .pdf).
        season: The detected liturgical season.
        keep_intermediates: If True, save debug HTML alongside the PDF.

    Returns:
        Path to the saved PDF file.
    """
    resolve_text_defaults(config, day)
    ctx = _build_leader_guide_context(day, config, season)
    return _render_large_format(
        ctx, output_path, keep_intermediates=keep_intermediates,
        label="Leader Guide",
    )


def generate_pulpit_scripture(
    day: DayContent,
    date_display: str,
    output_path: Path,
    *,
    config: ServiceConfig | None = None,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Pulpit Scripture PDF via HTML + Playwright."""
    if not day.readings:
        raise ContentNotFoundError("DayContent has no readings.")

    env = setup_jinja_env()
    template = env.get_template("pulpit_scripture.html")
    ctx = _build_pulpit_scripture_context(day, date_display, config)
    html_string = template.render(**ctx)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".lp_debug"
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "pulpit_scripture.html").write_text(html_string)

    result = render_with_shrink(
        html_string,
        output_path,
        margins=MARGINS_PULPIT,
        max_pages=2,
        header_left=f"SCRIPTURE Readings \u2013 {date_display}",
        pulpit_header=True,
    )

    logger.info("Pulpit Scripture PDF saved: %s", result)
    return result


def generate_pulpit_prayers(
    day: DayContent,
    date_display: str,
    creed_type: str = "apostles",
    creed_page_num: int | None = None,
    output_path: Path = Path("pulpit_prayers.pdf"),
    *,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Pulpit Prayers PDF via HTML + Playwright."""
    if not day.prayers_html:
        raise ContentNotFoundError("DayContent has no prayers_html.")

    env = setup_jinja_env()
    template = env.get_template("pulpit_prayers.html")
    ctx = _build_pulpit_prayers_context(day, date_display, creed_type, creed_page_num)
    html_string = template.render(**ctx)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".lp_debug"
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "pulpit_prayers.html").write_text(html_string)

    result = render_with_shrink(
        html_string,
        output_path,
        margins=MARGINS_PULPIT,
        max_pages=2,
        header_left=f"CREED & PRAYERS \u2013 {date_display}",
        pulpit_header=True,
    )

    logger.info("Pulpit Prayers PDF saved: %s", result)
    return result


def generate_bulletin(
    day: DayContent,
    config: ServiceConfig,
    output_path: Path,
    *,
    season: LiturgicalSeason,
    client: object | None = None,
    keep_intermediates: bool = False,
    on_progress: object | None = None,
) -> tuple[Path, int | None]:
    """Generate the standard Bulletin for Congregation as a booklet PDF.

    Renders sequential half-pages (7"x8.5"), finds the creed page number,
    then imposes into saddle-stitched booklet spreads on legal landscape.

    Args:
        day: S&S content for the Sunday.
        config: User-provided service configuration (already resolved).
        output_path: Where to save the final booklet PDF.
        season: The detected liturgical season.
        client: Optional authenticated SundaysClient for fetching the
            communion hymn notation image dynamically.
        keep_intermediates: If True, save debug HTML and sequential PDF.
        on_progress: Optional callable(detail_str) for UI status updates.

    Returns:
        Tuple of (path to booklet PDF, creed page number or None).
    """
    from bulletin_maker.renderer.image_manager import fetch_hymn_image

    resolve_text_defaults(config, day)

    # Fetch communion hymn notation image if client provided
    communion_hymn_image_uri = ""
    if client is not None and config.communion_hymn is not None:
        hymn_num = config.communion_hymn.number
        # Parse "ELW 512" -> collection="ELW", number="512"
        parts = hymn_num.split()
        if len(parts) == 2:
            try:
                img_path = fetch_hymn_image(
                    client, parts[1], collection=parts[0],
                )
                communion_hymn_image_uri = _image_to_data_uri(img_path)
            except (BulletinError, OSError):
                logger.warning("Could not fetch communion hymn image for %s",
                               hymn_num)

    env = setup_jinja_env()
    template = env.get_template("bulletin.html")
    ctx = _build_bulletin_context(
        day, config, season, communion_hymn_image_uri=communion_hymn_image_uri,
    )
    html_string = template.render(**ctx)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".bulletin_debug"
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "bulletin.html").write_text(html_string)

    # Render sequential half-pages (7" x 8.5") with auto-adjustment
    seq_path = output_path.parent / f".{output_path.stem}_sequential.pdf"
    bulletin_page_size = {"width": "7in", "height": "8.5in"}

    _auto_adjust_bulletin(html_string, seq_path, bulletin_page_size,
                          on_progress=on_progress)

    if on_progress is not None:
        on_progress("Assembling booklet...")

    # Find creed page in sequential PDF
    creed_page = _find_creed_page(seq_path)
    if creed_page:
        logger.info("Creed found on page %d of sequential bulletin", creed_page)
    else:
        logger.warning("Could not find creed page marker in bulletin")

    # Impose into booklet
    result = impose_booklet(seq_path, output_path)

    # Clean up sequential PDF unless keeping intermediates
    if not keep_intermediates and seq_path.exists():
        seq_path.unlink()

    page_count = count_pages(result)
    logger.info("Bulletin booklet PDF saved: %s (%s sheets)",
                result, page_count // 2 if page_count else "?")
    return result, creed_page

"""HTML-based document renderers using Jinja2 + Playwright.

Produces print-ready PDFs for:
  - Full with Hymns LARGE PRINT
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
from pathlib import Path

from bulletin_maker.exceptions import BulletinError, ContentNotFoundError
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading, ServiceConfig
from bulletin_maker.renderer.season import (
    LiturgicalSeason,
    detect_season,
    fill_seasonal_defaults,
)
from bulletin_maker.renderer.image_manager import (
    get_gospel_acclamation_image,
    get_setting_image,
)
from bulletin_maker.renderer.text_utils import (
    extract_book_name,
    group_psalm_verses,
    preprocess_html,
    strip_tags,
)
from bulletin_maker.renderer.filters import TEMPLATE_DIR, setup_jinja_env
from bulletin_maker.renderer.pdf_engine import (
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
    CHURCH_ADDRESS,
    CHURCH_NAME,
    COME_HOLY_SPIRIT,
    CONFESSION_AND_FORGIVENESS,
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
    gospel_raw = _get_reading(day, "gospel")
    if gospel_raw and gospel_raw.label.lower() == "gospel":
        return _reading_data(gospel_raw)
    if gospel_raw is None:
        for r in day.readings:
            if r.label.lower() == "gospel":
                return _reading_data(r)
    return None


def _build_psalm_data(day: DayContent) -> dict | None:
    """Build template-ready dict for the Psalm."""
    psalm_raw = _get_reading(day, "psalm")
    if not psalm_raw:
        return None
    psalm_num = psalm_raw.citation.replace("Psalm", "").replace("psalm", "").strip()
    return {
        "number": psalm_num,
        "intro": strip_tags(psalm_raw.intro) if psalm_raw.intro else "",
        "verses": group_psalm_verses(psalm_raw.text_html),
    }


# ══════════════════════════════════════════════════════════════════════
# Context builders
# ══════════════════════════════════════════════════════════════════════

def _build_large_print_context(day: DayContent, config: ServiceConfig) -> dict:
    """Build the full template context for the Large Print document."""
    season = detect_season(day.title)
    fill_seasonal_defaults(config, season)

    # Readings
    first_reading = _reading_data(_get_reading(day, "first"))
    second_reading = _reading_data(_get_reading(day, "second"))
    gospel_entry = _build_gospel_entry(day)
    psalm_data = _build_psalm_data(day)

    # Gospel Acclamation image
    ga_image_uri = ""
    try:
        path = get_gospel_acclamation_image(season)
        ga_image_uri = _image_to_data_uri(path)
    except FileNotFoundError:
        logger.warning("Gospel Acclamation image not found for season %s", season)
    except ImportError:
        logger.warning("Pillow not installed — cannot convert GA image to data URI")

    ga_text = ""
    if day.gospel_acclamation:
        ga_text = strip_tags(preprocess_html(day.gospel_acclamation))

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

    # CSS
    css = (TEMPLATE_DIR / "large_print.css").read_text()

    return {
        # CSS
        "css": css,

        # Cover
        "church_name": CHURCH_NAME,
        "church_address": CHURCH_ADDRESS,
        "cover_image_uri": cover_image_uri,
        "date_display": config.date_display,
        "day_name": _extract_day_name(day.title),

        # Welcome
        "welcome_message": WELCOME_MESSAGE,
        "standing_instructions": STANDING_INSTRUCTIONS,

        # Gathering
        "choral_title": config.choral_title,
        "confession_entries": CONFESSION_AND_FORGIVENESS,
        "gathering_hymn": config.gathering_hymn,

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
        "ga_text_fallback": ga_text,
        "gospel": gospel_entry,

        # Sermon
        "sermon_hymn": config.sermon_hymn,

        # Creed
        "creed_name": creed_name,
        "creed_stanzas": _split_stanzas(creed_text),

        # Prayers
        "prayers_response": prayers_response,

        # Offering
        "offertory_hymn_verses": OFFERTORY_HYMN_VERSES,

        # Great Thanksgiving
        "great_thanksgiving_dialog": GREAT_THANKSGIVING_DIALOG,
        "great_thanksgiving_preface": GREAT_THANKSGIVING_PREFACE,

        # Sanctus
        "sanctus_stanzas": _split_stanzas(SANCTUS),

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

        # Agnus Dei
        "agnus_dei_stanzas": _split_agnus_dei(),

        # Communion Hymn
        "communion_hymn": config.communion_hymn,

        # Closing
        "nunc_dimittis_lines": NUNC_DIMITTIS.split("\n"),
        "aaronic_blessing_lines": AARONIC_BLESSING.split("\n"),
        "sending_hymn": config.sending_hymn,
    }


def _build_pulpit_scripture_context(day: DayContent, date_display: str) -> dict:
    """Build template context for the Pulpit Scripture document."""
    first_reading = _reading_data(_get_reading(day, "first"))
    second_reading = _reading_data(_get_reading(day, "second"))
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
    *,
    communion_hymn_image_uri: str = "",
) -> dict:
    """Build template context for the standard Bulletin for Congregation."""
    season = detect_season(day.title)
    fill_seasonal_defaults(config, season)

    # Readings
    first_reading = _reading_data(_get_reading(day, "first"))
    second_reading = _reading_data(_get_reading(day, "second"))
    gospel_entry = _build_gospel_entry(day)
    psalm_data = _build_psalm_data(day)

    # Gospel Acclamation image
    ga_image_uri = ""
    try:
        path = get_gospel_acclamation_image(season)
        ga_image_uri = _image_to_data_uri(path)
    except FileNotFoundError:
        logger.warning("GA image not found for season %s", season)

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

    css = (TEMPLATE_DIR / "bulletin.css").read_text()

    return {
        # CSS
        "css": css,

        # Cover
        "church_name": CHURCH_NAME,
        "church_address": CHURCH_ADDRESS,
        "cover_image_uri": cover_image_uri,
        "date_display": config.date_display,
        "day_name": _extract_day_name(day.title),

        # Welcome
        "welcome_message": WELCOME_MESSAGE,
        "standing_instructions": STANDING_INSTRUCTIONS,

        # Prelude/postlude
        "prelude_title": config.prelude_title,
        "prelude_performer": config.prelude_performer,
        "postlude_title": config.postlude_title,
        "postlude_performer": config.postlude_performer,
        "choral_title": config.choral_title,

        # Confession
        "show_confession": season != LiturgicalSeason.CHRISTMAS_EVE,
        "confession_entries": CONFESSION_AND_FORGIVENESS,

        # Notation images — setting pieces
        "kyrie_image_uri": kyrie_uri,
        "canticle_image_uri": canticle_uri,

        # Gathering hymn (title only)
        "gathering_hymn_title": _hymn_title_str(config.gathering_hymn),

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

        # Sermon hymn (title only)
        "sermon_hymn_title": _hymn_title_str(config.sermon_hymn),

        # Creed
        "creed_name": creed_name,
        "creed_stanzas": _split_stanzas(creed_text),

        # Prayers
        "prayers_response": prayers_response,

        # Offering
        "offertory_image_uri": "",  # text fallback for now
        "offertory_hymn_verses": OFFERTORY_HYMN_VERSES,

        # Great Thanksgiving
        "great_thanksgiving_image_uri": great_thanksgiving_uri,
        "great_thanksgiving_preface": GREAT_THANKSGIVING_PREFACE,

        # Sanctus
        "sanctus_image_uri": sanctus_uri,

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
        "memorial_acclamation_image_uri": memorial_acc_uri,
        "amen_image_uri": amen_uri,
        "eucharistic_prayer_closing_stanzas": _split_stanzas(EUCHARISTIC_PRAYER_CLOSING),
        "come_holy_spirit": COME_HOLY_SPIRIT,

        # Lord's Prayer
        "lords_prayer_stanzas": _split_stanzas(LORDS_PRAYER),

        # Invitation to Communion
        "invitation_to_communion_text": invitation_text,

        # Agnus Dei
        "agnus_dei_image_uri": agnus_dei_uri,

        # Communion Hymn
        "communion_hymn_title": _hymn_title_str(config.communion_hymn),
        "communion_hymn_image_uri": communion_hymn_image_uri,

        # Nunc Dimittis
        "nunc_dimittis_image_uri": nunc_dimittis_uri,

        # Blessing
        "aaronic_blessing_lines": AARONIC_BLESSING.split("\n"),

        # Sending hymn (title only)
        "sending_hymn_title": _hymn_title_str(config.sending_hymn),
    }


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

def generate_large_print(
    day: DayContent,
    config: ServiceConfig,
    output_path: Path,
    *,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Full with Hymns LARGE PRINT PDF via HTML + Playwright.

    Args:
        day: S&S content for the Sunday.
        config: User-provided service configuration.
        output_path: Where to save the final PDF (suffix forced to .pdf).
        keep_intermediates: If True, save debug HTML alongside the PDF.

    Returns:
        Path to the saved PDF file.
    """
    env = setup_jinja_env()
    template = env.get_template("large_print.html")
    ctx = _build_large_print_context(day, config)
    html_string = template.render(**ctx)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".lp_debug"
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "large_print.html").write_text(html_string)

    result = render_to_pdf(
        html_string,
        output_path,
        margins={
            "top": "0.25in",
            "bottom": "0.5in",
            "left": "0.438in",
            "right": "0.438in",
        },
        display_footer=True,
    )

    logger.info("Large Print PDF saved: %s", result)
    return result


def generate_pulpit_scripture(
    day: DayContent,
    date_display: str,
    output_path: Path,
    *,
    keep_intermediates: bool = False,
) -> Path:
    """Generate the Pulpit Scripture PDF via HTML + Playwright."""
    if not day.readings:
        raise ContentNotFoundError("DayContent has no readings.")

    env = setup_jinja_env()
    template = env.get_template("pulpit_scripture.html")
    ctx = _build_pulpit_scripture_context(day, date_display)
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
        margins={
            "top": "0.85in",
            "bottom": "0.4in",
            "left": "0.5in",
            "right": "0.5in",
        },
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
        margins={
            "top": "0.85in",
            "bottom": "0.4in",
            "left": "0.5in",
            "right": "0.5in",
        },
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
    client: object | None = None,
    keep_intermediates: bool = False,
) -> tuple[Path, int | None]:
    """Generate the standard Bulletin for Congregation as a booklet PDF.

    Renders sequential half-pages (7"x8.5"), finds the creed page number,
    then imposes into saddle-stitched booklet spreads on legal landscape.

    Args:
        day: S&S content for the Sunday.
        config: User-provided service configuration.
        output_path: Where to save the final booklet PDF.
        client: Optional authenticated SundaysClient for fetching the
            communion hymn notation image dynamically.
        keep_intermediates: If True, save debug HTML and sequential PDF.

    Returns:
        Tuple of (path to booklet PDF, creed page number or None).
    """
    from bulletin_maker.renderer.image_manager import fetch_hymn_image

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
        day, config, communion_hymn_image_uri=communion_hymn_image_uri,
    )
    html_string = template.render(**ctx)

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if keep_intermediates:
        debug_dir = output_path.parent / ".bulletin_debug"
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "bulletin.html").write_text(html_string)

    # Render sequential half-pages (7" x 8.5")
    seq_path = output_path.parent / f".{output_path.stem}_sequential.pdf"
    render_to_pdf(
        html_string,
        seq_path,
        margins={
            "top": "0.3in",
            "bottom": "0.35in",
            "left": "0.35in",
            "right": "0.35in",
        },
        display_footer=True,
        page_size={"width": "7in", "height": "8.5in"},
    )

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

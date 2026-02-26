"""Data models for Sundays & Seasons content."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bulletin_maker.renderer.season import PrefaceType


@dataclass
class Reading:
    label: str        # e.g. "First Reading", "Psalm", "Gospel"
    citation: str     # e.g. "Genesis 2:15-17; 3:1-7"
    intro: str        # italic intro paragraph
    text_html: str    # raw HTML of the reading text


@dataclass
class DayContent:
    date: str
    title: str                          # e.g. "First Sunday in Lent, Year A"
    introduction: str
    confession_html: str
    prayer_of_the_day_html: str
    gospel_acclamation: str
    readings: list[Reading] = field(default_factory=list)
    prayers_html: str = ""              # prayers of intercession HTML
    offering_prayer_html: str = ""      # "O God, maker of heaven and earth..."
    invitation_to_communion: str = ""   # "Taste and see that the Lord is good."
    prayer_after_communion_html: str = ""
    blessing_html: str = ""             # Aaronic blessing text
    dismissal_html: str = ""            # "Go in peace..."
    raw_html: str = ""                  # full rightpanel HTML for fallback


@dataclass
class HymnResult:
    atom_id: str
    title: str
    hymn_numbers: str = ""              # e.g. "ELW 504, TFF 133, LBW 229"
    harmony_atom_id: str = ""           # atomId for harmony download
    melody_atom_id: str = ""            # atomId for melody download
    words_atom_id: str = ""             # atomId for words download
    harmony_image_url: str = ""
    melody_image_url: str = ""
    atom_code: str = ""
    copyright_html: str = ""


@dataclass
class HymnLyrics:
    """Hymn lyrics for Large Print document.

    Can be populated via ``SundaysClient.fetch_hymn_lyrics()`` or
    constructed manually.
    """
    number: str              # e.g. "ELW 335"
    title: str               # e.g. "Jesus, Keep Me Near the Cross"
    verses: list[str]        # Each verse as text with line breaks
    refrain: str = ""        # Refrain text (empty if none)
    copyright: str = ""      # Copyright line(s)


@dataclass
class ServiceConfig:
    """User inputs for a Sunday service — drives document generation.

    Liturgical choice fields (include_kyrie, canticle, creed_type, etc.)
    default to None meaning "use seasonal default".  The wizard UI
    pre-fills these from SeasonalConfig, and the user can override.
    Call ``fill_seasonal_defaults()`` before rendering to resolve Nones.
    """
    date: str                           # "2026-2-22" (for S&S API)
    date_display: str                   # "February 22, 2026" (for headers)

    # ── Liturgical choices (None = use seasonal default) ──
    creed_type: Optional[str] = None            # "apostles" or "nicene"
    include_kyrie: Optional[bool] = None        # Show Kyrie?
    canticle: Optional[str] = None              # "glory_to_god", "this_is_the_feast", or "none"
    eucharistic_form: Optional[str] = None      # "short", "poetic", or "extended"
    include_memorial_acclamation: Optional[bool] = None  # Memorial Acclamation in EP?
    preface: Optional[PrefaceType] = None       # Preface type. None = seasonal default.

    # ── Liturgical texts (None = use S&S default from DayContent) ──
    confession_entries: Optional[list] = None       # list of (DialogRole, text) tuples
    offering_prayer_text: Optional[str] = None      # plain text
    prayer_after_communion_text: Optional[str] = None
    blessing_text: Optional[str] = None             # newline-separated lines
    dismissal_entries: Optional[list] = None          # list of (DialogRole, text) tuples

    # ── Hymns ──
    gathering_hymn: Optional[HymnLyrics] = None
    sermon_hymn: Optional[HymnLyrics] = None
    communion_hymn: Optional[HymnLyrics] = None
    sending_hymn: Optional[HymnLyrics] = None

    # ── Other service details ──
    prelude_title: str = ""
    prelude_performer: str = ""
    postlude_title: str = ""
    postlude_performer: str = ""
    choral_title: str = ""
    cover_image: str = ""                   # Path to seasonal logo image

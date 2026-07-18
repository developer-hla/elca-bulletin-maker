"""Data models for Sundays & Seasons content."""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Reading slot constants ───────────────────────────────────────────
# Used as keys for reading lookups, overrides, and template variables.
SLOT_FIRST = "first"
SLOT_SECOND = "second"
SLOT_PSALM = "psalm"
SLOT_GOSPEL = "gospel"

# Reading labels a normal Sunday DayTexts page provides
EXPECTED_READING_LABELS = ("First Reading", "Psalm", "Second Reading", "Gospel")


# ── Canticle slug constants ──────────────────────────────────────────
# Values for ServiceConfig.canticle. Also used as image_manager keys.
# UI radio values (index.html) and asset catalog (catalog.json) match
# these strings as the contract.
CANTICLE_GLORY_TO_GOD = "glory_to_god"
CANTICLE_THIS_IS_THE_FEAST = "this_is_the_feast"
CANTICLE_NONE = "none"


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

    def content_warnings(self) -> list[str]:
        """Detect expected sections that came back empty from S&S.

        Scraping failures manifest as empty strings, not errors — a markup
        change on the S&S site would otherwise print as silent blank
        sections in the bulletin. Returns human-readable warnings.
        """
        warnings: list[str] = []

        found_labels = {r.label for r in self.readings}
        missing = [
            label for label in EXPECTED_READING_LABELS
            if label not in found_labels
        ]
        if len(missing) == len(EXPECTED_READING_LABELS):
            warnings.append("No readings were found for this date.")
        elif missing:
            warnings.append("Missing readings: " + ", ".join(missing) + ".")

        if not self.prayers_html:
            warnings.append(
                "Prayers of Intercession are missing — "
                "the Pulpit Prayers document cannot be generated."
            )
        if not self.prayer_of_the_day_html:
            warnings.append("Prayer of the Day is missing.")

        fallback_sections = [
            ("Confession", self.confession_html),
            ("Offering Prayer", self.offering_prayer_html),
            ("Prayer after Communion", self.prayer_after_communion_html),
            ("Blessing", self.blessing_html),
            ("Dismissal", self.dismissal_html),
        ]
        empty = [name for name, value in fallback_sections if not value]
        if empty:
            warnings.append(
                "Not provided by S&S this week (standard texts will be "
                "used): " + ", ".join(empty) + "."
            )
        return warnings


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
    verse_label: str = ""    # e.g. "Verses 1, 3-5" when subset selected

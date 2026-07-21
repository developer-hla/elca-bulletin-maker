"""Core domain models — the service configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

from bulletin_maker.sns.models import HymnLyrics

if TYPE_CHECKING:
    from bulletin_maker.renderer.season import PrefaceType


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

    # ── Rite selection (None = the bundled ELW Sunday Communion rite) ──
    rite_id: Optional[str] = None

    # ── Liturgical choices (None = use seasonal default) ──
    creed_type: Optional[str] = None            # "apostles" or "nicene"
    include_kyrie: Optional[bool] = None        # Show Kyrie?
    canticle: Optional[str] = None              # CANTICLE_GLORY_TO_GOD, CANTICLE_THIS_IS_THE_FEAST, or CANTICLE_NONE
    eucharistic_form: Optional[str] = None      # "short" or "extended"
    include_memorial_acclamation: Optional[bool] = None  # Memorial Acclamation in EP?
    memorial_acclamation_mode: Optional[str] = None       # "sung" or "spoken"
    preface: Optional[PrefaceType] = None       # None = Sundays/Ordinary Time (not seasonal)

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

    # ── Section toggles (None = use seasonal default) ──
    show_confession: Optional[bool] = None      # Show Confession section?
    show_greeting: Optional[bool] = None        # Show Greeting (P/C dialog after Gathering Hymn)?
    show_nunc_dimittis: Optional[bool] = None   # Show Nunc Dimittis?

    # ── Reading overrides — custom passages fetched via PassageSearch ──
    # Dict mapping slot ("first", "second", "psalm", "gospel") to Reading
    reading_overrides: Optional[dict] = None

    # ── Baptism ──
    include_baptism: bool = False
    baptism_candidate_names: str = ""           # Comma-separated names

    # ── Per-service rite variables (RB-3b) ──
    # Values for a rite's declared meta.variables, keyed by variable key.
    # Substituted into block text ({{key}}) at render time.  Empty for every
    # rite that declares no variables (the default), so output is unchanged.
    variables: Dict[str, str] = field(default_factory=dict)

    # ── Other service details ──
    prelude_title: str = ""
    prelude_performer: str = ""
    prelude_composer: str = ""
    offertory_type: str = "offertory"              # "offertory" or "choral_anthem"
    offertory_title: str = ""
    offertory_performer: str = ""
    offertory_composer: str = ""
    postlude_title: str = ""
    postlude_performer: str = ""
    postlude_composer: str = ""
    choral_title: str = ""
    choral_composer: str = ""
    cover_image: str = ""                   # Path to seasonal logo image

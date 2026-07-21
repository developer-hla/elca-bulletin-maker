"""Stable text-catalog keys -> fixed liturgical texts (LWS-0b).

This is the resolution target for a block's ``text_ref`` / ``fallback`` /
``text_fallback``.  Every key maps to a constant that already lives in
``renderer/static_text.py`` — the constants are *imported*, never copied,
so the text has a single source of truth.

Key conventions:
  ``elw.*``   — ELW ordo / Setting Two wording (copyrighted; lawfully
                distributed only to a licensed deployment — see LWS-4).
  ``house.*`` — Ascension house texts that override the S&S/ELW default.
  ``pd.*``    — genuinely public-domain texts (1662/1928 BCP, KJV, pre-1929
                hymn translations); bundle-able and distributable
                UNCONDITIONALLY.  Imported from ``renderer/pd_text.py``, which
                is kept separate from the ELW-copyrighted ``static_text.py`` so
                a future entitlement layer can gate the latter while always
                shipping the PD fallback.  See
                ``docs/research/2026-07-liturgy-strategy/10-pd-text-sourcing.md``.

A value is whatever shape the underlying constant is: a plain string
(creeds, Sanctus, ...), a list of ``(DialogRole, text)`` tuples (greeting,
kyrie dialog, ...), a list of verse strings (offertory hymn), or a dict
(canticle texts).  Callers that only need existence use :func:`has_text` /
:func:`text_keys`; :func:`get_text` returns the constant and fails fast on
an unknown key.

The per-church ``church_texts`` table (persistent, editable) arrives in
LWS-1 and will layer over this catalog; it is intentionally absent here.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from bulletin_maker.core.pd_text import (
    PD_BENEDICTUS_KJV,
    PD_COMPLINE_OPEN,
    PD_GENERAL_CONFESSION_BCP,
    PD_GLORIA_PATRI,
    PD_INTO_THY_HANDS,
    PD_MAGNIFICAT_KJV,
    PD_NUNC_DIMITTIS_KJV,
    PD_PHOS_HILARON_BRIDGES,
    PD_TE_DEUM_BCP1662,
    PD_VERSICLE_MAKE_SPEED,
    PD_VERSICLE_OPEN_LIPS,
)
from bulletin_maker.core.static_text import (
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
    COME_HOLY_SPIRIT,
    CONFESSION_AND_FORGIVENESS,
    DEFAULT_PRAYERS_CALL,
    DEFAULT_PRAYERS_RESPONSE,
    DISMISSAL,
    DISMISSAL_ENTRIES,
    EUCHARISTIC_PRAYER_CLOSING,
    EUCHARISTIC_PRAYER_EXTENDED,
    GLORY_TO_GOD_TEXT,
    GREAT_THANKSGIVING_DIALOG,
    GREAT_THANKSGIVING_PREFACE,
    GREAT_THANKSGIVING_PREFACE_SHORT,
    GREETING,
    INVITATION_TO_COMMUNION,
    INVITATION_TO_LENT,
    KYRIE_DIALOG,
    LORDS_PRAYER,
    MEMORIAL_ACCLAMATION,
    NICENE_CREED,
    NUNC_DIMITTIS,
    OFFERTORY_HYMN_VERSES,
    SANCTUS,
    THIS_IS_THE_FEAST_TEXT,
    WORDS_OF_INSTITUTION,
)

# Stable key -> constant.  Keep this the single mapping; do not inline text.
TEXT_CATALOG: Dict[str, Any] = {
    # ── Gathering ──
    "elw.confession_form_a": CONFESSION_AND_FORGIVENESS,
    "elw.greeting": GREETING,
    "elw.kyrie_dialog": KYRIE_DIALOG,
    "elw.glory_to_god": GLORY_TO_GOD_TEXT,
    "elw.this_is_the_feast": THIS_IS_THE_FEAST_TEXT,
    "elw.invitation_to_lent": INVITATION_TO_LENT,
    # ── Word ──
    "elw.nicene_creed": NICENE_CREED,
    "elw.apostles_creed": APOSTLES_CREED,
    "elw.default_prayers_call": DEFAULT_PRAYERS_CALL,
    "elw.default_prayers_response": DEFAULT_PRAYERS_RESPONSE,
    # ── Meal ──
    "elw.offertory_hymn_verses": OFFERTORY_HYMN_VERSES,
    "elw.great_thanksgiving_dialog": GREAT_THANKSGIVING_DIALOG,
    "elw.great_thanksgiving_preface": GREAT_THANKSGIVING_PREFACE,
    "elw.great_thanksgiving_preface_short": GREAT_THANKSGIVING_PREFACE_SHORT,
    "elw.sanctus": SANCTUS,
    "elw.eucharistic_prayer_extended": EUCHARISTIC_PRAYER_EXTENDED,
    "elw.words_of_institution": WORDS_OF_INSTITUTION,
    "elw.memorial_acclamation": MEMORIAL_ACCLAMATION,
    "elw.eucharistic_prayer_closing": EUCHARISTIC_PRAYER_CLOSING,
    "elw.come_holy_spirit": COME_HOLY_SPIRIT,
    "elw.lords_prayer": LORDS_PRAYER,
    "house.invitation_to_communion": INVITATION_TO_COMMUNION,
    "elw.agnus_dei": AGNUS_DEI,
    # ── Sending ──
    "elw.nunc_dimittis": NUNC_DIMITTIS,
    "elw.aaronic_blessing": AARONIC_BLESSING,
    "elw.dismissal": DISMISSAL_ENTRIES,
    "elw.dismissal_text": DISMISSAL,
    # ── Holy Baptism module ──
    "elw.baptism_presentation": BAPTISM_PRESENTATION,
    "elw.baptism_renunciation": BAPTISM_RENUNCIATION,
    "elw.baptism_profession": BAPTISM_PROFESSION,
    "elw.baptism_flood_prayer": BAPTISM_FLOOD_PRAYER,
    "elw.baptism_formula": BAPTISM_FORMULA,
    "elw.baptism_welcome": BAPTISM_WELCOME,
    "elw.baptism_welcome_response": BAPTISM_WELCOME_RESPONSE,
    # ── Daily Office (public domain — bundle-able unconditionally) ──
    "pd.benedictus_kjv": PD_BENEDICTUS_KJV,
    "pd.magnificat_kjv": PD_MAGNIFICAT_KJV,
    "pd.nunc_dimittis_kjv": PD_NUNC_DIMITTIS_KJV,
    "pd.te_deum_bcp1662": PD_TE_DEUM_BCP1662,
    "pd.phos_hilaron_bridges": PD_PHOS_HILARON_BRIDGES,
    "pd.versicle_open_lips": PD_VERSICLE_OPEN_LIPS,
    "pd.versicle_make_speed": PD_VERSICLE_MAKE_SPEED,
    "pd.gloria_patri": PD_GLORIA_PATRI,
    "pd.general_confession_bcp": PD_GENERAL_CONFESSION_BCP,
    "pd.compline_open": PD_COMPLINE_OPEN,
    "pd.into_thy_hands": PD_INTO_THY_HANDS,
}


class UnknownTextKey(KeyError):
    """Raised by :func:`get_text` when a key is not in the catalog."""


def get_text(key: str) -> Any:
    """Return the constant for ``key``; fail fast on an unknown key."""
    try:
        return TEXT_CATALOG[key]
    except KeyError:
        raise UnknownTextKey(
            "unknown text key %r (there are %d known keys)"
            % (key, len(TEXT_CATALOG))
        ) from None


def has_text(key: str) -> bool:
    """Return True if ``key`` resolves in the catalog."""
    return key in TEXT_CATALOG


def text_keys() -> FrozenSet[str]:
    """Return the full set of catalog keys (for validation/completeness)."""
    return frozenset(TEXT_CATALOG)

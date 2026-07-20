"""Entitlement-gated content-source resolution (CS-1).

The single chokepoint that turns a text-catalog key into its rendered value,
gated by the church's Sundays & Seasons entitlement.  A church WITH a validated
S&S link (``entitled=True`` — the default, and every parity/layout fixture)
resolves the ELW / Setting Two wording from ``text_catalog`` exactly as before;
a church WITHOUT one falls back to the public-domain equivalent (``pd_text`` via
:data:`ELW_TO_PD`) or, where no PD equivalent exists, a clear placeholder — and
NEVER receives the copyrighted ELW text.

This is the "bundle-gated" phase (doc 11, CS-1): the ELW text stays in the repo
but is only SERVED to entitled churches.  Pulling the ordinary live from S&S is
CS-2.  See ``docs/research/2026-07-liturgy-strategy/11-content-source-layer.md``.

Layering: core / renderer only — this module must NOT import ``web`` (same rule
as ``core/calendar.py``).  The web / generate layer supplies ``entitled``
(``sns_username`` non-empty) and ``church_texts`` via :class:`ContentContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

# ``text_catalog`` is imported lazily inside :func:`resolve_text`: it pulls in
# ``renderer.pd_text``, whose package ``__init__`` eagerly loads the renderer
# (which imports this module), so a top-level import would be circular.  The
# codebase already imports ``text_catalog`` lazily for the same reason
# (``core/rite.py``).

ENTITLEMENT_PLACEHOLDER = "[This text requires a Sundays & Seasons subscription]"

# Copyrighted (ELW / house) catalog key -> a GENUINE public-domain equivalent
# key in the same catalog (backed by ``pd_text.py``).  Only real equivalents
# belong here; a key that is ABSENT falls through to the placeholder rather than
# a fabricated substitute.  This map may grow (doc 10 [PD-BUNDLE] manifest);
# completeness is not required for CS-1, correctness of the gate is.
ELW_TO_PD: Dict[str, str] = {
    # Song of Simeon — ELW contemporary wording -> KJV (Luke 2:29-32).
    "elw.nunc_dimittis": "pd.nunc_dimittis_kjv",
    # Confession -> 1662 BCP General Confession (a working PD substitute,
    # NOT verbatim ELW — see doc 10 §Flagged).
    "elw.confession_form_a": "pd.general_confession_bcp",
}

# Scripture / reading resolution is intentionally NOT gated here (CS-1).
# Readings already resolve NRSVUE-via-S&S with a KJV/WEB PD fallback through
# content_service; pulling NRSVUE for the daily-office canticles is the CS-2
# seam (doc 11) and plugs in as another entitled/PD pair, not here.


@dataclass
class ContentContext:
    """Per-generation entitlement context threaded to the resolver.

    ``entitled`` defaults to True so the offline / parity / generate path is
    byte-identical to pre-CS-1.  ``church_texts`` maps a catalog key to the
    church's saved override value (LWS-1); an override wins over both the ELW
    and the PD source.
    """

    entitled: bool = True
    church_texts: Dict[str, Any] = field(default_factory=dict)


def _is_public_domain_key(key: str) -> bool:
    return key.startswith("pd.")


def resolve_text(key: str, context: ContentContext) -> Any:
    """Resolve a text-catalog ``key`` under an entitlement ``context``.

    Priority: the church's saved override -> the entitled catalog value (ELW /
    house wording, or any ``pd.*`` key, which is always allowed) -> the PD
    equivalent -> a placeholder.  Never returns the copyrighted ELW value to an
    unentitled church.
    """
    from bulletin_maker.core.text_catalog import get_text

    override = context.church_texts.get(key)
    if override:
        return override
    if context.entitled or _is_public_domain_key(key):
        return get_text(key)
    pd_key = ELW_TO_PD.get(key)
    if pd_key is not None:
        return get_text(pd_key)
    return ENTITLEMENT_PLACEHOLDER

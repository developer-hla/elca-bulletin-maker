"""Entitlement gate for the content-source layer (CS-1).

Verifies the copyright gate that ``core/content_source.resolve_text`` enforces:
an entitled church resolves the exact ELW wording; an unentitled church gets a
public-domain equivalent or a clear placeholder and NEVER the copyrighted ELW
text; a church's saved override wins over both.  The resolver must also stay in
the core/renderer layer (no ``web`` import).
"""

from __future__ import annotations

from pathlib import Path

from bulletin_maker.core.content_source import (
    ELW_TO_PD,
    ENTITLEMENT_PLACEHOLDER,
    ContentContext,
    resolve_text,
)
from bulletin_maker.core.text_catalog import get_text, text_keys

ENTITLED = ContentContext(entitled=True)
UNENTITLED = ContentContext(entitled=False)

# A representative sample of gated keys spanning creeds, ordinary, dialog, and
# prayers — every one is ELW/AF-copyrighted wording bundled in static_text.py.
SAMPLE_GATED_KEYS = [
    "elw.nicene_creed",
    "elw.apostles_creed",
    "elw.sanctus",
    "elw.kyrie_dialog",
    "elw.greeting",
    "elw.words_of_institution",
    "elw.lords_prayer",
    "elw.glory_to_god",
]

ELW_KEYS = sorted(k for k in text_keys() if k.startswith("elw."))


def test_entitled_resolves_exact_elw_text():
    """An entitled church gets the byte-identical catalog (ELW) value."""
    for key in SAMPLE_GATED_KEYS:
        assert resolve_text(key, ENTITLED) is get_text(key)


def test_unentitled_uses_pd_equivalent_where_mapped():
    """Keys with a genuine PD equivalent resolve to the PD catalog value."""
    assert ELW_TO_PD, "expected at least one elw->pd mapping"
    for elw_key, pd_key in ELW_TO_PD.items():
        resolved = resolve_text(elw_key, UNENTITLED)
        assert resolved is get_text(pd_key)
        assert resolved is not get_text(elw_key)


def test_unentitled_gets_placeholder_when_no_pd_equivalent():
    """A gated key with no PD equivalent resolves to a clear placeholder,
    never empty-silent and never the copyrighted text."""
    unmapped = [k for k in SAMPLE_GATED_KEYS if k not in ELW_TO_PD]
    assert unmapped, "sample should include keys without a PD equivalent"
    for key in unmapped:
        resolved = resolve_text(key, UNENTITLED)
        assert resolved == ENTITLEMENT_PLACEHOLDER
        assert resolved  # not empty


def test_unentitled_never_leaks_elw_text_for_any_gated_key():
    """Across EVERY elw.* catalog key, the unentitled result is never the ELW
    value and never contains the ELW copyrighted string as a substring."""
    for key in ELW_KEYS:
        elw_value = get_text(key)
        resolved = resolve_text(key, UNENTITLED)
        assert resolved is not elw_value
        assert resolved != elw_value
        assert str(elw_value) not in str(resolved)


def test_church_override_wins_over_elw_and_pd():
    """A saved church override is returned for both entitlement states and
    takes priority over the ELW value and the PD equivalent."""
    override = "OUR CONGREGATION'S OWN WORDING"
    for base in (ENTITLED, UNENTITLED):
        ctx = ContentContext(
            entitled=base.entitled, church_texts={"elw.sanctus": override}
        )
        assert resolve_text("elw.sanctus", ctx) == override

    # Override also beats a key that has a PD equivalent.
    ctx = ContentContext(
        entitled=False, church_texts={"elw.nunc_dimittis": override}
    )
    assert resolve_text("elw.nunc_dimittis", ctx) == override


def test_public_domain_keys_always_resolve_even_unentitled():
    """pd.* keys are bundle-able unconditionally, so they resolve for an
    unentitled church exactly as for an entitled one."""
    for key in (k for k in text_keys() if k.startswith("pd.")):
        assert resolve_text(key, UNENTITLED) is get_text(key)
        assert resolve_text(key, ENTITLED) is get_text(key)


def test_default_context_is_entitled():
    """The default context preserves the pre-CS-1 behavior (ELW served)."""
    assert ContentContext().entitled is True
    assert resolve_text("elw.nicene_creed", ContentContext()) is get_text(
        "elw.nicene_creed"
    )


def test_resolver_does_not_import_web():
    """Layering: the content-source resolver lives in core and must never
    depend on the web layer (same rule as core/calendar.py)."""
    import bulletin_maker.core.content_source as module

    source = Path(module.__file__).read_text()
    assert "bulletin_maker.web" not in source
    assert "import web" not in source

"""AC-1: embedded literal_text / dialogue text_refs resolve through the
entitlement gate, not the ungated catalog.

Before AC-1 the render path had two text-resolution mechanisms; these helpers
used the UNGATED ``text_catalog.get_text``, so an embedded block referencing
copyrighted ELW wording would render it to an unentitled church. They now go
through the gated ``content_source.resolve_text``: byte-identical for an
entitled church (parity), gated to a PD fallback / placeholder otherwise.
"""
from __future__ import annotations

import bulletin_maker.renderer  # noqa: F401  (warm the cold-import cycle)
from bulletin_maker.core.content_source import (
    ENTITLEMENT_PLACEHOLDER,
    ContentContext,
)
from bulletin_maker.core.text_catalog import get_text
from bulletin_maker.renderer.rite_resolver import _dialogue_lines, _literal_text

ENTITLED = ContentContext(entitled=True)
UNENTITLED = ContentContext(entitled=False)


def test_embedded_literal_text_is_byte_identical_when_entitled():
    data = {"text_ref": "elw.nicene_creed"}
    assert _literal_text(data, {}, ENTITLED) == get_text("elw.nicene_creed")


def test_embedded_literal_text_gated_when_unentitled():
    data = {"text_ref": "elw.nicene_creed"}
    gated = _literal_text(data, {}, UNENTITLED)
    assert gated != get_text("elw.nicene_creed")
    assert gated == ENTITLEMENT_PLACEHOLDER


def test_embedded_pd_literal_text_always_renders():
    # A public-domain key is always allowed — same value entitled or not.
    data = {"text_ref": "pd.benedictus_kjv"}
    assert _literal_text(data, {}, ENTITLED) == get_text("pd.benedictus_kjv")
    assert _literal_text(data, {}, UNENTITLED) == get_text("pd.benedictus_kjv")


def test_embedded_dialogue_gated_when_unentitled():
    data = {"text_ref": "elw.confession_form_a"}
    entitled = _dialogue_lines(data, {}, ENTITLED)
    unentitled = _dialogue_lines(data, {}, UNENTITLED)
    assert all("text" in ln and "role" in ln for ln in entitled)
    # Unentitled must not receive the entitled ELW wording.
    assert entitled != unentitled

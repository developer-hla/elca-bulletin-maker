"""Generic child-rite / module embedding (RB-3a).

A ``module_ref`` block that is *not* macro-rendered (i.e. anything but the
baptism module) expands, in ``rite_resolver``, into the referenced module's
condition-filtered blocks.  Those embedded blocks are tagged
``{"embedded": True, "type": ...}`` and render generically **by type** via the
``render_block`` macro — so any module is embeddable, without an id-dispatch
case per block.  The baptism module_ref stays on its bespoke macro, so every
existing rite is byte-identical (proven by the parity/layout suites).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from bulletin_maker.core.library import HOLY_BAPTISM_MODULE_ID, load_modules
from bulletin_maker.core.rite import Block, Condition, Rite, RiteModule
from bulletin_maker.renderer.filters import setup_jinja_env
from bulletin_maker.renderer.rite_resolver import (
    RiteEmbedError,
    _MAX_EMBED_DEPTH,
    _resolve_units,
)

TEST_MODULE_ID = "test_embed_module"


def _context(**toggles: bool) -> Dict[str, Any]:
    return {"season": "none", "feasts": [], "toggles": toggles}


def _test_module() -> RiteModule:
    """A small module: heading + literal_text + dialogue (+ a gated block)."""
    return RiteModule(
        id=TEST_MODULE_ID,
        name="Test Embed Module",
        blocks=[
            Block(id="tm_heading", type="heading", data={"text": "TEST RITE"}),
            Block(
                id="tm_literal",
                type="literal_text",
                data={"text": "Peace be with you.", "style": "plain"},
            ),
            Block(
                id="tm_dialogue",
                type="dialogue",
                data={
                    "lines": [
                        {"role": "leader", "text": "The Lord be with you."},
                        {"role": "congregation", "text": "And also with you."},
                    ]
                },
            ),
            Block(
                id="tm_gated",
                type="heading",
                condition=Condition(toggles={"show_extra": True}),
                data={"text": "EXTRA"},
            ),
        ],
    )


def _rite_embedding(module_id: str) -> Rite:
    return Rite(
        id="test_rite",
        name="Test Rite",
        blocks=[
            Block(id="opening", type="heading", data={"text": "OPENING"}),
            Block(
                id="child",
                type="module_ref",
                data={"module_id": module_id},
            ),
            Block(id="closing", type="heading", data={"text": "CLOSING"}),
        ],
    )


def _render(unit: Dict[str, Any], heading_class: str = "section-heading") -> str:
    macro = setup_jinja_env().get_template("_macros.html").module.render_block
    return str(macro(unit, heading_class=heading_class))


# ── Expansion ─────────────────────────────────────────────────────────


def test_module_ref_expands_to_module_blocks_by_type():
    modules = {TEST_MODULE_ID: _test_module()}
    units = _resolve_units(_rite_embedding(TEST_MODULE_ID), _context(), modules)

    # The module_ref is replaced, in place and in order, by the module's blocks
    # as embedded, type-tagged units.  The rite's own headings ("opening",
    # "closing") are now embedded too (heading is universally type-dispatched).
    ids = [u if isinstance(u, str) else u["id"] for u in units]
    assert ids == ["opening", "tm_heading", "tm_literal", "tm_dialogue", "closing"]
    assert "child" not in ids  # the module_ref block id itself is gone

    assert all(isinstance(u, dict) and u["embedded"] is True for u in units)
    module_units = [u for u in units if u["id"].startswith("tm_")]
    assert [u["type"] for u in module_units] == ["heading", "literal_text", "dialogue"]


# ── By-type rendering ─────────────────────────────────────────────────


def test_embedded_heading_renders_as_section_heading():
    modules = {TEST_MODULE_ID: _test_module()}
    units = _resolve_units(_rite_embedding(TEST_MODULE_ID), _context(), modules)
    heading = next(
        u for u in units if isinstance(u, dict) and u["id"] == "tm_heading"
    )

    html = _render(heading)
    assert '<div class="section-heading"><span>TEST RITE</span></div>' in html
    # Large print uses its own heading taxonomy.
    lp = _render(heading, heading_class="liturgy-heading")
    assert '<div class="liturgy-heading"><span>TEST RITE</span></div>' in lp


def test_embedded_literal_text_renders_as_paragraph():
    modules = {TEST_MODULE_ID: _test_module()}
    units = _resolve_units(_rite_embedding(TEST_MODULE_ID), _context(), modules)
    literal = next(
        u for u in units if isinstance(u, dict) and u["type"] == "literal_text"
    )

    html = _render(literal)
    assert "<p>Peace be with you.</p>" in html


def test_embedded_dialogue_renders_p_c_layout():
    modules = {TEST_MODULE_ID: _test_module()}
    units = _resolve_units(_rite_embedding(TEST_MODULE_ID), _context(), modules)
    dialogue = next(
        u for u in units if isinstance(u, dict) and u["type"] == "dialogue"
    )

    html = _render(dialogue)
    assert '<span class="role-label">P: </span>The Lord be with you.' in html
    assert "<strong>C: And also with you.</strong>" in html


# ── Condition gating on an embedded block ─────────────────────────────


def test_embedded_block_condition_gates_off():
    modules = {TEST_MODULE_ID: _test_module()}
    rite = _rite_embedding(TEST_MODULE_ID)

    off = _resolve_units(rite, _context(show_extra=False), modules)
    off_ids = [u["id"] for u in off if isinstance(u, dict)]
    assert "tm_gated" not in off_ids

    on = _resolve_units(rite, _context(show_extra=True), modules)
    on_ids = [u["id"] for u in on if isinstance(u, dict)]
    assert "tm_gated" in on_ids


# ── Recursion guard ───────────────────────────────────────────────────


def test_module_ref_cycle_raises_not_hangs():
    mod_a = RiteModule(
        id="mod_a",
        name="A",
        blocks=[Block(id="a_ref", type="module_ref", data={"module_id": "mod_b"})],
    )
    mod_b = RiteModule(
        id="mod_b",
        name="B",
        blocks=[Block(id="b_ref", type="module_ref", data={"module_id": "mod_a"})],
    )
    modules = {"mod_a": mod_a, "mod_b": mod_b}

    with pytest.raises(RiteEmbedError) as excinfo:
        _resolve_units(_rite_embedding("mod_a"), _context(), modules)
    assert "cycle" in str(excinfo.value)


def test_excessive_module_ref_depth_raises():
    depth = _MAX_EMBED_DEPTH + 2
    modules: Dict[str, RiteModule] = {}
    for level in range(depth):
        nxt = "chain_%d" % (level + 1)
        modules["chain_%d" % level] = RiteModule(
            id="chain_%d" % level,
            name="chain %d" % level,
            blocks=[
                Block(id="r_%d" % level, type="module_ref", data={"module_id": nxt})
            ],
        )
    # Terminal module so it is only depth, never a cycle, that trips the guard.
    modules["chain_%d" % depth] = RiteModule(
        id="chain_%d" % depth,
        name="terminal",
        blocks=[Block(id="leaf", type="heading", data={"text": "LEAF"})],
    )

    with pytest.raises(RiteEmbedError) as excinfo:
        _resolve_units(_rite_embedding("chain_0"), _context(), modules)
    assert "depth" in str(excinfo.value)


def test_unknown_module_ref_raises_clear_error():
    with pytest.raises(RiteEmbedError) as excinfo:
        _resolve_units(_rite_embedding("does_not_exist"), _context(), {})
    assert "unknown module" in str(excinfo.value)


# ── Dispatch invariants ───────────────────────────────────────────────


def test_top_level_non_embedded_types_stay_bare_ids():
    # Only `heading` (universal) and the occasion types embed at the top level;
    # every other type keeps its bare id (Sunday-id-dispatched), so a rite of
    # such blocks yields all bare ids.
    rite = Rite(
        id="plain",
        name="Plain",
        blocks=[
            Block(id="a", type="literal_text", data={"text": "A"}),
            Block(id="b", type="literal_text", data={"text": "B"}),
        ],
    )
    units = _resolve_units(rite, _context(), {})
    assert units == ["a", "b"]


def test_top_level_headings_embed_as_type_dispatched_units():
    # heading is universally type-dispatched: even a top-level Sunday-style
    # heading now embeds (proven byte-identical by the parity/layout suites).
    rite = Rite(
        id="plain_headings",
        name="Plain Headings",
        blocks=[
            Block(id="a", type="heading", data={"text": "A"}),
            Block(id="b", type="heading", data={"text": "B"}),
        ],
    )
    units = _resolve_units(rite, _context(), {})
    assert all(isinstance(u, dict) and u["type"] == "heading" for u in units)
    assert [u["id"] for u in units] == ["a", "b"]


def test_baptism_module_ref_stays_a_bare_id_not_expanded():
    # Baptism keeps its bespoke macro: its module_ref emits the bare id
    # "baptism" (id-dispatched), never generic embedded units.  The rite's own
    # heading is embedded (universal heading dispatch), but baptism stays bare.
    rite = Rite(
        id="with_baptism",
        name="With Baptism",
        blocks=[
            Block(id="opening", type="heading", data={"text": "OPENING"}),
            Block(
                id="baptism",
                type="module_ref",
                condition=Condition(toggles={"baptism": True}),
                data={"module_id": HOLY_BAPTISM_MODULE_ID},
            ),
        ],
    )
    units: List[Any] = _resolve_units(rite, _context(baptism=True), load_modules())
    ids = [u if isinstance(u, str) else u["id"] for u in units]
    assert ids == ["opening", "baptism"]
    assert units[-1] == "baptism"  # baptism module_ref stays a bare string

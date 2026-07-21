"""Per-service variable fields (RB-3b).

A rite may declare ``meta.variables`` — fields a volunteer fills per service
(a deceased's name, a couple's names, a date).  Block text references a field
with a DOUBLE-brace placeholder ``{{key}}``; the per-service value is
substituted at render time.  This is what makes funeral/wedding bulletins
usable.

Parity contract: a rite that declares NO variables (every existing/default
rite) contains no ``{{}}`` placeholders, so substitution is a no-op and the
serialized rite carries no ``variables`` key — byte-identical output.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from bulletin_maker.core.library import load_library
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.rite import (
    Block,
    Rite,
    RiteModule,
    RiteSchemaError,
    RiteValidationError,
    RiteVariable,
    substitute_variables,
    validate_rite,
)
from bulletin_maker.core.service_form import build_service_config
from bulletin_maker.renderer.rite_resolver import _resolve_units

FUNERAL_MODULE_ID = "test_funeral_module"


def _context(**toggles: bool) -> Dict[str, Any]:
    return {"season": "none", "feasts": [], "toggles": toggles}


def _funeral_module() -> RiteModule:
    """A module using ``{{deceased_name}}`` in all four text-bearing types."""
    return RiteModule(
        id=FUNERAL_MODULE_ID,
        name="Test Funeral Module",
        blocks=[
            Block(
                id="fm_heading",
                type="heading",
                data={"text": "FUNERAL FOR {{deceased_name}}"},
            ),
            Block(
                id="fm_rubric",
                type="rubric",
                data={"text": "The body of {{deceased_name}} is carried in."},
            ),
            Block(
                id="fm_literal",
                type="literal_text",
                data={
                    "text": "Into your hands we commend your servant {{deceased_name}}.",
                    "style": "prayer",
                },
            ),
            Block(
                id="fm_dialogue",
                type="dialogue",
                data={
                    "lines": [
                        {"role": "leader", "text": "Let us pray for {{deceased_name}}."},
                        {"role": "congregation", "text": "Lord, have mercy."},
                    ]
                },
            ),
        ],
    )


def _funeral_rite(module_id: str = FUNERAL_MODULE_ID) -> Rite:
    return Rite(
        id="test_funeral",
        name="Funeral",
        occasion="funeral",
        blocks=[
            Block(id="opening", type="heading", data={"text": "GATHERING"}),
            Block(id="child", type="module_ref", data={"module_id": module_id}),
        ],
        variables=[
            RiteVariable(
                key="deceased_name",
                label="Name of the deceased",
                type="names",
                required=True,
            )
        ],
    )


def _embedded(units: list) -> Dict[str, Dict[str, Any]]:
    return {u["id"]: u for u in units if isinstance(u, dict)}


# ── Substitution across block types (incl. the EMBEDDED module path) ──


def test_substitution_in_all_block_types_via_embedded_module():
    rite = _funeral_rite()
    modules = {FUNERAL_MODULE_ID: _funeral_module()}
    variables = {"deceased_name": "Jane Doe"}

    units = _resolve_units(rite, _context(), modules, variables)
    by_id = _embedded(units)

    assert by_id["fm_heading"]["text"] == "FUNERAL FOR Jane Doe"
    assert by_id["fm_rubric"]["text"] == "The body of Jane Doe is carried in."
    assert (
        by_id["fm_literal"]["text"]
        == "Into your hands we commend your servant Jane Doe."
    )
    dialogue_lines = by_id["fm_dialogue"]["lines"]
    assert dialogue_lines[0]["text"] == "Let us pray for Jane Doe."
    assert dialogue_lines[1]["text"] == "Lord, have mercy."


def test_pure_substitute_helper():
    assert (
        substitute_variables(
            "...your servant {{deceased_name}}.", {"deceased_name": "Jane Doe"}
        )
        == "...your servant Jane Doe."
    )
    # Optional whitespace inside the braces is tolerated.
    assert substitute_variables("{{ deceased_name }}", {"deceased_name": "X"}) == "X"


def test_single_brace_baptism_syntax_is_left_untouched():
    # Baptism's per-candidate ``{name}`` (single brace) must NOT be treated as
    # a rite variable — different mechanism, left entirely alone.
    text = "N., I baptize you: {name}"
    assert substitute_variables(text, {"name": "SHOULD_NOT_APPEAR"}) == text


# ── Undeclared placeholder fails loud ─────────────────────────────────


def test_undeclared_placeholder_fails_loud_and_names_offender():
    rite = Rite(
        id="bad_rite",
        name="Bad",
        blocks=[
            Block(id="b1", type="literal_text", data={"text": "For {{typo}} we pray."})
        ],
    )
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite)
    message = str(exc.value)
    assert "typo" in message
    assert "b1" in message


def test_undeclared_placeholder_in_embedded_module_fails_loud():
    rite = _funeral_rite()
    # Module block references {{deceased_name}}, but the rite declares nothing.
    rite.variables = []
    modules = {FUNERAL_MODULE_ID: _funeral_module()}
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite, modules=modules)
    assert "deceased_name" in str(exc.value)


# ── Unfilled declared variable → visible bracketed hint (not blank) ───


def test_unfilled_declared_variable_renders_visible_hint():
    rite = _funeral_rite()
    modules = {FUNERAL_MODULE_ID: _funeral_module()}

    # Declared and validated, but the volunteer left it blank.
    validate_rite(rite, modules=modules)
    units = _resolve_units(rite, _context(), modules, {})
    by_id = _embedded(units)

    # Fails VISIBLY: a bracketed hint, never silently blank-and-wrong.
    assert by_id["fm_heading"]["text"] == "FUNERAL FOR [deceased_name]"
    assert "[deceased_name]" in by_id["fm_literal"]["text"]
    assert by_id["fm_literal"]["text"] != "Into your hands we commend your servant ."


def test_empty_string_value_also_renders_hint():
    assert substitute_variables("{{k}}", {"k": ""}) == "[k]"


# ── A rite with NO variables is unchanged (parity-adjacent) ───────────


def test_rite_without_variables_serializes_without_variables_key():
    rite = Rite(
        id="plain",
        name="Plain",
        blocks=[Block(id="h", type="heading", data={"text": "GATHERING"})],
    )
    meta = rite.to_dict()["meta"]
    assert "variables" not in meta


def test_library_rites_validate_and_sunday_declares_baptism_variable():
    rites, modules = load_library()
    for rite in rites:
        validate_rite(rite, modules=modules)
    sunday = next(r for r in rites if r.id == "elw_sunday_communion")
    baptism_var = next(
        v for v in sunday.variables if v.key == "baptism_candidate_names"
    )
    assert baptism_var.type == "names"
    assert baptism_var.required is False
    assert "variables" in sunday.to_dict()["meta"]


# ── Declaration round-trips; declared-but-unused is allowed ───────────


def test_variables_round_trip_through_to_dict_from_dict():
    rite = _funeral_rite()
    restored = Rite.from_dict(rite.to_dict())
    assert restored.variables == rite.variables
    assert restored.to_dict()["meta"]["variables"] == [
        {
            "key": "deceased_name",
            "label": "Name of the deceased",
            "type": "names",
            "required": True,
        }
    ]


def test_declared_but_unused_variable_is_valid():
    rite = Rite(
        id="r",
        name="R",
        blocks=[Block(id="h", type="heading", data={"text": "NO PLACEHOLDER HERE"})],
        variables=[RiteVariable(key="unused", label="Unused field")],
    )
    validate_rite(rite)  # a declared variable need not be used


@pytest.mark.parametrize(
    "data",
    [
        {"key": "1bad", "label": "Bad key"},
        {"key": "ok", "label": "Bad type", "type": "email"},
        {"key": "ok", "label": ""},
        {"key": "ok", "label": "L", "required": "yes"},
        {"key": "ok", "label": "L", "extra": 1},
    ],
)
def test_rite_variable_from_dict_fails_fast_on_bad_declaration(data):
    with pytest.raises(RiteSchemaError):
        RiteVariable.from_dict(data)


# ── build_service_config threads variables; baptism is untouched ──────


def test_build_service_config_threads_variables():
    form_data = {
        "date": "2026-07-25",
        "date_display": "July 25, 2026",
        "variables": {"deceased_name": "Jane Doe"},
    }
    config = build_service_config(form_data, {})
    assert config.variables == {"deceased_name": "Jane Doe"}


def test_build_service_config_defaults_variables_to_empty():
    config = build_service_config({"date": "d", "date_display": "D"}, {})
    assert config.variables == {}


def test_baptism_candidate_names_flow_through_general_variables():
    form_data = {
        "date": "d",
        "date_display": "D",
        "include_baptism": True,
        "variables": {
            "baptism_candidate_names": "Baby A, Baby B",
            "deceased_name": "Jane Doe",
        },
    }
    config = build_service_config(form_data, {})
    # Baptism names now ride the one general variables mechanism; the dedicated
    # baptism_candidate_names field has been retired.
    assert config.variables["baptism_candidate_names"] == "Baby A, Baby B"
    assert config.include_baptism is True
    assert not hasattr(config, "baptism_candidate_names")


def test_default_service_config_has_empty_variables():
    config = ServiceConfig(date="d", date_display="D")
    assert config.variables == {}

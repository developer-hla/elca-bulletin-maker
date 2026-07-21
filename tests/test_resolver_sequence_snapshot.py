"""AC-3 Phase 0: pin the resolved render-sequence STRUCTURE for the parity
variants — a fast (no-Chromium) change-detector for the renderer-unification
migration.

The parity/layout suites prove byte-identical PDFs but are slow; this asserts
the exact ``[{flow, ids}]`` shape ``resolve_bulletin_sequence`` /
``resolve_large_print_sequence`` produce, so a migration that moves a block
from bare-id dispatch to an embedded (type-dispatched) unit — or drops it from
its flow-group — is caught in milliseconds, before the slow suites run.

Golden: ``tests/parity/golden/resolver_sequence_snapshot.json``. A migration
that INTENTIONALLY changes the structure updates the golden deliberately (and
must still pass parity/layout byte-identical); an unintended change fails here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bulletin_maker.renderer  # noqa: F401  (warm the cold-import cycle)
from bulletin_maker.renderer.rite_resolver import (
    resolve_bulletin_sequence,
    resolve_large_print_sequence,
)
from tests.parity.variants import VARIANTS

GOLDEN = Path(__file__).parent / "parity" / "golden" / "resolver_sequence_snapshot.json"


def _normalize(sequence):
    groups = []
    for group in sequence:
        ids = [
            unit if isinstance(unit, str) else "<%s:%s>" % (unit.get("type"), unit.get("id"))
            for unit in group["ids"]
        ]
        groups.append({"flow": group["flow"], "ids": ids})
    return groups


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda v: v.name)
def test_bulletin_sequence_matches_snapshot(variant, golden):
    actual = _normalize(resolve_bulletin_sequence(variant.config, variant.season))
    assert actual == golden[variant.name]["bulletin"]


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda v: v.name)
def test_large_print_sequence_matches_snapshot(variant, golden):
    actual = _normalize(resolve_large_print_sequence(variant.config, variant.season))
    assert actual == golden[variant.name]["large_print"]

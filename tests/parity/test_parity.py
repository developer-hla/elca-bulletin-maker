"""LWS-0a output-parity harness.

Renders all five documents for four config variants of the fixture
Sunday (``tests/parity/variants.py``) and diffs the extracted text
against golden files in ``tests/parity/golden/``. This is the hard
acceptance gate for the upcoming rite-engine refactor: the generated
documents must not change.

Marked ``parity`` and excluded from the default run (slow, needs
Chromium — same reasoning as the ``layout`` suite). Run with:

    venv/bin/python -m pytest tests/ -m parity -v

Rebaseline (regenerates golden files instead of comparing — requires
owner approval, see ``tests/parity/README.md``):

    BULLETIN_PARITY_REBASELINE=1 venv/bin/python -m pytest tests/ -m parity -v
"""

from __future__ import annotations

import json
import os
from difflib import unified_diff
from pathlib import Path

import pytest
from pypdf import PdfReader

from bulletin_maker.core.documents import generate_documents
from bulletin_maker.core.profile import BUNDLED_PROFILE, load_profile

from tests.parity.conftest import REBASELINE_CHANGES_KEY
from tests.parity.variants import VARIANT_NAMES, VARIANTS

pytestmark = pytest.mark.parity

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
REBASELINE = os.environ.get("BULLETIN_PARITY_REBASELINE") == "1"

# The five documents generate_documents() knows how to produce — see
# bulletin_maker.core.documents.DOCUMENTS. "bulletin" is the final,
# imposed booklet PDF (what generate_documents() actually saves), not
# the sequential intermediate.
DOCUMENT_KEYS: tuple[str, ...] = (
    "bulletin", "prayers", "scripture", "large_print", "leader_guide",
)


# ── Text normalization ────────────────────────────────────────────────

def _normalize_page_text(raw: str) -> str:
    """Strip trailing whitespace per line and collapse blank-line runs.

    Also trims leading/trailing blank lines so incidental
    top/bottom padding differences don't count as a change.
    """
    lines = [line.rstrip() for line in raw.splitlines()]
    normalized: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        normalized.append(line)
        prev_blank = is_blank
    while normalized and normalized[0] == "":
        normalized.pop(0)
    while normalized and normalized[-1] == "":
        normalized.pop()
    return "\n".join(normalized)


def _extract_pdf(pdf_path: Path) -> dict:
    """Golden-extract format: page count, per-page line counts, per-page text.

    Deliberately does NOT capture PDF metadata (CreationDate/ModDate/
    Producer) — Chromium stamps those with the real render timestamp,
    which would make the harness flap run-to-run. Text-layer extraction
    via pypdf ignores document info dict entirely, so this is already
    immune to that nondeterminism.
    """
    reader = PdfReader(str(pdf_path))
    pages = [_normalize_page_text(p.extract_text() or "") for p in reader.pages]
    return {
        "page_count": len(pages),
        "line_counts": [len(t.splitlines()) if t else 0 for t in pages],
        "pages": pages,
    }


# ── Golden I/O ────────────────────────────────────────────────────────

def _golden_path(variant: str, doc_key: str) -> Path:
    return GOLDEN_DIR / f"{variant}__{doc_key}.json"


def _load_golden(variant: str, doc_key: str) -> dict:
    path = _golden_path(variant, doc_key)
    if not path.exists():
        pytest.fail(
            f"No golden file for {variant}/{doc_key} at {path}. "
            "Run with BULLETIN_PARITY_REBASELINE=1 to create it "
            "(requires owner approval — see tests/parity/README.md)."
        )
    return json.loads(path.read_text())


def _save_golden(variant: str, doc_key: str, extract: dict) -> None:
    path = _golden_path(variant, doc_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(extract, indent=2, ensure_ascii=False) + "\n")


def _describe_rebaseline_change(variant: str, doc_key: str, extract: dict) -> str:
    label = f"{variant}/{doc_key}"
    path = _golden_path(variant, doc_key)
    if not path.exists():
        return f"  {label}: NEW golden ({extract['page_count']} pages)"
    old = json.loads(path.read_text())
    if old == extract:
        return f"  {label}: unchanged ({extract['page_count']} pages)"
    if old["page_count"] != extract["page_count"]:
        return (
            f"  {label}: CHANGED — page count "
            f"{old['page_count']} -> {extract['page_count']}"
        )
    changed_pages = [
        i + 1 for i, (o, n) in enumerate(zip(old["pages"], extract["pages"]))
        if o != n
    ]
    return f"  {label}: CHANGED — text differs on page(s) {changed_pages}"


# ── Comparison with readable failure output ──────────────────────────

def _assert_matches(variant: str, doc_key: str, golden: dict, actual: dict) -> None:
    label = f"{variant}/{doc_key}"

    if golden["page_count"] != actual["page_count"]:
        pytest.fail(
            f"{label}: page count changed "
            f"{golden['page_count']} -> {actual['page_count']}"
        )

    mismatches: list[str] = []
    for i, (g_page, a_page) in enumerate(zip(golden["pages"], actual["pages"]), start=1):
        if g_page == a_page:
            continue
        diff = "\n".join(unified_diff(
            g_page.splitlines(), a_page.splitlines(),
            fromfile=f"golden/{label} p{i}", tofile=f"actual/{label} p{i}",
            lineterm="",
        ))
        mismatches.append(f"--- {label} page {i} differs ---\n{diff}")

    if mismatches:
        pytest.fail("\n\n".join(mismatches))

    if golden["line_counts"] != actual["line_counts"]:
        pytest.fail(
            f"{label}: per-page line counts changed "
            f"{golden['line_counts']} -> {actual['line_counts']}"
        )


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module", params=VARIANT_NAMES)
def rendered_variant(request, tmp_path_factory):
    """Render all five documents for one variant, once per test run."""
    variant_name = request.param
    variant = next(v for v in VARIANTS if v.name == variant_name)
    out = tmp_path_factory.mktemp(f"parity_{variant_name}")

    # Pin the congregation profile to the bundled default regardless of
    # $BULLETIN_PROFILE or ~/.bulletin-maker/profile.toml on the host —
    # otherwise the golden extracts would depend on machine-local state.
    profile = load_profile(BUNDLED_PROFILE)

    outcome = generate_documents(
        variant.day, variant.config, out,
        season=variant.season,
        client=None,
        selected=set(DOCUMENT_KEYS),
        profile=profile,
    )
    assert outcome.success, outcome.errors

    extracts = {
        key: _extract_pdf(Path(outcome.results[key])) for key in DOCUMENT_KEYS
    }
    return variant_name, extracts


# ── The test ──────────────────────────────────────────────────────────

class TestParity:

    def test_matches_golden(self, rendered_variant, request):
        variant_name, extracts = rendered_variant

        if REBASELINE:
            changes = request.config.stash[REBASELINE_CHANGES_KEY]
            for doc_key, extract in extracts.items():
                changes.append(_describe_rebaseline_change(variant_name, doc_key, extract))
                _save_golden(variant_name, doc_key, extract)
            pytest.skip(f"Rebaselined golden files for variant={variant_name!r}")

        for doc_key, extract in extracts.items():
            golden = _load_golden(variant_name, doc_key)
            _assert_matches(variant_name, doc_key, golden, extract)

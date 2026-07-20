"""Document registry and the generation workflow.

The single place that knows which documents exist, what they are
called, in what order they generate, and how they depend on each
other (the bulletin renders first so Pulpit Prayers can reference the
creed's page number).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from bulletin_maker.core.content_source import ContentContext
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.naming import build_filename
from bulletin_maker.core.profile import CongregationProfile, load_profile
from bulletin_maker.renderer.paper import get_paper_preset
from bulletin_maker.renderer import (
    generate_bulletin,
    generate_large_print,
    generate_leader_guide,
    generate_pulpit_prayers,
    generate_pulpit_scripture,
)
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]


@dataclass(frozen=True)
class DocumentSpec:
    """One generatable document: registry key + filename label."""
    key: str
    label: str


DOCUMENTS: tuple[DocumentSpec, ...] = (
    DocumentSpec("bulletin", "Bulletin for Congregation"),
    DocumentSpec("prayers", "Pulpit PRAYERS"),          # creed suffix added at runtime
    DocumentSpec("scripture", "Pulpit SCRIPTURE"),
    DocumentSpec("large_print", "Full with Hymns LARGE PRINT"),
    DocumentSpec("leader_guide", "Leader Guide"),
)

DEFAULT_SELECTION: tuple[str, ...] = tuple(spec.key for spec in DOCUMENTS)

_SPECS_BY_KEY = {spec.key: spec for spec in DOCUMENTS}


def document_label(key: str, *, creed_type: str = "apostles") -> str:
    """Return the filename label for a document key.

    The prayers document embeds the creed name in its filename
    (e.g. ``Pulpit PRAYERS + APOSTLES``).
    """
    spec = _SPECS_BY_KEY[key]
    if key == "prayers":
        creed = "NICENE" if creed_type == "nicene" else "APOSTLES"
        return f"{spec.label} + {creed}"
    return spec.label


@dataclass
class GenerationResult:
    """Outcome of a generate_documents() run."""
    results: dict = field(default_factory=dict)   # key -> saved PDF path (str)
    errors: dict = field(default_factory=dict)    # key -> error message
    creed_page: Optional[int] = None

    @property
    def success(self) -> bool:
        return not self.errors


def _run_one(
    key: str,
    label: str,
    gen_fn: Callable[[], Path],
    outcome: GenerationResult,
    report: Callable[[str, str], None],
) -> None:
    """Run one document generation with error isolation.

    Catches all exceptions so one failing document never prevents the
    others from generating.
    """
    report(key, f"Generating {label}...")
    try:
        path = gen_fn()
        outcome.results[key] = str(path)
        report(key, f"{label} saved")
    except Exception as e:
        logger.exception("%s generation failed", label)
        outcome.errors[key] = str(e)
        report(key, f"{label} failed: {e}")


def generate_documents(
    day: DayContent,
    config: ServiceConfig,
    output_dir: Path,
    *,
    season: LiturgicalSeason,
    client: SundaysClient | None = None,
    selected: set[str] | None = None,
    keep_intermediates: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    profile: CongregationProfile | None = None,
    entitled: bool = True,
    church_texts: dict | None = None,
) -> GenerationResult:
    """Generate the selected documents into output_dir.

    The bulletin always generates first among selected documents — it
    determines the creed page number that Pulpit Prayers references.

    Args:
        on_progress: Optional callback(key, detail, pct) for UI status.
        entitled: Whether the church holds a validated S&S link. True (the
            default, and every offline/parity/generate path) resolves the ELW
            wording exactly as before; False falls back to public-domain text
            or a placeholder and never serves the copyrighted ELW text.
        church_texts: The church's saved text overrides keyed by catalog key.

    Returns:
        GenerationResult with per-document paths and isolated errors.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    content = ContentContext(entitled=entitled, church_texts=church_texts or {})

    selected = set(selected) if selected is not None else set(DEFAULT_SELECTION)
    unknown = selected - set(_SPECS_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown document keys: {sorted(unknown)}")

    if profile is None:
        profile = load_profile()
    if not config.cover_image and profile.cover_image:
        config.cover_image = profile.cover_image
    paper = get_paper_preset(profile.paper_size)

    outcome = GenerationResult()
    total = len(selected)
    step = 0

    def _report_step(key: str, detail: str) -> None:
        pct = int(step / total * 95) if total else 0
        if on_progress is not None:
            on_progress(key, f"[{step}/{total}] {detail}", pct)

    def _filename(key: str) -> str:
        label = document_label(key, creed_type=config.creed_type or "apostles")
        return build_filename(label, config.date, day.title)

    if "bulletin" in selected:
        step += 1

        def _bulletin_progress(detail: str) -> None:
            _report_step("bulletin", f"Bulletin: {detail}")

        def _gen_bulletin() -> Path:
            path, creed_page = generate_bulletin(
                day, config,
                output_path=output_dir / _filename("bulletin"),
                season=season,
                client=client,
                keep_intermediates=keep_intermediates,
                on_progress=_bulletin_progress,
                profile=profile,
                content=content,
            )
            outcome.creed_page = creed_page
            return path

        _run_one("bulletin", "Bulletin booklet", _gen_bulletin,
                 outcome, _report_step)

    if "prayers" in selected:
        step += 1
        _run_one(
            "prayers", "Pulpit prayers",
            lambda: generate_pulpit_prayers(
                day, config.date_display,
                creed_type=config.creed_type or "apostles",
                creed_page_num=outcome.creed_page,
                output_path=output_dir / _filename("prayers"),
                keep_intermediates=keep_intermediates,
                page_size=paper.flat_page_size,
                content=content,
            ),
            outcome, _report_step,
        )

    if "scripture" in selected:
        step += 1
        _run_one(
            "scripture", "Pulpit scripture",
            lambda: generate_pulpit_scripture(
                day, config.date_display,
                output_path=output_dir / _filename("scripture"),
                config=config,
                keep_intermediates=keep_intermediates,
                page_size=paper.flat_page_size,
            ),
            outcome, _report_step,
        )

    if "large_print" in selected:
        step += 1
        _run_one(
            "large_print", "Large print",
            lambda: generate_large_print(
                day, config,
                output_path=output_dir / _filename("large_print"),
                season=season, client=client,
                keep_intermediates=keep_intermediates,
                profile=profile,
                content=content,
            ),
            outcome, _report_step,
        )

    if "leader_guide" in selected:
        step += 1
        _run_one(
            "leader_guide", "Leader guide",
            lambda: generate_leader_guide(
                day, config,
                output_path=output_dir / _filename("leader_guide"),
                season=season, client=client,
                keep_intermediates=keep_intermediates,
                profile=profile,
                content=content,
            ),
            outcome, _report_step,
        )

    if on_progress is not None:
        on_progress("done", "Generation complete!", 100)
    return outcome

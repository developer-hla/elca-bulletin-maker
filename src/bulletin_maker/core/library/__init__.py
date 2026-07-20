"""Bundled library rites and modules (LWS-0b).

The JSON files in this package are the *library* content — full service
orders (``church_id`` NULL) and reusable occasion modules — shipped with the
product.  This loader reads them, parses them into the :mod:`rite` dataclasses
(strict ``from_dict``), and validates them referentially against the text
catalog and the sibling modules.

Rites and modules share a directory but are distinct kinds, so the file lists
are explicit rather than guessed from JSON shape.  ``validate_library`` is the
import-time sanity check exercised by the tests: it fails loudly if any block
references a missing text key, an unresolvable module, or an unknown field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from bulletin_maker.core.rite import Rite, RiteModule, validate_rite

LIBRARY_DIR = Path(__file__).resolve().parent

RITE_FILES: Tuple[str, ...] = (
    "elw_sunday_communion.json",
    "elw_service_of_the_word.json",
    "elw_morning_prayer.json",
    "elw_evening_prayer.json",
    "elw_night_prayer.json",
)
MODULE_FILES: Tuple[str, ...] = ("elw_holy_baptism.json",)

SUNDAY_COMMUNION_RITE_ID = "elw_sunday_communion"
SERVICE_OF_THE_WORD_RITE_ID = "elw_service_of_the_word"
MORNING_PRAYER_RITE_ID = "elw_morning_prayer"
EVENING_PRAYER_RITE_ID = "elw_evening_prayer"
NIGHT_PRAYER_RITE_ID = "elw_night_prayer"
HOLY_BAPTISM_MODULE_ID = "elw_holy_baptism"


def _read_json(filename: str) -> dict:
    path = LIBRARY_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_modules() -> Dict[str, RiteModule]:
    """Load every library module, keyed by id (fails fast on a duplicate)."""
    modules: Dict[str, RiteModule] = {}
    for filename in MODULE_FILES:
        module = RiteModule.from_dict(_read_json(filename))
        if module.id in modules:
            raise ValueError("duplicate library module id %r" % module.id)
        modules[module.id] = module
    return modules


def load_rites() -> List[Rite]:
    """Load every library rite in declaration order."""
    return [Rite.from_dict(_read_json(filename)) for filename in RITE_FILES]


def load_rite(rite_id: str) -> Rite:
    """Load a single library rite by id (fails fast if absent)."""
    for rite in load_rites():
        if rite.id == rite_id:
            return rite
    raise KeyError("no library rite with id %r" % rite_id)


def load_library() -> Tuple[List[Rite], Dict[str, RiteModule]]:
    """Return ``(rites, modules)`` — the whole bundled library."""
    return load_rites(), load_modules()


def validate_library() -> None:
    """Parse and referentially validate every library rite; raise on error.

    Each rite is checked against the text catalog and the loaded modules, so a
    ``module_ref`` or ``text_ref`` that cannot resolve fails here.
    """
    rites, modules = load_library()
    for rite in rites:
        validate_rite(rite, modules=modules)

"""Congregation profile — identity fields and bounded output options.

The profile holds everything another congregation must change to adopt
the tool (name, address, service time, welcome text, license footer)
plus the two bounded options (liturgical setting, paper size). All
other content is fixed house style by design.

Resolution order: explicit path → $BULLETIN_PROFILE →
~/.bulletin-maker/profile.toml → the bundled Ascension default.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from bulletin_maker.exceptions import BulletinError

BUNDLED_PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "ascension.toml"
USER_PROFILE = Path.home() / ".bulletin-maker" / "profile.toml"


@dataclass(frozen=True)
class CongregationProfile:
    church_name: str
    address_lines: tuple
    service_time: str
    welcome_message: str
    standing_instructions: str
    copyright_paragraphs: tuple = ()
    liturgical_setting: str = "setting_two"
    paper_size: str = "legal_booklet"
    cover_image: str = ""
    source_path: str = field(default="", compare=False)

    @property
    def church_address(self) -> str:
        return "\n".join(self.address_lines)


def _require(table: dict, section: str, key: str):
    try:
        return table[section][key]
    except KeyError:
        raise BulletinError(
            f"Congregation profile is missing [{section}] {key}"
        ) from None


PROFILE_FIELDS = (
    "church_name", "address_lines", "service_time", "welcome_message",
    "standing_instructions", "copyright_paragraphs", "liturgical_setting",
    "paper_size", "cover_image",
)


def profile_from_dict(data: dict, source: str = "account") -> CongregationProfile:
    """Build a profile from a stored dict (per-church account storage)."""
    return CongregationProfile(
        church_name=data.get("church_name", ""),
        address_lines=tuple(data.get("address_lines", ())),
        service_time=data.get("service_time", ""),
        welcome_message=data.get("welcome_message", ""),
        standing_instructions=data.get("standing_instructions", ""),
        copyright_paragraphs=tuple(data.get("copyright_paragraphs", ())),
        liturgical_setting=data.get("liturgical_setting", "setting_two"),
        paper_size=data.get("paper_size", "legal_booklet"),
        cover_image=data.get("cover_image", ""),
        source_path=source,
    )


def profile_to_dict(profile: CongregationProfile) -> dict:
    return {
        "church_name": profile.church_name,
        "address_lines": list(profile.address_lines),
        "service_time": profile.service_time,
        "welcome_message": profile.welcome_message,
        "standing_instructions": profile.standing_instructions,
        "copyright_paragraphs": list(profile.copyright_paragraphs),
        "liturgical_setting": profile.liturgical_setting,
        "paper_size": profile.paper_size,
        "cover_image": profile.cover_image,
    }


def load_profile(path: Path | str | None = None) -> CongregationProfile:
    """Load a congregation profile TOML.

    Args:
        path: Explicit profile path. When None, uses
            ~/.bulletin-maker/profile.toml if present, else the bundled
            Ascension default.
    """
    if path is None:
        path = os.environ.get("BULLETIN_PROFILE") or (
            USER_PROFILE if USER_PROFILE.exists() else BUNDLED_PROFILE
        )
    path = Path(path)

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise BulletinError(f"Congregation profile not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise BulletinError(f"Invalid congregation profile {path}: {e}") from e

    options = data.get("options", {})
    return CongregationProfile(
        church_name=_require(data, "church", "name"),
        address_lines=tuple(_require(data, "church", "address_lines")),
        service_time=_require(data, "church", "service_time"),
        welcome_message=_require(data, "texts", "welcome_message"),
        standing_instructions=_require(data, "texts", "standing_instructions"),
        copyright_paragraphs=tuple(data.get("texts", {}).get("copyright_paragraphs", ())),
        liturgical_setting=options.get("liturgical_setting", "setting_two"),
        paper_size=options.get("paper_size", "legal_booklet"),
        cover_image=options.get("cover_image", ""),
        source_path=str(path),
    )

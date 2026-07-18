"""ELW liturgical settings — a bounded, data-driven choice.

Every ELW musical setting sets the same liturgical texts; what differs
is the notation. A LiturgicalSetting therefore only carries the S&S
atom-code prefix and where its notation images live. Setting Two ships
bundled with the app (Ascension's default); the others download on
demand into the user cache via the congregation's own S&S login, which
keeps asset licensing tied to their subscription.

The atom-code pattern ``elw_hc{N}_{piece}_m`` was verified against the
S&S Library for settings 1-5 (July 2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bulletin_maker.exceptions import BulletinError

USER_ASSETS_DIR = Path.home() / ".bulletin-maker" / "assets"


@dataclass(frozen=True)
class LiturgicalSetting:
    key: str            # profile value, e.g. "setting_two"
    label: str          # human name for UI lists
    atom_prefix: str    # S&S Library code prefix, e.g. "elw_hc2"
    bundled: bool = False  # True = notation ships inside the package
    ga_segment: str = "accltext"       # atom segment for the standard acclamation
    missing_pieces: frozenset = frozenset()  # pieces this setting doesn't include


# Piece availability and GA segments verified against the S&S Library
# tree (scripts/data/holy_communion_tree.json): settings 1-2 use
# "accltext" and include a Nunc Dimittis; 3-4 use "alleluia" and have
# none; 5 lacks both the Nunc Dimittis and "This Is the Feast".
SETTINGS: dict = {
    s.key: s
    for s in (
        LiturgicalSetting("setting_one", "ELW Setting One", "elw_hc1"),
        LiturgicalSetting("setting_two", "ELW Setting Two", "elw_hc2", bundled=True),
        LiturgicalSetting("setting_three", "ELW Setting Three", "elw_hc3",
                          ga_segment="alleluia",
                          missing_pieces=frozenset({"nunc_dimittis"})),
        LiturgicalSetting("setting_four", "ELW Setting Four", "elw_hc4",
                          ga_segment="alleluia",
                          missing_pieces=frozenset({"nunc_dimittis"})),
        LiturgicalSetting("setting_five", "ELW Setting Five", "elw_hc5",
                          missing_pieces=frozenset({"nunc_dimittis",
                                                    "this_is_the_feast"})),
    )
}

DEFAULT_SETTING_KEY = "setting_two"


def get_setting(key: str) -> LiturgicalSetting:
    """Look up a liturgical setting by profile key."""
    try:
        return SETTINGS[key]
    except KeyError:
        raise BulletinError(
            f"Unknown liturgical setting: {key!r}. "
            f"Valid settings: {', '.join(sorted(SETTINGS))}"
        ) from None

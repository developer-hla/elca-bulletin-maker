"""Calendar provider seam (LWS-3a).

Today, "what day/season/propers is this date" is computed inline in the
web layer: ``fetch_day`` asks the content service for an S&S ``DayContent``
and calls ``detect_season(day.title)`` on it. That's fine as long as S&S is
the only source of calendar truth, but it hardwires the app to S&S.

This module introduces :class:`CalendarProvider`, the seam that makes
"what day/season/propers is this date" pluggable per church, plus the two
providers this workstream implements: :class:`SnsCalendarProvider` (wraps
today's behavior unchanged) and :class:`ManualCalendarProvider`
(sermon-series / no-lectionary mode, no network).

Design note — ``resolve()`` is a classifier, not a fetcher. A provider's
``resolve(date, ...)`` turns *already-obtained* input into a
:class:`LiturgicalDay`; it never performs I/O itself. For ``sns`` that
input is a ``DayContent`` the caller already fetched via ``ContentService``
(which needs the church's S&S credential — a web/sns concern, not a domain
one); for ``manual`` it is the day name/citations a volunteer typed into a
form. Forcing one fixed parameter list on both would either saddle
``sns`` with unused manual-only arguments or saddle ``manual`` with a
``DayContent`` it will never have. The call sites already know which
concrete provider they're using (they read it off the church profile
before calling resolve()), so each provider is free to declare exactly the
keyword arguments it needs. What's shared — the contract that matters — is
the input type (``date`` plus provider-specific context) and the output
type (``LiturgicalDay``). Keeping I/O out of this module also means every
provider here is trivially unit-testable with no network or DB.

Design note — calendar-shape-agnostic types. ELCA/RCL is the only content
this workstream deals with, but LWS-3b adds calendars that are *structurally*
different: Roman Catholic (forward-numbered Ordinary Time, separate
Sunday A/B/C + weekday I/II cycles), LCMS's historic one-year lectionary
(single year, Gesima pre-Lent Sundays), the Narrative Lectionary (4-year,
Sept-May, one primary reading a week), and manual/sermon-series (no
lectionary at all). None of that data or logic belongs here — but the
*types* must not bake in RCL's shape, or every later provider would be
fighting the type instead of using it:

* ``cycles`` is an open ``{name: value}`` dict — a day can carry several
  cycle positions at once (``{"rcl": "C"}``, or later
  ``{"narrative": 4, "lcms_1yr": True}``); nothing assumes a single
  three-year A/B/C axis.
* ``propers`` is an open ``{slot: value}`` dict — not hardcoded to exactly
  four readings. The sns provider happens to populate first/second/psalm/
  gospel because that's what RCL Sundays have; other providers populate
  whatever slots their calendar actually has (Narrative Lectionary's one
  primary reading, LCMS's historic set, none at all for manual).
* ``day_name`` is whatever string the *provider* produces (S&S's title
  minus its date prefix for sns; the volunteer's typed name for manual).
  Numbering/naming logic lives inside each provider, never in this shared
  type.
* ``season`` is the subtle one. The app's existing
  ``renderer.season.LiturgicalSeason`` is a closed, 7-value Western/RCL
  enum. Locking ``LiturgicalDay.season`` to that type would force every
  future calendar to lie in that vocabulary. Instead ``season`` is a
  :class:`SeasonId` — an open ``(id, label)`` pair a provider defines for
  itself — so Roman Ordinary Time counted forward, LCMS's Gesima Sundays,
  Narrative's own season names, or manual's "no season at all" can all be
  expressed without changing this type. The ``sns`` provider is
  nonetheless *constrained*, by its own contract, to always set
  ``season.id`` to one of today's ``LiturgicalSeason`` values — that's
  what keeps output byte-identical (the hard gate for this workstream).
  :func:`liturgical_season_of` recovers the closed enum from a
  ``LiturgicalDay`` for the parts of the app (``get_seasonal_config``,
  ``fill_seasonal_defaults``, ``generate_documents``) that are out of
  this workstream's scope to generalize and still expect that enum.

Real lectionary data/computed propers (rcl_local, narrative, lcms_1yr) are
LWS-3b, not this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Union

from bulletin_maker.core.naming import extract_day_name
from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.season import LiturgicalSeason, detect_season
from bulletin_maker.sns.models import DayContent

# Slot keys mirror core.rite.READING_SLOTS ("first"/"second"/"psalm"/
# "gospel") so a LiturgicalDay.propers dict lines up with reading_slot
# blocks. Duplicated here rather than imported from core.content_views to
# keep this module's only sns.models dependency the DayContent shape —
# content_views additionally pulls in renderer.text_utils/static_text,
# which resolve() has no need of. This mapping is sns/RCL-specific (it
# translates S&S's own reading labels); other providers are free to key
# their propers dict however their calendar's structure calls for.
_READING_SLOT_LABELS: Dict[str, str] = {
    "first": "First Reading",
    "second": "Second Reading",
    "psalm": "Psalm",
    "gospel": "Gospel",
}
_SLOT_BY_LABEL: Dict[str, str] = {
    label: slot for slot, label in _READING_SLOT_LABELS.items()
}


def _propers_from_readings(readings: Any) -> Dict[str, Any]:
    """Project DayContent.readings onto the {slot: citation} propers shape.

    Alternate readings (label "First Reading (alternate)" etc.) aren't in
    _SLOT_BY_LABEL and are skipped — propers carries the primary citation
    per slot, matching what the current renderer path uses.
    """
    return {
        _SLOT_BY_LABEL[r.label]: r.citation
        for r in readings
        if r.label in _SLOT_BY_LABEL
    }


@dataclass(frozen=True)
class SeasonId:
    """A provider-defined season identity — open, not a fixed vocabulary.

    ``id`` is the provider's own season name; ``label`` is an optional
    human-readable form when it differs from ``id`` (providers whose id
    already reads naturally, like "advent", can leave it unset).

    Use :meth:`of` to normalize a season value of unknown shape (another
    ``SeasonId``, a ``renderer.season.LiturgicalSeason`` member, or a raw
    string id) — this is what lets :class:`ManualCalendarProvider` accept
    whichever form a caller finds convenient.
    """

    id: str
    label: Optional[str] = None

    @classmethod
    def of(cls, value: Union["SeasonId", LiturgicalSeason, str]) -> "SeasonId":
        if isinstance(value, SeasonId):
            return value
        if isinstance(value, LiturgicalSeason):
            return cls(id=value.value)
        return cls(id=str(value))


NEUTRAL_SEASON = SeasonId(id="none", label="No season")


def liturgical_season_of(day: "LiturgicalDay") -> LiturgicalSeason:
    """Recover the closed LiturgicalSeason enum from a LiturgicalDay.

    Only valid when ``day.season.id`` is one of LiturgicalSeason's own
    values — always true for a LiturgicalDay the sns provider produced
    (its contract requires it), and true for a manual day only if the
    church happened to pass a real LiturgicalSeason as its override.
    Raises BulletinError otherwise: this is the seam back to the closed
    vocabulary that get_seasonal_config/fill_seasonal_defaults/
    generate_documents still require, not something every provider's
    output can be expected to satisfy.
    """
    try:
        return LiturgicalSeason(day.season.id)
    except ValueError:
        raise BulletinError(
            "LiturgicalDay.season.id %r is not a renderer.season."
            "LiturgicalSeason value — liturgical_season_of() only applies "
            "to days whose provider populates that closed vocabulary"
            % day.season.id
        ) from None


@dataclass
class LiturgicalDay:
    """Provider-neutral answer to "what is this date, liturgically".

    ``color`` and ``cycles`` are carried for forward compatibility with
    LWS-3b (rcl_local/narrative/lcms_1yr need to report a paraments color
    and one or more lectionary cycle positions); neither provider in this
    workstream populates them. ``overlays`` is the per-week-override hook
    from §2.2 — also unpopulated here.
    """

    date: str
    day_name: str
    season: SeasonId
    color: Optional[str] = None
    cycles: Dict[str, Any] = field(default_factory=dict)
    propers: Dict[str, Any] = field(default_factory=dict)
    overlays: List[Any] = field(default_factory=list)


class CalendarProvider(ABC):
    """A pluggable source of "what day/season/propers is this date".

    See the module docstring for why ``resolve()`` classifies
    already-obtained input rather than fetching it itself.
    """

    key: str = ""

    @abstractmethod
    def resolve(self, date: str, **context: Any) -> LiturgicalDay:
        """Build a LiturgicalDay for ``date`` from provider-specific context."""


class SnsCalendarProvider(CalendarProvider):
    """Wraps today's behavior: classify an already-fetched S&S DayContent.

    Output-neutral by construction — season comes from the exact same
    ``detect_season(day.title)`` call the server has always made, day_name
    from the exact same ``extract_day_name(day.title)``, and propers from
    the reading citations already embedded in DayContent. A church on this
    provider generates byte-identically to a church with no provider seam
    at all. Contract: ``season.id`` is always one of LiturgicalSeason's
    own values (see :func:`liturgical_season_of`).
    """

    key = "sns"

    def resolve(self, date: str, day: Optional[DayContent] = None,
                **_context: Any) -> LiturgicalDay:
        if day is None:
            raise BulletinError(
                "sns calendar provider requires a fetched DayContent (day=...)"
            )
        return LiturgicalDay(
            date=date,
            day_name=extract_day_name(day.title),
            season=SeasonId.of(detect_season(day.title)),
            propers=_propers_from_readings(day.readings),
        )


class ManualCalendarProvider(CalendarProvider):
    """Sermon-series / no-lectionary mode: no external fetch.

    Builds a LiturgicalDay straight from church/form-supplied ``day_name``
    plus optional reading citations. Season defaults to
    :data:`NEUTRAL_SEASON` ("none") when the church doesn't specify one —
    a manual/sermon-series day genuinely has no lectionary season. A
    church preaching a series that *does* track a season (e.g. a Lenten
    teaching series) can pass an explicit override — a ``SeasonId``, a
    ``LiturgicalSeason`` member, or a plain string id — via
    :meth:`SeasonId.of`.
    """

    key = "manual"

    def resolve(self, date: str, day_name: str = "",
                season: Optional[Union[SeasonId, LiturgicalSeason, str]] = None,
                propers: Optional[Dict[str, Any]] = None,
                **_context: Any) -> LiturgicalDay:
        if not day_name:
            raise BulletinError("manual calendar provider requires a day_name")
        resolved_season = SeasonId.of(season) if season is not None else NEUTRAL_SEASON
        return LiturgicalDay(
            date=date,
            day_name=day_name,
            season=resolved_season,
            propers=dict(propers or {}),
        )


_PROVIDERS: Dict[str, CalendarProvider] = {
    provider.key: provider
    for provider in (SnsCalendarProvider(), ManualCalendarProvider())
}

CALENDAR_PROVIDER_KEYS: FrozenSet[str] = frozenset(_PROVIDERS)

DEFAULT_CALENDAR_PROVIDER = "sns"


def get_calendar_provider(key: str) -> CalendarProvider:
    """Look up a registered CalendarProvider by its profile key.

    Fails fast on an unknown key — a typo in a church profile must never
    silently fall back to a different calendar behavior.
    """
    try:
        return _PROVIDERS[key]
    except KeyError:
        raise BulletinError(
            "Unknown calendar provider %r (known: %s)"
            % (key, ", ".join(sorted(CALENDAR_PROVIDER_KEYS)))
        ) from None

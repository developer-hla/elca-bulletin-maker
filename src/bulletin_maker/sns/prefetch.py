"""Thursday prefetch — warm the S&S cache for the coming Sunday.

Run weekly (see docs/sns-cache.md for the cron line). For every church with a
linked, validated S&S credential it fetches the coming Sunday's day content
(which carries all the day texts) and stores it in ``sns_cache`` so the
weekend's bulletin prep is served from cache instead of live S&S.

Hymn lyrics are not prefetched: hymns are chosen by the user, so none can be
determined ahead of time without input. Day content alone is the warm target.

Per-church failures are logged and never abort the run.

Usage: ``python -m bulletin_maker.sns.prefetch``
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.content_service import ContentService
from bulletin_maker.web import db, security

logger = logging.getLogger(__name__)

SUNDAY_WEEKDAY = 6  # Python date.weekday(): Monday=0 .. Sunday=6


def coming_sunday(today: date) -> date:
    """The next Sunday strictly after ``today`` (a full week out on Sundays)."""
    days_ahead = (SUNDAY_WEEKDAY - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _api_date(day: date) -> str:
    return f"{day.year}-{day.month}-{day.day}"


def linked_churches() -> list:
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, name, sns_username, sns_password_enc FROM churches"
            " WHERE sns_username <> '' AND sns_password_enc <> ''"
        ).fetchall()


def warm_church(church: dict, api_date: str) -> None:
    password = security.decrypt_secret(church["sns_password_enc"])
    client = SundaysClient()
    try:
        client.login(church["sns_username"], password)
        service = ContentService(entitled=True, client_provider=lambda: client)
        service.get_day_content(api_date, force_refresh=True)
    finally:
        client.close()


def run(today: date) -> int:
    """Warm every linked church for the coming Sunday. Returns failure count."""
    api_date = _api_date(coming_sunday(today))
    churches = linked_churches()
    failures = 0
    for church in churches:
        try:
            warm_church(church, api_date)
        except BulletinError as e:
            failures += 1
            logger.error(
                "Prefetch failed for church %s (%s): %s",
                church["id"], church["name"], e)
    if failures:
        logger.warning(
            "Prefetch warmed %d/%d churches for %s (%d failed)",
            len(churches) - failures, len(churches), api_date, failures)
    return failures


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    run(date.today())


if __name__ == "__main__":
    main()

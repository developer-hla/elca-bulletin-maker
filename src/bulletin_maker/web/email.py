"""Transactional email — a thin provider abstraction.

One public function, ``send_email``. The backend is chosen by
``$EMAIL_PROVIDER``: ``console`` (the default) logs the message and is used
in development and tests, and ``resend`` posts to the Resend HTTP API. Under
pytest the console backend also captures messages in ``sent_for_tests`` so
tests can assert on them.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import httpx

from bulletin_maker.exceptions import BulletinError

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
RESEND_TIMEOUT = 10.0

sent_for_tests: List[dict] = []


def send_email(to: str, subject: str, text: str,
               html: Optional[str] = None) -> None:
    provider = os.environ.get("EMAIL_PROVIDER", "console")
    if provider == "console":
        _send_console(to, subject, text, html)
        return
    if provider == "resend":
        _send_resend(to, subject, text, html)
        return
    raise BulletinError(f"Unknown EMAIL_PROVIDER: {provider!r}")


def _send_console(to: str, subject: str, text: str,
                  html: Optional[str]) -> None:
    logger.warning("Email (console) to=%s subject=%r\n%s", to, subject, text)
    if "PYTEST_CURRENT_TEST" in os.environ:
        sent_for_tests.append(
            {"to": to, "subject": subject, "text": text, "html": html})


def _send_resend(to: str, subject: str, text: str,
                 html: Optional[str]) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    from_address = os.environ.get("EMAIL_FROM")
    if not api_key or not from_address:
        raise BulletinError(
            "EMAIL_PROVIDER=resend requires RESEND_API_KEY and EMAIL_FROM.")
    payload = {"from": from_address, "to": [to],
               "subject": subject, "text": text}
    if html:
        payload["html"] = html
    headers = {"Authorization": f"Bearer {api_key}"}
    response = httpx.post(RESEND_ENDPOINT, json=payload,
                          headers=headers, timeout=RESEND_TIMEOUT)
    response.raise_for_status()

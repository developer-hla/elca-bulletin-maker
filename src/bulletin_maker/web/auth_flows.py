"""Password-reset, magic-link, and email-verification token flows.

Tokens are random and single-use: only their sha256 hash is stored in the
`auth_tokens` table, alongside a purpose and expiry. Issuance never reveals
whether an account exists. Reset and magic links live 30 minutes; email
verification links live 7 days.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from bulletin_maker.web import db, email, security

RESET_TTL = timedelta(minutes=30)
MAGIC_TTL = timedelta(minutes=30)
VERIFY_TTL = timedelta(days=7)

DEFAULT_APP_BASE_URL = "http://127.0.0.1:8000"


def _app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", DEFAULT_APP_BASE_URL)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_token(user_id: int, purpose: str, ttl: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at)"
            " VALUES (%s, %s, %s, %s)",
            (user_id, purpose, _hash_token(token), _now() + ttl))
    return token


def _consume_token(token: str, purpose: str) -> Optional[int]:
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "UPDATE auth_tokens SET used_at = now()"
            " WHERE token_hash = %s AND purpose = %s"
            " AND used_at IS NULL AND expires_at > now()"
            " RETURNING user_id",
            (_hash_token(token), purpose)).fetchone()
    return row["user_id"] if row else None


def send_verification(user: dict) -> None:
    token = _issue_token(user["id"], "verify", VERIFY_TTL)
    link = f"{_app_base_url()}/#verify={token}"
    body = (
        "Welcome to Bulletin Maker.\n\n"
        "Please confirm your email address by opening this link:\n"
        f"{link}\n\n"
        "The link expires in 7 days."
    )
    email.send_email(user["email"], "Verify your email", body)


def request_password_reset(email_address: str) -> None:
    user = db.get_user_by_email(email_address) if email_address else None
    if user is None:
        return
    token = _issue_token(user["id"], "reset", RESET_TTL)
    link = f"{_app_base_url()}/#reset={token}"
    body = (
        "We received a request to reset your Bulletin Maker password.\n\n"
        f"Open this link to choose a new password:\n{link}\n\n"
        "The link expires in 30 minutes. If you didn't ask for this, "
        "you can safely ignore this email."
    )
    email.send_email(user["email"], "Reset your password", body)


def reset_password(token: str, new_password: str) -> Optional[int]:
    user_id = _consume_token(token, "reset")
    if user_id is None:
        return None
    password_hash = security.hash_password(new_password)
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, user_id))
        conn.execute(
            "UPDATE auth_tokens SET used_at = now()"
            " WHERE user_id = %s AND purpose = 'reset' AND used_at IS NULL",
            (user_id,))
    return user_id


def request_magic_link(email_address: str) -> None:
    user = db.get_user_by_email(email_address) if email_address else None
    if user is None:
        return
    token = _issue_token(user["id"], "magic", MAGIC_TTL)
    link = f"{_app_base_url()}/#magic={token}"
    body = (
        "Here is your Bulletin Maker sign-in link:\n\n"
        f"{link}\n\n"
        "The link expires in 30 minutes and can be used once."
    )
    email.send_email(user["email"], "Your sign-in link", body)


def consume_magic_link(token: str) -> Optional[int]:
    return _consume_token(token, "magic")


def verify_email(token: str) -> bool:
    user_id = _consume_token(token, "verify")
    if user_id is None:
        return False
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET email_verified = true WHERE id = %s", (user_id,))
    return True

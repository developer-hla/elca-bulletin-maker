"""Password hashing and the S&S credential vault.

Passwords: stdlib scrypt with per-hash random salt.
S&S credentials: Fernet (AES-128-CBC + HMAC) with an instance key —
``$BULLETIN_SECRET_KEY`` in hosted deployments, or an auto-generated
keyfile at ~/.bulletin-maker/secret.key for local installs. Losing the
key means re-linking S&S accounts; nothing else is lost.
"""

from __future__ import annotations

import base64
import hmac
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from bulletin_maker.exceptions import BulletinError

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 32

KEYFILE = Path.home() / ".bulletin-maker" / "secret.key"


# ── Password hashing ─────────────────────────────────────────────────

def _derive(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32,
                 n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(password.encode())


def hash_password(password: str) -> str:
    """Hash a password with scrypt; returns a self-describing string."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt)
    return "scrypt${}${}".format(
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash (constant-time compare)."""
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    candidate = _derive(password, salt)
    return hmac.compare_digest(candidate, expected)


# ── Credential vault ─────────────────────────────────────────────────

def _load_key() -> bytes:
    env_key = os.environ.get("BULLETIN_SECRET_KEY")
    if env_key:
        return env_key.encode()
    if KEYFILE.exists():
        return KEYFILE.read_bytes().strip()
    key = Fernet.generate_key()
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_bytes(key)
    KEYFILE.chmod(0o600)
    return key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret with the instance key."""
    return Fernet(_load_key()).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a secret; raises BulletinError on key mismatch."""
    try:
        return Fernet(_load_key()).decrypt(token.encode()).decode()
    except InvalidToken:
        raise BulletinError(
            "Stored credential could not be decrypted — the instance "
            "secret key has changed. Re-link the Sundays & Seasons account."
        ) from None

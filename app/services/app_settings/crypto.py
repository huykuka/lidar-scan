"""Encrypt/decrypt secret settings with a key derived from an environment passphrase.

``SETTINGS_ENCRYPTION_KEY`` can be any string; it is stretched (PBKDF2-SHA256) into a Fernet key.
It lives outside the database, so a leaked ``data.db`` or
backup does not expose the credentials. Stored form: ``enc:v1:<fernet token>``.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

PREFIX = "enc:v1:"
# Fixed, app-specific salt: the passphrase is the only secret. Slow KDF makes brute-forcing a
# weak passphrase from a leaked database expensive.
_SALT = b"lidar-studio/app-settings/v1"
_ITERATIONS = 200_000


class EncryptionUnavailable(Exception):
    """No SETTINGS_ENCRYPTION_KEY is configured."""


class DecryptionFailed(Exception):
    """Stored value cannot be decrypted with the current key."""


@lru_cache(maxsize=4)
def _derive(passphrase: str) -> Fernet:
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), _SALT, _ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    """Fernet derived from any non-empty string in SETTINGS_ENCRYPTION_KEY."""
    passphrase = settings.SETTINGS_ENCRYPTION_KEY.strip()
    if not passphrase:
        raise EncryptionUnavailable("SETTINGS_ENCRYPTION_KEY is not set")
    return _derive(passphrase)


def unavailable_reason() -> str | None:
    """None when encryption works, otherwise why it does not."""
    try:
        _fernet()
        return None
    except EncryptionUnavailable as exc:
        return str(exc)


def is_available() -> bool:
    return unavailable_reason() is None


def encrypt(plaintext: str) -> str:
    return PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(stored: str) -> str:
    if not stored.startswith(PREFIX):
        raise DecryptionFailed("Value is not encrypted")
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise DecryptionFailed("Wrong encryption key or corrupted value") from exc

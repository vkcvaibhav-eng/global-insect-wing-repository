"""Small password-hashing helpers for the local Version 0.1 login.

The encoded value is self-describing so iteration counts can be increased
without invalidating existing accounts.  No plaintext password or global
application secret is embedded in source code.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

from .errors import ValidationError

PASSWORD_SCHEME = "pbkdf2_sha256"
DEFAULT_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_DERIVED_KEY_BYTES = 32
_MAX_PASSWORD_CHARACTERS = 4_096
_MAX_PARSED_ITERATIONS = 5_000_000


def normalize_email(value: str) -> str:
    """Return the canonical representation used for login lookup."""

    if not isinstance(value, str):
        raise ValidationError("Email address must be text.")
    normalized = value.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValidationError("Enter a valid email address.")
    return normalized


def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValidationError("Password must be text.")
    if not password:
        raise ValidationError("Password cannot be empty.")
    if len(password) > _MAX_PASSWORD_CHARACTERS:
        raise ValidationError("Password is too long.")


def hash_password(
    password: str,
    *,
    iterations: int = DEFAULT_PBKDF2_ITERATIONS,
) -> str:
    """Hash ``password`` using a fresh salt and PBKDF2-HMAC-SHA256."""

    _validate_password(password)
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise ValidationError("PBKDF2 iteration count must be an integer.")
    if iterations < 100_000 or iterations > _MAX_PARSED_ITERATIONS:
        raise ValidationError("PBKDF2 iteration count is outside the safe range.")

    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=_DERIVED_KEY_BYTES,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{PASSWORD_SCHEME}${iterations}${salt_text}${digest_text}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Return ``True`` only when ``password`` matches a valid encoded hash.

    Malformed or unsupported hashes return ``False`` rather than exposing
    parser details through the login endpoint.
    """

    if not isinstance(password, str) or not password or not isinstance(encoded_hash, str):
        return False
    if len(password) > _MAX_PASSWORD_CHARACTERS:
        return False

    try:
        scheme, iteration_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iteration_text)
        if iterations < 100_000 or iterations > _MAX_PARSED_ITERATIONS:
            return False
        salt = base64.b64decode(salt_text.encode("ascii"), altchars=b"-_", validate=True)
        expected = base64.b64decode(
            digest_text.encode("ascii"), altchars=b"-_", validate=True
        )
        if not salt or len(expected) != _DERIVED_KEY_BYTES:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
    except (ValueError, TypeError, UnicodeEncodeError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(
    encoded_hash: str,
    *,
    desired_iterations: int = DEFAULT_PBKDF2_ITERATIONS,
) -> bool:
    """Return whether a valid stored hash uses an older work factor/scheme."""

    try:
        scheme, iteration_text, _salt, _digest = encoded_hash.split("$", 3)
        return scheme != PASSWORD_SCHEME or int(iteration_text) < desired_iterations
    except (AttributeError, TypeError, ValueError):
        return True

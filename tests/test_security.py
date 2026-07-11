from __future__ import annotations

import pytest

from wing_repository.errors import ValidationError
from wing_repository.security import (
    PASSWORD_SCHEME,
    hash_password,
    normalize_email,
    password_needs_rehash,
    verify_password,
)


def test_email_normalization_is_stable_for_login_lookup() -> None:
    assert normalize_email("  Student@Example.COM ") == "student@example.com"


@pytest.mark.parametrize("value", ["", "not-an-email", "   ", None])
def test_email_normalization_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValidationError):
        normalize_email(value)  # type: ignore[arg-type]


def test_password_hash_round_trip_uses_fresh_salts() -> None:
    first = hash_password("correct horse battery staple", iterations=100_000)
    second = hash_password("correct horse battery staple", iterations=100_000)

    assert first.startswith(f"{PASSWORD_SCHEME}$100000$")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert verify_password("correct horse battery staple", second)
    assert not verify_password("wrong password", first)


@pytest.mark.parametrize(
    "encoded_hash",
    [
        "",
        "not-a-hash",
        "unknown$100000$c2FsdA==$ZGlnaWVzdA==",
        "pbkdf2_sha256$abc$c2FsdA==$ZGlnaWVzdA==",
        "pbkdf2_sha256$99999$c2FsdA==$ZGlnaWVzdA==",
        "pbkdf2_sha256$100000$%%%$%%%",
    ],
)
def test_verify_password_fails_closed_for_malformed_hashes(encoded_hash: str) -> None:
    assert not verify_password("password", encoded_hash)


@pytest.mark.parametrize(
    ("password", "iterations"),
    [
        ("", 100_000),
        ("password", 99_999),
        ("password", 5_000_001),
        ("password", True),
    ],
)
def test_hash_password_rejects_unsafe_inputs(password: str, iterations: object) -> None:
    with pytest.raises(ValidationError):
        hash_password(password, iterations=iterations)  # type: ignore[arg-type]


def test_password_needs_rehash_detects_older_work_factor() -> None:
    encoded = hash_password("password", iterations=100_000)

    assert not password_needs_rehash(encoded, desired_iterations=100_000)
    assert password_needs_rehash(encoded, desired_iterations=200_000)
    assert password_needs_rehash("malformed", desired_iterations=100_000)

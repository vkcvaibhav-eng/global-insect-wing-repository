from __future__ import annotations

import pytest

from wing_repository.config import Settings
from wing_repository.image_store import LocalImageStore, image_store_from_settings


@pytest.mark.parametrize("value", ["true", "1", "YES", "on"])
def test_demo_bootstrap_truthy_environment(monkeypatch, value: str) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", value)
    assert Settings.from_env().auto_bootstrap_demo


@pytest.mark.parametrize("value", ["false", "0", "NO", "off"])
def test_demo_bootstrap_falsey_environment(monkeypatch, value: str) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", value)
    assert not Settings.from_env().auto_bootstrap_demo


def test_demo_bootstrap_rejects_ambiguous_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_AUTO_BOOTSTRAP_DEMO", "sometimes")
    with pytest.raises(ValueError, match="must be true or false"):
        Settings.from_env()


def test_demo_password_reset_flag_uses_environment_bool(monkeypatch) -> None:
    monkeypatch.setenv("WBR_DEMO_RESET_PASSWORDS", "yes")

    assert Settings.from_env().demo_reset_passwords


def test_default_storage_backend_is_local(monkeypatch) -> None:
    monkeypatch.delenv("WBR_STORAGE_BACKEND", raising=False)
    settings = Settings.from_env()

    assert settings.storage_backend == "local"
    assert isinstance(image_store_from_settings(settings), LocalImageStore)


def test_r2_storage_settings_are_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_STORAGE_BACKEND", "R2")
    monkeypatch.setenv("WBR_R2_ENDPOINT_URL", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("WBR_R2_BUCKET_NAME", "wing-originals")
    monkeypatch.setenv("WBR_R2_ACCESS_KEY_ID", "access-key")
    monkeypatch.setenv("WBR_R2_SECRET_ACCESS_KEY", "secret-key")
    monkeypatch.setenv("WBR_R2_KEY_PREFIX", "hymenoptera/originals/")

    settings = Settings.from_env()

    assert settings.storage_backend == "r2"
    assert settings.r2_endpoint_url == "https://example.r2.cloudflarestorage.com"
    assert settings.r2_bucket_name == "wing-originals"
    assert settings.r2_access_key_id == "access-key"
    assert settings.r2_secret_access_key == "secret-key"
    assert settings.r2_key_prefix == "hymenoptera/originals/"


def test_storage_backend_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("WBR_STORAGE_BACKEND", "github")

    with pytest.raises(ValueError, match="WBR_STORAGE_BACKEND"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        (
            "postgresql://user:pass@example.neon.tech/db?sslmode=require",
            "postgresql+psycopg://user:pass@example.neon.tech/db?sslmode=require",
        ),
        (
            "postgres://user:pass@example.neon.tech/db?sslmode=require",
            "postgresql+psycopg://user:pass@example.neon.tech/db?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:pass@example.neon.tech/db?sslmode=require",
            "postgresql+psycopg://user:pass@example.neon.tech/db?sslmode=require",
        ),
    ],
)
def test_postgresql_urls_use_installed_psycopg_driver(
    monkeypatch,
    provided: str,
    expected: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", provided)

    assert Settings.from_env().database_url == expected

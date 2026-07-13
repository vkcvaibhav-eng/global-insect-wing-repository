from __future__ import annotations

import pytest

from wing_repository.config import Settings
from wing_repository.image_store import LocalImageStore, image_store_from_settings


def test_bootstrap_admin_settings_are_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_EMAIL", "curator@institute.edu")
    monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_FULL_NAME", "Institute Curator")
    monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_PASSWORD", "curator-password-2026")
    monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD", "yes")

    settings = Settings.from_env()

    assert settings.bootstrap_admin_email == "curator@institute.edu"
    assert settings.bootstrap_admin_full_name == "Institute Curator"
    assert settings.bootstrap_admin_password == "curator-password-2026"
    assert settings.bootstrap_admin_reset_password


def test_bootstrap_admin_reset_flag_rejects_ambiguous_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD", "sometimes")
    with pytest.raises(ValueError, match="must be true or false"):
        Settings.from_env()


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
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_BACKEND", "R2")
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_R2_PREFIX", "analysis-artifacts/")

    settings = Settings.from_env()

    assert settings.storage_backend == "r2"
    assert settings.r2_endpoint_url == "https://example.r2.cloudflarestorage.com"
    assert settings.r2_bucket_name == "wing-originals"
    assert settings.r2_access_key_id == "access-key"
    assert settings.r2_secret_access_key == "secret-key"
    assert settings.r2_key_prefix == "hymenoptera/originals/"
    assert settings.analysis_artifact_backend == "r2"
    assert settings.analysis_artifact_r2_prefix == "analysis-artifacts/"


def test_reference_data_settings_are_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", "C:/reference-data/oleksa")
    monkeypatch.setenv("WBR_NAWROCKA_REFERENCE_DIR", "C:/reference-data/nawrocka")
    monkeypatch.setenv("WBR_KAUR_INDIA_REFERENCE_DIR", "C:/reference-data/kaur-india")
    monkeypatch.setenv("WBR_SOUTHWEST_ASIA_REFERENCE_DIR", "C:/reference-data/southwest-asia")
    monkeypatch.setenv("WBR_KAZAKHSTAN_REFERENCE_DIR", "C:/reference-data/kazakhstan")
    monkeypatch.setenv("WBR_SERBIA_REFERENCE_DIR", "C:/reference-data/serbia")
    monkeypatch.setenv("WBR_MEXICO_REFERENCE_DIR", "C:/reference-data/mexico")
    monkeypatch.setenv(
        "WBR_NORTHWESTERN_EUROPE_REFERENCE_DIR",
        "C:/reference-data/northwestern-europe",
    )
    monkeypatch.setenv("WBR_ALGERIA_REFERENCE_DIR", "C:/reference-data/algeria")
    monkeypatch.setenv("WBR_QUEENS_DRONES_REFERENCE_DIR", "C:/reference-data/queens-drones")
    monkeypatch.setenv("WBR_APIS_WORKFLOW_DIR", "C:/reference-data/workflowhub")

    settings = Settings.from_env()

    assert str(settings.oleksa_reference_dir).replace("\\", "/") == "C:/reference-data/oleksa"
    assert str(settings.nawrocka_reference_dir).replace("\\", "/") == "C:/reference-data/nawrocka"
    assert str(settings.kaur_india_reference_dir).replace("\\", "/") == "C:/reference-data/kaur-india"
    assert str(settings.southwest_asia_reference_dir).replace("\\", "/") == "C:/reference-data/southwest-asia"
    assert str(settings.kazakhstan_reference_dir).replace("\\", "/") == "C:/reference-data/kazakhstan"
    assert str(settings.serbia_reference_dir).replace("\\", "/") == "C:/reference-data/serbia"
    assert str(settings.mexico_reference_dir).replace("\\", "/") == "C:/reference-data/mexico"
    assert (
        str(settings.northwestern_europe_reference_dir).replace("\\", "/")
        == "C:/reference-data/northwestern-europe"
    )
    assert str(settings.algeria_reference_dir).replace("\\", "/") == "C:/reference-data/algeria"
    assert str(settings.queens_drones_reference_dir).replace("\\", "/") == "C:/reference-data/queens-drones"
    assert str(settings.apis_workflow_dir).replace("\\", "/") == "C:/reference-data/workflowhub"


def test_storage_backend_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("WBR_STORAGE_BACKEND", "github")

    with pytest.raises(ValueError, match="WBR_STORAGE_BACKEND"):
        Settings.from_env()


def test_analysis_artifact_backend_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_BACKEND", "github")

    with pytest.raises(ValueError, match="WBR_ANALYSIS_ARTIFACT_BACKEND"):
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

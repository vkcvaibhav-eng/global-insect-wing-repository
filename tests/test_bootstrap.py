from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text

from wing_repository.bootstrap import ensure_database_ready
from wing_repository.config import get_settings
from wing_repository.db import build_engine, build_session_factory
from wing_repository.enums import Role, TemplateStatus
from wing_repository.models import LandmarkTemplate, RepositoryRecord, User
from wing_repository.security import verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_institution_bootstrap_migrates_and_creates_real_admin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "hosted" / "repository.sqlite3"
    data_dir = tmp_path / "hosted-data"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {
        "DATABASE_URL": database_url,
        "WBR_DATA_DIR": str(data_dir),
        "WBR_BOOTSTRAP_ADMIN_EMAIL": "curator@institute.edu",
        "WBR_BOOTSTRAP_ADMIN_FULL_NAME": "Institute Curator",
        "WBR_BOOTSTRAP_ADMIN_PASSWORD": "curator-password-2026",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    app_engine = build_engine(database_url)
    factory = build_session_factory(app_engine)

    try:
        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=settings,
        )
        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=settings,
        )
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert (
                session.scalar(select(func.count()).select_from(RepositoryRecord))
                == 0
            )
            admin = session.scalar(
                select(User).where(User.email == "curator@institute.edu")
            )
            assert admin is not None
            assert admin.role is Role.ADMINISTRATOR
            assert admin.is_active
            assert verify_password("curator-password-2026", admin.password_hash)
            template = session.scalar(select(LandmarkTemplate))
            assert template is not None
            assert template.status is TemplateStatus.PUBLISHED
            assert len(template.landmarks) == 19
    finally:
        app_engine.dispose()
        get_settings.cache_clear()


def test_existing_alembic_database_is_upgraded_on_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "existing.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "0001_initial")
    app_engine = build_engine(database_url)
    factory = build_session_factory(app_engine)

    try:
        with app_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "0001_initial"

        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=get_settings(),
        )

        with app_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "0007_sampling_metadata"
        assert "scale_mm_per_pixel" in {
            column["name"] for column in inspect(app_engine).get_columns("wing_images")
        }
    finally:
        app_engine.dispose()
        get_settings.cache_clear()


def test_bootstrap_requires_admin_configuration_for_empty_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}"
    app_engine = build_engine(database_url)
    factory = build_session_factory(app_engine)
    try:
        assert not ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
        )
    finally:
        app_engine.dispose()


def test_institution_bootstrap_can_reset_admin_password(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "hosted" / "repository.sqlite3"
    data_dir = tmp_path / "hosted-data"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {
        "DATABASE_URL": database_url,
        "WBR_DATA_DIR": str(data_dir),
        "WBR_BOOTSTRAP_ADMIN_EMAIL": "curator@institute.edu",
        "WBR_BOOTSTRAP_ADMIN_FULL_NAME": "Institute Curator",
        "WBR_BOOTSTRAP_ADMIN_PASSWORD": "old-curator-password",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app_engine = build_engine(database_url)
    factory = build_session_factory(app_engine)

    try:
        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=get_settings(),
        )
        with factory() as session:
            admin = session.scalar(
                select(User).where(User.email == "curator@institute.edu")
            )
            assert admin is not None
            assert verify_password("old-curator-password", admin.password_hash)

        monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_PASSWORD", "new-curator-password")
        monkeypatch.setenv("WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD", "true")
        get_settings.cache_clear()
        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=get_settings(),
        )
        with factory() as session:
            admin = session.scalar(
                select(User).where(User.email == "curator@institute.edu")
            )
            assert admin is not None
            assert not verify_password("old-curator-password", admin.password_hash)
            assert verify_password("new-curator-password", admin.password_hash)
    finally:
        app_engine.dispose()
        get_settings.cache_clear()

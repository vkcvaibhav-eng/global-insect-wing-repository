from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy import inspect, text

from wing_repository.bootstrap import ensure_database_ready
from wing_repository.config import Settings, get_settings
from wing_repository.db import build_engine, build_session_factory
from wing_repository.models import RepositoryRecord, User
from wing_repository.security import verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_opt_in_demo_bootstrap_migrates_and_seeds_idempotently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "hosted" / "repository.sqlite3"
    data_dir = tmp_path / "hosted-data"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {
        "DATABASE_URL": database_url,
        "WBR_DATA_DIR": str(data_dir),
        "WBR_AUTO_BOOTSTRAP_DEMO": "true",
        "WBR_DEMO_ADMIN_PASSWORD": "bootstrap-admin-123",
        "WBR_DEMO_STUDENT_PASSWORD": "bootstrap-student-123",
        "WBR_DEMO_REVIEWER_PASSWORD": "bootstrap-reviewer-123",
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
            assert session.scalar(select(func.count()).select_from(User)) == 3
            assert (
                session.scalar(select(func.count()).select_from(RepositoryRecord))
                == 1
            )
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
            ) == "0006_retire_apis_v1"
        assert "scale_mm_per_pixel" in {
            column["name"] for column in inspect(app_engine).get_columns("wing_images")
        }
    finally:
        app_engine.dispose()
        get_settings.cache_clear()


def test_demo_bootstrap_remains_disabled_by_default(tmp_path: Path) -> None:
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


def test_demo_bootstrap_can_reset_existing_demo_passwords(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "hosted" / "repository.sqlite3"
    data_dir = tmp_path / "hosted-data"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {
        "DATABASE_URL": database_url,
        "WBR_DATA_DIR": str(data_dir),
        "WBR_AUTO_BOOTSTRAP_DEMO": "true",
        "WBR_DEMO_ADMIN_PASSWORD": "old-admin-password",
        "WBR_DEMO_STUDENT_PASSWORD": "old-student-password",
        "WBR_DEMO_REVIEWER_PASSWORD": "old-reviewer-password",
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
            student = session.scalar(
                select(User).where(User.email == "student@example.test")
            )
            assert student is not None
            assert verify_password("old-student-password", student.password_hash)

        monkeypatch.setenv("WBR_DEMO_ADMIN_PASSWORD", "new-admin-password")
        monkeypatch.setenv("WBR_DEMO_STUDENT_PASSWORD", "new-student-password")
        monkeypatch.setenv("WBR_DEMO_REVIEWER_PASSWORD", "new-reviewer-password")
        monkeypatch.setenv("WBR_DEMO_RESET_PASSWORDS", "true")
        get_settings.cache_clear()
        assert ensure_database_ready(
            app_engine=app_engine,
            session_factory=factory,
            settings=get_settings(),
        )
        with factory() as session:
            student = session.scalar(
                select(User).where(User.email == "student@example.test")
            )
            assert student is not None
            assert not verify_password("old-student-password", student.password_hash)
            assert verify_password("new-student-password", student.password_hash)
    finally:
        app_engine.dispose()
        get_settings.cache_clear()

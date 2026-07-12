"""Opt-in database bootstrap for disposable hosted demonstrations."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from wing_repository.config import Settings, get_settings
from wing_repository.db import SessionLocal, engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_bootstrap_lock = Lock()


def _prepare_demo_storage(settings: Settings) -> None:
    """Create writable local directories before the first SQLite connection."""

    settings.data_dir.expanduser().mkdir(parents=True, exist_ok=True)
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return
    database_path = Path(url.database).expanduser()
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


def ensure_database_ready(
    *,
    app_engine: Engine = engine,
    session_factory: sessionmaker[Session] = SessionLocal,
    settings: Settings | None = None,
) -> bool:
    """Return whether the schema exists, optionally creating a demo database.

    Automatic migration and seeding are deliberately gated behind
    ``WBR_AUTO_BOOTSTRAP_DEMO``. The mode is intended for disposable Streamlit
    Community Cloud demonstrations only, never production repositories.
    """

    active_settings = settings or get_settings()
    if active_settings.auto_bootstrap_demo:
        _prepare_demo_storage(active_settings)
    if inspect(app_engine).has_table("users"):
        if active_settings.auto_bootstrap_demo and active_settings.demo_reset_passwords:
            with _bootstrap_lock:
                alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
                command.upgrade(alembic_config, "head")
                from scripts.seed_demo import seed_demo_accounts

                with session_factory() as session:
                    seed_demo_accounts(
                        session,
                        reset_passwords=active_settings.demo_reset_passwords,
                    )
        elif active_settings.auto_bootstrap_demo:
            with _bootstrap_lock:
                alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
                command.upgrade(alembic_config, "head")
        return True
    if not active_settings.auto_bootstrap_demo:
        return False

    with _bootstrap_lock:
        if inspect(app_engine).has_table("users"):
            return True
        alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
        command.upgrade(alembic_config, "head")

        # Import lazily so ordinary production startup does not depend on the
        # repository maintenance command package.
        from scripts.seed_demo import seed_demo

        with session_factory() as session:
            seed_demo(session)
    return inspect(app_engine).has_table("users")


__all__ = ["ensure_database_ready"]

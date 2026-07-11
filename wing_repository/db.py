"""SQLAlchemy engine and session configuration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wing_repository.config import get_settings


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every repository entity."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    """Enable FK enforcement for every SQLite DB-API connection."""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def build_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Create an engine suitable for Streamlit and tests.

    SQLite needs ``check_same_thread=False`` because Streamlit can execute a
    session on different worker threads. An in-memory SQLite URL also uses one
    static connection so separate ORM sessions see the same database.
    """

    url = database_url or get_settings().database_url
    parsed_url = make_url(url)
    kwargs: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}

    if parsed_url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if parsed_url.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool
        else:
            Path(parsed_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, **kwargs)
    if parsed_url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the session factory used by services and tests."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = build_engine()
SessionLocal = build_session_factory(engine)


@contextmanager
def session_scope(
    factory: sessionmaker[Session] = SessionLocal,
) -> Iterator[Session]:
    """Provide a transaction boundary that rolls back on failure."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Yield a session for dependency-style callers."""

    with session_scope() as session:
        yield session

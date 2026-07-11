from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from wing_repository.db import Base, build_engine, build_session_factory
from wing_repository.enums import Role, TemplateStatus
from wing_repository.image_store import LocalImageStore
from wing_repository.models import (
    Assignment,
    LandmarkTemplate,
    Taxon,
    TemplateLandmark,
    User,
)


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Engine:
    """Create a file-backed SQLite database with production-like FK checks."""

    database_path = tmp_path / "repository-test.sqlite3"
    engine = build_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Session:
    factory = build_session_factory(sqlite_engine)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _user(session: Session, *, email: str, name: str, role: Role) -> User:
    user = User(
        email=email,
        full_name=name,
        password_hash="test-only-password-hash",
        role=role,
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def administrator(db_session: Session) -> User:
    return _user(
        db_session,
        email="administrator@example.test",
        name="Test Administrator",
        role=Role.ADMINISTRATOR,
    )


@pytest.fixture
def student(db_session: Session) -> User:
    return _user(
        db_session,
        email="student@example.test",
        name="Test Student",
        role=Role.STUDENT,
    )


@pytest.fixture
def reviewer(db_session: Session) -> User:
    return _user(
        db_session,
        email="reviewer@example.test",
        name="Test Reviewer",
        role=Role.EXPERT_REVIEWER,
    )


@pytest.fixture
def second_student(db_session: Session) -> User:
    return _user(
        db_session,
        email="other-student@example.test",
        name="Other Student",
        role=Role.STUDENT,
    )


@pytest.fixture
def taxon(db_session: Session) -> Taxon:
    record = Taxon(family="Apidae", genus="Apis", genus_code="APIS")
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def landmark_template(
    db_session: Session,
    administrator: User,
    taxon: Taxon,
) -> LandmarkTemplate:
    template = LandmarkTemplate(
        taxon_id=taxon.id,
        version=1,
        name="Apis test template",
        status=TemplateStatus.PUBLISHED,
        created_by_id=administrator.id,
    )
    db_session.add(template)
    db_session.flush()
    db_session.add_all(
        [
            TemplateLandmark(
                template_id=template.id,
                ordinal=ordinal,
                label=f"LM{ordinal:02d}",
                description=f"Test landmark {ordinal}",
            )
            for ordinal in range(1, 4)
        ]
    )
    db_session.flush()
    db_session.refresh(template)
    return template


@pytest.fixture
def assignment(
    db_session: Session,
    student: User,
    administrator: User,
    taxon: Taxon,
    landmark_template: LandmarkTemplate,
) -> Assignment:
    record = Assignment(
        student_id=student.id,
        taxon_id=taxon.id,
        template_id=landmark_template.id,
        assigned_by_id=administrator.id,
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 50), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def image_store(tmp_path: Path) -> LocalImageStore:
    return LocalImageStore(tmp_path / "original-images")

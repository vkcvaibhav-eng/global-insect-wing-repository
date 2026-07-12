from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.enums import Role
from wing_repository.errors import AuthorizationError, ConflictError, ValidationError
from wing_repository.models import User
from wing_repository.security import verify_password
from wing_repository.services import create_user_account


def test_administrator_can_create_student_account(
    db_session: Session,
    administrator: User,
) -> None:
    created = create_user_account(
        db_session,
        administrator,
        email=" New.Student@Example.TEST ",
        full_name=" New Student ",
        role=Role.STUDENT,
        password="student-password-2026",
    )

    assert created.id is not None
    assert created.email == "new.student@example.test"
    assert created.full_name == "New Student"
    assert created.role is Role.STUDENT
    assert created.is_active
    assert verify_password("student-password-2026", created.password_hash)


def test_created_student_email_must_be_unique(
    db_session: Session,
    administrator: User,
) -> None:
    create_user_account(
        db_session,
        administrator,
        email="duplicate.student@example.test",
        full_name="Duplicate Student",
        role=Role.STUDENT,
        password="student-password-2026",
    )

    with pytest.raises(ConflictError, match="email"):
        create_user_account(
            db_session,
            administrator,
            email=" DUPLICATE.STUDENT@example.test ",
            full_name="Other Student",
            role=Role.STUDENT,
            password="another-password-2026",
        )


def test_non_administrator_cannot_create_user_account(
    db_session: Session,
    student: User,
) -> None:
    with pytest.raises(AuthorizationError):
        create_user_account(
            db_session,
            student,
            email="blocked@example.test",
            full_name="Blocked User",
            role=Role.STUDENT,
            password="blocked-password-2026",
        )


def test_administrator_cannot_create_administrator_account_in_version_01(
    db_session: Session,
    administrator: User,
) -> None:
    with pytest.raises(ValidationError, match="student or reviewer"):
        create_user_account(
            db_session,
            administrator,
            email="other.admin@example.test",
            full_name="Other Admin",
            role=Role.ADMINISTRATOR,
            password="admin-password-2026",
        )


def test_created_reviewer_account_is_queryable(
    db_session: Session,
    administrator: User,
) -> None:
    create_user_account(
        db_session,
        administrator,
        email="reviewer.two@example.test",
        full_name="Reviewer Two",
        role=Role.EXPERT_REVIEWER,
        password="reviewer-password-2026",
    )

    reviewer = db_session.scalar(
        select(User).where(User.email == "reviewer.two@example.test")
    )
    assert reviewer is not None
    assert reviewer.role is Role.EXPERT_REVIEWER

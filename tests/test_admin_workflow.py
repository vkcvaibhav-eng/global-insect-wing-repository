from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wing_repository.enums import Role, TemplateStatus
from wing_repository.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from wing_repository.models import LandmarkTemplate, User
from wing_repository.security import verify_password
from wing_repository.services import (
    approve_user_account,
    authenticate_user,
    create_user_account,
    import_bundled_sample_template,
    request_student_signup,
)


def test_student_signup_creates_pending_inactive_account(
    db_session: Session,
) -> None:
    created = request_student_signup(
        db_session,
        email=" Student.Signup@Gmail.COM ",
        full_name=" Student Signup ",
        password="student-signup-password-2026",
    )

    assert created.id is not None
    assert created.email == "student.signup@gmail.com"
    assert created.full_name == "Student Signup"
    assert created.role is Role.STUDENT
    assert not created.is_active
    assert verify_password("student-signup-password-2026", created.password_hash)


def test_pending_student_signup_cannot_authenticate_until_approved(
    db_session: Session,
    administrator: User,
) -> None:
    pending = request_student_signup(
        db_session,
        email="waiting.student@example.test",
        full_name="Waiting Student",
        password="waiting-password-2026",
    )

    with pytest.raises(AuthenticationError):
        authenticate_user(
            db_session,
            "waiting.student@example.test",
            "waiting-password-2026",
        )

    approved = approve_user_account(
        db_session,
        administrator,
        user_id=pending.id,
    )
    assert approved.is_active
    authenticated = authenticate_user(
        db_session,
        "waiting.student@example.test",
        "waiting-password-2026",
    )
    assert authenticated.id == pending.id


def test_non_administrator_cannot_approve_student_signup(
    db_session: Session,
    student: User,
) -> None:
    pending = request_student_signup(
        db_session,
        email="approval.blocked@example.test",
        full_name="Approval Blocked",
        password="approval-password-2026",
    )

    with pytest.raises(AuthorizationError):
        approve_user_account(
            db_session,
            student,
            user_id=pending.id,
        )


def test_student_signup_email_must_be_unique(db_session: Session) -> None:
    request_student_signup(
        db_session,
        email="duplicate.signup@example.test",
        full_name="Duplicate Signup",
        password="signup-password-2026",
    )

    with pytest.raises(ConflictError, match="email"):
        request_student_signup(
            db_session,
            email=" DUPLICATE.SIGNUP@example.test ",
            full_name="Duplicate Signup Again",
            password="signup-password-2027",
        )


def test_administrator_can_import_bundled_sample_template(
    db_session: Session,
    administrator: User,
) -> None:
    created = import_bundled_sample_template(db_session, administrator)
    same = import_bundled_sample_template(db_session, administrator)

    assert same.id == created.id
    assert created.status is TemplateStatus.PUBLISHED
    assert created.taxon.genus == "Apis"
    assert created.taxon.genus_code == "APIS"
    assert len(created.landmarks) == 10
    assert db_session.scalar(select(func.count()).select_from(LandmarkTemplate)) == 1


def test_non_administrator_cannot_import_bundled_sample_template(
    db_session: Session,
    student: User,
) -> None:
    with pytest.raises(AuthorizationError):
        import_bundled_sample_template(db_session, student)


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

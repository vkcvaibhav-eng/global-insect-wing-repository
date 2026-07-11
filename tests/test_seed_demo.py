from __future__ import annotations

import pytest

from scripts.seed_demo import _required_passwords
from wing_repository.enums import Role
from wing_repository.errors import ConflictError


def test_demo_seed_requires_every_password() -> None:
    with pytest.raises(ConflictError, match="missing"):
        _required_passwords({})


def test_demo_seed_rejects_example_placeholders() -> None:
    with pytest.raises(ConflictError, match="placeholders"):
        _required_passwords(
            {
                "WBR_DEMO_ADMIN_PASSWORD": "change-this-admin-password",
                "WBR_DEMO_STUDENT_PASSWORD": "student-password-123",
                "WBR_DEMO_REVIEWER_PASSWORD": "reviewer-password-123",
            }
        )


def test_demo_seed_requires_distinct_role_passwords() -> None:
    with pytest.raises(ConflictError, match="different password"):
        _required_passwords(
            {
                "WBR_DEMO_ADMIN_PASSWORD": "same-password-123",
                "WBR_DEMO_STUDENT_PASSWORD": "same-password-123",
                "WBR_DEMO_REVIEWER_PASSWORD": "reviewer-password-123",
            }
        )


def test_demo_seed_accepts_strong_distinct_environment_values() -> None:
    passwords = _required_passwords(
        {
            "WBR_DEMO_ADMIN_PASSWORD": "admin-password-123",
            "WBR_DEMO_STUDENT_PASSWORD": "student-password-123",
            "WBR_DEMO_REVIEWER_PASSWORD": "reviewer-password-123",
        }
    )

    assert passwords == {
        Role.ADMINISTRATOR: "admin-password-123",
        Role.STUDENT: "student-password-123",
        Role.EXPERT_REVIEWER: "reviewer-password-123",
    }

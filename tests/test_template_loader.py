from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wing_repository.enums import Role, TemplateStatus, WingSide, WingType
from wing_repository.errors import AuthorizationError, ConflictError, ValidationError
from wing_repository.models import LandmarkTemplate, Taxon, TemplateLandmark, User
from wing_repository.template_loader import (
    create_template,
    load_template_definition,
    parse_template_definition,
)


SAMPLE_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "demo_data" / "templates" / "apis_v1.json"
)


@pytest.fixture
def sample_document() -> dict[str, object]:
    return json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))


def test_sample_template_loads_with_exact_version_and_ordered_landmarks() -> None:
    definition = load_template_definition(SAMPLE_TEMPLATE)

    assert definition.schema_version == "1.0"
    assert definition.order == "Hymenoptera"
    assert definition.genus == "Apis"
    assert definition.genus_code == "APIS"
    assert definition.version == 1
    assert definition.status is TemplateStatus.PUBLISHED
    assert definition.wing_side is WingSide.RIGHT
    assert definition.wing_type is WingType.FOREWING
    assert [item.ordinal for item in definition.landmarks] == list(range(1, 11))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("order", "Diptera"),
        ("genus_code", "A-INVALID"),
        ("genus_code", "ABCDEFGHIJKLM"),
        ("version", 0),
        ("version", True),
        ("wing_side", "LEFT"),
        ("wing_type", "HINDWING"),
    ],
)
def test_template_parser_rejects_out_of_scope_or_invalid_fields(
    sample_document: dict[str, object], field: str, value: object
) -> None:
    sample_document[field] = value

    with pytest.raises(ValidationError):
        parse_template_definition(sample_document)


def test_template_parser_requires_contiguous_landmark_ordinals(
    sample_document: dict[str, object],
) -> None:
    document = deepcopy(sample_document)
    landmarks = document["landmarks"]
    assert isinstance(landmarks, list)
    assert isinstance(landmarks[1], dict)
    landmarks[1]["ordinal"] = 3

    with pytest.raises(ValidationError, match="contiguous"):
        parse_template_definition(document)


def test_template_parser_rejects_case_insensitive_duplicate_labels(
    sample_document: dict[str, object],
) -> None:
    document = deepcopy(sample_document)
    landmarks = document["landmarks"]
    assert isinstance(landmarks, list)
    assert isinstance(landmarks[0], dict)
    assert isinstance(landmarks[1], dict)
    landmarks[1]["label"] = str(landmarks[0]["label"]).lower()

    with pytest.raises(ValidationError, match="Duplicate"):
        parse_template_definition(document)


def test_admin_can_import_template_and_repeat_is_idempotent(
    db_session: Session,
    administrator: User,
) -> None:
    definition = load_template_definition(SAMPLE_TEMPLATE)

    created = create_template(db_session, definition, created_by=administrator)
    same = create_template(db_session, definition, created_by=administrator)

    assert same.id == created.id
    assert created.created_by_id == administrator.id
    assert created.source_json
    assert created.source_sha256 and len(created.source_sha256) == 64
    assert created.taxon.order_name == "Hymenoptera"
    assert created.taxon.genus == "Apis"
    assert created.taxon.genus_code == "APIS"
    assert [item.ordinal for item in created.landmarks] == list(range(1, 11))
    assert db_session.scalar(select(func.count()).select_from(Taxon)) == 1
    assert db_session.scalar(select(func.count()).select_from(LandmarkTemplate)) == 1
    assert db_session.scalar(select(func.count()).select_from(TemplateLandmark)) == 10


def test_non_admin_cannot_import_a_template(
    db_session: Session,
    student: User,
) -> None:
    definition = load_template_definition(SAMPLE_TEMPLATE)

    with pytest.raises(AuthorizationError):
        create_template(db_session, definition, created_by=student)

    assert db_session.scalar(select(func.count()).select_from(LandmarkTemplate)) == 0


def test_same_genus_version_with_different_content_is_rejected(
    db_session: Session,
    administrator: User,
    sample_document: dict[str, object],
) -> None:
    first = parse_template_definition(sample_document)
    create_template(db_session, first, created_by=administrator)
    changed = deepcopy(sample_document)
    changed["template_name"] = "Conflicting definition"

    with pytest.raises(ConflictError):
        create_template(
            db_session,
            parse_template_definition(changed),
            created_by=administrator,
        )


def test_inactive_administrator_cannot_import_template(
    db_session: Session,
    administrator: User,
) -> None:
    administrator.is_active = False
    db_session.flush()

    with pytest.raises(AuthorizationError):
        create_template(
            db_session,
            load_template_definition(SAMPLE_TEMPLATE),
            created_by=administrator,
        )

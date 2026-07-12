from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wing_repository.enums import SpeciesIdentificationMethod, WingSide, WingType
from wing_repository.errors import AuthorizationError, TemplateVersionMismatchError, ValidationError
from wing_repository.image_store import LocalImageStore
from wing_repository.models import Assignment, Specimen, Taxon, User, WingImage
from wing_repository.services import create_specimen_with_image


def _required_metadata(specimen_code: str) -> dict[str, object]:
    return {
        "species_text": "Apis mellifera",
        "species_identification_method": SpeciesIdentificationMethod.DICHOTOMOUS_KEY,
        "sex": "worker",
        "collection_date": date(2026, 1, 1),
        "country": "India",
        "locality": "Test locality",
        "locality_sample_code": f"{specimen_code}-LOC",
        "locality_sample_size": 15,
        "locality_sample_number": 1,
        "collector_name": "Test Collector",
    }


def test_create_specimen_with_image_preserves_original_and_assignment_provenance(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    specimen, wing_image = create_specimen_with_image(
        db_session,
        student,
        image_store,
        specimen_code="  APIS-001  ",
        image_bytes=image_bytes,
        original_filename=r"C:\private\right forewing.png",
        assignment_id=assignment.id,
        **_required_metadata("APIS-001"),
        latitude=12.5,
        longitude=77.6,
    )

    assert specimen.specimen_code == "APIS-001"
    assert specimen.species_text == "Apis mellifera"
    assert specimen.species_identification_method is SpeciesIdentificationMethod.DICHOTOMOUS_KEY
    assert specimen.sex == "worker"
    assert specimen.collection_date == date(2026, 1, 1)
    assert specimen.country == "India"
    assert specimen.locality == "Test locality"
    assert specimen.locality_sample_code == "APIS-001-LOC"
    assert specimen.locality_sample_size == 15
    assert specimen.locality_sample_number == 1
    assert specimen.collector_name == "Test Collector"
    assert specimen.assignment_id == assignment.id
    assert specimen.taxon_id == assignment.taxon_id
    assert specimen.contributor_id == student.id
    assert wing_image.specimen_id == specimen.id
    assert wing_image.uploaded_by_id == student.id
    assert wing_image.side is WingSide.RIGHT
    assert wing_image.wing_type is WingType.FOREWING
    assert wing_image.original_filename == "right forewing.png"
    assert wing_image.sha256 == sha256(image_bytes).hexdigest()
    assert wing_image.byte_size == len(image_bytes)
    assert (wing_image.image_width, wing_image.image_height) == (100, 50)
    assert image_store.load_original(wing_image.storage_key) == image_bytes


def test_required_specimen_metadata_is_enforced(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    metadata = _required_metadata("APIS-MISSING")
    metadata["country"] = " "

    with pytest.raises(ValidationError, match="Country"):
        create_specimen_with_image(
            db_session,
            student,
            image_store,
            specimen_code="APIS-MISSING",
            image_bytes=image_bytes,
            original_filename="wing.png",
            assignment_id=assignment.id,
            **metadata,
        )


def test_molecular_identification_requires_genbank_accession(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    metadata = _required_metadata("APIS-MOLECULAR")
    metadata["species_identification_method"] = SpeciesIdentificationMethod.MOLECULAR

    with pytest.raises(ValidationError, match="GenBank"):
        create_specimen_with_image(
            db_session,
            student,
            image_store,
            specimen_code="APIS-MOLECULAR",
            image_bytes=image_bytes,
            original_filename="wing.png",
            assignment_id=assignment.id,
            **metadata,
        )

    metadata["genbank_accession"] = "OR123456"
    specimen, _wing_image = create_specimen_with_image(
        db_session,
        student,
        image_store,
        specimen_code="APIS-MOLECULAR",
        image_bytes=image_bytes,
        original_filename="wing.png",
        assignment_id=assignment.id,
        **metadata,
    )
    assert specimen.genbank_accession == "OR123456"


def test_locality_sample_count_must_meet_template_minimum(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    metadata = _required_metadata("APIS-SMALL-SAMPLE")
    metadata["locality_sample_size"] = 9

    with pytest.raises(ValidationError, match="At least 10 wings"):
        create_specimen_with_image(
            db_session,
            student,
            image_store,
            specimen_code="APIS-SMALL-SAMPLE",
            image_bytes=image_bytes,
            original_filename="wing.png",
            assignment_id=assignment.id,
            **metadata,
        )


def test_invalid_image_rolls_back_specimen_and_leaves_no_original(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
) -> None:
    with pytest.raises(ValidationError):
        create_specimen_with_image(
            db_session,
            student,
            image_store,
            specimen_code="APIS-BAD",
            image_bytes=b"not an image",
            original_filename="bad.png",
            assignment_id=assignment.id,
            **_required_metadata("APIS-BAD"),
        )

    assert db_session.scalar(select(func.count()).select_from(Specimen)) == 0
    assert db_session.scalar(select(func.count()).select_from(WingImage)) == 0
    assert not image_store.root.exists()


def test_student_cannot_upload_under_another_students_assignment(
    db_session: Session,
    second_student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    with pytest.raises(AuthorizationError):
        create_specimen_with_image(
            db_session,
            second_student,
            image_store,
            specimen_code="STOLEN-ASSIGNMENT",
            image_bytes=image_bytes,
            original_filename="wing.png",
            assignment_id=assignment.id,
            **_required_metadata("STOLEN-ASSIGNMENT"),
        )

    assert db_session.scalar(select(func.count()).select_from(Specimen)) == 0
    assert not image_store.root.exists()


def test_explicit_taxon_must_match_exact_assignment(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    other_taxon = Taxon(family="Vespidae", genus="Vespa", genus_code="VESP")
    db_session.add(other_taxon)
    db_session.flush()

    with pytest.raises(TemplateVersionMismatchError):
        create_specimen_with_image(
            db_session,
            student,
            image_store,
            specimen_code="WRONG-GENUS",
            image_bytes=image_bytes,
            original_filename="wing.png",
            assignment_id=assignment.id,
            taxon_id=other_taxon.id,
            **_required_metadata("WRONG-GENUS"),
        )

    assert not image_store.root.exists()

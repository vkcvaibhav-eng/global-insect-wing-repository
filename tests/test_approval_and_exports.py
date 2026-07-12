from __future__ import annotations

import csv
from datetime import date
from io import StringIO

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wing_repository.enums import (
    AnnotationStatus,
    ReviewDecision,
    SpeciesIdentificationMethod,
    TemplateStatus,
)
from wing_repository.errors import (
    AuthorizationError,
    ConflictError,
    ExportError,
    InvalidStateError,
    ValidationError,
)
from wing_repository.exports import export_approved_csv, export_approved_tps
from wing_repository.image_store import LocalImageStore
from wing_repository.models import (
    Annotation,
    Assignment,
    LandmarkTemplate,
    RepositoryRecord,
    Review,
    Taxon,
    TemplateLandmark,
    User,
)
from wing_repository.services import (
    approve_annotation,
    calibrate_wing_image_scale,
    create_draft_annotation,
    create_specimen_with_image,
    place_annotation_point,
    return_annotation,
    submit_annotation,
)


POINTS = ((10.0, 5.0), (20.5, 10.25), (30.0, 15.0))


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


def _submitted_annotation(
    session: Session,
    student: User,
    assignment: Assignment,
    template: LandmarkTemplate,
    store: LocalImageStore,
    data: bytes,
    *,
    specimen_code: str,
    filename: str = "wing.png",
    calibrate: bool = False,
) -> Annotation:
    _specimen, image = create_specimen_with_image(
        session,
        student,
        store,
        specimen_code=specimen_code,
        image_bytes=data,
        original_filename=filename,
        assignment_id=assignment.id,
        **_required_metadata(specimen_code),
    )
    if calibrate:
        calibrate_wing_image_scale(
            session,
            student,
            wing_image_id=image.id,
            reference_length=1.0,
            reference_unit="millimeters",
            x1_pixel=0,
            y1_pixel=0,
            x2_pixel=50,
            y2_pixel=0,
        )
    annotation = create_draft_annotation(session, student, wing_image_id=image.id)
    for landmark, (x, y) in zip(template.landmarks, POINTS, strict=True):
        place_annotation_point(
            session,
            student,
            annotation_id=annotation.id,
            template_landmark_id=landmark.id,
            x_pixel=x,
            y_pixel=y,
        )
    return submit_annotation(session, student, annotation_id=annotation.id)


def _second_genus_assignment(
    session: Session,
    administrator: User,
    second_student: User,
) -> tuple[Taxon, LandmarkTemplate, Assignment]:
    taxon = Taxon(family="Vespidae", genus="Vespa", genus_code="VESP")
    session.add(taxon)
    session.flush()
    template = LandmarkTemplate(
        taxon_id=taxon.id,
        version=1,
        name="Vespa test template",
        status=TemplateStatus.PUBLISHED,
        created_by_id=administrator.id,
    )
    session.add(template)
    session.flush()
    session.add_all(
        [
            TemplateLandmark(
                template_id=template.id,
                ordinal=ordinal,
                label=f"V{ordinal:02d}",
                description=f"Vespa landmark {ordinal}",
            )
            for ordinal in range(1, 4)
        ]
    )
    session.flush()
    assignment = Assignment(
        student_id=second_student.id,
        taxon_id=taxon.id,
        template_id=template.id,
        assigned_by_id=administrator.id,
    )
    session.add(assignment)
    session.flush()
    session.refresh(template)
    return taxon, template, assignment


def test_approval_allocates_per_genus_accessions_and_is_idempotent(
    db_session: Session,
    student: User,
    second_student: User,
    reviewer: User,
    administrator: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    taxon: Taxon,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    first = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-001",
    )

    with pytest.raises(AuthorizationError):
        approve_annotation(db_session, student, annotation_id=first.id)
    first_record = approve_annotation(db_session, reviewer, annotation_id=first.id)
    repeated = approve_annotation(db_session, reviewer, annotation_id=first.id)
    assert first_record.accession_number == "WBR-HYM-APIS-000001"
    assert repeated.id == first_record.id
    assert first.status is AnnotationStatus.APPROVED
    assert first_record.review.decision is ReviewDecision.APPROVE
    assert taxon.next_accession_serial == 2

    second = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-002",
    )
    second_record = approve_annotation(db_session, reviewer, annotation_id=second.id)
    assert second_record.accession_number == "WBR-HYM-APIS-000002"

    second_taxon, second_template, second_assignment = _second_genus_assignment(
        db_session,
        administrator,
        second_student,
    )
    other_genus = _submitted_annotation(
        db_session,
        second_student,
        second_assignment,
        second_template,
        image_store,
        image_bytes,
        specimen_code="VESP-001",
    )
    other_record = approve_annotation(
        db_session,
        reviewer,
        annotation_id=other_genus.id,
    )
    assert other_record.accession_number == "WBR-HYM-VESP-000001"
    assert second_taxon.next_accession_serial == 2
    assert db_session.scalar(select(func.count()).select_from(RepositoryRecord)) == 3


def test_returned_annotation_can_never_be_approved(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    annotation = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-RETURNED",
    )
    return_annotation(
        db_session,
        reviewer,
        annotation_id=annotation.id,
        comments="Please revise.",
    )

    with pytest.raises(InvalidStateError):
        approve_annotation(db_session, reviewer, annotation_id=annotation.id)

    assert db_session.scalar(select(func.count()).select_from(RepositoryRecord)) == 0


def test_approval_rejects_corrupt_coordinate_pair_atomically(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    taxon: Taxon,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    annotation = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-CORRUPT",
    )
    annotation.points[0].x_normalized += 0.01
    db_session.commit()

    with pytest.raises(ValidationError, match="inconsistent normalized"):
        approve_annotation(db_session, reviewer, annotation_id=annotation.id)

    assert annotation.status is AnnotationStatus.SUBMITTED
    assert taxon.next_accession_serial == 1
    assert db_session.scalar(select(func.count()).select_from(Review)) == 0
    assert db_session.scalar(select(func.count()).select_from(RepositoryRecord)) == 0


def test_accession_exhaustion_does_not_create_partial_approval(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    taxon: Taxon,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    annotation = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-EXHAUSTED",
    )
    taxon.next_accession_serial = 1_000_000
    db_session.commit()

    with pytest.raises(ConflictError, match="exhausted"):
        approve_annotation(db_session, reviewer, annotation_id=annotation.id)

    assert annotation.status is AnnotationStatus.SUBMITTED
    assert db_session.scalar(select(func.count()).select_from(Review)) == 0
    assert db_session.scalar(select(func.count()).select_from(RepositoryRecord)) == 0


def test_csv_and_tps_are_approved_only_ordered_and_exact_template(
    db_session: Session,
    student: User,
    reviewer: User,
    administrator: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    approved = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS,APPROVED",
        filename="wing, source.png",
    )
    record = approve_annotation(db_session, reviewer, annotation_id=approved.id)
    pending = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-PENDING",
    )

    csv_text = export_approved_csv(db_session, template_id=landmark_template.id)
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert len(rows) == 3
    assert {row["accession_number"] for row in rows} == {record.accession_number}
    assert pending.id not in {int(row["annotation_id"]) for row in rows}
    assert [int(row["landmark_ordinal"]) for row in rows] == [1, 2, 3]
    assert [float(row["x_pixel"]) for row in rows] == [10.0, 20.5, 30.0]
    assert [float(row["y_pixel"]) for row in rows] == [5.0, 10.25, 15.0]
    assert [float(row["x_normalized"]) for row in rows] == [0.1, 0.205, 0.3]
    assert [float(row["y_normalized"]) for row in rows] == [0.1, 0.205, 0.3]
    assert {row["mm_per_pixel"] for row in rows} == {""}
    assert {row["x_mm"] for row in rows} == {""}
    assert {row["y_mm"] for row in rows} == {""}
    assert {row["template_id"] for row in rows} == {str(landmark_template.id)}
    assert {row["template_version"] for row in rows} == {"1"}
    assert {row["specimen_code"] for row in rows} == {"APIS,APPROVED"}
    assert {row["species"] for row in rows} == {"Apis mellifera"}
    assert {row["species_identification_method"] for row in rows} == {
        "dichotomous_key"
    }
    assert {row["locality_sample_size"] for row in rows} == {"15"}
    assert {row["locality_sample_number"] for row in rows} == {"1"}
    assert {row["original_filename"] for row in rows} == {"wing, source.png"}

    tps_text = export_approved_tps(db_session, template_id=landmark_template.id)
    assert tps_text.splitlines() == [
        "LM=3",
        "10 5",
        "20.5 10.25",
        "30 15",
        f"ID={record.accession_number}",
        "IMAGE=wing, source.png",
        (
            "COMMENT="
            f"template_id:{landmark_template.id};template_version:1;"
            f"annotation_id:{approved.id};revision:1;"
            "origin:top-left;y_axis:down;units:source_pixels"
        ),
    ]

    incompatible = LandmarkTemplate(
        taxon_id=landmark_template.taxon_id,
        version=2,
        name="Exact but incompatible Version 2",
        status=TemplateStatus.PUBLISHED,
        created_by_id=administrator.id,
    )
    db_session.add(incompatible)
    db_session.flush()
    db_session.add(
        TemplateLandmark(
            template_id=incompatible.id,
            ordinal=1,
            label="V2-01",
            description="Different template identity",
        )
    )
    db_session.commit()
    incompatible_csv = export_approved_csv(db_session, template_id=incompatible.id)
    assert list(csv.DictReader(StringIO(incompatible_csv))) == []
    assert record.accession_number not in incompatible_csv
    assert export_approved_tps(db_session, template_id=incompatible.id) == ""


def test_csv_export_includes_calibrated_millimeter_coordinates(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    approved = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-CALIBRATED",
        calibrate=True,
    )
    record = approve_annotation(db_session, reviewer, annotation_id=approved.id)

    rows = list(
        csv.DictReader(
            StringIO(export_approved_csv(db_session, template_id=landmark_template.id))
        )
    )

    assert len(rows) == 3
    assert {row["accession_number"] for row in rows} == {record.accession_number}
    assert {float(row["scale_reference_length"]) for row in rows} == {1.0}
    assert {row["scale_reference_unit"] for row in rows} == {"millimeters"}
    assert {float(row["scale_reference_pixels"]) for row in rows} == {50.0}
    assert [float(row["mm_per_pixel"]) for row in rows] == pytest.approx(
        [0.02, 0.02, 0.02]
    )
    assert [float(row["x_mm"]) for row in rows] == pytest.approx([0.2, 0.41, 0.6])
    assert [float(row["y_mm"]) for row in rows] == pytest.approx([0.1, 0.205, 0.3])

    assert "scale_mm_per_pixel:0.02" in export_approved_tps(
        db_session,
        template_id=landmark_template.id,
    )


def test_export_revalidates_approved_coordinate_integrity(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    annotation = _submitted_annotation(
        db_session,
        student,
        assignment,
        landmark_template,
        image_store,
        image_bytes,
        specimen_code="APIS-EXPORT-CORRUPT",
    )
    approve_annotation(db_session, reviewer, annotation_id=annotation.id)
    annotation.points[0].y_normalized += 0.01
    db_session.commit()

    with pytest.raises(ExportError, match="invalid coordinate"):
        export_approved_csv(db_session, template_id=landmark_template.id)
    with pytest.raises(ExportError, match="invalid coordinate"):
        export_approved_tps(db_session, template_id=landmark_template.id)

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.enums import AnnotationStatus, TemplateStatus
from wing_repository.errors import (
    AuthorizationError,
    ConflictError,
    IncompleteAnnotationError,
    InvalidStateError,
    TemplateVersionMismatchError,
    ValidationError,
)
from wing_repository.image_store import LocalImageStore
from wing_repository.models import (
    Annotation,
    AnnotationPoint,
    Assignment,
    LandmarkTemplate,
    TemplateLandmark,
    User,
    WingImage,
)
from wing_repository.services import (
    calibrate_wing_image_scale,
    clone_preserved_annotation,
    clone_returned_annotation,
    create_draft_annotation,
    create_specimen_with_image,
    delete_annotation_point,
    place_annotation_point,
    return_annotation,
    list_submitted_annotations,
    submit_annotation,
    undo_last_point,
    withdraw_submitted_annotation,
)


POINTS = ((10.0, 5.0), (20.5, 10.25), (30.0, 15.0))


def _uploaded_image(
    session: Session,
    student: User,
    assignment: Assignment,
    store: LocalImageStore,
    data: bytes,
    *,
    specimen_code: str = "APIS-ANNOTATION",
) -> WingImage:
    _specimen, image = create_specimen_with_image(
        session,
        student,
        store,
        specimen_code=specimen_code,
        image_bytes=data,
        original_filename="wing.png",
        assignment_id=assignment.id,
    )
    return image


def _complete_draft(
    session: Session,
    student: User,
    image: WingImage,
    template: LandmarkTemplate,
) -> Annotation:
    annotation = create_draft_annotation(
        session,
        student,
        wing_image_id=image.id,
    )
    for landmark, (x, y) in zip(template.landmarks, POINTS, strict=True):
        place_annotation_point(
            session,
            student,
            annotation_id=annotation.id,
            template_landmark_id=landmark.id,
            x_pixel=x,
            y_pixel=y,
        )
    return annotation


def test_point_crud_saves_pixel_and_normalized_coordinates(
    db_session: Session,
    student: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    draft = create_draft_annotation(db_session, student, wing_image_id=image.id)
    landmark = landmark_template.landmarks[0]

    point = place_annotation_point(
        db_session,
        student,
        annotation_id=draft.id,
        template_landmark_id=landmark.id,
        x_pixel=10.5,
        y_pixel=5.25,
    )

    assert point.x_pixel == 10.5
    assert point.y_pixel == 5.25
    assert point.x_normalized == pytest.approx(0.105)
    assert point.y_normalized == pytest.approx(0.105)
    with pytest.raises(ConflictError):
        place_annotation_point(
            db_session,
            student,
            annotation_id=draft.id,
            template_landmark_id=landmark.id,
            x_pixel=11,
            y_pixel=6,
            replace_existing=False,
        )

    replaced = place_annotation_point(
        db_session,
        student,
        annotation_id=draft.id,
        template_landmark_id=landmark.id,
        x_pixel=11,
        y_pixel=6,
    )
    assert replaced.id == point.id
    assert (replaced.x_pixel, replaced.y_pixel) == (11, 6)


def test_student_can_calibrate_image_scale_from_known_reference(
    db_session: Session,
    student: User,
    assignment: Assignment,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)

    calibrated = calibrate_wing_image_scale(
        db_session,
        student,
        wing_image_id=image.id,
        reference_length=1.0,
        reference_unit="millimeters",
        x1_pixel=10,
        y1_pixel=10,
        x2_pixel=60,
        y2_pixel=10,
    )

    assert calibrated.scale_reference_length == 1.0
    assert calibrated.scale_reference_unit == "millimeters"
    assert calibrated.scale_reference_pixels == pytest.approx(50.0)
    assert calibrated.scale_mm_per_pixel == pytest.approx(0.02)
    assert calibrated.scale_x1_pixel == pytest.approx(10)
    assert calibrated.scale_x2_pixel == pytest.approx(60)


def test_scale_calibration_rejects_unowned_or_submitted_images(
    db_session: Session,
    student: User,
    second_student: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)

    with pytest.raises(AuthorizationError):
        calibrate_wing_image_scale(
            db_session,
            second_student,
            wing_image_id=image.id,
            reference_length=1.0,
            reference_unit="millimeters",
            x1_pixel=10,
            y1_pixel=10,
            x2_pixel=60,
            y2_pixel=10,
        )

    draft = _complete_draft(db_session, student, image, landmark_template)
    submit_annotation(db_session, student, annotation_id=draft.id)

    with pytest.raises(InvalidStateError):
        calibrate_wing_image_scale(
            db_session,
            student,
            wing_image_id=image.id,
            reference_length=1.0,
            reference_unit="millimeters",
            x1_pixel=10,
            y1_pixel=10,
            x2_pixel=60,
            y2_pixel=10,
        )


def test_undo_and_delete_affect_only_editable_draft_points(
    db_session: Session,
    student: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    draft = _complete_draft(db_session, student, image, landmark_template)

    removed = undo_last_point(db_session, student, annotation_id=draft.id)
    assert removed.template_landmark_id == landmark_template.landmarks[2].id
    remaining_ids = set(
        db_session.scalars(
            select(AnnotationPoint.template_landmark_id).where(
                AnnotationPoint.annotation_id == draft.id
            )
        )
    )
    assert remaining_ids == {
        landmark_template.landmarks[0].id,
        landmark_template.landmarks[1].id,
    }

    delete_annotation_point(
        db_session,
        student,
        annotation_id=draft.id,
        template_landmark_id=landmark_template.landmarks[0].id,
    )
    assert list(
        db_session.scalars(
            select(AnnotationPoint.template_landmark_id).where(
                AnnotationPoint.annotation_id == draft.id
            )
        )
    ) == [landmark_template.landmarks[1].id]


def test_submit_requires_exact_template_point_set(
    db_session: Session,
    student: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    draft = create_draft_annotation(db_session, student, wing_image_id=image.id)
    place_annotation_point(
        db_session,
        student,
        annotation_id=draft.id,
        template_landmark_id=landmark_template.landmarks[0].id,
        x_pixel=10,
        y_pixel=5,
    )

    with pytest.raises(IncompleteAnnotationError):
        submit_annotation(db_session, student, annotation_id=draft.id)

    assert draft.status is AnnotationStatus.DRAFT


def test_landmark_from_another_template_version_is_rejected(
    db_session: Session,
    student: User,
    administrator: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    draft = create_draft_annotation(db_session, student, wing_image_id=image.id)
    other_template = LandmarkTemplate(
        taxon_id=landmark_template.taxon_id,
        version=2,
        name="Apis incompatible version",
        status=TemplateStatus.PUBLISHED,
        created_by_id=administrator.id,
    )
    db_session.add(other_template)
    db_session.flush()
    other_landmark = TemplateLandmark(
        template_id=other_template.id,
        ordinal=1,
        label="OTHER-01",
        description="Not part of Version 1",
    )
    db_session.add(other_landmark)
    db_session.flush()

    with pytest.raises(TemplateVersionMismatchError):
        place_annotation_point(
            db_session,
            student,
            annotation_id=draft.id,
            template_landmark_id=other_landmark.id,
            x_pixel=10,
            y_pixel=5,
        )


def test_submitted_annotation_is_immutable_and_return_clones_history(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    original = _complete_draft(db_session, student, image, landmark_template)
    submit_annotation(db_session, student, annotation_id=original.id)

    with pytest.raises(InvalidStateError):
        place_annotation_point(
            db_session,
            student,
            annotation_id=original.id,
            template_landmark_id=landmark_template.landmarks[0].id,
            x_pixel=99,
            y_pixel=49,
        )

    review = return_annotation(
        db_session,
        reviewer,
        annotation_id=original.id,
        comments="Please recheck LM01.",
    )
    assert review.annotation_id == original.id
    assert original.status is AnnotationStatus.RETURNED

    revision = clone_returned_annotation(
        db_session,
        student,
        annotation_id=original.id,
    )
    assert revision.parent_annotation_id == original.id
    assert revision.revision_number == 2
    assert revision.status is AnnotationStatus.DRAFT
    assert [
        (point.template_landmark_id, point.x_pixel, point.y_pixel)
        for point in sorted(revision.points, key=lambda item: item.template_landmark_id)
    ] == [
        (point.template_landmark_id, point.x_pixel, point.y_pixel)
        for point in sorted(original.points, key=lambda item: item.template_landmark_id)
    ]

    place_annotation_point(
        db_session,
        student,
        annotation_id=revision.id,
        template_landmark_id=landmark_template.landmarks[0].id,
        x_pixel=99,
        y_pixel=49,
    )
    original_first = next(
        point
        for point in original.points
        if point.template_landmark_id == landmark_template.landmarks[0].id
    )
    assert (original_first.x_pixel, original_first.y_pixel) == POINTS[0]
    assert (
        clone_returned_annotation(
            db_session,
            student,
            annotation_id=original.id,
        ).id
        == revision.id
    )


def test_student_can_withdraw_unreviewed_submission_and_create_replacement(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    submitted = submit_annotation(
        db_session,
        student,
        annotation_id=_complete_draft(db_session, student, image, landmark_template).id,
    )

    assert submitted in list_submitted_annotations(db_session, reviewer)
    withdrawn = withdraw_submitted_annotation(
        db_session,
        student,
        annotation_id=submitted.id,
    )

    assert withdrawn.status is AnnotationStatus.WITHDRAWN
    assert withdrawn.submitted_at is not None
    assert withdrawn not in list_submitted_annotations(db_session, reviewer)

    replacement = clone_preserved_annotation(
        db_session,
        student,
        annotation_id=withdrawn.id,
    )
    assert replacement.status is AnnotationStatus.DRAFT
    assert replacement.parent_annotation_id == withdrawn.id
    assert replacement.revision_number == withdrawn.revision_number + 1
    assert [
        (point.template_landmark_id, point.x_pixel, point.y_pixel)
        for point in sorted(replacement.points, key=lambda item: item.template_landmark_id)
    ] == [
        (point.template_landmark_id, point.x_pixel, point.y_pixel)
        for point in sorted(withdrawn.points, key=lambda item: item.template_landmark_id)
    ]


def test_student_cannot_withdraw_another_or_reviewed_submission(
    db_session: Session,
    student: User,
    second_student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    submitted = submit_annotation(
        db_session,
        student,
        annotation_id=_complete_draft(db_session, student, image, landmark_template).id,
    )

    with pytest.raises(AuthorizationError):
        withdraw_submitted_annotation(
            db_session,
            second_student,
            annotation_id=submitted.id,
        )

    return_annotation(
        db_session,
        reviewer,
        annotation_id=submitted.id,
        comments="Please revise.",
    )
    with pytest.raises(InvalidStateError):
        withdraw_submitted_annotation(
            db_session,
            student,
            annotation_id=submitted.id,
        )


def test_review_requires_reviewer_role_and_nonblank_return_comments(
    db_session: Session,
    student: User,
    reviewer: User,
    assignment: Assignment,
    landmark_template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    image = _uploaded_image(db_session, student, assignment, image_store, image_bytes)
    annotation = _complete_draft(db_session, student, image, landmark_template)
    submit_annotation(db_session, student, annotation_id=annotation.id)

    with pytest.raises(AuthorizationError):
        return_annotation(
            db_session,
            student,
            annotation_id=annotation.id,
            comments="Self review",
        )
    with pytest.raises(ValidationError):
        return_annotation(
            db_session,
            reviewer,
            annotation_id=annotation.id,
            comments="   ",
        )
    assert annotation.status is AnnotationStatus.SUBMITTED

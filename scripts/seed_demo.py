"""Idempotently seed the complete synthetic Version 0.1 demonstration workflow."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from wing_repository.config import get_settings
from wing_repository.db import SessionLocal, engine
from wing_repository.demo_data import (
    DEMO_IMAGE_HEIGHT,
    DEMO_IMAGE_WIDTH,
    DEMO_LANDMARK_PIXELS,
    synthetic_wing_png,
)
from wing_repository.enums import AnnotationStatus, Role
from wing_repository.errors import ConflictError, RepositoryError
from wing_repository.image_store import ImageStore, image_store_from_settings
from wing_repository.models import (
    Annotation,
    Assignment,
    LandmarkTemplate,
    RepositoryRecord,
    Specimen,
    Taxon,
    User,
    WingImage,
)
from wing_repository.security import hash_password, normalize_email
from wing_repository.services import (
    approve_annotation,
    attach_wing_image,
    clone_returned_annotation,
    create_assignment,
    create_draft_annotation,
    create_specimen_with_image,
    place_annotation_point,
    submit_annotation,
)
from wing_repository.template_loader import create_template, load_template_definition


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPOSITORY_ROOT / "demo_data" / "templates" / "apis_v1.json"

PASSWORD_ENVIRONMENT = {
    Role.ADMINISTRATOR: "WBR_DEMO_ADMIN_PASSWORD",
    Role.STUDENT: "WBR_DEMO_STUDENT_PASSWORD",
    Role.EXPERT_REVIEWER: "WBR_DEMO_REVIEWER_PASSWORD",
}
ACCOUNT_DEFINITIONS = {
    Role.ADMINISTRATOR: ("admin@example.test", "Demo Administrator"),
    Role.STUDENT: ("student@example.test", "Demo Student"),
    Role.EXPERT_REVIEWER: ("reviewer@example.test", "Demo Expert Reviewer"),
}

DEMO_SPECIMEN_CODE = "SYNTHETIC-APIS-0001"
DEMO_IMAGE_FILENAME = "synthetic_apis_right_forewing.png"


def _required_passwords(
    environment: Mapping[str, str] | None = None,
) -> dict[Role, str]:
    """Read all seed-only passwords without providing source-code defaults."""

    source = os.environ if environment is None else environment
    missing = [
        variable
        for variable in PASSWORD_ENVIRONMENT.values()
        if not source.get(variable)
    ]
    if missing:
        joined = ", ".join(sorted(missing))
        raise ConflictError(f"Required demo password environment variables are missing: {joined}.")
    passwords = {
        role: source[variable]
        for role, variable in PASSWORD_ENVIRONMENT.items()
    }
    unsafe = [
        PASSWORD_ENVIRONMENT[role]
        for role, password in passwords.items()
        if len(password) < 12 or password.casefold().startswith("change-this")
    ]
    if unsafe:
        joined = ", ".join(sorted(unsafe))
        raise ConflictError(
            f"Demo passwords must be at least 12 characters and must not use "
            f"the example placeholders: {joined}."
        )
    if len(set(passwords.values())) != len(passwords):
        raise ConflictError("Each demo role must use a different password.")
    return passwords


def _ensure_user(
    session: Session,
    *,
    role: Role,
    password: str,
) -> tuple[User, str]:
    """Create one account, preserving an existing account's password hash."""

    email, full_name = ACCOUNT_DEFINITIONS[role]
    normalized_email = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized_email))
    if user is not None:
        if user.role is not role:
            raise ConflictError(
                f"Existing demo login {normalized_email} has role {user.role.value}, "
                f"not {role.value}."
            )
        changed = False
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            session.commit()
            return user, "reactivated; password preserved"
        return user, "existing; password preserved"

    user = User(
        email=normalized_email,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user, "created"


def _ensure_template(
    session: Session,
    *,
    administrator: User,
) -> tuple[LandmarkTemplate, str]:
    definition = load_template_definition(TEMPLATE_PATH)
    existing = session.scalar(
        select(LandmarkTemplate)
        .join(Taxon)
        .where(
            Taxon.genus_code == definition.genus_code,
            LandmarkTemplate.version == definition.version,
        )
    )
    template = create_template(session, definition, created_by=administrator)
    session.commit()
    return template, "existing" if existing is not None else "created"


def _ensure_assignment(
    session: Session,
    *,
    administrator: User,
    student: User,
    template: LandmarkTemplate,
) -> tuple[Assignment, str]:
    active_assignments = list(
        session.scalars(
            select(Assignment).where(
                Assignment.student_id == student.id,
                Assignment.is_active.is_(True),
            )
        )
    )
    if len(active_assignments) > 1:
        raise ConflictError("The demo student has more than one active assignment.")
    if active_assignments:
        assignment = active_assignments[0]
        if (
            assignment.taxon_id != template.taxon_id
            or assignment.template_id != template.id
        ):
            raise ConflictError(
                "The demo student already has a different active assignment; "
                "the seed will not replace it."
            )
        return assignment, "existing"

    assignment = create_assignment(
        session,
        administrator,
        student_id=student.id,
        taxon_id=template.taxon_id,
        template_id=template.id,
    )
    return assignment, "created"


def _ensure_specimen_and_image(
    session: Session,
    *,
    student: User,
    assignment: Assignment,
    image_store: ImageStore,
) -> tuple[Specimen, WingImage, str, str]:
    specimen = session.scalar(
        select(Specimen).where(
            Specimen.contributor_id == student.id,
            Specimen.specimen_code == DEMO_SPECIMEN_CODE,
        )
    )
    image_bytes = synthetic_wing_png()
    if specimen is None:
        specimen, image = create_specimen_with_image(
            session,
            student,
            image_store,
            specimen_code=DEMO_SPECIMEN_CODE,
            image_bytes=image_bytes,
            original_filename=DEMO_IMAGE_FILENAME,
            assignment_id=assignment.id,
            taxon_id=assignment.taxon_id,
            species_text="Apis sp. (synthetic demonstration)",
            sex="unknown",
            country="Synthetic demonstration",
            locality="Generated non-sensitive teaching image",
            collector_name="Global Insect Wing Repository",
            notes=(
                "Synthetic right-forewing schematic for exercising the Version "
                "0.1 workflow; not a taxonomic reference specimen."
            ),
        )
        return specimen, image, "created", "created"

    if (
        specimen.assignment_id != assignment.id
        or specimen.taxon_id != assignment.taxon_id
    ):
        raise ConflictError(
            "The demonstration specimen code already exists under another assignment."
        )
    image = session.scalar(
        select(WingImage).where(WingImage.specimen_id == specimen.id)
    )
    if image is None:
        image = attach_wing_image(
            session,
            student,
            image_store,
            specimen_id=specimen.id,
            image_bytes=image_bytes,
            original_filename=DEMO_IMAGE_FILENAME,
        )
        return specimen, image, "existing", "created"
    if image.uploaded_by_id != student.id:
        raise ConflictError(
            "The demonstration specimen's existing image belongs to another uploader."
        )
    expected_digest = sha256(image_bytes).hexdigest()
    if (
        image.sha256 != expected_digest
        or image.image_width != DEMO_IMAGE_WIDTH
        or image.image_height != DEMO_IMAGE_HEIGHT
    ):
        raise ConflictError(
            "The demonstration specimen's preserved image does not match the "
            "generated synthetic PNG; existing bytes will not be replaced or digitized."
        )
    preserved_bytes = image_store.load_original(image.storage_key)
    if sha256(preserved_bytes).hexdigest() != expected_digest:
        raise ConflictError(
            "The demonstration image checksum does not match its preserved original bytes."
        )
    return specimen, image, "existing", "existing"


def _existing_demo_record(
    session: Session,
    *,
    image: WingImage,
    template: LandmarkTemplate,
) -> RepositoryRecord | None:
    return session.scalar(
        select(RepositoryRecord)
        .join(Annotation)
        .where(
            Annotation.wing_image_id == image.id,
            Annotation.template_id == template.id,
            Annotation.status == AnnotationStatus.APPROVED,
        )
    )


def _ensure_approved_record(
    session: Session,
    *,
    student: User,
    reviewer: User,
    image: WingImage,
    template: LandmarkTemplate,
) -> tuple[RepositoryRecord, str]:
    existing_record = _existing_demo_record(
        session, image=image, template=template
    )
    if existing_record is not None:
        return existing_record, "existing"

    annotations = list(
        session.scalars(
            select(Annotation)
            .where(
                Annotation.wing_image_id == image.id,
                Annotation.template_id == template.id,
            )
            .order_by(Annotation.revision_number.desc())
        )
    )
    annotation = annotations[0] if annotations else None
    if annotation is None:
        annotation = create_draft_annotation(
            session, student, wing_image_id=image.id
        )
    elif annotation.status is AnnotationStatus.RETURNED:
        annotation = clone_returned_annotation(
            session, student, annotation_id=annotation.id
        )
    elif annotation.status is AnnotationStatus.APPROVED:
        raise ConflictError(
            "The demonstration annotation is approved but has no repository record."
        )

    if annotation.status is AnnotationStatus.DRAFT:
        landmarks = sorted(template.landmarks, key=lambda item: item.ordinal)
        if len(landmarks) != len(DEMO_LANDMARK_PIXELS):
            raise ConflictError(
                "The sample coordinate count does not match the Apis template version."
            )
        for landmark, (x_pixel, y_pixel) in zip(
            landmarks, DEMO_LANDMARK_PIXELS, strict=True
        ):
            place_annotation_point(
                session,
                student,
                annotation_id=annotation.id,
                template_landmark_id=landmark.id,
                x_pixel=x_pixel,
                y_pixel=y_pixel,
                replace_existing=True,
            )
        annotation = submit_annotation(
            session, student, annotation_id=annotation.id
        )

    if annotation.status is not AnnotationStatus.SUBMITTED:
        raise ConflictError(
            f"The demonstration annotation is unexpectedly {annotation.status.value}."
        )
    record = approve_annotation(
        session,
        reviewer,
        annotation_id=annotation.id,
        comments="Approved synthetic Version 0.1 demonstration record.",
    )
    return record, "created"


def seed_demo(session: Session) -> dict[str, str]:
    """Seed accounts and one approved synthetic record into an upgraded schema."""

    passwords = _required_passwords()
    account_states: dict[Role, str] = {}
    accounts: dict[Role, User] = {}
    for role in (
        Role.ADMINISTRATOR,
        Role.STUDENT,
        Role.EXPERT_REVIEWER,
    ):
        account, state = _ensure_user(
            session, role=role, password=passwords[role]
        )
        accounts[role] = account
        account_states[role] = state

    template, template_state = _ensure_template(
        session, administrator=accounts[Role.ADMINISTRATOR]
    )
    assignment, assignment_state = _ensure_assignment(
        session,
        administrator=accounts[Role.ADMINISTRATOR],
        student=accounts[Role.STUDENT],
        template=template,
    )
    image_store = image_store_from_settings(get_settings())
    specimen, image, specimen_state, image_state = _ensure_specimen_and_image(
        session,
        student=accounts[Role.STUDENT],
        assignment=assignment,
        image_store=image_store,
    )
    record, record_state = _ensure_approved_record(
        session,
        student=accounts[Role.STUDENT],
        reviewer=accounts[Role.EXPERT_REVIEWER],
        image=image,
        template=template,
    )

    return {
        "administrator": account_states[Role.ADMINISTRATOR],
        "student": account_states[Role.STUDENT],
        "reviewer": account_states[Role.EXPERT_REVIEWER],
        "template": f"{template_state} (ID {template.id}, version {template.version})",
        "assignment": f"{assignment_state} (ID {assignment.id})",
        "specimen": f"{specimen_state} ({specimen.specimen_code})",
        "image": f"{image_state} ({image.original_filename})",
        "record": f"{record_state} ({record.accession_number})",
    }


def main() -> None:
    load_dotenv()
    if not inspect(engine).has_table("users"):
        raise SystemExit("Database schema is missing; run `alembic upgrade head` first.")

    try:
        with SessionLocal() as session:
            summary = seed_demo(session)
    except (RepositoryError, SQLAlchemyError) as exc:
        raise SystemExit(f"Demo seed failed: {exc}") from exc

    print("Demo seed complete")
    print("Accounts:")
    for role in ("administrator", "student", "reviewer"):
        enum_role = {
            "administrator": Role.ADMINISTRATOR,
            "student": Role.STUDENT,
            "reviewer": Role.EXPERT_REVIEWER,
        }[role]
        email, _name = ACCOUNT_DEFINITIONS[enum_role]
        print(f"  {role}: {email} ({summary[role]})")
    print(f"Template: {summary['template']}")
    print(f"Assignment: {summary['assignment']}")
    print(f"Specimen/image: {summary['specimen']}; {summary['image']}")
    print(f"Approved record: {summary['record']}")


if __name__ == "__main__":
    main()

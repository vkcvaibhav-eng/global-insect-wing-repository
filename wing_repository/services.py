"""Authorization-aware domain operations for the Version 0.1 workflow.

Every public mutation owns its database transaction: it commits only after all
related rows are valid and rolls back on failure.  Streamlit pages call these
operations instead of mutating ORM status fields directly.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from pathlib import Path
from typing import Iterable

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .coordinates import Coordinate, normalize_coordinates
from .enums import (
    AnnotationStatus,
    ReviewDecision,
    Role,
    SpeciesIdentificationMethod,
    TemplateStatus,
    WingSide,
    WingType,
)
from .errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    IncompleteAnnotationError,
    InvalidStateError,
    NotFoundError,
    TemplateVersionMismatchError,
    ValidationError,
)
from .image_store import ImageStore, StoredImage
from .models import (
    Annotation,
    AnnotationPoint,
    Assignment,
    LandmarkTemplate,
    RepositoryRecord,
    Review,
    Specimen,
    Taxon,
    TemplateLandmark,
    User,
    WingImage,
)
from .security import hash_password, normalize_email, verify_password
from .template_loader import create_template, load_template_definition


MIN_ACCOUNT_PASSWORD_CHARACTERS = 12
BUNDLED_STANDARD_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "repository_assets"
    / "templates"
    / "apis_standard_19_v2.json"
)
LENGTH_UNIT_TO_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "um": 0.001,
    "µm": 0.001,
    "micrometer": 0.001,
    "micrometers": 0.001,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
}
SCALE_CALIBRATION_EDITABLE_ANNOTATION_STATUSES = {
    AnnotationStatus.DRAFT,
    AnnotationStatus.WITHDRAWN,
    AnnotationStatus.DELETED,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(value: str, field_name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} is required.")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValidationError(f"{field_name} must be at most {max_length} characters.")
    return normalized


def _optional_text(
    value: str | None,
    field_name: str,
    *,
    max_length: int | None = None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None and len(normalized) > max_length:
        raise ValidationError(f"{field_name} must be at most {max_length} characters.")
    return normalized


def _optional_coordinate(
    value: float | None,
    field_name: str,
    minimum: float,
    maximum: float,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not math.isfinite(normalized) or not minimum <= normalized <= maximum:
        raise ValidationError(f"{field_name} must be between {minimum} and {maximum}.")
    return normalized


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValidationError(f"{field_name} must be greater than zero.")
    return normalized


def _length_to_millimeters(length: float, unit: str) -> tuple[float, str]:
    normalized_length = _positive_number(length, "Reference length")
    normalized_unit = _required_text(unit, "Reference unit", max_length=32).casefold()
    if normalized_unit not in LENGTH_UNIT_TO_MM:
        allowed = ", ".join(sorted(LENGTH_UNIT_TO_MM))
        raise ValidationError(f"Reference unit must be one of: {allowed}.")
    return normalized_length * LENGTH_UNIT_TO_MM[normalized_unit], normalized_unit


def _required_collection_date(value: date | None) -> date:
    if value is None:
        raise ValidationError("Collection date is required.")
    if not isinstance(value, date):
        raise ValidationError("Collection date must be a date.")
    return value


def _required_positive_int(value: int | None, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} is required and must be a whole number.")
    if value < 1:
        raise ValidationError(f"{field_name} must be at least 1.")
    return value


def _species_identification_method(
    value: SpeciesIdentificationMethod | str | None,
) -> SpeciesIdentificationMethod:
    if isinstance(value, SpeciesIdentificationMethod):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return SpeciesIdentificationMethod(value.strip())
        except ValueError as exc:
            allowed = ", ".join(method.value for method in SpeciesIdentificationMethod)
            raise ValidationError(
                f"Species identification method must be one of: {allowed}."
            ) from exc
    raise ValidationError("Species identification method is required.")


def _species_identification_details(
    *,
    method: SpeciesIdentificationMethod,
    genbank_accession: str | None,
    taxonomist_name: str | None,
) -> tuple[str | None, str | None]:
    normalized_genbank = _optional_text(
        genbank_accession,
        "GenBank accession number",
        max_length=120,
    )
    normalized_taxonomist = _optional_text(
        taxonomist_name,
        "Taxonomist name",
        max_length=200,
    )
    if method is SpeciesIdentificationMethod.MOLECULAR and normalized_genbank is None:
        raise ValidationError(
            "GenBank accession number is required when species identification is molecular."
        )
    if method is SpeciesIdentificationMethod.TAXONOMIST and normalized_taxonomist is None:
        raise ValidationError(
            "Taxonomist name is required when species identification is by taxonomist."
        )
    return normalized_genbank, normalized_taxonomist


def _locality_sample_fields(
    assignment: Assignment,
    *,
    locality_sample_code: str | None,
    locality_sample_size: int | None,
    locality_sample_number: int | None,
) -> tuple[str, int, int]:
    sample_code = _required_text(
        locality_sample_code or "",
        "Locality sample code",
        max_length=120,
    )
    sample_size = _required_positive_int(
        locality_sample_size,
        "Number of wings from this locality",
    )
    minimum = assignment.template.minimum_wings_per_locality
    if sample_size < minimum:
        raise ValidationError(
            f"At least {minimum} wings are required from one locality for "
            f"{assignment.template.name}."
        )
    sample_number = _required_positive_int(
        locality_sample_number,
        "This wing number in the locality sample",
    )
    if sample_number > sample_size:
        raise ValidationError("This wing number cannot exceed the locality sample count.")
    return sample_code, sample_size, sample_number


def require_active_role(actor: User, *allowed_roles: Role) -> User:
    """Require an active ORM user with one of ``allowed_roles``."""

    if actor is None or not getattr(actor, "is_active", False):
        raise AuthorizationError("An active account is required.")
    if actor.role not in allowed_roles:
        raise AuthorizationError("Your account is not allowed to perform this action.")
    return actor


def authenticate_user(session: Session, email: str, password: str) -> User:
    """Authenticate an active user while returning one generic failure message."""

    try:
        normalized_email = normalize_email(email)
    except ValidationError as exc:
        raise AuthenticationError("Invalid email or password.") from exc
    user = session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")
    return user


def _validated_account_password(password: str, label: str = "Password") -> str:
    if not isinstance(password, str) or len(password) < MIN_ACCOUNT_PASSWORD_CHARACTERS:
        raise ValidationError(
            f"{label} must be at least {MIN_ACCOUNT_PASSWORD_CHARACTERS} characters."
        )
    return password


def request_account_signup(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: Role,
) -> User:
    """Create an inactive student/reviewer account request for admin approval."""

    if role not in {Role.STUDENT, Role.EXPERT_REVIEWER}:
        raise ValidationError("Only student or expert reviewer signup is supported.")

    normalized_email = normalize_email(email)
    normalized_name = _required_text(full_name, "Full name", max_length=200)
    user = User(
        email=normalized_email,
        full_name=normalized_name,
        password_hash=hash_password(_validated_account_password(password)),
        role=role,
        is_active=False,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("An account already exists for that email.") from exc
    return user


def request_student_signup(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """Backward-compatible helper for inactive student signup requests."""

    return request_account_signup(
        session,
        email=email,
        full_name=full_name,
        password=password,
        role=Role.STUDENT,
    )


def approve_user_account(
    session: Session,
    actor: User,
    *,
    user_id: int,
) -> User:
    """Activate a pending student/reviewer account as an administrator."""

    require_active_role(actor, Role.ADMINISTRATOR)
    account = session.get(User, user_id)
    if account is None:
        raise NotFoundError("The requested account was not found.")
    if account.role not in {Role.STUDENT, Role.EXPERT_REVIEWER}:
        raise ValidationError("Only student or reviewer accounts can be approved.")
    if account.is_active:
        return account
    account.is_active = True
    session.commit()
    return account


def create_user_account(
    session: Session,
    actor: User,
    *,
    email: str,
    full_name: str,
    role: Role,
    password: str,
) -> User:
    """Create an active contributor or reviewer account as an administrator."""

    require_active_role(actor, Role.ADMINISTRATOR)
    if role not in {Role.STUDENT, Role.EXPERT_REVIEWER}:
        raise ValidationError(
            "Version 0.1 administrators can create student or reviewer accounts."
        )
    normalized_email = normalize_email(email)
    normalized_name = _required_text(full_name, "Full name", max_length=200)
    user = User(
        email=normalized_email,
        full_name=normalized_name,
        password_hash=hash_password(
            _validated_account_password(password, "Temporary password")
        ),
        role=role,
        is_active=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("An active or inactive account already uses that email.") from exc
    return user


def import_bundled_standard_template(session: Session, actor: User) -> LandmarkTemplate:
    """Import the bundled Apis 19-landmark template so assignments can be created."""

    require_active_role(actor, Role.ADMINISTRATOR)
    definition = load_template_definition(BUNDLED_STANDARD_TEMPLATE_PATH)
    template = create_template(session, definition, created_by=actor)
    session.commit()
    return template


def import_bundled_sample_template(session: Session, actor: User) -> LandmarkTemplate:
    """Backward-compatible alias for the bundled standard template import."""

    return import_bundled_standard_template(session, actor)


def get_active_assignment(
    session: Session,
    student: User,
    *,
    for_update: bool = False,
) -> Assignment:
    """Return a student's sole active exact-template assignment."""

    require_active_role(student, Role.STUDENT)
    statement: Select[tuple[Assignment]] = select(Assignment).where(
        Assignment.student_id == student.id,
        Assignment.is_active.is_(True),
    )
    if for_update:
        statement = statement.with_for_update()
    assignments = list(session.scalars(statement))
    if not assignments:
        raise NotFoundError("No active genus/template assignment was found.")
    if len(assignments) != 1:
        raise ConflictError("More than one active assignment exists for this student.")
    assignment = assignments[0]
    _validate_assignment_links(assignment)
    return assignment


def _validate_assignment_links(assignment: Assignment) -> None:
    if assignment.template.taxon_id != assignment.taxon_id:
        raise TemplateVersionMismatchError("Assignment template and genus do not match.")
    if assignment.template.side is not WingSide.RIGHT:
        raise ValidationError("Assignment template is not for a right wing.")
    if assignment.template.wing_type is not WingType.FOREWING:
        raise ValidationError("Assignment template is not for a forewing.")


def create_assignment(
    session: Session,
    actor: User,
    *,
    student_id: int,
    taxon_id: int,
    template_id: int,
) -> Assignment:
    """Assign one active student to one published exact template version."""

    require_active_role(actor, Role.ADMINISTRATOR)
    student = session.get(User, student_id)
    if student is None:
        raise NotFoundError("Student account was not found.")
    require_active_role(student, Role.STUDENT)
    taxon = session.get(Taxon, taxon_id)
    if taxon is None:
        raise NotFoundError("Taxon was not found.")
    template = session.get(LandmarkTemplate, template_id)
    if template is None:
        raise NotFoundError("Landmark template was not found.")
    if template.status is not TemplateStatus.PUBLISHED:
        raise ValidationError("Only a published template can be assigned.")
    if template.taxon_id != taxon.id:
        raise TemplateVersionMismatchError("Template does not belong to the selected genus.")
    if template.side is not WingSide.RIGHT or template.wing_type is not WingType.FOREWING:
        raise ValidationError("Version 0.1 assignments require a right-forewing template.")
    active = session.scalar(
        select(Assignment).where(
            Assignment.student_id == student.id,
            Assignment.is_active.is_(True),
        )
    )
    if active is not None:
        raise ConflictError("The student already has an active assignment.")
    assignment = Assignment(
        student_id=student.id,
        taxon_id=taxon.id,
        template_id=template.id,
        assigned_by_id=actor.id,
        is_active=True,
        ended_at=None,
    )
    session.add(assignment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("The student could not be assigned because state changed.") from exc
    return assignment


def update_template_sample_requirements(
    session: Session,
    actor: User,
    *,
    template_id: int,
    minimum_wings_per_locality: int,
    recommended_wings_per_locality: int,
) -> LandmarkTemplate:
    """Set locality sampling requirements for a published landmark template."""

    require_active_role(actor, Role.ADMINISTRATOR)
    template = session.get(LandmarkTemplate, template_id)
    if template is None:
        raise NotFoundError("Landmark template was not found.")
    minimum = _required_positive_int(
        minimum_wings_per_locality,
        "Minimum wings per locality",
    )
    recommended = _required_positive_int(
        recommended_wings_per_locality,
        "Recommended wings per locality",
    )
    if recommended < minimum:
        raise ValidationError(
            "Recommended wings per locality cannot be below the minimum."
        )
    template.minimum_wings_per_locality = minimum
    template.recommended_wings_per_locality = recommended
    session.commit()
    return template


def deactivate_assignment(
    session: Session,
    actor: User,
    *,
    assignment_id: int,
) -> Assignment:
    """End an assignment while preserving its specimen provenance."""

    require_active_role(actor, Role.ADMINISTRATOR)
    assignment = session.scalar(
        select(Assignment).where(Assignment.id == assignment_id).with_for_update()
    )
    if assignment is None:
        raise NotFoundError("Assignment was not found.")
    if not assignment.is_active:
        return assignment
    assignment.is_active = False
    assignment.ended_at = _utc_now()
    session.commit()
    return assignment


def _assignment_for_specimen_creation(
    session: Session,
    actor: User,
    assignment_id: int | None,
    taxon_id: int | None,
) -> Assignment:
    require_active_role(actor, Role.STUDENT)
    assignment = (
        get_active_assignment(session, actor)
        if assignment_id is None
        else session.get(Assignment, assignment_id)
    )
    if assignment is None:
        raise NotFoundError("Assignment was not found.")
    if assignment.student_id != actor.id:
        raise AuthorizationError("That assignment does not belong to this contributor.")
    if not assignment.is_active:
        raise InvalidStateError("The assignment is no longer active.")
    _validate_assignment_links(assignment)
    if taxon_id is not None and assignment.taxon_id != taxon_id:
        raise TemplateVersionMismatchError("Selected genus does not match the assignment.")
    return assignment


def _build_specimen(
    session: Session,
    actor: User,
    *,
    assignment_id: int | None,
    taxon_id: int | None,
    specimen_code: str,
    species_text: str | None,
    species_identification_method: SpeciesIdentificationMethod | str | None,
    genbank_accession: str | None,
    taxonomist_name: str | None,
    sex: str | None,
    collection_date: date | None,
    country: str | None,
    locality: str | None,
    locality_sample_code: str | None,
    locality_sample_size: int | None,
    locality_sample_number: int | None,
    latitude: float | None,
    longitude: float | None,
    collector_name: str | None,
    voucher_institution: str | None,
    voucher_code: str | None,
    notes: str | None,
) -> Specimen:
    assignment = _assignment_for_specimen_creation(
        session, actor, assignment_id, taxon_id
    )
    method = _species_identification_method(species_identification_method)
    normalized_genbank, normalized_taxonomist = _species_identification_details(
        method=method,
        genbank_accession=genbank_accession,
        taxonomist_name=taxonomist_name,
    )
    sample_code, sample_size, sample_number = _locality_sample_fields(
        assignment,
        locality_sample_code=locality_sample_code,
        locality_sample_size=locality_sample_size,
        locality_sample_number=locality_sample_number,
    )
    specimen = Specimen(
        taxon_id=assignment.taxon_id,
        contributor_id=actor.id,
        assignment_id=assignment.id,
        specimen_code=_required_text(specimen_code, "Specimen code", max_length=120),
        species_text=_required_text(species_text or "", "Species identification", max_length=200),
        species_identification_method=method,
        genbank_accession=normalized_genbank,
        taxonomist_name=normalized_taxonomist,
        sex=_required_text(sex or "", "Sex", max_length=40),
        collection_date=_required_collection_date(collection_date),
        country=_required_text(country or "", "Country", max_length=100),
        locality=_required_text(locality or "", "Locality", max_length=10_000),
        locality_sample_code=sample_code,
        locality_sample_size=sample_size,
        locality_sample_number=sample_number,
        latitude=_optional_coordinate(latitude, "Latitude", -90, 90),
        longitude=_optional_coordinate(longitude, "Longitude", -180, 180),
        collector_name=_required_text(collector_name or "", "Collector", max_length=200),
        voucher_institution=_optional_text(
            voucher_institution, "Voucher institution", max_length=200
        ),
        voucher_code=_optional_text(voucher_code, "Voucher code", max_length=120),
        notes=_optional_text(notes, "Notes"),
    )
    session.add(specimen)
    return specimen


def create_specimen(
    session: Session,
    actor: User,
    *,
    specimen_code: str,
    assignment_id: int | None = None,
    taxon_id: int | None = None,
    species_text: str | None = None,
    species_identification_method: SpeciesIdentificationMethod | str | None = None,
    genbank_accession: str | None = None,
    taxonomist_name: str | None = None,
    sex: str | None = None,
    collection_date: date | None = None,
    country: str | None = None,
    locality: str | None = None,
    locality_sample_code: str | None = None,
    locality_sample_size: int | None = None,
    locality_sample_number: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    collector_name: str | None = None,
    voucher_institution: str | None = None,
    voucher_code: str | None = None,
    notes: str | None = None,
) -> Specimen:
    """Create contributor metadata pinned to the current exact assignment."""

    specimen = _build_specimen(
        session,
        actor,
        assignment_id=assignment_id,
        taxon_id=taxon_id,
        specimen_code=specimen_code,
        species_text=species_text,
        species_identification_method=species_identification_method,
        genbank_accession=genbank_accession,
        taxonomist_name=taxonomist_name,
        sex=sex,
        collection_date=collection_date,
        country=country,
        locality=locality,
        locality_sample_code=locality_sample_code,
        locality_sample_size=locality_sample_size,
        locality_sample_number=locality_sample_number,
        latitude=latitude,
        longitude=longitude,
        collector_name=collector_name,
        voucher_institution=voucher_institution,
        voucher_code=voucher_code,
        notes=notes,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "That specimen code or locality sample number is already in use."
        ) from exc
    return specimen


def _owned_specimen_for_upload(session: Session, actor: User, specimen_id: int) -> Specimen:
    require_active_role(actor, Role.STUDENT)
    specimen = session.get(Specimen, specimen_id)
    if specimen is None:
        raise NotFoundError("Specimen was not found.")
    if specimen.contributor_id != actor.id or specimen.assignment.student_id != actor.id:
        raise AuthorizationError("That specimen does not belong to this contributor.")
    if not specimen.assignment.is_active:
        raise InvalidStateError("The specimen's assignment is no longer active.")
    if specimen.assignment.taxon_id != specimen.taxon_id:
        raise TemplateVersionMismatchError("Specimen genus and assignment do not match.")
    _validate_assignment_links(specimen.assignment)
    existing_image = session.scalar(
        select(WingImage).where(WingImage.specimen_id == specimen.id)
    )
    if existing_image is not None:
        raise ConflictError("This specimen already has its right-forewing image.")
    return specimen


def _wing_image_from_stored(
    specimen: Specimen,
    actor: User,
    stored: StoredImage,
) -> WingImage:
    return WingImage(
        specimen_id=specimen.id,
        uploaded_by_id=actor.id,
        side=WingSide.RIGHT,
        wing_type=WingType.FOREWING,
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        sha256=stored.sha256,
        byte_size=stored.byte_count,
        image_width=stored.width,
        image_height=stored.height,
    )


def attach_wing_image(
    session: Session,
    actor: User,
    image_store: ImageStore,
    *,
    specimen_id: int,
    image_bytes: bytes,
    original_filename: str,
) -> WingImage:
    """Preserve and attach the sole immutable right-forewing original."""

    specimen = _owned_specimen_for_upload(session, actor, specimen_id)
    stored = image_store.save_original(image_bytes, original_filename)
    wing_image = _wing_image_from_stored(specimen, actor, stored)
    session.add(wing_image)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        image_store.discard_uncommitted(stored.storage_key)
        if isinstance(exc, IntegrityError):
            raise ConflictError("This specimen already has a wing image.") from exc
        raise
    return wing_image


def calibrate_wing_image_scale(
    session: Session,
    actor: User,
    *,
    wing_image_id: int,
    reference_length: float,
    reference_unit: str,
    x1_pixel: float,
    y1_pixel: float,
    x2_pixel: float,
    y2_pixel: float,
) -> WingImage:
    """Save an image-level physical scale from two reference endpoints."""

    require_active_role(actor, Role.STUDENT)
    wing_image = session.get(WingImage, wing_image_id)
    if wing_image is None:
        raise NotFoundError("Wing image was not found.")
    if (
        wing_image.uploaded_by_id != actor.id
        or wing_image.specimen.contributor_id != actor.id
    ):
        raise AuthorizationError("That wing image does not belong to this contributor.")
    if any(
        annotation.status not in SCALE_CALIBRATION_EDITABLE_ANNOTATION_STATUSES
        or annotation.review is not None
        or annotation.repository_record is not None
        for annotation in wing_image.annotations
    ):
        raise InvalidStateError(
            "Scale calibration cannot be changed after an annotation is awaiting "
            "review or has been reviewed."
        )

    endpoint_1 = normalize_coordinates(
        x1_pixel,
        y1_pixel,
        wing_image.image_width,
        wing_image.image_height,
    )
    endpoint_2 = normalize_coordinates(
        x2_pixel,
        y2_pixel,
        wing_image.image_width,
        wing_image.image_height,
    )
    measured_pixels = math.hypot(
        endpoint_2.x_pixel - endpoint_1.x_pixel,
        endpoint_2.y_pixel - endpoint_1.y_pixel,
    )
    if measured_pixels < 1:
        raise ValidationError("Scale endpoints must be at least 1 pixel apart.")
    reference_length_mm, normalized_unit = _length_to_millimeters(
        reference_length,
        reference_unit,
    )

    wing_image.scale_reference_length = _positive_number(
        reference_length,
        "Reference length",
    )
    wing_image.scale_reference_unit = normalized_unit
    wing_image.scale_reference_pixels = measured_pixels
    wing_image.scale_mm_per_pixel = reference_length_mm / measured_pixels
    wing_image.scale_x1_pixel = endpoint_1.x_pixel
    wing_image.scale_y1_pixel = endpoint_1.y_pixel
    wing_image.scale_x2_pixel = endpoint_2.x_pixel
    wing_image.scale_y2_pixel = endpoint_2.y_pixel
    wing_image.scale_calibrated_at = _utc_now()
    session.commit()
    return wing_image


def create_specimen_with_image(
    session: Session,
    actor: User,
    image_store: ImageStore,
    *,
    specimen_code: str,
    image_bytes: bytes,
    original_filename: str,
    assignment_id: int | None = None,
    taxon_id: int | None = None,
    species_text: str | None = None,
    species_identification_method: SpeciesIdentificationMethod | str | None = None,
    genbank_accession: str | None = None,
    taxonomist_name: str | None = None,
    sex: str | None = None,
    collection_date: date | None = None,
    country: str | None = None,
    locality: str | None = None,
    locality_sample_code: str | None = None,
    locality_sample_size: int | None = None,
    locality_sample_number: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    collector_name: str | None = None,
    voucher_institution: str | None = None,
    voucher_code: str | None = None,
    notes: str | None = None,
) -> tuple[Specimen, WingImage]:
    """Create metadata and immutable upload in one compensated transaction."""

    specimen = _build_specimen(
        session,
        actor,
        assignment_id=assignment_id,
        taxon_id=taxon_id,
        specimen_code=specimen_code,
        species_text=species_text,
        species_identification_method=species_identification_method,
        genbank_accession=genbank_accession,
        taxonomist_name=taxonomist_name,
        sex=sex,
        collection_date=collection_date,
        country=country,
        locality=locality,
        locality_sample_code=locality_sample_code,
        locality_sample_size=locality_sample_size,
        locality_sample_number=locality_sample_number,
        latitude=latitude,
        longitude=longitude,
        collector_name=collector_name,
        voucher_institution=voucher_institution,
        voucher_code=voucher_code,
        notes=notes,
    )
    stored: StoredImage | None = None
    try:
        session.flush()
        stored = image_store.save_original(image_bytes, original_filename)
        wing_image = _wing_image_from_stored(specimen, actor, stored)
        session.add(wing_image)
        session.commit()
    except Exception as exc:
        session.rollback()
        if stored is not None:
            image_store.discard_uncommitted(stored.storage_key)
        if isinstance(exc, IntegrityError):
            raise ConflictError("Specimen or wing-image data conflict with an existing record.") from exc
        raise
    return specimen, wing_image


def _validate_annotation_links(annotation: Annotation) -> None:
    specimen = annotation.wing_image.specimen
    if annotation.template_id != specimen.assignment.template_id:
        raise TemplateVersionMismatchError(
            "Annotation template differs from the specimen's exact assignment."
        )
    if annotation.template.taxon_id != specimen.taxon_id:
        raise TemplateVersionMismatchError("Annotation template and specimen genus differ.")
    if annotation.image_width != annotation.wing_image.image_width or annotation.image_height != annotation.wing_image.image_height:
        raise ConflictError("Annotation dimensions differ from the immutable original image.")
    if (
        annotation.template.side is not WingSide.RIGHT
        or annotation.template.wing_type is not WingType.FOREWING
        or annotation.wing_image.side is not WingSide.RIGHT
        or annotation.wing_image.wing_type is not WingType.FOREWING
    ):
        raise ValidationError("Version 0.1 annotations require a right forewing.")


def create_draft_annotation(
    session: Session,
    actor: User,
    *,
    wing_image_id: int,
) -> Annotation:
    """Create or return the first draft pinned to the specimen assignment."""

    require_active_role(actor, Role.STUDENT)
    wing_image = session.get(WingImage, wing_image_id)
    if wing_image is None:
        raise NotFoundError("Wing image was not found.")
    specimen = wing_image.specimen
    if specimen.contributor_id != actor.id or wing_image.uploaded_by_id != actor.id:
        raise AuthorizationError("That wing image does not belong to this contributor.")
    assignment = specimen.assignment
    if assignment.student_id != actor.id or not assignment.is_active:
        raise InvalidStateError("The specimen's assignment is no longer active.")
    _validate_assignment_links(assignment)
    if assignment.template.status is not TemplateStatus.PUBLISHED:
        raise InvalidStateError("A new annotation requires a published template.")

    existing = list(
        session.scalars(
            select(Annotation)
            .where(
                Annotation.wing_image_id == wing_image.id,
                Annotation.template_id == assignment.template_id,
            )
            .order_by(Annotation.revision_number.desc())
        )
    )
    if existing:
        latest = existing[0]
        if latest.status is AnnotationStatus.DRAFT:
            return latest
        raise InvalidStateError(
            "This image already has a submitted revision; returned work must be cloned."
        )

    annotation = Annotation(
        wing_image_id=wing_image.id,
        template_id=assignment.template_id,
        contributor_id=actor.id,
        revision_number=1,
        status=AnnotationStatus.DRAFT,
        image_width=wing_image.image_width,
        image_height=wing_image.image_height,
    )
    session.add(annotation)
    session.commit()
    return annotation


def _owned_draft(session: Session, actor: User, annotation_id: int) -> Annotation:
    require_active_role(actor, Role.STUDENT)
    annotation = session.get(Annotation, annotation_id)
    if annotation is None:
        raise NotFoundError("Annotation was not found.")
    if annotation.contributor_id != actor.id:
        raise AuthorizationError("That annotation does not belong to this contributor.")
    if annotation.status is not AnnotationStatus.DRAFT:
        raise InvalidStateError("Only a draft annotation can be edited.")
    _validate_annotation_links(annotation)
    return annotation


def place_annotation_point(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
    template_landmark_id: int,
    x_pixel: float,
    y_pixel: float,
    replace_existing: bool = True,
) -> AnnotationPoint:
    """Insert or replace one draft point belonging to the exact template."""

    annotation = _owned_draft(session, actor, annotation_id)
    landmark = session.get(TemplateLandmark, template_landmark_id)
    if landmark is None:
        raise NotFoundError("Template landmark was not found.")
    if landmark.template_id != annotation.template_id:
        raise TemplateVersionMismatchError(
            "Landmark does not belong to this annotation's template version."
        )
    coordinate: Coordinate = normalize_coordinates(
        x_pixel,
        y_pixel,
        annotation.image_width,
        annotation.image_height,
    )
    point = session.scalar(
        select(AnnotationPoint).where(
            AnnotationPoint.annotation_id == annotation.id,
            AnnotationPoint.template_landmark_id == landmark.id,
        )
    )
    if point is not None and not replace_existing:
        raise ConflictError("That landmark already has a point in this draft.")
    if point is None:
        point = AnnotationPoint(
            annotation_id=annotation.id,
            template_landmark_id=landmark.id,
            x_pixel=coordinate.x_pixel,
            y_pixel=coordinate.y_pixel,
            x_normalized=coordinate.x_normalized,
            y_normalized=coordinate.y_normalized,
        )
        session.add(point)
    else:
        point.x_pixel = coordinate.x_pixel
        point.y_pixel = coordinate.y_pixel
        point.x_normalized = coordinate.x_normalized
        point.y_normalized = coordinate.y_normalized
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("The landmark point could not be saved.") from exc
    session.expire(annotation, ["points"])
    return point


def delete_annotation_point(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
    template_landmark_id: int,
) -> None:
    """Delete one working point from an owned draft."""

    annotation = _owned_draft(session, actor, annotation_id)
    point = session.scalar(
        select(AnnotationPoint).where(
            AnnotationPoint.annotation_id == annotation.id,
            AnnotationPoint.template_landmark_id == template_landmark_id,
        )
    )
    if point is None:
        raise NotFoundError("Draft point was not found.")
    session.delete(point)
    session.commit()
    session.expire(annotation, ["points"])


def undo_last_point(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> AnnotationPoint:
    """Remove the highest-ordinal point from sequential digitization."""

    annotation = _owned_draft(session, actor, annotation_id)
    point = session.scalar(
        select(AnnotationPoint)
        .join(TemplateLandmark)
        .where(AnnotationPoint.annotation_id == annotation.id)
        .order_by(TemplateLandmark.ordinal.desc())
        .limit(1)
    )
    if point is None:
        raise InvalidStateError("This draft has no landmark point to undo.")
    session.delete(point)
    session.commit()
    session.expire(annotation, ["points"])
    return point


def validate_annotation_complete(annotation: Annotation) -> None:
    """Validate exact membership plus pixel/normalized coordinate integrity."""

    expected = {landmark.id for landmark in annotation.template.landmarks}
    actual = {point.template_landmark_id for point in annotation.points}
    if not expected or actual != expected:
        missing = len(expected - actual)
        extra = len(actual - expected)
        raise IncompleteAnnotationError(
            f"Annotation must contain the exact template point set "
            f"({missing} missing, {extra} unexpected)."
        )
    for point in annotation.points:
        try:
            calculated = normalize_coordinates(
                point.x_pixel,
                point.y_pixel,
                annotation.image_width,
                annotation.image_height,
            )
        except ValidationError as exc:
            raise ValidationError(
                f"Landmark point {point.template_landmark_id} has invalid source coordinates."
            ) from exc
        stored_normalized = (point.x_normalized, point.y_normalized)
        expected_normalized = (calculated.x_normalized, calculated.y_normalized)
        normalized_values_match = all(
            not isinstance(stored, bool)
            and isinstance(stored, (int, float))
            and math.isfinite(float(stored))
            and math.isclose(
                float(stored), expected, rel_tol=1e-12, abs_tol=1e-12
            )
            for stored, expected in zip(
                stored_normalized, expected_normalized, strict=True
            )
        )
        if not normalized_values_match:
            raise ValidationError(
                f"Landmark point {point.template_landmark_id} has inconsistent normalized coordinates."
            )


def _reload_annotation_points(session: Session, annotation: Annotation) -> None:
    """Discard any UI-loaded draft collection and read DB-authoritative points."""

    session.expire(annotation, ["points"])
    # Force the read inside the service transaction so validation cannot be
    # deferred until after a status transition.
    len(annotation.points)


def submit_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> Annotation:
    """Freeze a complete draft and place it in the expert review queue."""

    annotation = _owned_draft(session, actor, annotation_id)
    if not annotation.wing_image.specimen.assignment.is_active:
        raise InvalidStateError("The specimen's assignment is no longer active.")
    _reload_annotation_points(session, annotation)
    validate_annotation_complete(annotation)
    annotation.status = AnnotationStatus.SUBMITTED
    annotation.submitted_at = _utc_now()
    session.commit()
    return annotation


def clone_returned_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> Annotation:
    """Clone a preserved returned revision into a new editable draft."""

    require_active_role(actor, Role.STUDENT)
    source = session.get(Annotation, annotation_id)
    if source is None:
        raise NotFoundError("Returned annotation was not found.")
    if source.contributor_id != actor.id:
        raise AuthorizationError("That annotation does not belong to this contributor.")
    if source.status is not AnnotationStatus.RETURNED:
        raise InvalidStateError("Only a returned annotation can be revised.")
    _validate_annotation_links(source)
    assignment = source.wing_image.specimen.assignment
    if not assignment.is_active or assignment.student_id != actor.id:
        raise InvalidStateError("The specimen's assignment is no longer active.")
    existing_child = session.scalar(
        select(Annotation).where(Annotation.parent_annotation_id == source.id)
    )
    if existing_child is not None:
        if existing_child.status is AnnotationStatus.DRAFT:
            return existing_child
        raise InvalidStateError("A revision has already been created for this return.")

    _reload_annotation_points(session, source)

    revision = Annotation(
        wing_image_id=source.wing_image_id,
        template_id=source.template_id,
        contributor_id=source.contributor_id,
        parent_annotation_id=source.id,
        revision_number=source.revision_number + 1,
        status=AnnotationStatus.DRAFT,
        image_width=source.image_width,
        image_height=source.image_height,
    )
    source_id = source.id
    try:
        session.add(revision)
        session.flush()
        for source_point in source.points:
            session.add(
                AnnotationPoint(
                    annotation_id=revision.id,
                    template_landmark_id=source_point.template_landmark_id,
                    x_pixel=source_point.x_pixel,
                    y_pixel=source_point.y_pixel,
                    x_normalized=source_point.x_normalized,
                    y_normalized=source_point.y_normalized,
                )
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(Annotation).where(Annotation.parent_annotation_id == source_id)
        )
        if existing is not None:
            return existing
        raise ConflictError("A revision could not be created.") from exc
    return revision


def clone_preserved_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> Annotation:
    """Clone a preserved returned/withdrawn revision into a new editable draft."""

    require_active_role(actor, Role.STUDENT)
    source = session.get(Annotation, annotation_id)
    if source is None:
        raise NotFoundError("Preserved annotation was not found.")
    if source.contributor_id != actor.id:
        raise AuthorizationError("That annotation does not belong to this contributor.")
    if source.status not in {AnnotationStatus.RETURNED, AnnotationStatus.WITHDRAWN}:
        raise InvalidStateError(
            "Only a returned or withdrawn annotation can be copied into a new draft."
        )
    _validate_annotation_links(source)
    assignment = source.wing_image.specimen.assignment
    if not assignment.is_active or assignment.student_id != actor.id:
        raise InvalidStateError("The specimen's assignment is no longer active.")
    existing_child = session.scalar(
        select(Annotation).where(Annotation.parent_annotation_id == source.id)
    )
    if existing_child is not None:
        if existing_child.status is AnnotationStatus.DRAFT:
            return existing_child
        raise InvalidStateError("A replacement revision has already been created.")

    _reload_annotation_points(session, source)

    replacement = Annotation(
        wing_image_id=source.wing_image_id,
        template_id=source.template_id,
        contributor_id=source.contributor_id,
        parent_annotation_id=source.id,
        revision_number=source.revision_number + 1,
        status=AnnotationStatus.DRAFT,
        image_width=source.image_width,
        image_height=source.image_height,
    )
    source_id = source.id
    try:
        session.add(replacement)
        session.flush()
        for source_point in source.points:
            session.add(
                AnnotationPoint(
                    annotation_id=replacement.id,
                    template_landmark_id=source_point.template_landmark_id,
                    x_pixel=source_point.x_pixel,
                    y_pixel=source_point.y_pixel,
                    x_normalized=source_point.x_normalized,
                    y_normalized=source_point.y_normalized,
                )
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(Annotation).where(Annotation.parent_annotation_id == source_id)
        )
        if existing is not None:
            return existing
        raise ConflictError("A replacement revision could not be created.") from exc
    return replacement


def withdraw_submitted_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> Annotation:
    """Remove a mistaken submission from review while preserving its data."""

    require_active_role(actor, Role.STUDENT)
    annotation = session.get(Annotation, annotation_id)
    if annotation is None:
        raise NotFoundError("Submitted annotation was not found.")
    if annotation.contributor_id != actor.id:
        raise AuthorizationError("That annotation does not belong to this contributor.")
    _validate_annotation_links(annotation)
    if annotation.status is not AnnotationStatus.SUBMITTED:
        raise InvalidStateError("Only an awaiting-review submission can be withdrawn.")
    if annotation.review is not None or annotation.repository_record is not None:
        raise InvalidStateError("A reviewed annotation cannot be withdrawn.")
    annotation.status = AnnotationStatus.WITHDRAWN
    session.commit()
    return annotation


def delete_withdrawn_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
) -> Annotation:
    """Hide a withdrawn, unreviewed submission from the student's workspace."""

    require_active_role(actor, Role.STUDENT)
    annotation = session.get(Annotation, annotation_id)
    if annotation is None:
        raise NotFoundError("Withdrawn annotation was not found.")
    if annotation.contributor_id != actor.id:
        raise AuthorizationError("That annotation does not belong to this contributor.")
    _validate_annotation_links(annotation)
    if annotation.status is not AnnotationStatus.WITHDRAWN:
        raise InvalidStateError("Only a withdrawn submission can be deleted.")
    if annotation.review is not None or annotation.repository_record is not None:
        raise InvalidStateError("A reviewed annotation cannot be deleted.")
    annotation.status = AnnotationStatus.DELETED
    session.commit()
    return annotation


def _reviewable_annotation(
    session: Session,
    actor: User,
    annotation_id: int,
    *,
    for_update: bool = False,
) -> Annotation:
    require_active_role(actor, Role.EXPERT_REVIEWER, Role.ADMINISTRATOR)
    statement = select(Annotation).where(Annotation.id == annotation_id)
    if for_update:
        statement = statement.with_for_update()
    annotation = session.scalar(statement)
    if annotation is None:
        raise NotFoundError("Submitted annotation was not found.")
    if annotation.contributor_id == actor.id:
        raise AuthorizationError("Contributors cannot review their own annotations.")
    _validate_annotation_links(annotation)
    return annotation


def return_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
    comments: str,
) -> Review:
    """Atomically preserve a return decision and mark the revision returned."""

    annotation = _reviewable_annotation(
        session, actor, annotation_id, for_update=True
    )
    normalized_comments = _required_text(comments, "Return comments", max_length=10_000)
    existing_review = session.scalar(
        select(Review).where(Review.annotation_id == annotation.id)
    )
    if existing_review is not None:
        if existing_review.decision is ReviewDecision.RETURN:
            return existing_review
        raise InvalidStateError("This annotation already has an approval review.")
    if annotation.status is not AnnotationStatus.SUBMITTED:
        raise InvalidStateError("Only a submitted annotation can be returned.")
    _reload_annotation_points(session, annotation)
    validate_annotation_complete(annotation)
    review = Review(
        annotation_id=annotation.id,
        reviewer_id=actor.id,
        decision=ReviewDecision.RETURN,
        comments=normalized_comments,
    )
    annotation.status = AnnotationStatus.RETURNED
    session.add(review)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(Review).where(Review.annotation_id == annotation_id)
        )
        if existing is not None and existing.decision is ReviewDecision.RETURN:
            return existing
        raise ConflictError("The return decision could not be recorded.") from exc
    return review


def approve_annotation(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
    comments: str | None = None,
) -> RepositoryRecord:
    """Approve, allocate a permanent accession, and publish atomically."""

    annotation = _reviewable_annotation(
        session, actor, annotation_id, for_update=True
    )
    existing_record = session.scalar(
        select(RepositoryRecord).where(
            RepositoryRecord.annotation_id == annotation.id
        )
    )
    if existing_record is not None:
        return existing_record
    existing_review = session.scalar(
        select(Review).where(Review.annotation_id == annotation.id)
    )
    if existing_review is not None:
        raise InvalidStateError("This annotation already has a review decision.")
    if annotation.status is not AnnotationStatus.SUBMITTED:
        raise InvalidStateError("Only a submitted annotation can be approved.")
    _reload_annotation_points(session, annotation)
    validate_annotation_complete(annotation)

    specimen = annotation.wing_image.specimen
    if specimen.taxon_id != annotation.template.taxon_id:
        raise TemplateVersionMismatchError("Specimen and template genus do not match.")
    taxon = session.scalar(
        select(Taxon).where(Taxon.id == specimen.taxon_id).with_for_update()
    )
    if taxon is None:
        raise NotFoundError("Annotation genus was not found.")
    serial = taxon.next_accession_serial
    if serial < 1 or serial > 999_999:
        raise ConflictError("This genus has exhausted its six-digit accession range.")
    accession = f"WBR-HYM-{taxon.genus_code}-{serial:06d}"

    review = Review(
        annotation_id=annotation.id,
        reviewer_id=actor.id,
        decision=ReviewDecision.APPROVE,
        comments=_optional_text(comments, "Approval comments"),
    )
    try:
        session.add(review)
        session.flush()
        record = RepositoryRecord(
            annotation_id=annotation.id,
            review_id=review.id,
            taxon_id=taxon.id,
            serial_number=serial,
            accession_number=accession,
        )
        session.add(record)
        taxon.next_accession_serial = serial + 1
        annotation.status = AnnotationStatus.APPROVED
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(RepositoryRecord).where(
                RepositoryRecord.annotation_id == annotation_id
            )
        )
        if existing is not None:
            return existing
        raise ConflictError("Approval conflicted with another accession allocation.") from exc
    return record


def list_student_annotations(session: Session, actor: User) -> list[Annotation]:
    """Return visible current-student revisions, newest first."""

    require_active_role(actor, Role.STUDENT)
    return list(
        session.scalars(
            select(Annotation)
            .where(
                Annotation.contributor_id == actor.id,
                Annotation.status != AnnotationStatus.DELETED,
            )
            .order_by(Annotation.created_at.desc())
        )
    )


def list_submitted_annotations(session: Session, actor: User) -> list[Annotation]:
    """Return the expert queue after role authorization."""

    require_active_role(actor, Role.EXPERT_REVIEWER, Role.ADMINISTRATOR)
    return list(
        session.scalars(
            select(Annotation)
            .where(Annotation.status == AnnotationStatus.SUBMITTED)
            .order_by(Annotation.submitted_at.asc(), Annotation.id.asc())
        )
    )


def list_repository_records(session: Session, actor: User) -> list[RepositoryRecord]:
    """Return accessioned records to any active application role."""

    require_active_role(
        actor, Role.STUDENT, Role.EXPERT_REVIEWER, Role.ADMINISTRATOR
    )
    return list(
        session.scalars(
            select(RepositoryRecord).order_by(RepositoryRecord.accession_number.asc())
        )
    )


__all__ = [
    "approve_annotation",
    "approve_user_account",
    "attach_wing_image",
    "authenticate_user",
    "calibrate_wing_image_scale",
    "clone_preserved_annotation",
    "clone_returned_annotation",
    "create_assignment",
    "create_draft_annotation",
    "create_specimen",
    "create_specimen_with_image",
    "create_user_account",
    "delete_withdrawn_annotation",
    "deactivate_assignment",
    "delete_annotation_point",
    "get_active_assignment",
    "import_bundled_sample_template",
    "import_bundled_standard_template",
    "list_repository_records",
    "list_student_annotations",
    "list_submitted_annotations",
    "place_annotation_point",
    "require_active_role",
    "request_account_signup",
    "request_student_signup",
    "return_annotation",
    "submit_annotation",
    "undo_last_point",
    "update_template_sample_requirements",
    "validate_annotation_complete",
    "withdraw_submitted_annotation",
]

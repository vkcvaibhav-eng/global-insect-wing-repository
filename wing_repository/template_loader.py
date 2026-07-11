"""Strict loading of versioned landmark-template JSON documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .enums import Role, TemplateStatus, WingSide, WingType
from .errors import AuthorizationError, ConflictError, ValidationError

if TYPE_CHECKING:
    from .models import LandmarkTemplate, User

_GENUS_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")


@dataclass(frozen=True, slots=True)
class TemplateLandmarkDefinition:
    ordinal: int
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    schema_version: str
    order: str
    family: str | None
    genus: str
    genus_code: str
    template_name: str
    version: int
    status: TemplateStatus
    wing_side: WingSide
    wing_type: WingType
    description: str | None
    landmarks: tuple[TemplateLandmarkDefinition, ...]


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Template field {key!r} must be non-empty text.")
    return value.strip()


def _optional_text(document: Mapping[str, Any], key: str) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"Template field {key!r} must be text or null.")
    normalized = value.strip()
    return normalized or None


def _enum_value(enum_type: type[Any], value: object, key: str) -> Any:
    if not isinstance(value, str):
        raise ValidationError(f"Template field {key!r} must be text.")
    try:
        return enum_type(value.strip().casefold())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValidationError(f"Template field {key!r} must be one of: {allowed}.") from exc


def parse_template_definition(document: Mapping[str, Any]) -> TemplateDefinition:
    """Validate a decoded template document without touching the database."""

    if not isinstance(document, Mapping):
        raise ValidationError("Landmark template JSON must contain an object.")
    schema_version = _required_text(document, "schema_version")
    if schema_version != "1.0":
        raise ValidationError(f"Unsupported template schema version {schema_version!r}.")
    order = _required_text(document, "order")
    if order.casefold() != "hymenoptera":
        raise ValidationError("Version 0.1 accepts Hymenoptera templates only.")
    genus = _required_text(document, "genus")
    genus_code = _required_text(document, "genus_code").upper()
    if not _GENUS_CODE_PATTERN.fullmatch(genus_code):
        raise ValidationError(
            "genus_code must be 2-12 uppercase ASCII letters or digits and start with a letter."
        )
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise ValidationError("Template version must be a positive integer.")
    status = _enum_value(TemplateStatus, document.get("status"), "status")
    wing_side = _enum_value(WingSide, document.get("wing_side"), "wing_side")
    wing_type = _enum_value(WingType, document.get("wing_type"), "wing_type")
    if wing_side is not WingSide.RIGHT or wing_type is not WingType.FOREWING:
        raise ValidationError("Version 0.1 templates must describe a right forewing.")

    raw_landmarks = document.get("landmarks")
    if not isinstance(raw_landmarks, list) or not raw_landmarks:
        raise ValidationError("Template must contain at least one landmark.")
    landmarks: list[TemplateLandmarkDefinition] = []
    labels: set[str] = set()
    for expected_ordinal, raw_landmark in enumerate(raw_landmarks, start=1):
        if not isinstance(raw_landmark, Mapping):
            raise ValidationError("Every template landmark must be an object.")
        ordinal = raw_landmark.get("ordinal")
        if ordinal != expected_ordinal:
            raise ValidationError("Landmark ordinals must be contiguous and begin at 1.")
        label = _required_text(raw_landmark, "label")
        if label.casefold() in labels:
            raise ValidationError(f"Duplicate landmark label {label!r}.")
        labels.add(label.casefold())
        landmarks.append(
            TemplateLandmarkDefinition(
                ordinal=expected_ordinal,
                label=label,
                description=_required_text(raw_landmark, "description"),
            )
        )

    return TemplateDefinition(
        schema_version=schema_version,
        order="Hymenoptera",
        family=_optional_text(document, "family"),
        genus=genus,
        genus_code=genus_code,
        template_name=_required_text(document, "template_name"),
        version=version,
        status=status,
        wing_side=wing_side,
        wing_type=wing_type,
        description=_optional_text(document, "description"),
        landmarks=tuple(landmarks),
    )


def load_template_definition(source: str | Path | Mapping[str, Any]) -> TemplateDefinition:
    """Load and validate a template from a path or already-decoded mapping."""

    if isinstance(source, Mapping):
        return parse_template_definition(source)
    path = Path(source)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Template file does not exist: {path}") from exc
    except OSError as exc:
        raise ValidationError(f"Template file could not be read: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Template file is not valid JSON: {exc.msg}") from exc
    return parse_template_definition(document)


def _canonical_source(definition: TemplateDefinition) -> str:
    document = {
        "schema_version": definition.schema_version,
        "order": definition.order,
        "family": definition.family,
        "genus": definition.genus,
        "genus_code": definition.genus_code,
        "template_name": definition.template_name,
        "version": definition.version,
        "status": definition.status.value,
        "wing_side": definition.wing_side.value.upper(),
        "wing_type": definition.wing_type.value.upper(),
        "description": definition.description,
        "landmarks": [
            {
                "ordinal": landmark.ordinal,
                "label": landmark.label,
                "description": landmark.description,
            }
            for landmark in definition.landmarks
        ],
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def create_template(
    session: Session,
    definition: TemplateDefinition,
    *,
    created_by: User,
) -> LandmarkTemplate:
    """Persist a validated taxon and its exact template version.

    Existing taxa are reused only when their stable genus code and name match.
    The import is idempotent for an already-identical template version and
    rejects conflicting attempts to reuse that version number.
    """

    # Imported lazily so JSON validation remains usable without initializing
    # SQLAlchemy mappings (and to avoid import cycles during migrations).
    from .models import LandmarkTemplate, Taxon, TemplateLandmark

    if (
        getattr(created_by, "role", None) is not Role.ADMINISTRATOR
        or not getattr(created_by, "is_active", False)
    ):
        raise AuthorizationError("Only an active administrator can import templates.")

    canonical_source = _canonical_source(definition)
    source_digest = sha256(canonical_source.encode("utf-8")).hexdigest()

    taxon = session.scalar(select(Taxon).where(Taxon.genus_code == definition.genus_code))
    if taxon is None:
        taxon = Taxon(
            order_name=definition.order,
            order_code="HYM",
            family=definition.family,
            genus=definition.genus,
            genus_code=definition.genus_code,
        )
        session.add(taxon)
        session.flush()
    elif taxon.genus.casefold() != definition.genus.casefold():
        raise ConflictError(
            f"Genus code {definition.genus_code} already belongs to {taxon.genus}."
        )

    existing = session.scalar(
        select(LandmarkTemplate).where(
            LandmarkTemplate.taxon_id == taxon.id,
            LandmarkTemplate.version == definition.version,
        )
    )
    if existing is not None:
        if existing.source_sha256 == source_digest:
            return existing
        same_landmarks = [
            (item.ordinal, item.label, item.description)
            for item in sorted(existing.landmarks, key=lambda item: item.ordinal)
        ] == [
            (item.ordinal, item.label, item.description) for item in definition.landmarks
        ]
        if (
            existing.name == definition.template_name
            and existing.description == definition.description
            and existing.status is definition.status
            and same_landmarks
        ):
            return existing
        raise ConflictError("That genus and template version already exist with other content.")

    template = LandmarkTemplate(
        taxon_id=taxon.id,
        name=definition.template_name,
        version=definition.version,
        status=definition.status,
        side=definition.wing_side,
        wing_type=definition.wing_type,
        description=definition.description,
        source_json=canonical_source,
        source_sha256=source_digest,
        created_by_id=created_by.id,
        published_at=(
            datetime.now(timezone.utc)
            if definition.status is TemplateStatus.PUBLISHED
            else None
        ),
    )
    session.add(template)
    session.flush()
    for landmark in definition.landmarks:
        session.add(
            TemplateLandmark(
                template_id=template.id,
                ordinal=landmark.ordinal,
                label=landmark.label,
                description=landmark.description,
            )
        )
    try:
        session.flush()
    except IntegrityError as exc:
        raise ConflictError("Template conflicts with existing persistent data.") from exc
    return template

"""SQLAlchemy persistence model for the version 0.1 repository.

The database stores enum values as constrained strings rather than native
PostgreSQL enums. This keeps SQLite development and PostgreSQL production
schemas equivalent and makes future vocabulary migrations explicit.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum as PythonEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wing_repository.db import Base
from wing_repository.enums import (
    AnnotationStatus,
    AnalysisModelStatus,
    AnalysisOutlierStatus,
    AnalysisQualityStatus,
    AnalysisRunStatus,
    AnalysisType,
    ReviewDecision,
    Role,
    TemplateStatus,
    WingSide,
    WingType,
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp for Python-side defaults."""

    return datetime.now(timezone.utc)


def enum_column_type(
    enum_class: type[PythonEnum], *, name: str, length: int
) -> SqlEnum[Any]:
    """Create a portable VARCHAR enum with a named CHECK constraint."""

    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        length=length,
    )


class User(Base):
    """An authenticated user with exactly one version 0.1 role."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(email)) >= 3", name="email_nonempty"),
        CheckConstraint("length(trim(full_name)) >= 1", name="full_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        enum_column_type(Role, name="role_enum", length=24), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    student_assignments: Mapped[list[Assignment]] = relationship(
        back_populates="student",
        foreign_keys="Assignment.student_id",
        passive_deletes=True,
    )
    assignments_created: Mapped[list[Assignment]] = relationship(
        back_populates="assigned_by",
        foreign_keys="Assignment.assigned_by_id",
        passive_deletes=True,
    )
    specimens: Mapped[list[Specimen]] = relationship(
        back_populates="contributor", passive_deletes=True
    )
    images_uploaded: Mapped[list[WingImage]] = relationship(
        back_populates="uploader", passive_deletes=True
    )
    templates_created: Mapped[list[LandmarkTemplate]] = relationship(
        back_populates="creator", passive_deletes=True
    )
    annotations: Mapped[list[Annotation]] = relationship(
        back_populates="contributor", passive_deletes=True
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="reviewer", passive_deletes=True
    )


class Taxon(Base):
    """A genus-level Hymenoptera taxon and its accession counter."""

    __tablename__ = "taxa"
    __table_args__ = (
        UniqueConstraint("order_name", "genus", name="uq_taxa_order_genus"),
        UniqueConstraint("order_code", "genus_code", name="uq_taxa_order_genus_code"),
        CheckConstraint("order_name = 'Hymenoptera'", name="hymenoptera_only"),
        CheckConstraint("order_code = 'HYM'", name="hymenoptera_code_only"),
        CheckConstraint("length(trim(genus)) >= 2", name="genus_nonempty"),
        CheckConstraint(
            "length(genus_code) BETWEEN 2 AND 12 AND genus_code = upper(genus_code)",
            name="genus_code_shape",
        ),
        CheckConstraint(
            "next_accession_serial BETWEEN 1 AND 1000000",
            name="next_accession_serial_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Hymenoptera", server_default="Hymenoptera"
    )
    order_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="HYM", server_default="HYM"
    )
    family: Mapped[str | None] = mapped_column(String(100))
    genus: Mapped[str] = mapped_column(String(100), nullable=False)
    genus_code: Mapped[str] = mapped_column(String(12), nullable=False)
    next_accession_serial: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="taxon", passive_deletes=True
    )
    specimens: Mapped[list[Specimen]] = relationship(
        back_populates="taxon", passive_deletes=True
    )
    landmark_templates: Mapped[list[LandmarkTemplate]] = relationship(
        back_populates="taxon", passive_deletes=True
    )
    repository_records: Mapped[list[RepositoryRecord]] = relationship(
        back_populates="taxon", passive_deletes=True
    )


class LandmarkTemplate(Base):
    """An exact, versioned definition of a genus's landmark sequence."""

    __tablename__ = "landmark_templates"
    __table_args__ = (
        UniqueConstraint("taxon_id", "version", name="uq_templates_taxon_version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("length(trim(name)) >= 1", name="name_nonempty"),
        CheckConstraint(
            "source_sha256 IS NULL OR length(source_sha256) = 64",
            name="source_sha256_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxon_id: Mapped[int] = mapped_column(
        ForeignKey("taxa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    side: Mapped[WingSide] = mapped_column(
        enum_column_type(WingSide, name="template_wing_side_enum", length=8),
        nullable=False,
        default=WingSide.RIGHT,
        server_default=WingSide.RIGHT.value,
    )
    wing_type: Mapped[WingType] = mapped_column(
        enum_column_type(WingType, name="template_wing_type_enum", length=12),
        nullable=False,
        default=WingType.FOREWING,
        server_default=WingType.FOREWING.value,
    )
    status: Mapped[TemplateStatus] = mapped_column(
        enum_column_type(TemplateStatus, name="template_status_enum", length=16),
        nullable=False,
        default=TemplateStatus.DRAFT,
        server_default=TemplateStatus.DRAFT.value,
    )
    source_json: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    taxon: Mapped[Taxon] = relationship(back_populates="landmark_templates")
    creator: Mapped[User] = relationship(back_populates="templates_created")
    landmarks: Mapped[list[TemplateLandmark]] = relationship(
        back_populates="template",
        order_by="TemplateLandmark.ordinal",
        passive_deletes=True,
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="template", passive_deletes=True
    )
    annotations: Mapped[list[Annotation]] = relationship(
        back_populates="template", passive_deletes=True
    )
    external_reference_datasets: Mapped[list[ExternalReferenceDataset]] = relationship(
        back_populates="template", passive_deletes=True
    )
    analysis_models: Mapped[list[AnalysisModel]] = relationship(
        back_populates="template", passive_deletes=True
    )


class TemplateLandmark(Base):
    """One anatomically defined position in a landmark template."""

    __tablename__ = "template_landmarks"
    __table_args__ = (
        UniqueConstraint("template_id", "ordinal", name="uq_landmarks_template_ordinal"),
        CheckConstraint("ordinal >= 1", name="ordinal_positive"),
        CheckConstraint("length(trim(label)) >= 1", name="label_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("landmark_templates.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    template: Mapped[LandmarkTemplate] = relationship(back_populates="landmarks")
    annotation_points: Mapped[list[AnnotationPoint]] = relationship(
        back_populates="template_landmark", passive_deletes=True
    )


class Assignment(Base):
    """A student's one version 0.1 genus/template assignment."""

    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "(is_active = true AND ended_at IS NULL) OR "
            "(is_active = false AND ended_at IS NOT NULL)",
            name="active_end_consistency",
        ),
        Index(
            "uq_assignments_active_student",
            "student_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    taxon_id: Mapped[int] = mapped_column(
        ForeignKey("taxa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("landmark_templates.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[User] = relationship(
        back_populates="student_assignments", foreign_keys=[student_id]
    )
    taxon: Mapped[Taxon] = relationship(back_populates="assignments")
    template: Mapped[LandmarkTemplate] = relationship(back_populates="assignments")
    assigned_by: Mapped[User] = relationship(
        back_populates="assignments_created", foreign_keys=[assigned_by_id]
    )
    specimens: Mapped[list[Specimen]] = relationship(
        back_populates="assignment", passive_deletes=True
    )


class Specimen(Base):
    """Contributor-supplied metadata for one biological specimen."""

    __tablename__ = "specimens"
    __table_args__ = (
        UniqueConstraint(
            "contributor_id", "specimen_code", name="uq_specimens_contributor_code"
        ),
        CheckConstraint("length(trim(specimen_code)) >= 1", name="code_nonempty"),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxon_id: Mapped[int] = mapped_column(
        ForeignKey("taxa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    specimen_code: Mapped[str] = mapped_column(String(120), nullable=False)
    species_text: Mapped[str | None] = mapped_column(String(200))
    sex: Mapped[str | None] = mapped_column(String(40))
    collection_date: Mapped[date | None] = mapped_column(Date)
    country: Mapped[str | None] = mapped_column(String(100))
    locality: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    collector_name: Mapped[str | None] = mapped_column(String(200))
    voucher_institution: Mapped[str | None] = mapped_column(String(200))
    voucher_code: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    taxon: Mapped[Taxon] = relationship(back_populates="specimens")
    contributor: Mapped[User] = relationship(back_populates="specimens")
    assignment: Mapped[Assignment] = relationship(back_populates="specimens")
    wing_image: Mapped[WingImage | None] = relationship(
        back_populates="specimen", passive_deletes=True, uselist=False
    )


class WingImage(Base):
    """Metadata and immutable storage reference for an original wing image."""

    __tablename__ = "wing_images"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("image_width > 0", name="width_positive"),
        CheckConstraint("image_height > 0", name="height_positive"),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
        CheckConstraint("length(trim(original_filename)) >= 1", name="filename_nonempty"),
        CheckConstraint(
            "scale_reference_length IS NULL OR scale_reference_length > 0",
            name="scale_reference_length_positive",
        ),
        CheckConstraint(
            "scale_reference_pixels IS NULL OR scale_reference_pixels > 0",
            name="scale_reference_pixels_positive",
        ),
        CheckConstraint(
            "scale_mm_per_pixel IS NULL OR scale_mm_per_pixel > 0",
            name="scale_mm_per_pixel_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specimen_id: Mapped[int] = mapped_column(
        ForeignKey("specimens.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    side: Mapped[WingSide] = mapped_column(
        enum_column_type(WingSide, name="wing_side_enum", length=8),
        nullable=False,
        default=WingSide.RIGHT,
        server_default=WingSide.RIGHT.value,
    )
    wing_type: Mapped[WingType] = mapped_column(
        enum_column_type(WingType, name="wing_type_enum", length=12),
        nullable=False,
        default=WingType.FOREWING,
        server_default=WingType.FOREWING.value,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    scale_reference_length: Mapped[float | None] = mapped_column(Float)
    scale_reference_unit: Mapped[str | None] = mapped_column(String(32))
    scale_reference_pixels: Mapped[float | None] = mapped_column(Float)
    scale_mm_per_pixel: Mapped[float | None] = mapped_column(Float)
    scale_x1_pixel: Mapped[float | None] = mapped_column(Float)
    scale_y1_pixel: Mapped[float | None] = mapped_column(Float)
    scale_x2_pixel: Mapped[float | None] = mapped_column(Float)
    scale_y2_pixel: Mapped[float | None] = mapped_column(Float)
    scale_calibrated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    specimen: Mapped[Specimen] = relationship(back_populates="wing_image")
    uploader: Mapped[User] = relationship(back_populates="images_uploaded")
    annotations: Mapped[list[Annotation]] = relationship(
        back_populates="wing_image", passive_deletes=True
    )


class Annotation(Base):
    """One immutable-on-submission revision of a coordinate set."""

    __tablename__ = "annotations"
    __table_args__ = (
        UniqueConstraint(
            "wing_image_id",
            "template_id",
            "revision_number",
            name="uq_annotations_image_template_revision",
        ),
        UniqueConstraint("parent_annotation_id", name="uq_annotations_parent"),
        CheckConstraint("revision_number >= 1", name="revision_positive"),
        CheckConstraint("image_width > 0", name="width_positive"),
        CheckConstraint("image_height > 0", name="height_positive"),
        Index("ix_annotations_status_submitted", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wing_image_id: Mapped[int] = mapped_column(
        ForeignKey("wing_images.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("landmark_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parent_annotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotations.id", ondelete="RESTRICT")
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[AnnotationStatus] = mapped_column(
        enum_column_type(AnnotationStatus, name="annotation_status_enum", length=16),
        nullable=False,
        default=AnnotationStatus.DRAFT,
        server_default=AnnotationStatus.DRAFT.value,
    )
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wing_image: Mapped[WingImage] = relationship(back_populates="annotations")
    template: Mapped[LandmarkTemplate] = relationship(back_populates="annotations")
    contributor: Mapped[User] = relationship(back_populates="annotations")
    parent: Mapped[Annotation | None] = relationship(
        back_populates="child",
        foreign_keys=[parent_annotation_id],
        remote_side="Annotation.id",
    )
    child: Mapped[Annotation | None] = relationship(
        back_populates="parent",
        foreign_keys=[parent_annotation_id],
        passive_deletes=True,
        uselist=False,
    )
    points: Mapped[list[AnnotationPoint]] = relationship(
        back_populates="annotation", passive_deletes=True
    )
    review: Mapped[Review | None] = relationship(
        back_populates="annotation", passive_deletes=True, uselist=False
    )
    repository_record: Mapped[RepositoryRecord | None] = relationship(
        back_populates="annotation", passive_deletes=True, uselist=False
    )
    analysis_runs: Mapped[list[WingAnalysisRun]] = relationship(
        back_populates="query_annotation", passive_deletes=True
    )


class AnnotationPoint(Base):
    """A landmark's pixel and normalized coordinates in one annotation."""

    __tablename__ = "annotation_points"
    __table_args__ = (
        UniqueConstraint(
            "annotation_id",
            "template_landmark_id",
            name="uq_points_annotation_landmark",
        ),
        CheckConstraint("x_pixel >= 0", name="x_pixel_nonnegative"),
        CheckConstraint("y_pixel >= 0", name="y_pixel_nonnegative"),
        CheckConstraint(
            "x_normalized >= 0 AND x_normalized < 1", name="x_normalized_range"
        ),
        CheckConstraint(
            "y_normalized >= 0 AND y_normalized < 1", name="y_normalized_range"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_landmark_id: Mapped[int] = mapped_column(
        ForeignKey("template_landmarks.id", ondelete="RESTRICT"), nullable=False
    )
    x_pixel: Mapped[float] = mapped_column(Float, nullable=False)
    y_pixel: Mapped[float] = mapped_column(Float, nullable=False)
    x_normalized: Mapped[float] = mapped_column(Float, nullable=False)
    y_normalized: Mapped[float] = mapped_column(Float, nullable=False)

    annotation: Mapped[Annotation] = relationship(back_populates="points")
    template_landmark: Mapped[TemplateLandmark] = relationship(
        back_populates="annotation_points"
    )


class Review(Base):
    """One expert decision for one submitted annotation revision."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "decision <> 'return' OR "
            "(comments IS NOT NULL AND length(trim(comments)) > 0)",
            name="return_requires_comments",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[ReviewDecision] = mapped_column(
        enum_column_type(ReviewDecision, name="review_decision_enum", length=12),
        nullable=False,
    )
    comments: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    annotation: Mapped[Annotation] = relationship(back_populates="review")
    reviewer: Mapped[User] = relationship(back_populates="reviews")
    repository_record: Mapped[RepositoryRecord | None] = relationship(
        back_populates="review", passive_deletes=True, uselist=False
    )


class RepositoryRecord(Base):
    """An approved annotation with a permanent public accession."""

    __tablename__ = "repository_records"
    __table_args__ = (
        UniqueConstraint(
            "taxon_id", "serial_number", name="uq_repository_taxon_serial"
        ),
        CheckConstraint(
            "serial_number BETWEEN 1 AND 999999", name="serial_six_digit_range"
        ),
        CheckConstraint(
            "accession_number LIKE 'WBR-HYM-%'", name="accession_prefix"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    taxon_id: Mapped[int] = mapped_column(
        ForeignKey("taxa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    accession_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    annotation: Mapped[Annotation] = relationship(back_populates="repository_record")
    review: Mapped[Review] = relationship(back_populates="repository_record")
    taxon: Mapped[Taxon] = relationship(back_populates="repository_records")


class ExternalReferenceDataset(Base):
    """A published external dataset used only as reproducible reference data."""

    __tablename__ = "external_reference_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_code", name="uq_external_datasets_code"),
        CheckConstraint("length(trim(dataset_code)) >= 1", name="dataset_code_nonempty"),
        CheckConstraint("length(trim(title)) >= 1", name="dataset_title_nonempty"),
        CheckConstraint("length(trim(authors)) >= 1", name="dataset_authors_nonempty"),
        CheckConstraint("publication_year >= 1800", name="publication_year_plausible"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)
    publication_year: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_doi: Mapped[str] = mapped_column(String(120), nullable=False)
    article_doi: Mapped[str | None] = mapped_column(String(120))
    workflow_doi: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[str | None] = mapped_column(String(80))
    licence: Mapped[str | None] = mapped_column(String(200))
    taxonomic_scope: Mapped[str] = mapped_column(String(200), nullable=False)
    geographic_scope: Mapped[str | None] = mapped_column(String(200))
    template_id: Mapped[int] = mapped_column(
        ForeignKey("landmark_templates.id", ondelete="RESTRICT"), nullable=False
    )
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    template: Mapped[LandmarkTemplate] = relationship(
        back_populates="external_reference_datasets"
    )
    shapes: Mapped[list[ExternalReferenceShape]] = relationship(
        back_populates="external_dataset", passive_deletes=True
    )
    import_issues: Mapped[list[ExternalReferenceImportIssue]] = relationship(
        back_populates="external_dataset", passive_deletes=True
    )


class ExternalReferenceShape(Base):
    """One published coordinate configuration, not a native WBR specimen."""

    __tablename__ = "external_reference_shapes"
    __table_args__ = (
        UniqueConstraint(
            "external_dataset_id",
            "source_record_identifier",
            name="uq_external_shapes_dataset_record",
        ),
        UniqueConstraint(
            "external_dataset_id",
            "source_row_hash",
            name="uq_external_shapes_dataset_row_hash",
        ),
        CheckConstraint(
            "length(trim(source_record_identifier)) >= 1",
            name="external_record_identifier_nonempty",
        ),
        CheckConstraint("coordinate_count = 19", name="external_shape_19_coordinates"),
        CheckConstraint("wing_type = 'forewing'", name="external_shape_forewing_only"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_dataset_id: Mapped[int] = mapped_column(
        ForeignKey("external_reference_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_record_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sample_identifier: Mapped[str | None] = mapped_column(String(255))
    taxon_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="Apis mellifera", server_default="Apis mellifera"
    )
    country_code: Mapped[str | None] = mapped_column(String(16), index=True)
    published_region: Mapped[str | None] = mapped_column(String(120), index=True)
    published_lineage: Mapped[str | None] = mapped_column(String(16), index=True)
    wing_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="forewing", server_default="forewing"
    )
    original_side: Mapped[str | None] = mapped_column(String(40))
    coordinate_json: Mapped[str] = mapped_column(Text, nullable=False)
    analytical_coordinate_json: Mapped[str | None] = mapped_column(Text)
    coordinate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    external_dataset: Mapped[ExternalReferenceDataset] = relationship(
        back_populates="shapes"
    )
    published_shape_matches: Mapped[list[PublishedShapeMatch]] = relationship(
        back_populates="external_reference_shape", passive_deletes=True
    )


class ExternalReferenceImportIssue(Base):
    """A quarantined source row that failed import validation."""

    __tablename__ = "external_reference_import_issues"
    __table_args__ = (
        UniqueConstraint(
            "external_dataset_id",
            "source_row_hash",
            name="uq_external_import_issues_dataset_row_hash",
        ),
        CheckConstraint("length(trim(reason)) >= 1", name="import_issue_reason_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_dataset_id: Mapped[int] = mapped_column(
        ForeignKey("external_reference_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_identifier: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    external_dataset: Mapped[ExternalReferenceDataset] = relationship(
        back_populates="import_issues"
    )


class AnalysisModel(Base):
    """A versioned, reproducible morphometric model artifact."""

    __tablename__ = "analysis_models"
    __table_args__ = (
        UniqueConstraint(
            "model_code", "model_version", name="uq_analysis_models_code_version"
        ),
        CheckConstraint("model_version >= 1", name="analysis_model_version_positive"),
        CheckConstraint(
            "reference_wing_count >= 0", name="analysis_model_wing_count_nonnegative"
        ),
        CheckConstraint(
            "reference_sample_count >= 0", name="analysis_model_sample_count_nonnegative"
        ),
        CheckConstraint(
            "artifact_sha256 IS NULL OR length(artifact_sha256) = 64",
            name="analysis_model_artifact_sha256_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_code: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("landmark_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    analysis_type: Mapped[AnalysisType] = mapped_column(
        enum_column_type(AnalysisType, name="analysis_type_enum", length=40),
        nullable=False,
        index=True,
    )
    source_dataset_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reference_wing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preprocessing_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    software_versions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_hashes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    validation_metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    artifact_storage_key: Mapped[str | None] = mapped_column(String(500))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    model_status: Mapped[AnalysisModelStatus] = mapped_column(
        enum_column_type(AnalysisModelStatus, name="analysis_model_status_enum", length=24),
        nullable=False,
        default=AnalysisModelStatus.BUILDING,
        server_default=AnalysisModelStatus.BUILDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[LandmarkTemplate] = relationship(back_populates="analysis_models")
    analysis_runs: Mapped[list[WingAnalysisRun]] = relationship(
        back_populates="model", passive_deletes=True
    )


class WingAnalysisRun(Base):
    """A persisted query result tied to one exact model version."""

    __tablename__ = "wing_analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "analysis_scope = 'single_wing'", name="analysis_scope_single_wing_only"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    analysis_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, default="single_wing", server_default="single_wing"
    )
    status: Mapped[AnalysisRunStatus] = mapped_column(
        enum_column_type(AnalysisRunStatus, name="analysis_run_status_enum", length=16),
        nullable=False,
        default=AnalysisRunStatus.RUNNING,
        server_default=AnalysisRunStatus.RUNNING.value,
        index=True,
    )
    preliminary_single_wing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    quality_status: Mapped[AnalysisQualityStatus] = mapped_column(
        enum_column_type(AnalysisQualityStatus, name="analysis_quality_status_enum", length=16),
        nullable=False,
        default=AnalysisQualityStatus.PASS,
        server_default=AnalysisQualityStatus.PASS.value,
    )
    outlier_status: Mapped[AnalysisOutlierStatus] = mapped_column(
        enum_column_type(AnalysisOutlierStatus, name="analysis_outlier_status_enum", length=40),
        nullable=False,
        default=AnalysisOutlierStatus.IN_DISTRIBUTION,
        server_default=AnalysisOutlierStatus.IN_DISTRIBUTION.value,
    )
    warning_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    query_annotation: Mapped[Annotation] = relationship(back_populates="analysis_runs")
    model: Mapped[AnalysisModel] = relationship(back_populates="analysis_runs")
    region_probabilities: Mapped[list[RegionProbability]] = relationship(
        back_populates="analysis_run", passive_deletes=True
    )
    lineage_probabilities: Mapped[list[LineageProbability]] = relationship(
        back_populates="analysis_run", passive_deletes=True
    )
    published_shape_matches: Mapped[list[PublishedShapeMatch]] = relationship(
        back_populates="analysis_run", passive_deletes=True
    )


class RegionProbability(Base):
    """One ranked geographical reference-group affinity result."""

    __tablename__ = "region_probabilities"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "rank", name="uq_region_prob_run_rank"),
        CheckConstraint("rank >= 1", name="region_probability_rank_positive"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="region_probability_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("wing_analysis_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_group: Mapped[str] = mapped_column(String(120), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    reference_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interpretation: Mapped[str] = mapped_column(String(200), nullable=False)

    analysis_run: Mapped[WingAnalysisRun] = relationship(
        back_populates="region_probabilities"
    )


class LineageProbability(Base):
    """One ranked A/C/M/O wing-shape lineage-affinity result."""

    __tablename__ = "lineage_probabilities"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "rank", name="uq_lineage_prob_run_rank"),
        UniqueConstraint(
            "analysis_run_id", "lineage_code", name="uq_lineage_prob_run_lineage"
        ),
        CheckConstraint("rank >= 1", name="lineage_probability_rank_positive"),
        CheckConstraint("lineage_code IN ('A', 'C', 'M', 'O')", name="lineage_code_acmo"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="lineage_probability_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("wing_analysis_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    lineage_code: Mapped[str] = mapped_column(String(1), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    reference_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interpretation: Mapped[str] = mapped_column(String(200), nullable=False)

    analysis_run: Mapped[WingAnalysisRun] = relationship(
        back_populates="lineage_probabilities"
    )


class PublishedShapeMatch(Base):
    """Nearest external published forewing-coordinate configuration."""

    __tablename__ = "published_shape_matches"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id", "rank", name="uq_published_shape_match_run_rank"
        ),
        CheckConstraint("rank >= 1", name="published_shape_match_rank_positive"),
        CheckConstraint(
            "procrustes_distance >= 0", name="published_shape_distance_nonnegative"
        ),
        CheckConstraint(
            "similarity_percentile >= 0 AND similarity_percentile <= 100",
            name="published_shape_similarity_percentile_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("wing_analysis_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    external_reference_shape_id: Mapped[int] = mapped_column(
        ForeignKey("external_reference_shapes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    procrustes_distance: Mapped[float] = mapped_column(Float, nullable=False)
    similarity_percentile: Mapped[float] = mapped_column(Float, nullable=False)

    analysis_run: Mapped[WingAnalysisRun] = relationship(
        back_populates="published_shape_matches"
    )
    external_reference_shape: Mapped[ExternalReferenceShape] = relationship(
        back_populates="published_shape_matches"
    )


__all__ = [
    "Annotation",
    "AnnotationPoint",
    "AnalysisModel",
    "Assignment",
    "Base",
    "ExternalReferenceDataset",
    "ExternalReferenceImportIssue",
    "ExternalReferenceShape",
    "LandmarkTemplate",
    "LineageProbability",
    "PublishedShapeMatch",
    "RepositoryRecord",
    "RegionProbability",
    "Review",
    "Specimen",
    "Taxon",
    "TemplateLandmark",
    "User",
    "WingAnalysisRun",
    "WingImage",
    "utc_now",
]

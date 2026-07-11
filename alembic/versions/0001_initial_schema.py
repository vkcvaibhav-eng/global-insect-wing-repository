"""Create the version 0.1 repository schema.

Revision ID: 0001_initial
Revises: None
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(email)) >= 3", name=op.f("ck_users_email_nonempty")
        ),
        sa.CheckConstraint(
            "length(trim(full_name)) >= 1", name=op.f("ck_users_full_name_nonempty")
        ),
        sa.CheckConstraint(
            "role IN ('administrator', 'student', 'expert_reviewer')",
            name=op.f("ck_users_role_enum"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "taxa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "order_name",
            sa.String(length=50),
            server_default="Hymenoptera",
            nullable=False,
        ),
        sa.Column(
            "order_code", sa.String(length=3), server_default="HYM", nullable=False
        ),
        sa.Column("family", sa.String(length=100), nullable=True),
        sa.Column("genus", sa.String(length=100), nullable=False),
        sa.Column("genus_code", sa.String(length=12), nullable=False),
        sa.Column(
            "next_accession_serial",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(genus_code) BETWEEN 2 AND 12 AND genus_code = upper(genus_code)",
            name=op.f("ck_taxa_genus_code_shape"),
        ),
        sa.CheckConstraint(
            "length(trim(genus)) >= 2", name=op.f("ck_taxa_genus_nonempty")
        ),
        sa.CheckConstraint(
            "order_code = 'HYM'", name=op.f("ck_taxa_hymenoptera_code_only")
        ),
        sa.CheckConstraint(
            "order_name = 'Hymenoptera'", name=op.f("ck_taxa_hymenoptera_only")
        ),
        sa.CheckConstraint(
            "next_accession_serial BETWEEN 1 AND 1000000",
            name=op.f("ck_taxa_next_accession_serial_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_taxa")),
        sa.UniqueConstraint(
            "order_name", "genus", name="uq_taxa_order_genus"
        ),
        sa.UniqueConstraint(
            "order_code", "genus_code", name="uq_taxa_order_genus_code"
        ),
    )

    op.create_table(
        "landmark_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taxon_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("side", sa.String(length=8), server_default="right", nullable=False),
        sa.Column(
            "wing_type",
            sa.String(length=12),
            server_default="forewing",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("source_json", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(name)) >= 1",
            name=op.f("ck_landmark_templates_name_nonempty"),
        ),
        sa.CheckConstraint(
            "side IN ('right')",
            name=op.f("ck_landmark_templates_template_wing_side_enum"),
        ),
        sa.CheckConstraint(
            "wing_type IN ('forewing')",
            name=op.f("ck_landmark_templates_template_wing_type_enum"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name=op.f("ck_landmark_templates_template_status_enum"),
        ),
        sa.CheckConstraint(
            "source_sha256 IS NULL OR length(source_sha256) = 64",
            name=op.f("ck_landmark_templates_source_sha256_length"),
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_landmark_templates_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_landmark_templates_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"],
            ["taxa.id"],
            name=op.f("fk_landmark_templates_taxon_id_taxa"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_landmark_templates")),
        sa.UniqueConstraint(
            "taxon_id", "version", name="uq_templates_taxon_version"
        ),
    )
    op.create_index(
        op.f("ix_landmark_templates_taxon_id"),
        "landmark_templates",
        ["taxon_id"],
        unique=False,
    )

    op.create_table(
        "template_landmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(trim(label)) >= 1",
            name=op.f("ck_template_landmarks_label_nonempty"),
        ),
        sa.CheckConstraint(
            "ordinal >= 1", name=op.f("ck_template_landmarks_ordinal_positive")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["landmark_templates.id"],
            name=op.f(
                "fk_template_landmarks_template_id_landmark_templates"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_landmarks")),
        sa.UniqueConstraint(
            "template_id", "ordinal", name="uq_landmarks_template_ordinal"
        ),
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("taxon_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(is_active = true AND ended_at IS NULL) OR "
            "(is_active = false AND ended_at IS NOT NULL)",
            name=op.f("ck_assignments_active_end_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            name=op.f("fk_assignments_assigned_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_assignments_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"],
            ["taxa.id"],
            name=op.f("fk_assignments_taxon_id_taxa"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["landmark_templates.id"],
            name=op.f("fk_assignments_template_id_landmark_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
    )
    op.create_index(
        op.f("ix_assignments_taxon_id"), "assignments", ["taxon_id"], unique=False
    )
    op.create_index(
        "uq_assignments_active_student",
        "assignments",
        ["student_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "specimens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taxon_id", sa.Integer(), nullable=False),
        sa.Column("contributor_id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("specimen_code", sa.String(length=120), nullable=False),
        sa.Column("species_text", sa.String(length=200), nullable=True),
        sa.Column("sex", sa.String(length=40), nullable=True),
        sa.Column("collection_date", sa.Date(), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("collector_name", sa.String(length=200), nullable=True),
        sa.Column("voucher_institution", sa.String(length=200), nullable=True),
        sa.Column("voucher_code", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(specimen_code)) >= 1",
            name=op.f("ck_specimens_code_nonempty"),
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name=op.f("ck_specimens_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_specimens_longitude_range"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_specimens_assignment_id_assignments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contributor_id"],
            ["users.id"],
            name=op.f("fk_specimens_contributor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"],
            ["taxa.id"],
            name=op.f("fk_specimens_taxon_id_taxa"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specimens")),
        sa.UniqueConstraint(
            "contributor_id", "specimen_code", name="uq_specimens_contributor_code"
        ),
    )
    op.create_index(
        op.f("ix_specimens_assignment_id"),
        "specimens",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_specimens_contributor_id"),
        "specimens",
        ["contributor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_specimens_taxon_id"), "specimens", ["taxon_id"], unique=False
    )

    op.create_table(
        "wing_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("specimen_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=8), server_default="right", nullable=False),
        sa.Column(
            "wing_type",
            sa.String(length=12),
            server_default="forewing",
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size > 0", name=op.f("ck_wing_images_byte_size_positive")
        ),
        sa.CheckConstraint(
            "length(trim(original_filename)) >= 1",
            name=op.f("ck_wing_images_filename_nonempty"),
        ),
        sa.CheckConstraint(
            "image_height > 0", name=op.f("ck_wing_images_height_positive")
        ),
        sa.CheckConstraint(
            "length(sha256) = 64", name=op.f("ck_wing_images_sha256_length")
        ),
        sa.CheckConstraint(
            "image_width > 0", name=op.f("ck_wing_images_width_positive")
        ),
        sa.CheckConstraint(
            "side IN ('right')", name=op.f("ck_wing_images_wing_side_enum")
        ),
        sa.CheckConstraint(
            "wing_type IN ('forewing')", name=op.f("ck_wing_images_wing_type_enum")
        ),
        sa.ForeignKeyConstraint(
            ["specimen_id"],
            ["specimens.id"],
            name=op.f("fk_wing_images_specimen_id_specimens"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_wing_images_uploaded_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wing_images")),
        sa.UniqueConstraint("specimen_id", name=op.f("uq_wing_images_specimen_id")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_wing_images_storage_key")),
    )
    op.create_index(
        op.f("ix_wing_images_uploaded_by_id"),
        "wing_images",
        ["uploaded_by_id"],
        unique=False,
    )

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wing_image_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("contributor_id", sa.Integer(), nullable=False),
        sa.Column("parent_annotation_id", sa.Integer(), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'returned', 'approved')",
            name=op.f("ck_annotations_annotation_status_enum"),
        ),
        sa.CheckConstraint(
            "image_height > 0", name=op.f("ck_annotations_height_positive")
        ),
        sa.CheckConstraint(
            "revision_number >= 1", name=op.f("ck_annotations_revision_positive")
        ),
        sa.CheckConstraint(
            "image_width > 0", name=op.f("ck_annotations_width_positive")
        ),
        sa.ForeignKeyConstraint(
            ["contributor_id"],
            ["users.id"],
            name=op.f("fk_annotations_contributor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_annotation_id"],
            ["annotations.id"],
            name=op.f("fk_annotations_parent_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["landmark_templates.id"],
            name=op.f("fk_annotations_template_id_landmark_templates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["wing_image_id"],
            ["wing_images.id"],
            name=op.f("fk_annotations_wing_image_id_wing_images"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotations")),
        sa.UniqueConstraint(
            "wing_image_id",
            "template_id",
            "revision_number",
            name="uq_annotations_image_template_revision",
        ),
        sa.UniqueConstraint("parent_annotation_id", name="uq_annotations_parent"),
    )
    op.create_index(
        op.f("ix_annotations_contributor_id"),
        "annotations",
        ["contributor_id"],
        unique=False,
    )
    op.create_index(
        "ix_annotations_status_submitted",
        "annotations",
        ["status", "submitted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_annotations_template_id"),
        "annotations",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_annotations_wing_image_id"),
        "annotations",
        ["wing_image_id"],
        unique=False,
    )

    op.create_table(
        "annotation_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("annotation_id", sa.Integer(), nullable=False),
        sa.Column("template_landmark_id", sa.Integer(), nullable=False),
        sa.Column("x_pixel", sa.Float(), nullable=False),
        sa.Column("y_pixel", sa.Float(), nullable=False),
        sa.Column("x_normalized", sa.Float(), nullable=False),
        sa.Column("y_normalized", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "x_normalized >= 0 AND x_normalized < 1",
            name=op.f("ck_annotation_points_x_normalized_range"),
        ),
        sa.CheckConstraint(
            "x_pixel >= 0", name=op.f("ck_annotation_points_x_pixel_nonnegative")
        ),
        sa.CheckConstraint(
            "y_normalized >= 0 AND y_normalized < 1",
            name=op.f("ck_annotation_points_y_normalized_range"),
        ),
        sa.CheckConstraint(
            "y_pixel >= 0", name=op.f("ck_annotation_points_y_pixel_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            name=op.f("fk_annotation_points_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_landmark_id"],
            ["template_landmarks.id"],
            name=op.f(
                "fk_annotation_points_template_landmark_id_template_landmarks"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotation_points")),
        sa.UniqueConstraint(
            "annotation_id",
            "template_landmark_id",
            name="uq_points_annotation_landmark",
        ),
    )
    op.create_index(
        op.f("ix_annotation_points_annotation_id"),
        "annotation_points",
        ["annotation_id"],
        unique=False,
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("annotation_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=12), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'return')",
            name=op.f("ck_reviews_review_decision_enum"),
        ),
        sa.CheckConstraint(
            "decision <> 'return' OR "
            "(comments IS NOT NULL AND length(trim(comments)) > 0)",
            name=op.f("ck_reviews_return_requires_comments"),
        ),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            name=op.f("fk_reviews_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_reviews_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("annotation_id", name=op.f("uq_reviews_annotation_id")),
    )
    op.create_index(
        op.f("ix_reviews_reviewer_id"),
        "reviews",
        ["reviewer_id"],
        unique=False,
    )

    op.create_table(
        "repository_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("annotation_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("taxon_id", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=64), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "accession_number LIKE 'WBR-HYM-%'",
            name=op.f("ck_repository_records_accession_prefix"),
        ),
        sa.CheckConstraint(
            "serial_number BETWEEN 1 AND 999999",
            name=op.f("ck_repository_records_serial_six_digit_range"),
        ),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            name=op.f("fk_repository_records_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["reviews.id"],
            name=op.f("fk_repository_records_review_id_reviews"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"],
            ["taxa.id"],
            name=op.f("fk_repository_records_taxon_id_taxa"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repository_records")),
        sa.UniqueConstraint(
            "accession_number", name=op.f("uq_repository_records_accession_number")
        ),
        sa.UniqueConstraint(
            "annotation_id", name=op.f("uq_repository_records_annotation_id")
        ),
        sa.UniqueConstraint(
            "review_id", name=op.f("uq_repository_records_review_id")
        ),
        sa.UniqueConstraint(
            "taxon_id", "serial_number", name="uq_repository_taxon_serial"
        ),
    )
    op.create_index(
        op.f("ix_repository_records_taxon_id"),
        "repository_records",
        ["taxon_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("repository_records")
    op.drop_table("reviews")
    op.drop_table("annotation_points")
    op.drop_table("annotations")
    op.drop_table("wing_images")
    op.drop_table("specimens")
    op.drop_table("assignments")
    op.drop_table("template_landmarks")
    op.drop_table("landmark_templates")
    op.drop_table("taxa")
    op.drop_table("users")

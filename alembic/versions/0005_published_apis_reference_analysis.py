"""Add published Apis reference analysis schema.

Revision ID: 0005_published_apis_reference_analysis
Revises: 0004_deleted_annotation_status
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_published_apis_reference_analysis"
down_revision: str | None = "0004_deleted_annotation_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_reference_datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=False),
        sa.Column("dataset_doi", sa.String(length=120), nullable=False),
        sa.Column("article_doi", sa.String(length=120), nullable=True),
        sa.Column("workflow_doi", sa.String(length=120), nullable=True),
        sa.Column("version", sa.String(length=80), nullable=True),
        sa.Column("licence", sa.String(length=200), nullable=True),
        sa.Column("taxonomic_scope", sa.String(length=200), nullable=False),
        sa.Column("geographic_scope", sa.String(length=200), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(authors)) >= 1",
            name=op.f("ck_external_reference_datasets_dataset_authors_nonempty"),
        ),
        sa.CheckConstraint(
            "length(trim(dataset_code)) >= 1",
            name=op.f("ck_external_reference_datasets_dataset_code_nonempty"),
        ),
        sa.CheckConstraint(
            "length(trim(title)) >= 1",
            name=op.f("ck_external_reference_datasets_dataset_title_nonempty"),
        ),
        sa.CheckConstraint(
            "publication_year >= 1800",
            name=op.f("ck_external_reference_datasets_publication_year_plausible"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["landmark_templates.id"],
            name=op.f("fk_external_reference_datasets_template_id_landmark_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_reference_datasets")),
        sa.UniqueConstraint(
            "dataset_code", name=op.f("uq_external_reference_datasets_dataset_code")
        ),
    )

    op.create_table(
        "analysis_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_code", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("analysis_type", sa.String(length=40), nullable=False),
        sa.Column("source_dataset_ids", sa.Text(), nullable=False),
        sa.Column("reference_wing_count", sa.Integer(), nullable=False),
        sa.Column("reference_sample_count", sa.Integer(), nullable=False),
        sa.Column("preprocessing_json", sa.Text(), nullable=False),
        sa.Column("software_versions_json", sa.Text(), nullable=False),
        sa.Column("source_hashes_json", sa.Text(), nullable=False),
        sa.Column("validation_metrics_json", sa.Text(), nullable=False),
        sa.Column("artifact_storage_key", sa.String(length=500), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("model_status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "analysis_type IN ('apis_mellifera_eu_region', "
            "'apis_mellifera_lineage', 'apis_mellifera_nearest_shape')",
            name=op.f("ck_analysis_models_analysis_type_enum"),
        ),
        sa.CheckConstraint(
            "artifact_sha256 IS NULL OR length(artifact_sha256) = 64",
            name=op.f("ck_analysis_models_analysis_model_artifact_sha256_length"),
        ),
        sa.CheckConstraint(
            "model_status IN ('building', 'validation_failed', 'validated', "
            "'active', 'retired')",
            name=op.f("ck_analysis_models_analysis_model_status_enum"),
        ),
        sa.CheckConstraint(
            "model_version >= 1",
            name=op.f("ck_analysis_models_analysis_model_version_positive"),
        ),
        sa.CheckConstraint(
            "reference_sample_count >= 0",
            name=op.f("ck_analysis_models_analysis_model_sample_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "reference_wing_count >= 0",
            name=op.f("ck_analysis_models_analysis_model_wing_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["landmark_templates.id"],
            name=op.f("fk_analysis_models_template_id_landmark_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_models")),
        sa.UniqueConstraint(
            "model_code",
            "model_version",
            name=op.f("uq_analysis_models_model_code_model_version"),
        ),
    )
    op.create_index(
        op.f("ix_analysis_models_analysis_type"),
        "analysis_models",
        ["analysis_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_models_model_status"),
        "analysis_models",
        ["model_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_models_template_id"),
        "analysis_models",
        ["template_id"],
        unique=False,
    )

    op.create_table(
        "external_reference_shapes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_dataset_id", sa.Integer(), nullable=False),
        sa.Column("source_record_identifier", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_sample_identifier", sa.String(length=255), nullable=True),
        sa.Column(
            "taxon_name",
            sa.String(length=200),
            server_default="Apis mellifera",
            nullable=False,
        ),
        sa.Column("country_code", sa.String(length=16), nullable=True),
        sa.Column("published_region", sa.String(length=120), nullable=True),
        sa.Column("published_lineage", sa.String(length=16), nullable=True),
        sa.Column(
            "wing_type",
            sa.String(length=16),
            server_default="forewing",
            nullable=False,
        ),
        sa.Column("original_side", sa.String(length=40), nullable=True),
        sa.Column("coordinate_json", sa.Text(), nullable=False),
        sa.Column("analytical_coordinate_json", sa.Text(), nullable=True),
        sa.Column("coordinate_count", sa.Integer(), nullable=False),
        sa.Column("source_metadata_json", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "coordinate_count = 19",
            name=op.f("ck_external_reference_shapes_external_shape_19_coordinates"),
        ),
        sa.CheckConstraint(
            "length(trim(source_record_identifier)) >= 1",
            name=op.f("ck_external_reference_shapes_external_record_identifier_nonempty"),
        ),
        sa.CheckConstraint(
            "wing_type = 'forewing'",
            name=op.f("ck_external_reference_shapes_external_shape_forewing_only"),
        ),
        sa.ForeignKeyConstraint(
            ["external_dataset_id"],
            ["external_reference_datasets.id"],
            name=op.f("fk_external_reference_shapes_external_dataset_id_external_reference_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_reference_shapes")),
        sa.UniqueConstraint(
            "external_dataset_id",
            "source_record_identifier",
            name="uq_external_shapes_dataset_record",
        ),
        sa.UniqueConstraint(
            "external_dataset_id",
            "source_row_hash",
            name="uq_external_shapes_dataset_row_hash",
        ),
    )
    op.create_index(
        op.f("ix_external_reference_shapes_country_code"),
        "external_reference_shapes",
        ["country_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_reference_shapes_external_dataset_id"),
        "external_reference_shapes",
        ["external_dataset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_reference_shapes_published_lineage"),
        "external_reference_shapes",
        ["published_lineage"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_reference_shapes_published_region"),
        "external_reference_shapes",
        ["published_region"],
        unique=False,
    )

    op.create_table(
        "external_reference_import_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_dataset_id", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_row_identifier", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(reason)) >= 1",
            name=op.f("ck_external_reference_import_issues_import_issue_reason_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["external_dataset_id"],
            ["external_reference_datasets.id"],
            name=op.f("fk_external_reference_import_issues_external_dataset_id_external_reference_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_reference_import_issues")),
        sa.UniqueConstraint(
            "external_dataset_id",
            "source_row_hash",
            name="uq_external_import_issues_dataset_row_hash",
        ),
    )
    op.create_index(
        op.f("ix_external_reference_import_issues_external_dataset_id"),
        "external_reference_import_issues",
        ["external_dataset_id"],
        unique=False,
    )

    op.create_table(
        "wing_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_annotation_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column(
            "analysis_scope",
            sa.String(length=40),
            server_default="single_wing",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "preliminary_single_wing",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("outlier_status", sa.String(length=40), nullable=False),
        sa.Column("warning_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "analysis_scope = 'single_wing'",
            name=op.f("ck_wing_analysis_runs_analysis_scope_single_wing_only"),
        ),
        sa.CheckConstraint(
            "outlier_status IN ('in_distribution', 'outside_reference_distribution')",
            name=op.f("ck_wing_analysis_runs_analysis_outlier_status_enum"),
        ),
        sa.CheckConstraint(
            "quality_status IN ('pass', 'warning', 'fail')",
            name=op.f("ck_wing_analysis_runs_analysis_quality_status_enum"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name=op.f("ck_wing_analysis_runs_analysis_run_status_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["analysis_models.id"],
            name=op.f("fk_wing_analysis_runs_model_id_analysis_models"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["query_annotation_id"],
            ["annotations.id"],
            name=op.f("fk_wing_analysis_runs_query_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wing_analysis_runs")),
    )
    op.create_index(
        op.f("ix_wing_analysis_runs_model_id"),
        "wing_analysis_runs",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wing_analysis_runs_query_annotation_id"),
        "wing_analysis_runs",
        ["query_annotation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wing_analysis_runs_status"),
        "wing_analysis_runs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "lineage_probabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("lineage_code", sa.String(length=1), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("reference_sample_count", sa.Integer(), nullable=False),
        sa.Column("interpretation", sa.String(length=200), nullable=False),
        sa.CheckConstraint(
            "lineage_code IN ('A', 'C', 'M', 'O')",
            name=op.f("ck_lineage_probabilities_lineage_code_acmo"),
        ),
        sa.CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name=op.f("ck_lineage_probabilities_lineage_probability_range"),
        ),
        sa.CheckConstraint(
            "rank >= 1",
            name=op.f("ck_lineage_probabilities_lineage_probability_rank_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["wing_analysis_runs.id"],
            name=op.f("fk_lineage_probabilities_analysis_run_id_wing_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineage_probabilities")),
        sa.UniqueConstraint(
            "analysis_run_id",
            "lineage_code",
            name=op.f("uq_lineage_probabilities_analysis_run_id_lineage_code"),
        ),
        sa.UniqueConstraint(
            "analysis_run_id",
            "rank",
            name=op.f("uq_lineage_probabilities_analysis_run_id_rank"),
        ),
    )
    op.create_index(
        op.f("ix_lineage_probabilities_analysis_run_id"),
        "lineage_probabilities",
        ["analysis_run_id"],
        unique=False,
    )

    op.create_table(
        "published_shape_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("external_reference_shape_id", sa.Integer(), nullable=False),
        sa.Column("procrustes_distance", sa.Float(), nullable=False),
        sa.Column("similarity_percentile", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "rank >= 1",
            name=op.f("ck_published_shape_matches_published_shape_match_rank_positive"),
        ),
        sa.CheckConstraint(
            "procrustes_distance >= 0",
            name=op.f("ck_published_shape_matches_published_shape_distance_nonnegative"),
        ),
        sa.CheckConstraint(
            "similarity_percentile >= 0 AND similarity_percentile <= 100",
            name=op.f("ck_published_shape_matches_published_shape_similarity_percentile_range"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["wing_analysis_runs.id"],
            name=op.f("fk_published_shape_matches_analysis_run_id_wing_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["external_reference_shape_id"],
            ["external_reference_shapes.id"],
            name=op.f("fk_published_shape_matches_external_reference_shape_id_external_reference_shapes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_published_shape_matches")),
        sa.UniqueConstraint(
            "analysis_run_id",
            "rank",
            name=op.f("uq_published_shape_matches_analysis_run_id_rank"),
        ),
    )
    op.create_index(
        op.f("ix_published_shape_matches_analysis_run_id"),
        "published_shape_matches",
        ["analysis_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_shape_matches_external_reference_shape_id"),
        "published_shape_matches",
        ["external_reference_shape_id"],
        unique=False,
    )

    op.create_table(
        "region_probabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("reference_group", sa.String(length=120), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("reference_sample_count", sa.Integer(), nullable=False),
        sa.Column("interpretation", sa.String(length=200), nullable=False),
        sa.CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name=op.f("ck_region_probabilities_region_probability_range"),
        ),
        sa.CheckConstraint(
            "rank >= 1",
            name=op.f("ck_region_probabilities_region_probability_rank_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["wing_analysis_runs.id"],
            name=op.f("fk_region_probabilities_analysis_run_id_wing_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_region_probabilities")),
        sa.UniqueConstraint(
            "analysis_run_id",
            "rank",
            name=op.f("uq_region_probabilities_analysis_run_id_rank"),
        ),
    )
    op.create_index(
        op.f("ix_region_probabilities_analysis_run_id"),
        "region_probabilities",
        ["analysis_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("region_probabilities")
    op.drop_table("published_shape_matches")
    op.drop_table("lineage_probabilities")
    op.drop_table("wing_analysis_runs")
    op.drop_table("external_reference_import_issues")
    op.drop_table("external_reference_shapes")
    op.drop_table("analysis_models")
    op.drop_table("external_reference_datasets")

"""Add specimen species-ID and locality sampling metadata.

Revision ID: 0007_sampling_metadata
Revises: 0006_retire_apis_v1
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_sampling_metadata"
down_revision: str | None = "0006_retire_apis_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name
    op.add_column(
        "landmark_templates",
        sa.Column(
            "minimum_wings_per_locality",
            sa.Integer(),
            nullable=False,
            server_default="10",
        )
    )
    op.add_column(
        "landmark_templates",
        sa.Column(
            "recommended_wings_per_locality",
            sa.Integer(),
            nullable=False,
            server_default="15",
        )
    )

    op.add_column(
        "specimens",
        sa.Column(
            "species_identification_method",
            sa.String(length=24),
            nullable=True,
        ),
    )
    op.add_column("specimens", sa.Column("genbank_accession", sa.String(length=120)))
    op.add_column("specimens", sa.Column("taxonomist_name", sa.String(length=200)))
    op.add_column("specimens", sa.Column("locality_sample_code", sa.String(length=120)))
    op.add_column("specimens", sa.Column("locality_sample_size", sa.Integer()))
    op.add_column("specimens", sa.Column("locality_sample_number", sa.Integer()))
    op.create_index(
        "uq_specimens_contributor_locality_sample_number",
        "specimens",
        ["contributor_id", "locality_sample_code", "locality_sample_number"],
        unique=True,
    )

    if dialect_name != "sqlite":
        op.create_check_constraint(
            "minimum_wings_per_locality_positive",
            "landmark_templates",
            "minimum_wings_per_locality >= 1",
        )
        op.create_check_constraint(
            "recommended_wings_not_below_minimum",
            "landmark_templates",
            "recommended_wings_per_locality >= minimum_wings_per_locality",
        )
        op.create_check_constraint(
            "species_identification_method_enum",
            "specimens",
            "species_identification_method IS NULL OR "
            "species_identification_method IN "
            "('molecular', 'taxonomist', 'dichotomous_key')",
        )
        op.create_check_constraint(
            "locality_sample_size_positive",
            "specimens",
            "locality_sample_size IS NULL OR locality_sample_size >= 1",
        )
        op.create_check_constraint(
            "locality_sample_number_positive",
            "specimens",
            "locality_sample_number IS NULL OR locality_sample_number >= 1",
        )
        op.create_check_constraint(
            "locality_sample_number_within_size",
            "specimens",
            "locality_sample_size IS NULL OR locality_sample_number IS NULL "
            "OR locality_sample_number <= locality_sample_size",
        )


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name != "sqlite":
        op.drop_constraint(
            "locality_sample_number_within_size",
            "specimens",
            type_="check",
        )
        op.drop_constraint(
            "locality_sample_number_positive",
            "specimens",
            type_="check",
        )
        op.drop_constraint("locality_sample_size_positive", "specimens", type_="check")
        op.drop_constraint(
            "species_identification_method_enum",
            "specimens",
            type_="check",
        )
        op.drop_constraint(
            "recommended_wings_not_below_minimum",
            "landmark_templates",
            type_="check",
        )
        op.drop_constraint(
            "minimum_wings_per_locality_positive",
            "landmark_templates",
            type_="check",
        )
    op.drop_index(
        "uq_specimens_contributor_locality_sample_number",
        table_name="specimens",
    )
    op.drop_column("specimens", "locality_sample_number")
    op.drop_column("specimens", "locality_sample_size")
    op.drop_column("specimens", "locality_sample_code")
    op.drop_column("specimens", "taxonomist_name")
    op.drop_column("specimens", "genbank_accession")
    op.drop_column("specimens", "species_identification_method")
    op.drop_column("landmark_templates", "recommended_wings_per_locality")
    op.drop_column("landmark_templates", "minimum_wings_per_locality")

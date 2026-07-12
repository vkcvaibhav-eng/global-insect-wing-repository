"""Add image scale calibration metadata.

Revision ID: 0002_image_calibration
Revises: 0001_initial
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_image_calibration"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("wing_images") as batch_op:
        batch_op.add_column(sa.Column("scale_reference_length", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_reference_unit", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("scale_reference_pixels", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_mm_per_pixel", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_x1_pixel", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_y1_pixel", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_x2_pixel", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("scale_y2_pixel", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("scale_calibrated_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("wing_images") as batch_op:
        batch_op.drop_column("scale_calibrated_at")
        batch_op.drop_column("scale_y2_pixel")
        batch_op.drop_column("scale_x2_pixel")
        batch_op.drop_column("scale_y1_pixel")
        batch_op.drop_column("scale_x1_pixel")
        batch_op.drop_column("scale_mm_per_pixel")
        batch_op.drop_column("scale_reference_pixels")
        batch_op.drop_column("scale_reference_unit")
        batch_op.drop_column("scale_reference_length")

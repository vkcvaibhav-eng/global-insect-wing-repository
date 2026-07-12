"""Allow students to withdraw mistaken submitted annotations.

Revision ID: 0003_annotation_withdrawal
Revises: 0002_image_calibration
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_annotation_withdrawal"
down_revision: str | None = "0002_image_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_STATUSES = "'draft', 'submitted', 'returned', 'approved'"
NEW_STATUSES = "'draft', 'submitted', 'withdrawn', 'returned', 'approved'"


def upgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            f"status IN ({NEW_STATUSES})",
        )


def downgrade() -> None:
    op.execute("UPDATE annotations SET status = 'submitted' WHERE status = 'withdrawn'")
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            f"status IN ({OLD_STATUSES})",
        )

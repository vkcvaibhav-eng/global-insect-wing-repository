"""Allow withdrawn annotations to be hidden as deleted.

Revision ID: 0004_deleted_annotation_status
Revises: 0003_annotation_withdrawal
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0004_deleted_annotation_status"
down_revision: str | None = "0003_annotation_withdrawal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_STATUSES = "'draft', 'submitted', 'withdrawn', 'returned', 'approved'"
NEW_STATUSES = "'draft', 'submitted', 'withdrawn', 'deleted', 'returned', 'approved'"


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
    op.execute("UPDATE annotations SET status = 'withdrawn' WHERE status = 'deleted'")
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_annotations_annotation_status_enum"),
            f"status IN ({OLD_STATUSES})",
        )

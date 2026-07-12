"""Retire the obsolete Apis teaching template.

Revision ID: 0006_retire_apis_v1
Revises: 0005_apis_analysis
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0006_retire_apis_v1"
down_revision: str | None = "0005_apis_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_APIS_TEMPLATE_FILTER = """
    SELECT landmark_templates.id
    FROM landmark_templates
    JOIN taxa ON taxa.id = landmark_templates.taxon_id
    WHERE taxa.genus_code = 'APIS'
      AND landmark_templates.version = 1
      AND landmark_templates.name = 'Apis right-forewing teaching template'
"""

STANDARD_APIS_TEMPLATE_FILTER = """
    SELECT landmark_templates.id
    FROM landmark_templates
    JOIN taxa ON taxa.id = landmark_templates.taxon_id
    WHERE taxa.genus_code = 'APIS'
      AND landmark_templates.version = 2
      AND landmark_templates.name = 'Apis right forewing standard 19-landmark template'
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE assignments
        SET is_active = false,
            ended_at = CURRENT_TIMESTAMP
        WHERE is_active = true
          AND template_id IN ({OLD_APIS_TEMPLATE_FILTER})
        """
    )
    op.execute(
        f"""
        UPDATE landmark_templates
        SET status = 'retired'
        WHERE id IN ({OLD_APIS_TEMPLATE_FILTER})
          AND status != 'retired'
        """
    )
    op.execute(
        f"""
        UPDATE landmark_templates
        SET status = 'published',
            published_at = COALESCE(published_at, CURRENT_TIMESTAMP)
        WHERE id IN ({STANDARD_APIS_TEMPLATE_FILTER})
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE landmark_templates
        SET status = 'published',
            published_at = COALESCE(published_at, CURRENT_TIMESTAMP)
        WHERE id IN ({OLD_APIS_TEMPLATE_FILTER})
        """
    )
    op.execute(
        f"""
        UPDATE landmark_templates
        SET status = 'draft',
            published_at = NULL
        WHERE id IN ({STANDARD_APIS_TEMPLATE_FILTER})
        """
    )

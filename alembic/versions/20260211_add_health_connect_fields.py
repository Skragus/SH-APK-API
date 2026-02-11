"""Add Health Connect JSONB fields to shealth_daily

Revision ID: 20260211_add_health_connect_fields
Revises: None
Create Date: 2026-02-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260211_add_health_connect_fields"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shealth_daily",
        sa.Column(
            "body_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "shealth_daily",
        sa.Column(
            "nutrition_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "shealth_daily",
        sa.Column(
            "exercise_sessions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("shealth_daily", "exercise_sessions")
    op.drop_column("shealth_daily", "nutrition_summary")
    op.drop_column("shealth_daily", "body_metrics")


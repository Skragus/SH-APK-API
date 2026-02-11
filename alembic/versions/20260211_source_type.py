"""Add source_type column to shealth_daily

Revision ID: 20260211_source_type
Revises: 20260211_hc_fields
Create Date: 2026-02-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260211_source_type"
down_revision: Union[str, None] = "20260211_hc_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shealth_daily",
        sa.Column(
            "source_type",
            sa.String(),
            nullable=False,
            server_default="daily",
        ),
    )


def downgrade() -> None:
    op.drop_column("shealth_daily", "source_type")

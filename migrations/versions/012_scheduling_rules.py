"""Add machine-type scheduling rule configuration.

Revision ID: 012_scheduling_rules
Revises: 011_default_dual_shift_calendar
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012_scheduling_rules"
down_revision: Union[str, None] = "011_default_dual_shift_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machine_type",
        sa.Column("scheduling_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("machine_type", "scheduling_config")

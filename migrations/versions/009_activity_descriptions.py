"""Add activity description fields

Revision ID: 009_activity_descriptions
Revises: 008_network_editor_bindings
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_activity_descriptions"
down_revision: Union[str, None] = "008_network_editor_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("activity_node", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("atomic_activity", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("atomic_activity", "description")
    op.drop_column("activity_node", "description")

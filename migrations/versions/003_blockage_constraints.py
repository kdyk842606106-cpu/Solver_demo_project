"""Add solve_request.blockage_constraints

Revision ID: 003_blockage_constraints
Revises: 002_v0.2_model_extension
Create Date: 2026-04-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_blockage_constraints'
down_revision: Union[str, None] = '002_v0.2_model_extension'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column('solve_request', 'blockage_constraints'):
        op.add_column(
            'solve_request',
            sa.Column('blockage_constraints', postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    if _has_column('solve_request', 'blockage_constraints'):
        op.drop_column('solve_request', 'blockage_constraints')

"""Add maintenance intent template

Revision ID: 005_maintenance_intent_template
Revises: 004_layered_activity_state
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "005_maintenance_intent_template"
down_revision: Union[str, None] = "004_layered_activity_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maintenance_intent_template",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_type_id", sa.Integer(), nullable=False),
        sa.Column("scope_activity_node_id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_state_node_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("candidate_activity_scope_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("observed_fact_templates", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("desired_fact_templates", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["machine_type_id"], ["machine_type.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scope_activity_node_id"], ["activity_node.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_type_id", "issue_type", name="uq_maintenance_intent_machine_type_issue"),
    )


def downgrade() -> None:
    op.drop_table("maintenance_intent_template")

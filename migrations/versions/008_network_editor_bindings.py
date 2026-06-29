"""Add network editor binding tables

Revision ID: 008_network_editor_bindings
Revises: 007_atomic_activity_refactor
Create Date: 2026-06-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_network_editor_bindings"
down_revision: Union[str, None] = "007_atomic_activity_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_node_reference",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_node_id", sa.Integer(), nullable=False),
        sa.Column("parent_state_node_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["state_node_id"], ["state_node.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_state_node_id"], ["state_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_node_id", "parent_state_node_id", name="uq_state_node_reference_pair"),
    )
    op.create_table(
        "activity_state_binding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_type_id", sa.Integer(), nullable=False),
        sa.Column("activity_node_id", sa.Integer(), nullable=True),
        sa.Column("atomic_activity_id", sa.Integer(), nullable=True),
        sa.Column("op_rule_id", sa.Integer(), nullable=True),
        sa.Column("state_node_id", sa.Integer(), nullable=False),
        sa.Column("binding_role", sa.String(32), nullable=False),
        sa.Column("binding_type", sa.String(32), nullable=False),
        sa.Column("coverage_policy", sa.String(32), nullable=False, server_default="snapshot"),
        sa.Column("covered_leaf_state_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("coverage_status", sa.String(32), nullable=False, server_default="stale"),
        sa.Column("is_inherited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(activity_node_id IS NOT NULL AND atomic_activity_id IS NULL) "
            "OR (activity_node_id IS NULL AND atomic_activity_id IS NOT NULL)",
            name="ck_activity_state_binding_one_activity_identity",
        ),
        sa.CheckConstraint(
            "binding_role IN ('input', 'output', 'context_input', 'declared_output')",
            name="ck_activity_state_binding_role",
        ),
        sa.CheckConstraint(
            "binding_type IN ('state_package', 'atomic_state')",
            name="ck_activity_state_binding_type",
        ),
        sa.CheckConstraint(
            "coverage_policy IN ('snapshot')",
            name="ck_activity_state_binding_coverage_policy",
        ),
        sa.CheckConstraint(
            "coverage_status IN ('complete', 'partial', 'stale')",
            name="ck_activity_state_binding_coverage_status",
        ),
        sa.ForeignKeyConstraint(["machine_type_id"], ["machine_type.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_node_id"], ["activity_node.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["atomic_activity_id"], ["atomic_activity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["op_rule_id"], ["op_rule.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["state_node_id"], ["state_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_state_binding_machine_type_id",
        "activity_state_binding",
        ["machine_type_id"],
    )
    op.create_index(
        "ix_activity_state_binding_op_rule_id",
        "activity_state_binding",
        ["op_rule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_state_binding_op_rule_id", table_name="activity_state_binding")
    op.drop_index("ix_activity_state_binding_machine_type_id", table_name="activity_state_binding")
    op.drop_table("activity_state_binding")
    op.drop_table("state_node_reference")

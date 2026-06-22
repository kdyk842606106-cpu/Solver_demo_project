"""Add layered activity and state data foundation

Revision ID: 004_layered_activity_state
Revises: 003_blockage_constraints
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004_layered_activity_state"
down_revision: Union[str, None] = "003_blockage_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    op.create_table(
        "activity_node",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_type_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("activity_category", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level IN (1, 2, 3)", name="ck_activity_node_level"),
        sa.ForeignKeyConstraint(["machine_type_id"], ["machine_type.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["activity_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_type_id", "code", name="uq_activity_node_machine_type_code"),
    )

    op.create_table(
        "state_node",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_type_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("feature_key", sa.String(64), nullable=True),
        sa.Column("operator", sa.String(16), nullable=False, server_default="eq"),
        sa.Column("target_value", sa.String(256), nullable=True),
        sa.Column("state_kind", sa.String(32), nullable=False, server_default="aggregate"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level IN (1, 2, 3)", name="ck_state_node_level"),
        sa.ForeignKeyConstraint(["machine_type_id"], ["machine_type.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["state_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_type_id", "code", name="uq_state_node_machine_type_code"),
    )

    op.create_table(
        "scope_guard",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_node_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_node_id"], ["activity_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scope_guard_precond",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope_guard_id", sa.Integer(), nullable=False),
        sa.Column("state_node_id", sa.Integer(), nullable=False),
        sa.Column("operator", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("expected_value", sa.String(256), nullable=True),
        sa.Column("value_list", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["scope_guard_id"], ["scope_guard.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_node_id"], ["state_node.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    if not _has_column("op_rule", "activity_node_id"):
        op.add_column("op_rule", sa.Column("activity_node_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_op_rule_activity_node",
            "op_rule",
            "activity_node",
            ["activity_node_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _has_column("op_rule", "activity_node_id"):
        op.drop_constraint("fk_op_rule_activity_node", "op_rule", type_="foreignkey")
        op.drop_column("op_rule", "activity_node_id")
    op.drop_table("scope_guard_precond")
    op.drop_table("scope_guard")
    op.drop_table("state_node")
    op.drop_table("activity_node")


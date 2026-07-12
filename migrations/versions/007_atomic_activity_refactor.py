"""Add reusable atomic activities

Revision ID: 007_atomic_activity_refactor
Revises: 006_resource_machine_binding
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_atomic_activity_refactor"
down_revision: Union[str, None] = "006_resource_machine_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    op.drop_constraint("ck_state_node_level", "state_node", type_="check")
    op.create_check_constraint("ck_state_node_level_positive", "state_node", "level >= 1")

    op.create_table(
        "atomic_activity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_type_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("activity_category", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["machine_type_id"], ["machine_type.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_type_id", "code", name="uq_atomic_activity_machine_type_code"),
    )
    op.create_table(
        "activity_package_atomic_ref",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_node_id", sa.Integer(), nullable=False),
        sa.Column("atomic_activity_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_node_id"], ["activity_node.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["atomic_activity_id"], ["atomic_activity.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_node_id", "atomic_activity_id", name="uq_activity_package_atomic_ref"),
    )
    if not _has_column("op_rule", "atomic_activity_id"):
        op.add_column("op_rule", sa.Column("atomic_activity_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_op_rule_atomic_activity",
            "op_rule",
            "atomic_activity",
            ["atomic_activity_id"],
            ["id"],
            ondelete="SET NULL",
        )

    conn = op.get_bind()
    level3_nodes = conn.execute(sa.text(
        """
        SELECT id, machine_type_id, parent_id, code, name, activity_category, sort_order, is_active, metadata_json
        FROM activity_node
        WHERE level = 3
        ORDER BY id
        """
    )).mappings().all()
    for node in level3_nodes:
        atomic_id = conn.execute(sa.text(
            """
            INSERT INTO atomic_activity (
                machine_type_id, code, name, activity_category, sort_order, is_active, metadata_json
            )
            VALUES (
                :machine_type_id, :code, :name, :activity_category, :sort_order, :is_active, :metadata_json
            )
            ON CONFLICT (machine_type_id, code) DO UPDATE SET
                name = EXCLUDED.name,
                activity_category = EXCLUDED.activity_category,
                sort_order = EXCLUDED.sort_order,
                is_active = EXCLUDED.is_active,
                metadata_json = EXCLUDED.metadata_json
            RETURNING id
            """
        ), dict(node)).scalar_one()

        if node["parent_id"] is not None:
            conn.execute(sa.text(
                """
                INSERT INTO activity_package_atomic_ref (
                    activity_node_id, atomic_activity_id, sort_order, is_active, metadata_json
                )
                VALUES (:activity_node_id, :atomic_activity_id, :sort_order, :is_active, :metadata_json)
                ON CONFLICT (activity_node_id, atomic_activity_id) DO NOTHING
                """
            ), {
                "activity_node_id": node["parent_id"],
                "atomic_activity_id": atomic_id,
                "sort_order": node["sort_order"],
                "is_active": node["is_active"],
                "metadata_json": node["metadata_json"],
            })

        conn.execute(sa.text(
            """
            UPDATE op_rule
            SET atomic_activity_id = :atomic_activity_id
            WHERE activity_node_id = :activity_node_id
            """
        ), {"atomic_activity_id": atomic_id, "activity_node_id": node["id"]})


def downgrade() -> None:
    op.drop_constraint("ck_state_node_level_positive", "state_node", type_="check")
    op.create_check_constraint("ck_state_node_level", "state_node", "level IN (1, 2, 3)")
    if _has_column("op_rule", "atomic_activity_id"):
        op.drop_constraint("fk_op_rule_atomic_activity", "op_rule", type_="foreignkey")
        op.drop_column("op_rule", "atomic_activity_id")
    op.drop_table("activity_package_atomic_ref")
    op.drop_table("atomic_activity")

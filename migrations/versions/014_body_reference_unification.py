"""Unify canonical state/activity bodies with reusable package references.

Revision ID: 014_body_reference_unification
Revises: 013_plan_adjustment
Create Date: 2026-07-28

Scope Guard tables are intentionally not read or written by this migration.
Their sunset is an application-layer compatibility decision guarded by a
separate zero-data release assertion.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_body_reference_unification"
down_revision: Union[str, None] = "013_plan_adjustment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _foreign_key_name(table_name: str, constrained_column: str) -> str:
    inspector = sa.inspect(op.get_bind())
    matches = [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key.get("constrained_columns") == [constrained_column]
    ]
    if len(matches) != 1 or not matches[0].get("name"):
        raise RuntimeError(
            f"Expected exactly one named foreign key for "
            f"{table_name}.{constrained_column}; found {matches!r}"
        )
    return str(matches[0]["name"])


def _replace_foreign_key(
    table_name: str,
    constrained_column: str,
    referred_table: str,
    *,
    ondelete: str,
    constraint_name: str,
) -> None:
    current_name = _foreign_key_name(table_name, constrained_column)
    op.drop_constraint(current_name, table_name, type_="foreignkey")
    op.create_foreign_key(
        constraint_name,
        table_name,
        referred_table,
        [constrained_column],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Preserve any user-maintained reference metadata.  Only missing membership
    # references are created from the historical atomic-state parent link.
    bind.execute(
        sa.text(
            """
            INSERT INTO state_node_reference (
                state_node_id,
                parent_state_node_id,
                sort_order,
                is_active,
                metadata_json,
                created_at
            )
            SELECT
                child.id,
                child.parent_id,
                child.sort_order,
                child.is_active,
                child.metadata_json,
                child.created_at
            FROM state_node AS child
            WHERE child.state_kind <> 'aggregate'
              AND child.parent_id IS NOT NULL
            ON CONFLICT (state_node_id, parent_state_node_id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE state_node
            SET parent_id = NULL
            WHERE state_kind <> 'aggregate'
              AND parent_id IS NOT NULL
            """
        )
    )

    op.create_check_constraint(
        "ck_state_node_atomic_parent_null",
        "state_node",
        "state_kind = 'aggregate' OR parent_id IS NULL",
    )

    _replace_foreign_key(
        "state_node_reference",
        "state_node_id",
        "state_node",
        ondelete="RESTRICT",
        constraint_name="fk_state_node_reference_state_body",
    )
    _replace_foreign_key(
        "activity_package_atomic_ref",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="RESTRICT",
        constraint_name="fk_activity_package_atomic_ref_activity_body",
    )
    _replace_foreign_key(
        "activity_state_binding",
        "state_node_id",
        "state_node",
        ondelete="RESTRICT",
        constraint_name="fk_activity_state_binding_state_body",
    )
    _replace_foreign_key(
        "activity_state_binding",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="RESTRICT",
        constraint_name="fk_activity_state_binding_atomic_body",
    )
    _replace_foreign_key(
        "op_rule",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="RESTRICT",
        constraint_name="fk_op_rule_atomic_activity_body",
    )


def downgrade() -> None:
    # Body/reference data is intentionally not folded back into parent_id.  A
    # body may now have multiple package references, so choosing one parent
    # would be lossy.  Data rollback requires the pre-migration backup.
    _replace_foreign_key(
        "op_rule",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="SET NULL",
        constraint_name="fk_op_rule_atomic_activity",
    )
    _replace_foreign_key(
        "activity_state_binding",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="CASCADE",
        constraint_name="fk_activity_state_binding_atomic_activity",
    )
    _replace_foreign_key(
        "activity_state_binding",
        "state_node_id",
        "state_node",
        ondelete="CASCADE",
        constraint_name="fk_activity_state_binding_state_node",
    )
    _replace_foreign_key(
        "activity_package_atomic_ref",
        "atomic_activity_id",
        "atomic_activity",
        ondelete="CASCADE",
        constraint_name="fk_activity_package_atomic_ref_atomic_activity",
    )
    _replace_foreign_key(
        "state_node_reference",
        "state_node_id",
        "state_node",
        ondelete="CASCADE",
        constraint_name="fk_state_node_reference_state_node",
    )
    op.drop_constraint(
        "ck_state_node_atomic_parent_null",
        "state_node",
        type_="check",
    )

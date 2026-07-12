"""Bind resources to machines

Revision ID: 006_resource_machine_binding
Revises: 005_maintenance_intent_template
Create Date: 2026-06-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_resource_machine_binding"
down_revision: Union[str, None] = "005_maintenance_intent_template"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resource", sa.Column("machine_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    resource_count = conn.execute(sa.text("SELECT COUNT(*) FROM resource")).scalar_one()
    first_machine_id = conn.execute(sa.text("SELECT id FROM machine ORDER BY id LIMIT 1")).scalar_one_or_none()
    if resource_count and first_machine_id is None:
        raise RuntimeError("Cannot migrate resources: existing resources require at least one machine")
    if first_machine_id is not None:
        conn.execute(sa.text("UPDATE resource SET machine_id = :machine_id WHERE machine_id IS NULL"), {"machine_id": first_machine_id})

    op.alter_column("resource", "machine_id", nullable=False)
    op.create_foreign_key(
        "fk_resource_machine_id_machine",
        "resource",
        "machine",
        ["machine_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("resource_code_key", "resource", type_="unique")
    op.create_unique_constraint("uq_resource_machine_code", "resource", ["machine_id", "code"])


def downgrade() -> None:
    op.drop_constraint("uq_resource_machine_code", "resource", type_="unique")
    op.create_unique_constraint("resource_code_key", "resource", ["code"])
    op.drop_constraint("fk_resource_machine_id_machine", "resource", type_="foreignkey")
    op.drop_column("resource", "machine_id")

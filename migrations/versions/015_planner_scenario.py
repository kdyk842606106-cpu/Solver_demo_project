"""Add Planner shared scenario storage.

Revision ID: 015_planner_scenario
Revises: 014_body_reference_unification
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015_planner_scenario"
down_revision: Union[str, None] = "014_body_reference_unification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planner_scenario",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_activity_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_package_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scenario_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("display_code"),
    )
    op.create_table(
        "planner_run",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_hash", sa.String(length=64), nullable=False),
        sa.Column("engine", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("engine IN ('LEGACY', 'ASTAR', 'GA', 'ALL')", name="ck_planner_run_engine"),
        sa.ForeignKeyConstraint(["scenario_id"], ["planner_scenario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planner_run_scenario_id", "planner_run", ["scenario_id"])
    op.create_index("ix_planner_run_scenario_hash", "planner_run", ["scenario_hash"])


def downgrade() -> None:
    op.drop_index("ix_planner_run_scenario_hash", table_name="planner_run")
    op.drop_index("ix_planner_run_scenario_id", table_name="planner_run")
    op.drop_table("planner_run")
    op.drop_table("planner_scenario")

"""Add work calendar scheduling

Revision ID: 010_work_calendar_scheduling
Revises: 009_activity_descriptions
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010_work_calendar_scheduling"
down_revision: Union[str, None] = "009_activity_descriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_calendar",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("current_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "work_calendar_revision",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_calendar_id", sa.Integer(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("weekly_windows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("date_exceptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["work_calendar_id"], ["work_calendar.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_calendar_id", "revision_no", name="uq_work_calendar_revision_no"),
    )
    op.create_foreign_key(
        "fk_work_calendar_current_revision",
        "work_calendar",
        "work_calendar_revision",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "state_feature_def",
        sa.Column("is_dimension_template", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("state_feature_def", sa.Column("dimension_template_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_state_feature_def_dimension_template",
        "state_feature_def",
        "state_feature_def",
        ["dimension_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill from the canonical metadata written by the Network Editor.  The
    # legacy naming convention is deliberately not used at runtime.
    op.execute(
        """
        UPDATE state_feature_def AS template
        SET is_dimension_template = TRUE
        WHERE EXISTS (
            SELECT 1 FROM state_node AS node
            WHERE node.machine_type_id = template.machine_type_id
              AND node.metadata_json ->> 'dimension_template_key' = template.feature_key
        )
        """
    )
    op.execute(
        """
        UPDATE state_feature_def AS concrete
        SET dimension_template_id = template.id
        FROM state_node AS node, state_feature_def AS template
        WHERE node.machine_type_id = concrete.machine_type_id
          AND node.feature_key = concrete.feature_key
          AND template.machine_type_id = concrete.machine_type_id
          AND template.feature_key = node.metadata_json ->> 'dimension_template_key'
        """
    )

    op.add_column("machine", sa.Column("default_work_calendar_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_machine_default_work_calendar",
        "machine",
        "work_calendar",
        ["default_work_calendar_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "machine_state_dimension_calendar",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_id", sa.Integer(), nullable=False),
        sa.Column("state_dimension_template_id", sa.Integer(), nullable=False),
        sa.Column("work_calendar_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["machine_id"], ["machine.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["state_dimension_template_id"], ["state_feature_def.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["work_calendar_id"], ["work_calendar.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "machine_id", "state_dimension_template_id", name="uq_machine_state_dimension_calendar"
        ),
    )

    op.add_column(
        "solve_request",
        sa.Column("calendar_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("solve_request", sa.Column("schedule_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("solve_request", sa.Column("schedule_timezone", sa.String(length=64), nullable=True))
    op.add_column(
        "solve_request",
        sa.Column("calendar_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("solve_request", "calendar_snapshot")
    op.drop_column("solve_request", "schedule_timezone")
    op.drop_column("solve_request", "schedule_start_at")
    op.drop_column("solve_request", "calendar_enabled")
    op.drop_table("machine_state_dimension_calendar")
    op.drop_constraint("fk_machine_default_work_calendar", "machine", type_="foreignkey")
    op.drop_column("machine", "default_work_calendar_id")
    op.drop_constraint("fk_state_feature_def_dimension_template", "state_feature_def", type_="foreignkey")
    op.drop_column("state_feature_def", "dimension_template_id")
    op.drop_column("state_feature_def", "is_dimension_template")
    op.drop_constraint("fk_work_calendar_current_revision", "work_calendar", type_="foreignkey")
    op.drop_table("work_calendar_revision")
    op.drop_table("work_calendar")

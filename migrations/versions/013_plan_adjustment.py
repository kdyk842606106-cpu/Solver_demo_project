"""Add plan-family baselines and persisted plan adjustments.

Revision ID: 013_plan_adjustment
Revises: 012_scheduling_rules
Create Date: 2026-07-14
"""

from collections import defaultdict
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "013_plan_adjustment"
down_revision: Union[str, None] = "012_scheduling_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _root_id(plan_id: int, parents: dict[int, int | None]) -> int:
    current = plan_id
    visited: set[int] = set()
    while parents.get(current) is not None and current not in visited:
        visited.add(current)
        current = int(parents[current])
    return current


def _backfill_existing_plans() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        """
        SELECT cp.id, cp.parent_plan_id, cp.version, cp.created_at, sr.machine_id
        FROM candidate_plan cp
        JOIN solve_request sr ON sr.id = cp.solve_request_id
        ORDER BY cp.id
        """
    )).mappings().all()
    if not rows:
        return

    parents = {int(row["id"]): row["parent_plan_id"] for row in rows}
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        groups[_root_id(int(row["id"]), parents)].append(dict(row))

    successful = {
        int(value)
        for value in bind.execute(sa.text(
            "SELECT DISTINCT candidate_plan_id FROM schedule_result"
        )).scalars().all()
    }
    children: dict[int, list[int]] = defaultdict(list)
    for plan_id, parent_id in parents.items():
        if parent_id is not None:
            children[int(parent_id)].append(plan_id)

    for root_id, plans in groups.items():
        machine_id = int(plans[0]["machine_id"])
        max_version = max(int(row["version"] or 1) for row in plans)
        family_id = int(bind.execute(sa.text(
            """
            INSERT INTO plan_family(machine_id, baseline_plan_id, next_version)
            VALUES (:machine_id, NULL, :next_version)
            RETURNING id
            """
        ), {"machine_id": machine_id, "next_version": max_version + 1}).scalar_one())

        successful_ids = {int(row["id"]) for row in plans if int(row["id"]) in successful}
        successful_leaves = [
            plan_id for plan_id in successful_ids
            if not any(child in successful_ids for child in children.get(plan_id, []))
        ]
        row_by_id = {int(row["id"]): row for row in plans}
        baseline_id = None
        if successful_leaves:
            baseline_id = max(
                successful_leaves,
                key=lambda plan_id: (
                    int(row_by_id[plan_id]["version"] or 1),
                    row_by_id[plan_id]["created_at"],
                    plan_id,
                ),
            )

        baseline_ancestors: set[int] = set()
        cursor = baseline_id
        while cursor is not None and parents.get(cursor) is not None:
            parent_id = int(parents[cursor])
            baseline_ancestors.add(parent_id)
            cursor = parent_id

        for row in plans:
            plan_id = int(row["id"])
            if plan_id == baseline_id:
                status = "baseline"
            elif plan_id in baseline_ancestors:
                status = "superseded"
            elif plan_id in successful_ids:
                status = "candidate"
            else:
                status = "discarded"
            bind.execute(sa.text(
                """
                UPDATE candidate_plan
                SET plan_family_id = :family_id, status = :status
                WHERE id = :plan_id
                """
            ), {"family_id": family_id, "status": status, "plan_id": plan_id})

        if baseline_id is not None:
            bind.execute(sa.text(
                "UPDATE plan_family SET baseline_plan_id = :baseline_id WHERE id = :family_id"
            ), {"baseline_id": baseline_id, "family_id": family_id})

    step_rows = bind.execute(sa.text(
        """
        SELECT cps.id, cps.candidate_plan_id, cps.op_rule_id, cps.step_order,
               cp.parent_plan_id
        FROM candidate_plan_step cps
        JOIN candidate_plan cp ON cp.id = cps.candidate_plan_id
        ORDER BY cp.version, cp.id, cps.step_order, cps.id
        """
    )).mappings().all()
    lineages_by_plan: dict[int, dict[tuple[int, int], str]] = defaultdict(dict)
    occurrences: dict[tuple[int, int], int] = defaultdict(int)
    for row in step_rows:
        plan_id = int(row["candidate_plan_id"])
        op_rule_id = int(row["op_rule_id"])
        occurrence_key = (plan_id, op_rule_id)
        occurrence = occurrences[occurrence_key]
        occurrences[occurrence_key] += 1
        parent_id = row["parent_plan_id"]
        lineage = None
        if parent_id is not None:
            lineage = lineages_by_plan[int(parent_id)].get((op_rule_id, occurrence))
        lineage = lineage or str(uuid4())
        lineages_by_plan[plan_id][(op_rule_id, occurrence)] = lineage
        bind.execute(sa.text(
            "UPDATE candidate_plan_step SET lineage_key = :lineage WHERE id = :step_id"
        ), {"lineage": lineage, "step_id": int(row["id"])})


def upgrade() -> None:
    op.create_table(
        "plan_family",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("machine_id", sa.Integer(), nullable=False),
        sa.Column("baseline_plan_id", sa.Integer(), nullable=True),
        sa.Column("next_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["machine_id"], ["machine.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("candidate_plan", sa.Column("plan_family_id", sa.Integer(), nullable=True))
    op.add_column(
        "candidate_plan",
        sa.Column("adjustment_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidate_plan_plan_family",
        "candidate_plan",
        "plan_family",
        ["plan_family_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_candidate_plan_plan_family_id", "candidate_plan", ["plan_family_id"])

    op.add_column("candidate_plan_step", sa.Column("lineage_key", sa.String(length=36), nullable=True))
    op.create_index("ix_candidate_plan_step_lineage_key", "candidate_plan_step", ["lineage_key"])

    _backfill_existing_plans()
    op.alter_column("candidate_plan_step", "lineage_key", existing_type=sa.String(length=36), nullable=False)

    op.create_table(
        "plan_adjustment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_family_id", sa.Integer(), nullable=False),
        sa.Column("baseline_plan_id", sa.Integer(), nullable=False),
        sa.Column("candidate_plan_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), server_default="schedule", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "scope_step_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("remove_inherited_constraint_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("effective_constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preview_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('schedule', 'blockage', 'rule_exception')", name="ck_plan_adjustment_kind"),
        sa.CheckConstraint(
            "status IN ('draft', 'previewing', 'preview_ready', 'infeasible', 'confirmed', 'cancelled', 'stale')",
            name="ck_plan_adjustment_status",
        ),
        sa.ForeignKeyConstraint(["baseline_plan_id"], ["candidate_plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_plan_id"], ["candidate_plan.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_family_id"], ["plan_family.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_adjustment_plan_family_id", "plan_adjustment", ["plan_family_id"])
    op.create_index("ix_plan_adjustment_baseline_plan_id", "plan_adjustment", ["baseline_plan_id"])
    op.create_index("ix_plan_adjustment_status", "plan_adjustment", ["status"])


def downgrade() -> None:
    op.drop_table("plan_adjustment")
    op.drop_index("ix_candidate_plan_step_lineage_key", table_name="candidate_plan_step")
    op.drop_column("candidate_plan_step", "lineage_key")
    op.drop_index("ix_candidate_plan_plan_family_id", table_name="candidate_plan")
    op.drop_constraint("fk_candidate_plan_plan_family", "candidate_plan", type_="foreignkey")
    op.drop_column("candidate_plan", "adjustment_snapshot")
    op.drop_column("candidate_plan", "plan_family_id")
    op.drop_table("plan_family")

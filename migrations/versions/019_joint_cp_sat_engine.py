"""Allow the joint CP-SAT engine without changing existing run records.

Revision ID: 019_joint_cp_sat_engine
Revises: 018_planner_completion_states
"""
from alembic import op
import sqlalchemy as sa

revision = "019_joint_cp_sat_engine"
down_revision = "018_planner_completion_states"
branch_labels = None
depends_on = None

OLD = "engine IN ('LEGACY', 'ASTAR', 'GA', 'ALL')"
NEW = "engine IN ('LEGACY', 'ASTAR', 'GA', 'ALL', 'JOINT_CP_SAT', 'ALL_WITH_CP_SAT')"


def upgrade() -> None:
    with op.batch_alter_table("planner_run") as batch:
        batch.drop_constraint("ck_planner_run_engine", type_="check")
        batch.create_check_constraint("ck_planner_run_engine", NEW)


def downgrade() -> None:
    # Do not delete or relabel joint-engine history to make a downgrade pass.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM planner_run WHERE engine IN ('JOINT_CP_SAT', 'ALL_WITH_CP_SAT')")).scalar():
        raise RuntimeError("Cannot downgrade while joint CP-SAT run history exists; preserve/export that history first")
    with op.batch_alter_table("planner_run") as batch:
        batch.drop_constraint("ck_planner_run_engine", type_="check")
        batch.create_check_constraint("ck_planner_run_engine", OLD)

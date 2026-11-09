"""Latest validated incumbent and search telemetry for asynchronous runs."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "021_planner_progress"
down_revision = "020_planner_async_jobs"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("progress_version", "plan_version"):
        op.add_column("planner_run", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    for name in ("progress_json", "live_plan_json"):
        op.add_column("planner_run", sa.Column(name, sa.JSON().with_variant(JSONB(), "postgresql")))


def downgrade():
    for name in ("live_plan_json", "progress_json", "plan_version", "progress_version"):
        op.drop_column("planner_run", name)

"""Durable Planner queue; existing runs and snapshots are preserved."""

from alembic import op
import sqlalchemy as sa

revision = "020_planner_async_jobs"
down_revision = "019_joint_cp_sat_engine"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("planner_run") as batch:
        for name, kind in [
            ("job_status", sa.String(16)),
            ("client_request_id", sa.String(64)),
            ("execution_token", sa.String(64)),
            ("started_at", sa.DateTime(timezone=True)),
            ("lease_until", sa.DateTime(timezone=True)),
            ("error_message", sa.Text()),
        ]:
            batch.add_column(sa.Column(name, kind, nullable=True))
        batch.create_index("ix_planner_run_job_status", ["job_status"])
        batch.create_unique_constraint(
            "uq_planner_run_client_request_id", ["client_request_id"]
        )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text("SELECT COUNT(*) FROM planner_run WHERE job_status IS NOT NULL")
        )
        .scalar()
    ):
        raise RuntimeError("Preserve async run history before downgrading")
    with op.batch_alter_table("planner_run") as batch:
        batch.drop_constraint("uq_planner_run_client_request_id", type_="unique")
        batch.drop_index("ix_planner_run_job_status")
        for name in (
            "job_status",
            "client_request_id",
            "execution_token",
            "started_at",
            "lease_until",
            "error_message",
        ):
            batch.drop_column(name)

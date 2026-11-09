import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture(autouse=True)
def setup_db():
    pass


def test_async_upgrade_preserves_old_snapshots_and_guards_downgrade():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/020_planner_async_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("async_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with sa.create_engine("sqlite:///:memory:").begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE planner_run (id VARCHAR PRIMARY KEY, request_json TEXT, scenario_hash TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO planner_run VALUES ('old','immutable snapshot','original hash')"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            original = connection.execute(
                sa.text(
                    "SELECT request_json, scenario_hash, job_status FROM planner_run"
                )
            ).one()
            assert original == ("immutable snapshot", "original hash", None)
            connection.execute(
                sa.text(
                    "INSERT INTO planner_run (id,job_status,client_request_id) VALUES ('new','QUEUED','request-1')"
                )
            )
            with pytest.raises(RuntimeError, match="Preserve async run history"):
                migration.downgrade()
            assert (
                connection.execute(sa.text("SELECT COUNT(*) FROM planner_run")).scalar()
                == 2
            )

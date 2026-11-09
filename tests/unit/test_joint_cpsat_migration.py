import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture(autouse=True)
def setup_db():
    # This migration test owns its synchronous, in-memory database.
    pass


def test_upgrade_preserves_history_and_downgrade_protects_joint_runs():
    path=Path(__file__).resolve().parents[2]/'migrations/versions/019_joint_cp_sat_engine.py'
    spec=importlib.util.spec_from_file_location('joint_migration',path)
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with sa.create_engine('sqlite:///:memory:').begin() as connection:
        connection.execute(sa.text("CREATE TABLE planner_run (id INTEGER PRIMARY KEY, engine VARCHAR(16), "
            "CONSTRAINT ck_planner_run_engine CHECK (engine IN ('LEGACY','ASTAR','GA','ALL')))"))
        connection.execute(sa.text("INSERT INTO planner_run VALUES (1,'ALL')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.execute(sa.text("INSERT INTO planner_run VALUES (2,'JOINT_CP_SAT')"))
            connection.execute(sa.text("INSERT INTO planner_run VALUES (3,'ALL_WITH_CP_SAT')"))
            assert connection.execute(sa.text('SELECT COUNT(*) FROM planner_run')).scalar()==3
            with pytest.raises(RuntimeError,match='Cannot downgrade'):
                migration.downgrade()
            assert connection.execute(sa.text('SELECT COUNT(*) FROM planner_run')).scalar()==3

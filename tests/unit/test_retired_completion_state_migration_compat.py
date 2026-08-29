import importlib.util
from pathlib import Path


def _migration_module():
    path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "018_retired_planner_completion_states_compat.py"
    )
    spec = importlib.util.spec_from_file_location("planner_migration_018_compat", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_retired_completion_state_revision_remains_a_noop_compatibility_marker():
    migration = _migration_module()

    assert migration.revision == "018_planner_completion_states"
    assert migration.down_revision == "017_planner_runtime_state_targets"
    assert migration.upgrade() is None
    assert migration.downgrade() is None

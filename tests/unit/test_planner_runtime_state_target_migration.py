import importlib.util
from pathlib import Path


def _migration_module():
    path = Path(__file__).parents[2] / "migrations" / "versions" / "017_planner_runtime_state_targets.py"
    spec = importlib.util.spec_from_file_location("planner_migration_017", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_target_migration_recurses_deduplicates_and_is_idempotent():
    migration = _migration_module()
    scenario = {
        "goal_state_ids": ["state:existing"],
        "target_activity_ids": ["activity:a"],
        "target_activity_package_ids": ["package:root", "package:child"],
        "activities": [
            {"id": "activity:a", "output_state_id": "state:a", "is_active": True},
            {"id": "activity:b", "output_state_id": "state:b", "is_active": True},
            {"id": "activity:inactive", "output_state_id": "state:inactive", "is_active": False},
        ],
        "activity_packages": [
            {"id": "package:root", "parent_id": None},
            {"id": "package:child", "parent_id": "package:root"},
        ],
        "activity_package_memberships": [
            {"package_id": "package:root", "activity_id": "activity:a"},
            {"package_id": "package:child", "activity_id": "activity:a"},
            {"package_id": "package:child", "activity_id": "activity:b"},
            {"package_id": "package:child", "activity_id": "activity:inactive"},
        ],
        "provenance": {},
    }

    assert migration.revision == "017_planner_runtime_state_targets"
    assert migration._convert(scenario) is True
    assert scenario["goal_state_ids"] == ["state:a", "state:b", "state:existing"]
    assert scenario["target_activity_ids"] == []
    assert scenario["target_activity_package_ids"] == []
    marker = scenario["provenance"]["runtime_state_target_migration_v1"]
    assert marker["original_goal_state_ids"] == ["state:existing"]
    assert marker["original_target_activity_ids"] == ["activity:a"]
    assert marker["original_target_activity_package_ids"] == ["package:root", "package:child"]
    assert migration._convert(scenario) is False
    assert scenario["goal_state_ids"] == ["state:a", "state:b", "state:existing"]

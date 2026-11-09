import copy
import pytest

from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
from app.services.planner_scenarios import new_scenario, create_activity


def scenario_with_limits(limits):
    s = new_scenario("automatic")
    for i, limit in enumerate(limits):
        create_activity(s, {"name": f"A{i}", "max_instances": limit}, display_number=i + 1)
    return s


@pytest.mark.parametrize("count,seconds", [(0,60),(64,60),(65,120),(256,120),(257,300)])
def test_automatic_budget_tiers_ignore_inactive_definitions(count, seconds):
    s = scenario_with_limits([1] * (count + 1))
    s['activities'][-1]['is_active'] = False
    original = copy.deepcopy(s)
    allocation = automatic_solver_budget(s)
    assert allocation['activity_count'] == count
    assert allocation['time_limit_seconds'] == seconds
    assert s == original


def test_finite_limits_cover_256_activities_without_old_global_cap():
    s = scenario_with_limits([1] * 256)
    s["max_steps"] = 20
    original = copy.deepcopy(s)
    result = automatic_execution_bound(s)
    assert result["value"] == 256
    assert result["heuristic"] is False
    assert s == original


def test_restoration_reserve_is_heuristic_and_scales_with_activity_count():
    s = scenario_with_limits([None] * 30)
    for a in s["activities"]:
        a["delete_effect_state_ids"] = [s["states"][0]["id"]]
    result = automatic_execution_bound(s)
    assert result["value"] >= 120
    assert result["heuristic"] is True
    assert result["unlimited_activity_count"] == 30


def test_inactive_definitions_and_references_do_not_inflate_bound():
    s = scenario_with_limits([2, 3, 100])
    s["activities"][-1]["is_active"] = False
    # Multiple UI references do not create additional executable definitions.
    s["activity_package_memberships"] = [
        {"package_id": "one", "activity_id": s["activities"][0]["id"]},
        {"package_id": "two", "activity_id": s["activities"][0]["id"]},
    ]
    result = automatic_execution_bound(s)
    assert result["value"] == 5
    assert result["activity_count"] == 2


def test_empty_model_can_still_return_zero_step_plan():
    result = automatic_execution_bound(scenario_with_limits([]))
    assert result["value"] == 1  # schema requires positive max_steps, solver permits zero
    assert result["heuristic"] is False

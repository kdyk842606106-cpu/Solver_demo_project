import pytest

from app.services.planner_engine_bridge import planner_available, run_engine
from app.services.planner_scenarios import (
    add_membership,
    create_activity,
    create_package,
    new_scenario,
    rebuild_mirror,
    scenario_hash,
)


def _linear_scenario():
    scenario = new_scenario("三引擎线性场景")
    root = create_package(scenario, {"name": "一级包"}, display_number=1)
    child = create_package(scenario, {"name": "二级包", "parent_id": root["id"]}, display_number=2)
    seed_id = "state:linear:seed"
    scenario["states"].append({"id": seed_id, "name": "开始", "state_kind": "seed"})
    scenario["initial_state_ids"] = [seed_id]
    activity = create_activity(
        scenario,
        {
            "name": "完成任务",
            "duration": 1,
            "preconditions": [{"state_id": seed_id, "relation_role": "transition"}],
        },
        display_number=1,
    )
    add_membership(scenario, child["id"], activity["id"])
    scenario["target_activity_package_ids"] = [root["id"]]
    scenario["default_budget"] = {"time_limit_seconds": 0.5, "transition_limit": 1000, "max_solutions": 3}
    rebuild_mirror(scenario)
    return scenario, activity


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_legacy_astar_and_ga_use_same_snapshot_and_shared_validator():
    scenario, activity = _linear_scenario()
    expected_hash = scenario_hash(scenario)
    results = {
        engine: run_engine(scenario, engine=engine, run_id="bridge-test", seed=7)
        for engine in ("LEGACY", "ASTAR", "GA")
    }

    assert {item["scenario_hash"] for item in results.values()} == {expected_hash}
    for engine, result in results.items():
        assert result["paths"], (engine, result)
        assert result["paths"][0]["validator_status"] == "VALID"
        assert result["paths"][0]["executions"][0]["activity_id"] == activity["id"]


@pytest.mark.asyncio
@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
async def test_all_engine_api_persists_one_immutable_snapshot(client):
    scenario, _ = _linear_scenario()
    imported = await client.post(
        "/api/v1/planner-scenarios/import",
        json={"scenario": scenario, "preserve_ids": True},
    )
    assert imported.status_code == 201, imported.text
    scenario_id = imported.json()["id"]

    response = await client.post(
        "/api/v1/planner-runs",
        json={
            "scenario_id": scenario_id,
            "engine": "ALL",
            "seed": 7,
            "budget": {"time_limit_seconds": 0.5, "transition_limit": 1000, "max_solutions": 3},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "OK", payload
    results = payload["result"]["results"]
    assert set(results) == {"LEGACY", "ASTAR", "GA"}
    assert {item["scenario_hash"] for item in results.values()} == {payload["scenario_hash"]}
    assert all(item["paths"][0]["validator_status"] == "VALID" for item in results.values())

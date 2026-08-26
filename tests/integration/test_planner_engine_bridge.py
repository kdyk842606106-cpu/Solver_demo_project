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
    scenario["goal_state_ids"] = [activity["output_state_id"]]
    scenario["default_budget"] = {"time_limit_seconds": 0.5, "transition_limit": 1000, "max_solutions": 3}
    rebuild_mirror(scenario)
    return scenario, activity


def _module_x_scenario():
    scenario = new_scenario("模块X到料延迟提拉测试")
    power_off = "state:module-x:power-off"
    scenario["states"].append({"id": power_off, "name": "电源已下电", "state_kind": "seed"})
    scenario["initial_state_ids"] = [power_off]
    arrival = "event:module-x-arrival"
    scenario["external_events"] = [{"id": arrival, "name": "模块 X 到料", "time": 45, "add_state_ids": [], "remove_state_ids": []}]

    power_on = create_activity(
        scenario,
        {"name": "上电", "duration": 5, "preconditions": [{"state_id": power_off, "relation_role": "transition"}], "max_instances": 2},
        display_number=1,
    )
    power_down = create_activity(
        scenario,
        {"name": "下电", "duration": 5, "preconditions": [{"state_id": power_on["output_state_id"], "relation_role": "transition"}], "max_instances": 1},
        display_number=2,
    )
    power_down["output_state_id"] = power_off
    scenario["states"] = [item for item in scenario["states"] if item.get("source_activity_id") != power_down["id"]]
    installed = create_activity(
        scenario,
        {"name": "安装模块 X", "duration": 10, "preconditions": [{"state_id": power_off, "relation_role": "required"}], "event_reqs": [arrival], "max_instances": 1},
        display_number=3,
    )
    tested_a = create_activity(
        scenario,
        {"name": "功能 A 调测", "duration": 30, "preconditions": [{"state_id": power_on["output_state_id"], "relation_role": "required"}], "max_instances": 1},
        display_number=4,
    )
    tested_b = create_activity(
        scenario,
        {
            "name": "功能 B 调测",
            "duration": 30,
            "preconditions": [
                {"state_id": power_on["output_state_id"], "relation_role": "required"},
                {"state_id": installed["output_state_id"], "relation_role": "required"},
            ],
            "max_instances": 1,
        },
        display_number=5,
    )
    scenario["goal_state_ids"] = [
        power_on["output_state_id"], installed["output_state_id"], tested_a["output_state_id"], tested_b["output_state_id"],
    ]
    scenario["default_budget"] = {"time_limit_seconds": 10, "transition_limit": 20000, "max_solutions": 20}
    rebuild_mirror(scenario)
    return scenario


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


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_module_x_astar_pulls_test_a_before_arrival_and_finishes_at_90():
    scenario = _module_x_scenario()
    result = run_engine(
        scenario,
        engine="ASTAR",
        run_id="module-x-runtime-state-test",
        seed=23,
        budget_override={"time_limit_seconds": 10, "transition_limit": 20000, "max_solutions": 20},
    )

    assert result["paths"], result
    path = result["paths"][0]
    assert path["validator_status"] == "VALID"
    assert path["metrics"]["makespan"] == 90
    schedule = {item["activity_name"]: (item["start_time"], item["end_time"]) for item in path["executions"] if item["activity_name"] != "上电"}
    power_on_runs = [(item["start_time"], item["end_time"]) for item in path["executions"] if item["activity_name"] == "上电"]
    assert power_on_runs == [(0, 5), (55, 60)]
    assert schedule["功能 A 调测"] == (5, 35)
    assert schedule["下电"] == (35, 40)
    assert schedule["安装模块 X"] == (45, 55)
    assert schedule["功能 B 调测"] == (60, 90)


@pytest.mark.asyncio
@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
async def test_all_engine_api_persists_one_immutable_snapshot(client):
    scenario, _ = _linear_scenario()
    imported = await client.post(
        "/api/v1/planner-scenarios/import",
        json={"scenario": scenario, "preserve_ids": True},
    )
    assert imported.status_code == 201, imported.text
    imported_body = imported.json()
    scenario_id = imported_body["id"]
    imported_scenario = imported_body["scenario"]

    response = await client.post(
        "/api/v1/planner-runs",
        json={
            "scenario_id": scenario_id,
            "expected_revision": imported_body["revision"],
            "current_state_ids": imported_scenario["initial_state_ids"],
            "target_state_ids": imported_scenario["goal_state_ids"],
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
    assert payload["request"]["effective_scenario_snapshot"]["target_activity_ids"] == []
    assert payload["request"]["effective_scenario_snapshot"]["target_activity_package_ids"] == []

    unchanged = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}")).json()
    assert unchanged["revision"] == imported_body["revision"]
    assert unchanged["scenario"]["initial_state_ids"] == imported_scenario["initial_state_ids"]
    assert unchanged["scenario"]["goal_state_ids"] == imported_scenario["goal_state_ids"]

    listed = (await client.get(f"/api/v1/planner-runs?scenario_id={scenario_id}")).json()
    assert "effective_scenario_snapshot" not in listed[0]["request"]
    detailed = (await client.get(f"/api/v1/planner-runs/{payload['id']}")).json()
    assert detailed["request"]["effective_scenario_snapshot"]["initial_state_ids"] == imported_scenario["initial_state_ids"]
    assert detailed["request"]["effective_scenario_snapshot"]["goal_state_ids"] == imported_scenario["goal_state_ids"]

    repeated = await client.post(
        "/api/v1/planner-runs",
        json={
            "scenario_id": scenario_id,
            "expected_revision": imported_body["revision"],
            "current_state_ids": imported_scenario["initial_state_ids"],
            "target_state_ids": imported_scenario["goal_state_ids"],
            "engine": "ASTAR",
            "seed": 7,
            "budget": {"time_limit_seconds": 0.5, "transition_limit": 1000, "max_solutions": 3},
        },
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["scenario_hash"] == payload["scenario_hash"]

    already_satisfied = await client.post(
        "/api/v1/planner-runs",
        json={
            "scenario_id": scenario_id,
            "expected_revision": imported_body["revision"],
            "current_state_ids": imported_scenario["initial_state_ids"],
            "target_state_ids": imported_scenario["initial_state_ids"],
            "engine": "ASTAR",
            "seed": 7,
            "budget": {"time_limit_seconds": 0.5, "transition_limit": 1000, "max_solutions": 3},
        },
    )
    assert already_satisfied.status_code == 201, already_satisfied.text
    assert already_satisfied.json()["scenario_hash"] != payload["scenario_hash"]
    assert already_satisfied.json()["result"]["results"]["ASTAR"]["paths"][0]["validator_status"] == "VALID"

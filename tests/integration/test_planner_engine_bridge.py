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


def _shared_maintenance_scenario(*, technician_capacity: int):
    scenario = new_scenario("共享隔离并行维修")
    scenario["execution_mode"] = "parallel"
    scenario["resources"] = [{
        "id": "resource:technician",
        "name": "维修技师",
        "capacity": technician_capacity,
        "is_active": True,
    }]
    root = create_package(scenario, {"name": "联合维修"}, display_number=1)
    package_a = create_package(scenario, {"name": "维修任务 A", "parent_id": root["id"]}, display_number=2)
    package_b = create_package(scenario, {"name": "维修任务 B", "parent_id": root["id"]}, display_number=3)
    seed_id = "state:maintenance:ready"
    scenario["states"].append({"id": seed_id, "name": "设备可维修", "state_kind": "seed"})
    scenario["initial_state_ids"] = [seed_id]

    isolation = create_activity(
        scenario,
        {
            "name": "停机安全隔离",
            "duration": 10,
            "preconditions": [{"state_id": seed_id, "relation_role": "required"}],
            "resource_reqs": {"resource:technician": 1},
            "max_instances": 1,
        },
        display_number=1,
    )
    task_a = create_activity(
        scenario,
        {
            "name": "维修任务 A 实施",
            "duration": 30,
            "preconditions": [{"state_id": isolation["output_state_id"], "relation_role": "required"}],
            "resource_reqs": {"resource:technician": 1},
            "max_instances": 1,
        },
        display_number=2,
    )
    task_b = create_activity(
        scenario,
        {
            "name": "维修任务 B 实施",
            "duration": 20,
            "preconditions": [{"state_id": isolation["output_state_id"], "relation_role": "required"}],
            "resource_reqs": {"resource:technician": 1},
            "max_instances": 1,
        },
        display_number=3,
    )
    for package_id in (package_a["id"], package_b["id"]):
        add_membership(scenario, package_id, isolation["id"])
    add_membership(scenario, package_a["id"], task_a["id"])
    add_membership(scenario, package_b["id"], task_b["id"])
    scenario["goal_state_ids"] = [
        isolation["output_state_id"],
        task_a["output_state_id"],
        task_b["output_state_id"],
    ]
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


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_module_x_legacy_scheduler_honors_event_not_before():
    scenario = _module_x_scenario()
    result = run_engine(
        scenario,
        engine="LEGACY",
        run_id="module-x-legacy-event-test",
        seed=23,
        budget_override={"time_limit_seconds": 10},
    )

    assert result["paths"], result
    path = result["paths"][0]
    assert path["validator_status"] == "VALID"
    install = next(item for item in path["executions"] if item["activity_name"] == "安装模块 X")
    assert install["start_time"] >= 45


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_legacy_waits_for_event_only_goal_without_creating_activity():
    scenario = new_scenario("纯事件目标")
    seed_id = "state:event:seed"
    goal_id = "state:event:goal"
    scenario["states"].extend([
        {"id": seed_id, "name": "初始", "state_kind": "seed"},
        {"id": goal_id, "name": "到料", "state_kind": "seed"},
    ])
    scenario["initial_state_ids"] = [seed_id]
    scenario["goal_state_ids"] = [goal_id]
    scenario["external_events"] = [{
        "id": "event:arrival",
        "name": "到料事件",
        "time": 15,
        "add_state_ids": [goal_id],
        "remove_state_ids": [],
    }]

    result = run_engine(scenario, engine="LEGACY", run_id="event-only", seed=1)

    assert result["paths"][0]["validator_status"] == "VALID"
    assert result["paths"][0]["executions"] == []
    assert result["paths"][0]["metrics"]["makespan"] == 15
    assert result["stats"]["scheduler"]["status"] == "NOT_REQUIRED"


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_legacy_uses_event_state_availability_window():
    scenario = new_scenario("事件状态窗口")
    scenario["execution_mode"] = "parallel"
    ready_id = "state:event-window:ready"
    scenario["states"].append({"id": ready_id, "name": "允许作业", "state_kind": "seed"})
    scenario["initial_state_ids"] = [ready_id]
    scenario["external_events"] = [
        {"id": "event:close", "name": "窗口关闭", "time": 5, "add_state_ids": [], "remove_state_ids": [ready_id]},
        {"id": "event:reopen", "name": "窗口恢复", "time": 20, "add_state_ids": [ready_id], "remove_state_ids": []},
    ]
    activity = create_activity(
        scenario,
        {
            "name": "窗口内维修",
            "duration": 10,
            "preconditions": [{"state_id": ready_id, "relation_role": "required"}],
            "max_instances": 1,
        },
        display_number=1,
    )
    scenario["goal_state_ids"] = [activity["output_state_id"]]

    result = run_engine(scenario, engine="LEGACY", run_id="event-window", seed=1)

    assert result["paths"][0]["validator_status"] == "VALID"
    execution = result["paths"][0]["executions"][0]
    assert (execution["start_time"], execution["end_time"]) == (20, 30)


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
@pytest.mark.parametrize(
    ("capacity", "expected_makespan", "expected_branch_starts"),
    [
        (1, 60, {10, 40}),
        (2, 40, {10}),
    ],
)
def test_legacy_pathfinder_scheduler_parallelizes_and_resolves_resource_conflicts(
    capacity,
    expected_makespan,
    expected_branch_starts,
):
    scenario = _shared_maintenance_scenario(technician_capacity=capacity)
    result = run_engine(
        scenario,
        engine="LEGACY",
        run_id=f"legacy-shared-capacity-{capacity}",
        seed=7,
        objectives=[{"type": "minimize_makespan", "weight": 1.0}],
    )

    assert result["engine_pipeline"] == "partial_order_pathfinder+cp_sat_scheduler"
    assert result["paths"], result
    path = result["paths"][0]
    assert path["validator_status"] == "VALID"
    assert path["metrics"]["makespan"] == expected_makespan
    assert dict(path["metrics"]["resource_peak"])["resource:technician"] == capacity
    names = [item["activity_name"] for item in path["executions"]]
    assert names.count("停机安全隔离") == 1
    branch_starts = {
        item["start_time"]
        for item in path["executions"]
        if item["activity_name"].startswith("维修任务")
    }
    assert branch_starts == expected_branch_starts
    assert result["stats"]["pathfinder"]["selected_instance_count"] == 3
    assert result["stats"]["scheduler"]["makespan"] == expected_makespan
    assert result["stats"]["scheduler"]["status"] in {"OPTIMAL", "FEASIBLE"}
    assert result["stats"]["scheduler"]["critical_path"]
    assert result["applied_objectives"] == [{"type": "minimize_makespan", "weight": 1.0}]


@pytest.mark.skipif(not planner_available(), reason="external planner checkout is unavailable")
def test_legacy_applies_original_scheduler_package_objectives_without_duplicating_shared_activity():
    scenario = _shared_maintenance_scenario(technician_capacity=2)
    objectives = [
        {"type": "minimize_makespan", "weight": 1.0},
        {"type": "minimize_activity_group_span", "weight": 0.5},
        {"type": "minimize_activity_group_gaps", "weight": 0.25},
        {"type": "minimize_state_group_span", "weight": 0.5},
        {"type": "minimize_state_group_gaps", "weight": 0.25},
    ]

    result = run_engine(
        scenario,
        engine="LEGACY",
        run_id="legacy-package-objectives",
        seed=7,
        objectives=objectives,
    )

    assert result["paths"][0]["validator_status"] == "VALID"
    assert result["applied_objectives"] == objectives
    assert [item["type"] for item in result["stats"]["scheduler"]["objective_terms"]] == [
        item["type"] for item in objectives
    ]
    assert sum(
        execution["activity_name"] == "停机安全隔离"
        for execution in result["paths"][0]["executions"]
    ) == 1


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
    assert payload["request"]["objectives"] == [{"type": "minimize_makespan", "weight": 1.0}]
    assert results["LEGACY"]["engine_pipeline"] == "partial_order_pathfinder+cp_sat_scheduler"
    assert results["LEGACY"]["applied_objectives"] == payload["request"]["objectives"]
    assert results["ASTAR"]["applied_objectives"] == [{"type": "engine_native_path_metrics", "weight": 1.0}]
    assert results["GA"]["applied_objectives"] == [{"type": "engine_native_path_metrics", "weight": 1.0}]
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

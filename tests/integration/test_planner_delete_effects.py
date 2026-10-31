import copy
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.services.planner_engine_bridge import run_engine
from app.services.planner_excel import export_workbook, import_workbook, template_workbook
from app.services.planner_scenarios import (
    PlannerScenarioError, clone_activity, create_activity, delete_activity, graph_projection,
    new_scenario, normalize_import, scenario_hash, update_activity, validate_scenario,
)


def delete_scenario(mode="serial", present=True, restore=False):
    scenario = new_scenario("四类依赖")
    scenario["execution_mode"] = mode
    scenario["states"].append({"id": "state:ready", "name": "停电", "state_kind": "seed"})
    scenario["initial_state_ids"] = ["state:ready"]
    calibrate = create_activity(scenario, {"name": "校准", "duration": 2,
        "preconditions": [{"state_id": "state:ready", "relation_role": "required"}]}, display_number=1)
    if present and not restore:
        scenario["initial_state_ids"].append(calibrate["output_state_id"])
    inspect = create_activity(scenario, {"name": "检查", "duration": 1,
        "preconditions": [{"state_id": calibrate["output_state_id"], "relation_role": "required"}]}, display_number=2)
    adjust = create_activity(scenario, {"name": "调整", "duration": 3,
        "preconditions": [{"state_id": inspect["output_state_id"] if restore else "state:ready", "relation_role": "required"}],
        "delete_effect_state_ids": [calibrate["output_state_id"]]}, display_number=3)
    scenario["goal_state_ids"] = [adjust["output_state_id"], calibrate["output_state_id"]] if restore else ["state:ready"]
    scenario["forbidden_state_ids"] = [] if restore else [calibrate["output_state_id"]]
    scenario["max_steps"] = 8
    return scenario, calibrate, adjust


@pytest.mark.parametrize("engine", ["LEGACY", "ASTAR", "GA"])
@pytest.mark.parametrize("mode", ["serial", "parallel"])
@pytest.mark.parametrize("restore", [False, True])
def test_three_engines_delete_negative_goal_and_restore(engine, mode, restore):
    scenario, calibrate, adjust = delete_scenario(mode, restore=restore)
    before = copy.deepcopy(scenario)
    result = run_engine(scenario, engine=engine, run_id="delete", seed=11,
                        budget_override={"time_limit_seconds": 2, "transition_limit": 5000, "max_solutions": 3})
    assert result["paths"], result
    assert scenario == before
    assert result["scenario_hash"] == scenario_hash(before)
    assert result["input_schema"] == "planner-shared-scenario/v2"
    for path in result["paths"]:
        assert path["validator_status"] == "VALID"
        assert path["validator_version"] == "temporal-event-validator-v5"
        assert (calibrate["output_state_id"] in path["final_state_ids"]) is restore
        if restore:
            ids = [r["activity_id"] for r in path["executions"]]
            assert ids.count(calibrate["id"]) == 2
            assert ids.index(adjust["id"]) < len(ids) - 1


def test_delete_is_not_a_precondition_and_has_no_required_provider():
    scenario, calibrate, adjust = delete_scenario(present=False)
    scenario["goal_state_ids"] = [adjust["output_state_id"]]
    assert validate_scenario(scenario) == []
    for engine in ("LEGACY", "ASTAR", "GA"):
        result = run_engine(scenario, engine=engine, run_id="absent", seed=11,
                            budget_override={"time_limit_seconds": 1, "transition_limit": 2000})
        assert result["paths"], result
        assert [r["activity_id"] for r in result["paths"][0]["executions"]] == [adjust["id"]]


def test_binding_conflicts_reference_protection_clone_and_graph():
    scenario, calibrate, adjust = delete_scenario()
    for state in ("state:ready", adjust["output_state_id"], "missing"):
        before = copy.deepcopy(scenario)
        with pytest.raises(PlannerScenarioError):
            update_activity(scenario, adjust["id"], {"delete_effect_state_ids": [state]})
        assert scenario == before
    with pytest.raises(PlannerScenarioError, match="used"):
        delete_activity(scenario, calibrate["id"])
    cloned = clone_activity(scenario, adjust["id"], display_number=4)
    assert cloned["output_state_id"] != adjust["output_state_id"]
    assert cloned["delete_effect_state_ids"] == adjust["delete_effect_state_ids"]
    edges = [e for e in graph_projection(scenario)["edges"] if e["relation_role"] == "delete_effect"]
    assert len(edges) == 2
    assert all(e["is_precedence"] is False for e in edges)


def test_json_excel_and_old_workbook_compatibility():
    scenario, calibrate, adjust = delete_scenario()
    update_activity(scenario, adjust["id"], {"output_state_name": "设备已调整", "additional_output_state_ids": ["state:ready"]})
    for imported in (normalize_import(scenario, preserve_ids=False), import_workbook(export_workbook(scenario))):
        assert validate_scenario(imported) == []
        assert len(imported["states"]) == len(scenario["states"])
        assert all(s.get("source_activity_id") in {a["id"] for a in imported["activities"]} for s in imported["states"] if s.get("source_activity_id"))
        activities = {a["name"]: a for a in imported["activities"]}
        assert activities["调整"]["delete_effect_state_ids"] == [activities["校准"]["output_state_id"]]
        assert activities["调整"]["output_state_name"] == "设备已调整"
        assert activities["调整"]["additional_output_state_ids"]
        assert imported["forbidden_state_ids"] == [activities["校准"]["output_state_id"]]
        assert set(imported["goal_state_ids"]) <= {s["id"] for s in imported["states"]}
    workbook = load_workbook(BytesIO(template_workbook()))
    for sheet in ("活动破坏效果", "活动附加输出", "状态目标"):
        del workbook[sheet]
    stream = BytesIO()
    workbook.save(stream)
    old = import_workbook(stream.getvalue())
    assert validate_scenario(old) == []
    assert all(not a.get("delete_effect_state_ids") for a in old["activities"])


def test_old_snapshot_not_rewritten_and_hash_includes_deletions():
    scenario, _, adjust = delete_scenario()
    old = copy.deepcopy(scenario)
    old["schema_version"] = 1
    old["forbidden_state_ids"] = []
    old["goal_state_ids"] = [adjust["output_state_id"]]
    for a in old["activities"]:
        a.pop("delete_effect_state_ids", None)
    before = copy.deepcopy(old)
    old_hash = scenario_hash(old)
    for engine in ("LEGACY", "ASTAR", "GA"):
        result = run_engine(old, engine=engine, run_id="v1", seed=11, budget_override={"time_limit_seconds": 1, "transition_limit": 1000})
        assert result["paths"]
        assert result["input_schema"].endswith("/v1")
    assert old == before
    assert scenario_hash(old) == old_hash
    no_delete = copy.deepcopy(scenario)
    no_delete["activities"][-1]["delete_effect_state_ids"] = []
    assert scenario_hash(scenario) != scenario_hash(no_delete)


@pytest.mark.asyncio
async def test_api_delete_binding_and_atomic_draft_validation(client):
    create = (await client.post("/api/v1/planner-scenarios", json={"name": "破坏接口"})).json()
    base = f"/api/v1/planner-scenarios/{create['id']}"
    calibration = (await client.post(base + "/activities", json={"name": "校准"})).json()["activity"]
    valid = calibration["output_state_id"]
    created = await client.post(base + "/activities", json={"name": "调整", "delete_effect_state_ids": [valid, valid]})
    assert created.status_code == 201, created.text
    activity = created.json()["activity"]
    assert activity["delete_effect_state_ids"] == [valid]
    assert (await client.delete(base + f"/activities/{calibration['id']}")).status_code == 409
    current = (await client.get(base)).json()
    invalid = await client.post(base + "/draft-commit", json={"expected_revision": current["revision"], "operations": [
        {"operation": "create_activity", "client_ref": "draft:activity:uncommitted", "payload": {"name": "不应落库"}},
        {"operation": "update_activity", "object_id": activity["id"], "payload": {"delete_effect_state_ids": [activity["output_state_id"]]}},
    ]})
    assert invalid.status_code == 422, invalid.text
    after = (await client.get(base)).json()
    assert after == current
    assert (await client.patch(base + f"/activities/{activity['id']}", json={"delete_effect_state_ids": None})).status_code == 422
    renamed = await client.patch(base + f"/activities/{activity['id']}", json={"name": "重新调整"})
    assert renamed.json()["activity"]["output_state_id"] == activity["output_state_id"]
    assert renamed.json()["activity"]["output_state_name"] == "重新调整完成"


@pytest.mark.asyncio
async def test_draft_delete_references_a_new_automatic_output(client):
    created = (await client.post("/api/v1/planner-scenarios", json={"name": "草稿输出引用"})).json()
    response = await client.post(f"/api/v1/planner-scenarios/{created['id']}/draft-commit", json={
        "expected_revision": created["revision"], "operations": [
            {"operation": "create_activity", "client_ref": "draft:calibrate", "payload": {"name": "校准"}},
            {"operation": "create_activity", "client_ref": "draft:adjust", "payload": {"name": "调整", "delete_effect_state_ids": ["draft:calibrate:output"]}},
        ],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["created_refs"]) == {"draft:calibrate", "draft:adjust"}
    activities = {a["name"]: a for a in body["scenario"]["activities"]}
    assert activities["调整"]["delete_effect_state_ids"] == [activities["校准"]["output_state_id"]]
    assert body["created_output_refs"]["draft:calibrate:output"] == activities["校准"]["output_state_id"]


def test_outdated_engine_is_explicitly_rejected(monkeypatch):
    from app.services.planner_engine_bridge import PlannerEngineUnavailable, _planner_modules
    modules = _planner_modules()
    import planner_experiment.scenario as engine_scenario
    monkeypatch.setattr(engine_scenario, "ENGINE_CAPABILITIES", frozenset())
    with pytest.raises(PlannerEngineUnavailable, match="outdated"):
        _planner_modules()
    assert modules["scenario_from_dict"] is engine_scenario.scenario_from_dict


@pytest.mark.asyncio
async def test_all_engine_api_persists_delete_effects_in_one_shared_snapshot(client):
    scenario, calibrate, _ = delete_scenario("parallel")
    imported = await client.post("/api/v1/planner-scenarios/import", json={"scenario": scenario, "preserve_ids": True})
    assert imported.status_code == 201, imported.text
    source = imported.json()
    response = await client.post("/api/v1/planner-runs", json={
        "scenario_id": source["id"], "expected_revision": source["revision"],
        "current_state_ids": source["scenario"]["initial_state_ids"],
        "target_state_ids": source["scenario"]["goal_state_ids"], "engine": "ALL", "seed": 11,
        "budget": {"time_limit_seconds": 1, "transition_limit": 2000, "max_solutions": 3},
    })
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "OK", run
    assert run["result"]["engines_share_mutable_state"] is False
    assert run["request"]["effective_scenario_snapshot"]["activities"][-1]["delete_effect_state_ids"] == [calibrate["output_state_id"]]
    for result in run["result"]["results"].values():
        assert result["scenario_hash"] == run["scenario_hash"]
        assert result["paths"][0]["validator_status"] == "VALID"
        assert calibrate["output_state_id"] not in result["paths"][0]["final_state_ids"]
    after = (await client.get(f"/api/v1/planner-scenarios/{source['id']}")).json()
    assert after == source

import pytest


async def _create(client, path, payload):
    response = await client.post(path, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


@pytest.mark.asyncio
async def test_planner_scenario_activity_package_mirror_and_graph_flow(client):
    created = await _create(client, "/api/v1/planner-scenarios", {"name": "接口场景"})
    scenario_id = created["id"]

    forbidden_id = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/activities",
        json={"id": "activity:user-maintained", "name": "非法", "duration": 1},
    )
    assert forbidden_id.status_code == 422

    seed = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/seed-states",
        {"name": "开始", "initial": True},
    )
    root = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/activity-packages",
        {"name": "一级包"},
    )
    root_package = root["activity_package"]
    child = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/activity-packages",
        {"name": "二级包", "parent_id": root_package["id"]},
    )
    child_package = child["activity_package"]
    activity = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/activities",
        {
            "name": "执行活动",
            "duration": 3,
            "preconditions": [{"state_id": seed["state"]["id"], "relation_role": "transition"}],
        },
    )
    activity = activity["activity"]
    assert activity["id"].startswith("activity:")
    assert activity["display_code"] == "ACT-0001"
    assert activity["output_state_id"].endswith(":output")

    membership = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/activity-packages/{child_package['id']}/members",
        {"activity_id": activity["id"]},
    )
    assert membership["state_membership"]["state_id"] == activity["output_state_id"]

    current = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}")).json()
    deprecated = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}",
        json={"expected_revision": current["revision"], "target_activity_package_ids": [root_package["id"]]},
    )
    assert deprecated.status_code == 422
    assert deprecated.json()["error_message"]["error_code"] == "TARGET_ACTIVITY_DEPRECATED"

    patched = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}",
        json={"expected_revision": current["revision"], "goal_state_ids": [activity["output_state_id"]]},
    )
    assert patched.status_code == 200, patched.text

    validation = await client.post(f"/api/v1/planner-scenarios/{scenario_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["expanded_scenario"]["target_activity_ids"] == []
    assert validation.json()["expanded_scenario"]["goal_state_ids"] == [activity["output_state_id"]]

    graph = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}/graph")).json()
    assert graph["summary"]["state_node_count"] == 0
    assert {item["kind"] for item in graph["nodes"]} == {"activity"}
    assert all(container["id"].startswith("activity-package:") for container in graph["containers"])


@pytest.mark.asyncio
async def test_revision_conflict_and_json_round_trip(client):
    created = await _create(client, "/api/v1/planner-scenarios", {"name": "往返场景"})
    scenario_id = created["id"]
    conflict = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}",
        json={"expected_revision": 99, "name": "冲突"},
    )
    assert conflict.status_code == 409

    exported = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}/export")).json()
    imported = await client.post(
        "/api/v1/planner-scenarios/import",
        json={"scenario": exported["scenario"], "preserve_ids": False},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["id"] != scenario_id


@pytest.mark.asyncio
async def test_external_event_can_be_edited_directly_and_in_a_draft(client):
    created = await _create(client, "/api/v1/planner-scenarios", {"name": "事件编辑场景"})
    scenario_id = created["id"]
    state_a = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/seed-states",
        {"name": "状态 A"},
    )
    state_b = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/seed-states",
        {"name": "状态 B"},
    )
    event = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/external-events",
        {"name": "备件到货", "time": 30, "add_state_ids": [state_a["state"]["id"]]},
    )
    event_id = event["external_event"]["id"]

    patched = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}/external-events/{event_id}",
        json={
            "expected_revision": event["revision"],
            "name": "备件到货（调整）",
            "time": 45,
            "add_state_ids": [state_b["state"]["id"]],
            "remove_state_ids": [state_a["state"]["id"]],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["external_event"] == {
        "id": event_id,
        "name": "备件到货（调整）",
        "time": 45,
        "add_state_ids": [state_b["state"]["id"]],
        "remove_state_ids": [state_a["state"]["id"]],
    }

    drafted = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/draft-commit",
        json={
            "expected_revision": patched.json()["revision"],
            "operations": [
                {
                    "operation": "update_event",
                    "object_id": event_id,
                    "payload": {"name": "备件已到场", "time": 50},
                }
            ],
        },
    )
    assert drafted.status_code == 200, drafted.text
    updated = next(item for item in drafted.json()["scenario"]["external_events"] if item["id"] == event_id)
    assert updated["name"] == "备件已到场"
    assert updated["time"] == 50
    assert updated["add_state_ids"] == [state_b["state"]["id"]]
    assert updated["remove_state_ids"] == [state_a["state"]["id"]]

    missing = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}/external-events/event%3Amissing",
        json={"expected_revision": drafted.json()["revision"], "time": 60},
    )
    assert missing.status_code == 404
    assert missing.json()["error_message"]["error_code"] == "EVENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_runtime_state_selection_returns_stable_validation_errors(client):
    created = await _create(client, "/api/v1/planner-scenarios", {"name": "运行状态校验"})
    scenario_id = created["id"]
    seed = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/seed-states",
        {"name": "设备已准备", "initial": True},
    )
    target = await _create(
        client,
        f"/api/v1/planner-scenarios/{scenario_id}/activities",
        {
            "name": "执行任务",
            "duration": 1,
            "preconditions": [{"state_id": seed["state"]["id"], "relation_role": "required"}],
        },
    )
    current = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}")).json()
    base = {
        "scenario_id": scenario_id,
        "expected_revision": current["revision"],
        "current_state_ids": [seed["state"]["id"]],
        "target_state_ids": [target["activity"]["output_state_id"]],
        "engine": "ASTAR",
        "budget": {"time_limit_seconds": 0.1, "transition_limit": 10, "max_solutions": 1},
    }

    empty_current = await client.post("/api/v1/planner-runs", json={**base, "current_state_ids": []})
    assert empty_current.status_code == 422
    assert empty_current.json()["error_message"]["error_code"] == "CURRENT_STATE_REQUIRED"

    unknown_target = await client.post("/api/v1/planner-runs", json={**base, "target_state_ids": ["state:missing"]})
    assert unknown_target.status_code == 422
    detail = unknown_target.json()["error_message"]
    assert detail["error_code"] == "UNKNOWN_TARGET_STATE"
    assert detail["states"] == [{"id": "state:missing", "name": "state:missing"}]

    conflict = await client.post("/api/v1/planner-runs", json={**base, "expected_revision": current["revision"] - 1})
    assert conflict.status_code == 409
    assert conflict.json()["error_message"]["error_code"] == "SCENARIO_REVISION_CONFLICT"

    unsupported_objective = await client.post(
        "/api/v1/planner-runs",
        json={**base, "objectives": [{"type": "minimize_unknown_metric", "weight": 1}]},
    )
    assert unsupported_objective.status_code == 422
    assert unsupported_objective.json()["error_message"]["error_code"] == "PLANNER_OBJECTIVE_UNSUPPORTED"

    invalid_weight = await client.post(
        "/api/v1/planner-runs",
        json={**base, "objectives": [{"type": "minimize_makespan", "weight": 0}]},
    )
    assert invalid_weight.status_code == 422
    assert invalid_weight.json()["error_message"]["error_code"] == "PLANNER_OBJECTIVE_WEIGHT_INVALID"

    deprecated = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/activities",
        json={"name": "旧目标活动", "duration": 1, "is_target": True},
    )
    assert deprecated.status_code == 422
    assert deprecated.json()["error_message"]["error_code"] == "TARGET_ACTIVITY_DEPRECATED"

    patched = await client.patch(
        f"/api/v1/planner-scenarios/{scenario_id}",
        json={
            "expected_revision": current["revision"],
            "forbidden_state_ids": [target["activity"]["output_state_id"]],
        },
    )
    forbidden_base = {**base, "expected_revision": patched.json()["revision"]}
    forbidden = await client.post("/api/v1/planner-runs", json=forbidden_base)
    assert forbidden.status_code == 422
    forbidden_detail = forbidden.json()["error_message"]
    assert forbidden_detail["error_code"] == "TARGET_STATE_FORBIDDEN"
    assert forbidden_detail["states"][0]["name"] == "执行任务完成"


@pytest.mark.asyncio
async def test_draft_commit_resolves_temporary_refs_and_rolls_back_on_error(client):
    created = await _create(client, "/api/v1/planner-scenarios", {"name": "原子草稿"})
    scenario_id = created["id"]

    failed = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/draft-commit",
        json={
            "expected_revision": 1,
            "operations": [
                {"operation": "create_package", "client_ref": "draft:root", "payload": {"name": "不应保存"}},
                {"operation": "add_membership", "payload": {"package_id": "draft:missing", "activity_id": "draft:also-missing"}},
            ],
        },
    )
    assert failed.status_code == 422
    assert failed.json()["error_message"]["error_code"] == "DRAFT_REF_UNRESOLVED"
    unchanged = (await client.get(f"/api/v1/planner-scenarios/{scenario_id}")).json()
    assert unchanged["revision"] == 1
    assert unchanged["scenario"]["activity_packages"] == []

    committed = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/draft-commit",
        json={
            "expected_revision": 1,
            "operations": [
                {"operation": "create_package", "client_ref": "draft:root", "payload": {"name": "一级包"}},
                {"operation": "create_package", "client_ref": "draft:child", "payload": {"name": "二级包", "parent_id": "draft:root"}},
                {"operation": "create_seed_state", "client_ref": "draft:seed", "payload": {"name": "开始", "initial": True}},
                {"operation": "create_activity", "client_ref": "draft:activity", "payload": {"name": "执行", "duration": 2, "preconditions": [{"state_id": "draft:seed", "relation_role": "transition"}]}},
                {"operation": "add_membership", "client_ref": "draft:membership", "payload": {"package_id": "draft:child", "activity_id": "draft:activity"}},
                {"operation": "update_layout", "payload": {"activity_refs": [{"id": "draft:membership", "x": 48, "y": 72}], "package_containers": []}},
                {"operation": "update_scenario", "payload": {"target_activity_package_ids": ["draft:root"]}},
            ],
        },
    )
    assert committed.status_code == 422
    assert committed.json()["error_message"]["error_code"] == "TARGET_ACTIVITY_DEPRECATED"

    committed = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/draft-commit",
        json={
            "expected_revision": 1,
            "operations": [
                {"operation": "create_package", "client_ref": "draft:root", "payload": {"name": "一级包"}},
                {"operation": "create_package", "client_ref": "draft:child", "payload": {"name": "二级包", "parent_id": "draft:root"}},
                {"operation": "create_seed_state", "client_ref": "draft:seed", "payload": {"name": "开始", "initial": True}},
                {"operation": "create_activity", "client_ref": "draft:activity", "payload": {"name": "执行", "duration": 2, "preconditions": [{"state_id": "draft:seed", "relation_role": "transition"}]}},
                {"operation": "add_membership", "client_ref": "draft:membership", "payload": {"package_id": "draft:child", "activity_id": "draft:activity"}},
                {"operation": "update_layout", "payload": {"activity_refs": [{"id": "draft:membership", "x": 48, "y": 72}], "package_containers": []}},
            ],
        },
    )
    assert committed.status_code == 200, committed.text
    body = committed.json()
    assert body["revision"] == 2
    assert set(body["created_refs"]) == {"draft:root", "draft:child", "draft:seed", "draft:activity", "draft:membership"}
    assert body["graph"]["nodes"][0]["layout"] == {"x": 48.0, "y": 72.0}
    assert body["graph"]["summary"] == {
        "activity_count": 1,
        "display_node_count": 1,
        "package_count": 2,
        "state_node_count": 0,
    }
    activity_id = body["created_refs"]["draft:activity"]
    updated = await client.post(
        f"/api/v1/planner-scenarios/{scenario_id}/draft-commit",
        json={
            "expected_revision": 2,
            "operations": [
                {
                    "operation": "update_activity",
                    "object_id": activity_id,
                    "payload": {"name": "执行（已编辑）", "duration": 3, "max_instances": 2},
                }
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    updated_activity = next(item for item in updated.json()["scenario"]["activities"] if item["id"] == activity_id)
    assert updated_activity["name"] == "执行（已编辑）"
    assert updated_activity["duration"] == 3
    assert updated_activity["max_instances"] == 2
    validation = await client.post(f"/api/v1/planner-scenarios/{scenario_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

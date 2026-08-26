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
    validation = await client.post(f"/api/v1/planner-scenarios/{scenario_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

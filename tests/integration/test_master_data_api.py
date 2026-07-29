"""
Integration tests for master-data CRUD APIs.

Focus: verify that user-managed data can be written through the API and then
consumed by the existing /solve pipeline without seed SQL.
"""

import pytest
from sqlalchemy import select

from app.db.models import (
    ActivityNode,
    ActivityPackageAtomicRef,
    ActivityStateBinding,
    AtomicActivity,
    FeatureDefinition,
    ScopeGuard,
    ScopeGuardPrecond,
    StateFeatureDef,
    StateNode,
    StateNodeReference,
)


@pytest.mark.asyncio
async def test_master_data_to_solve_flow(client):
    # 1. Machine type
    resp = await client.post("/api/v1/machine-types", json={
        "code": "CNC_LATHE",
        "name": "CNC Lathe",
        "description": "Main machine type",
    })
    assert resp.status_code == 201
    machine_type_id = resp.json()["id"]

    # 2. Feature definitions
    feature_defs = [
        {
            "feature_key": "temperature_level",
            "feature_name": "Temperature",
            "value_type": "enum",
            "allowed_values": ["cold", "hot"],
        },
        {
            "feature_key": "clean_level",
            "feature_name": "Cleanliness",
            "value_type": "enum",
            "allowed_values": ["dirty", "clean"],
        },
        {
            "feature_key": "calibration",
            "feature_name": "Calibration",
            "value_type": "enum",
            "allowed_values": ["off", "on"],
        },
    ]
    for item in feature_defs:
        feature_resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={"machine_type_id": machine_type_id, **item},
        )
        assert feature_resp.status_code == 201

    # 3. Machine instance
    resp = await client.post("/api/v1/machines", json={
        "machine_type_id": machine_type_id,
        "code": "M-001",
        "name": "Main CNC",
        "location": "Workshop A",
    })
    assert resp.status_code == 201
    machine_id = resp.json()["id"]

    # 4. Resources
    resources = [
        {
            "code": "TECH-01",
            "name": "Tech Alice",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
        {
            "code": "TECH-02",
            "name": "Tech Bob",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
        {
            "code": "CLEAN-01",
            "name": "Cleaner",
            "resource_type": "CLEANER",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
    ]
    for item in resources:
        resource_resp = await client.post("/api/v1/resources", json={**item, "machine_id": machine_id})
        assert resource_resp.status_code == 201

    # 5. Operation rules
    op_rules = [
        {
            "code": "OP_WARMUP",
            "name": "Warm Up",
            "duration_min": 30,
            "description": "Warm machine to hot state",
            "is_active": True,
            "preconditions": [
                {"feature_key": "temperature_level", "operator": "eq", "feature_value": "cold"},
            ],
            "effects": [
                {"feature_key": "temperature_level", "new_value": "hot"},
            ],
            "resource_reqs": [
                {"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True},
            ],
        },
        {
            "code": "OP_CLEANING",
            "name": "Cleaning",
            "duration_min": 20,
            "description": "Clean machine",
            "is_active": True,
            "preconditions": [
                {"feature_key": "clean_level", "operator": "eq", "feature_value": "dirty"},
            ],
            "effects": [
                {"feature_key": "clean_level", "new_value": "clean"},
            ],
            "resource_reqs": [
                {"resource_type": "CLEANER", "quantity": 1, "is_required": True},
            ],
        },
        {
            "code": "OP_CALIBRATE",
            "name": "Calibrate",
            "duration_min": 15,
            "description": "Calibrate machine",
            "is_active": True,
            "preconditions": [
                {"feature_key": "temperature_level", "operator": "eq", "feature_value": "hot"},
                {"feature_key": "calibration", "operator": "eq", "feature_value": "off"},
            ],
            "effects": [
                {"feature_key": "calibration", "new_value": "on"},
            ],
            "resource_reqs": [
                {"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True},
            ],
        },
    ]
    for item in op_rules:
        rule_resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/op-rules",
            json={"machine_type_id": machine_type_id, **item},
        )
        assert rule_resp.status_code == 201

    # 6. States
    current_resp = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "current",
        "label": "Cold Dirty Uncalibrated",
        "features": {
            "temperature_level": "cold",
            "clean_level": "dirty",
            "calibration": "off",
        },
    })
    assert current_resp.status_code == 201
    current_state_id = current_resp.json()["state_id"]

    target_resp = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Hot Clean Calibrated",
        "features": {
            "temperature_level": "hot",
            "clean_level": "clean",
            "calibration": "on",
        },
    })
    assert target_resp.status_code == 201
    target_state_id = target_resp.json()["state_id"]

    # 7. Use query API to confirm states are visible to frontend
    list_resp = await client.get(f"/api/v1/machines/{machine_id}/states")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["states"]) == 2

    # 8. Solve using user-managed data
    solve_resp = await client.post("/api/v1/solve", json={
        "machine_id": machine_id,
        "current_state_id": current_state_id,
        "target_state_id": target_state_id,
        "objective": "minimize_makespan",
    })
    assert solve_resp.status_code == 200

    solve_data = solve_resp.json()
    assert solve_data["status"] == "done"
    assert solve_data["schedule"]["makespan"] == 45
    assert len(solve_data["schedule"]["tasks"]) == 3


async def _post_json(client, url: str, payload: dict, expected_status: int = 201) -> dict:
    response = await client.post(url, json=payload)
    assert response.status_code == expected_status, response.text
    return response.json()


async def _seed_network_editor_graph(client) -> dict:
    machine_type = await _post_json(
        client,
        "/api/v1/machine-types",
        {
            "code": "NET_EDITOR_DB",
            "name": "Network Editor DB",
            "description": "Network editor integration fixture",
        },
    )
    machine_type_id = machine_type["id"]
    for feature_key in ("ready_flag", "done_flag", "review_flag"):
        await _post_json(
            client,
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            {
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": ["false", "true"],
            },
        )

    root_state = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "PKG_ROOT",
            "name": "Root package",
            "feature_key": None,
            "operator": "eq",
            "target_value": None,
            "state_kind": "aggregate",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "keep": "state-root",
                "_network_editor_layout": {"x": 80, "y": 80},
                "_network_editor_container": {"width": 360, "height": 220},
            },
        },
    )
    ready_state = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_READY",
            "name": "Ready leaf",
            "feature_key": "ready_flag",
            "operator": "eq",
            "target_value": "true",
            "state_kind": "atomic",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 130, "y": 170}},
        },
    )
    await _post_json(
        client,
        f"/api/v1/state-nodes/{ready_state['id']}/references",
        {
            "parent_state_node_id": root_state["id"],
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 130, "y": 170}},
        },
    )
    done_state = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_DONE",
            "name": "Done leaf",
            "feature_key": "done_flag",
            "operator": "eq",
            "target_value": "true",
            "state_kind": "atomic",
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 130, "y": 260}},
        },
    )
    await _post_json(
        client,
        f"/api/v1/state-nodes/{done_state['id']}/references",
        {
            "parent_state_node_id": root_state["id"],
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 130, "y": 260}},
        },
    )
    reuse_parent = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "PKG_REUSE_PARENT",
            "name": "Reuse parent",
            "feature_key": None,
            "operator": "eq",
            "target_value": None,
            "state_kind": "aggregate",
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 80, "y": 420}},
        },
    )
    state_ref = await _post_json(
        client,
        f"/api/v1/state-nodes/{ready_state['id']}/references",
        {
            "parent_state_node_id": reuse_parent["id"],
            "sort_order": 30,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 160, "y": 500}},
        },
    )

    activity_root = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "ACT_ROOT",
            "name": "Activity root",
            "description": None,
            "activity_category": "normal",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 520, "y": 80}},
        },
    )
    activity_package = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        {
            "machine_type_id": machine_type_id,
            "parent_id": activity_root["id"],
            "level": 2,
            "code": "ACT_PACKAGE",
            "name": "Activity package",
            "description": None,
            "activity_category": "normal",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "_network_editor_layout": {"x": 560, "y": 170},
                "_network_editor_container": {"width": 360, "height": 220},
            },
        },
    )
    atomic = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/atomic-activities",
        {
            "machine_type_id": machine_type_id,
            "code": "AA_FINISH",
            "name": "Finish atomic",
            "description": None,
            "activity_category": "normal",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "library_note": "base",
                "_network_editor_layout": {"x": 900, "y": 900},
            },
        },
    )
    atomic_ref = await _post_json(
        client,
        f"/api/v1/activity-nodes/{activity_package['id']}/atomic-activity-refs",
        {
            "atomic_activity_id": atomic["id"],
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "ref_note": "package-instance",
                "_network_editor_layout": {"x": 620, "y": 260},
            },
        },
    )
    op_rule = await _post_json(
        client,
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        {
            "machine_type_id": machine_type_id,
            "activity_node_id": None,
            "atomic_activity_id": atomic["id"],
            "code": "RULE_FINISH",
            "name": "Finish rule",
            "duration_min": 30,
            "description": None,
            "is_active": True,
            "is_repair": False,
            "preconditions": [
                {"feature_key": "ready_flag", "operator": "eq", "feature_value": "true"},
            ],
            "effects": [
                {"feature_key": "done_flag", "new_value": "true"},
            ],
            "resource_reqs": [],
        },
    )
    await _post_json(
        client,
        "/api/v1/activity-state-bindings",
        {
            "machine_type_id": machine_type_id,
            "atomic_activity_id": atomic["id"],
            "activity_node_id": None,
            "op_rule_id": op_rule["id"],
            "state_node_id": ready_state["id"],
            "binding_role": "input",
            "covered_leaf_state_ids": [ready_state["id"]],
            "is_inherited": False,
            "is_active": True,
            "metadata_json": {"binding_note": "input"},
        },
    )
    await _post_json(
        client,
        "/api/v1/activity-state-bindings",
        {
            "machine_type_id": machine_type_id,
            "atomic_activity_id": atomic["id"],
            "activity_node_id": None,
            "op_rule_id": op_rule["id"],
            "state_node_id": done_state["id"],
            "binding_role": "output",
            "covered_leaf_state_ids": [done_state["id"]],
            "is_inherited": False,
            "is_active": True,
            "metadata_json": {"binding_note": "output"},
        },
    )

    return {
        "machine_type_id": machine_type_id,
        "root_state_id": root_state["id"],
        "ready_state_id": ready_state["id"],
        "done_state_id": done_state["id"],
        "reuse_parent_id": reuse_parent["id"],
        "state_ref_id": state_ref["id"],
        "activity_root_id": activity_root["id"],
        "activity_package_id": activity_package["id"],
        "atomic_id": atomic["id"],
        "atomic_ref_id": atomic_ref["id"],
        "op_rule_id": op_rule["id"],
    }


@pytest.mark.asyncio
async def test_activity_state_binding_rejects_activity_package_targets(client):
    ids = await _seed_network_editor_graph(client)

    response = await client.post(
        "/api/v1/activity-state-bindings",
        json={
            "machine_type_id": ids["machine_type_id"],
            "atomic_activity_id": None,
            "activity_node_id": ids["activity_package_id"],
            "op_rule_id": None,
            "state_node_id": ids["ready_state_id"],
            "binding_role": "context_input",
            "covered_leaf_state_ids": [ids["ready_state_id"]],
            "is_inherited": False,
            "is_active": True,
            "metadata_json": {},
        },
    )

    assert response.status_code == 410
    assert response.json()["error_message"]["error_code"] == "ACTIVITY_PACKAGE_BINDING_SUNSET"


async def _load_network_graph(client, machine_type_id: int, **overrides) -> dict:
    payload = {
        "state_root_ids": [],
        "activity_scope_node_ids": [],
        "view_mode": "implementation",
        "include_inactive": True,
        "state_depth": 0,
        "activity_depth": 0,
        **overrides,
    }
    response = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/network-editor/graph",
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_network_editor_loads_existing_graph_from_database(client):
    ids = await _seed_network_editor_graph(client)

    graph = await _load_network_graph(client, ids["machine_type_id"])
    assert graph["view_mode"] == "state_transition"
    assert graph["diagnostics"][0]["code"] == "LEGACY_VIEW_MODE_NORMALIZED"

    state_ref_graph_id = f"state_node:{ids['ready_state_id']}:ref:{ids['state_ref_id']}"
    state_ref_node = next(node for node in graph["state_nodes"] if node["id"] == state_ref_graph_id)
    assert state_ref_node["reference_id"] == ids["state_ref_id"]
    assert state_ref_node["parent_id"] == ids["reuse_parent_id"]
    assert state_ref_node["metadata_json"]["_network_editor_layout"] == {"x": 160, "y": 500}
    ready_reference_instances = [
        node
        for node in graph["state_nodes"]
        if node["state_node_id"] == ids["ready_state_id"]
        and node["reference_id"] is not None
    ]
    assert len(ready_reference_instances) == 2
    assert {node["parent_id"] for node in ready_reference_instances} == {
        ids["root_state_id"],
        ids["reuse_parent_id"],
    }

    atomic_node = next(
        node for node in graph["activity_nodes"]
        if node["canonical_id"] == f"atomic_activity:{ids['atomic_id']}"
    )
    assert atomic_node["reference_id"] == ids["atomic_ref_id"]
    assert atomic_node["reference_ids"] == [ids["atomic_ref_id"]]
    assert atomic_node["parent_graph_id"] == f"activity_node:{ids['activity_package_id']}"
    assert atomic_node["metadata_json"]["_network_editor_layout"] == {"x": 620, "y": 260}
    assert atomic_node["metadata_json"]["ref_note"] == "package-instance"
    assert atomic_node["atomic_metadata_json"]["library_note"] == "base"

    precheck_response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/solver-precheck",
        json={
            "state_root_ids": [],
            "activity_scope_node_ids": [ids["activity_root_id"]],
            "view_mode": "solver_ready",
            "include_inactive": True,
            "state_depth": 0,
            "activity_depth": 0,
        },
    )
    assert precheck_response.status_code == 200, precheck_response.text
    precheck = precheck_response.json()
    blocking_codes = {issue["code"] for issue in precheck["blocking_issues"]}
    assert blocking_codes.isdisjoint(
        {
            "EXECUTABLE_MISSING_INPUT",
            "EXECUTABLE_MISSING_OUTPUT",
            "EXECUTABLE_MISSING_RULE",
        }
    )
    assert blocking_codes == {"BROKEN_CHAIN"}
    assert precheck["summary"]["executable_activity_count"] == 1
    assert precheck["summary"]["candidate_activity_count"] == 1
    assert precheck["effective_model_version"].startswith("sha256:")
    assert precheck["solve_request_template"]["body"]["atomic_activity_scope_ids"] == [
        ids["atomic_id"]
    ]
    assert "activity_scope_node_ids" not in precheck["solve_request_template"]["body"]

    impact_response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/impact",
        json={
            "state_root_ids": [],
            "activity_scope_node_ids": [],
            "view_mode": "state_transition",
            "include_inactive": True,
            "state_depth": 0,
            "activity_depth": 0,
            "activity_graph_id": atomic_node["id"],
        },
    )
    assert impact_response.status_code == 200, impact_response.text
    impact = impact_response.json()
    assert impact["owner_activity_packages"][0]["id"] == (
        f"activity_node:{ids['activity_package_id']}"
    )
    assert {item["binding_role"] for item in impact["bindings"]} == {"input", "output"}

    edge_pairs = {(edge["source_id"], edge["target_id"], edge["binding_role"]) for edge in graph["edges"]}
    assert (f"state_node:{ids['ready_state_id']}", atomic_node["id"], "input") in edge_pairs
    assert (atomic_node["id"], f"state_node:{ids['done_state_id']}", "output") in edge_pairs
    assert graph["view_mode"] == "state_transition"
    assert graph["revision"]


@pytest.mark.asyncio
async def test_network_editor_projects_each_activity_reference_as_an_independent_instance(client):
    ids = await _seed_network_editor_graph(client)
    second_package = await _post_json(
        client,
        f"/api/v1/machine-types/{ids['machine_type_id']}/activity-nodes",
        {
            "machine_type_id": ids["machine_type_id"],
            "parent_id": ids["activity_root_id"],
            "level": 2,
            "code": "ACT_PACKAGE_REUSE",
            "name": "Activity package reuse",
            "description": None,
            "activity_category": "normal",
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {"_network_editor_layout": {"x": 840, "y": 170}},
        },
    )
    second_ref = await _post_json(
        client,
        f"/api/v1/activity-nodes/{second_package['id']}/atomic-activity-refs",
        {
            "atomic_activity_id": ids["atomic_id"],
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {
                "ref_note": "second-instance",
                "_network_editor_layout": {"x": 880, "y": 300},
            },
        },
    )

    graph = await _load_network_graph(
        client,
        ids["machine_type_id"],
        activity_scope_node_ids=[ids["activity_root_id"]],
        activity_depth=0,
    )
    instances = [
        node
        for node in graph["activity_nodes"]
        if node["canonical_id"] == f"atomic_activity:{ids['atomic_id']}"
    ]

    assert {node["id"] for node in instances} == {
        f"atomic_activity:{ids['atomic_id']}:ref:{ids['atomic_ref_id']}",
        f"atomic_activity:{ids['atomic_id']}:ref:{second_ref['id']}",
    }
    assert {node["reference_id"] for node in instances} == {
        ids["atomic_ref_id"],
        second_ref["id"],
    }
    assert {
        tuple(sorted(node["metadata_json"]["_network_editor_layout"].items()))
        for node in instances
    } == {
        (("x", 620), ("y", 260)),
        (("x", 880), ("y", 300)),
    }
    assert all(node["is_reference_instance"] for node in instances)
    assert {
        edge["source_id"]
        for edge in graph["edges"]
        if edge["binding_role"] == "output"
    } >= {node["id"] for node in instances}


@pytest.mark.asyncio
async def test_body_reference_endpoints_protect_identity_and_sunset_scope_guard(client):
    ids = await _seed_network_editor_graph(client)

    delete_body = await client.delete(f"/api/v1/atomic-activities/{ids['atomic_id']}")
    assert delete_body.status_code == 409
    assert delete_body.json()["error_message"]["error_code"] == "BODY_IN_USE"
    assert delete_body.json()["error_message"]["dependencies"]["package_references"] == 1

    move_ref = await client.put(
        f"/api/v1/activity-package-atomic-refs/{ids['atomic_ref_id']}",
        json={
            "atomic_activity_id": ids["atomic_id"] + 999,
            "sort_order": 1,
            "is_active": True,
            "metadata_json": None,
        },
    )
    assert move_ref.status_code == 409
    assert move_ref.json()["error_message"]["error_code"] == "RELATION_ENDPOINT_IMMUTABLE"

    create_guard = await client.post(
        f"/api/v1/activity-nodes/{ids['activity_package_id']}/scope-guards",
        json={
            "activity_node_id": ids["activity_package_id"],
            "name": "retired guard",
            "description": None,
            "is_active": True,
            "metadata_json": None,
            "preconditions": [
                {
                    "state_node_id": ids["ready_state_id"],
                    "operator": "completed",
                    "expected_value": None,
                    "value_list": None,
                }
            ],
        },
    )
    assert create_guard.status_code == 410
    assert create_guard.json()["error_message"]["error_code"] == "SCOPE_GUARD_SUNSET"

    legacy_guard_list = await client.get(
        f"/api/v1/activity-nodes/{ids['activity_package_id']}/scope-guards"
    )
    assert legacy_guard_list.status_code == 410
    audit_guard_list = await client.get(
        f"/api/v1/audit/activity-nodes/{ids['activity_package_id']}/scope-guards"
    )
    assert audit_guard_list.status_code == 200
    assert audit_guard_list.json() == []


@pytest.mark.asyncio
async def test_historical_package_bindings_and_scope_guards_are_audit_only(
    client,
    db_session,
):
    ids = await _seed_network_editor_graph(client)
    historical_binding = ActivityStateBinding(
        machine_type_id=ids["machine_type_id"],
        activity_node_id=ids["activity_package_id"],
        atomic_activity_id=None,
        op_rule_id=None,
        state_node_id=ids["ready_state_id"],
        binding_role="context_input",
        binding_type="atomic_state",
        coverage_policy="snapshot",
        covered_leaf_state_ids=[ids["ready_state_id"]],
        coverage_status="complete",
        is_inherited=True,
        is_active=True,
    )
    guard = ScopeGuard(
        activity_node_id=ids["activity_package_id"],
        name="historical-only",
        is_active=True,
    )
    db_session.add_all([historical_binding, guard])
    await db_session.flush()
    db_session.add(
        ScopeGuardPrecond(
            scope_guard_id=guard.id,
            state_node_id=ids["ready_state_id"],
            operator="completed",
        )
    )
    await db_session.commit()

    graph = await _load_network_graph(client, ids["machine_type_id"])
    assert historical_binding.id not in {item["id"] for item in graph["bindings"]}
    assert historical_binding.id not in {
        item.get("binding_id") for item in graph["edges"]
    }

    expansion_response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/layered-expansion",
        json={
            "target_state_node_ids": [],
            "activity_scope_node_ids": [ids["activity_package_id"]],
            "include_inactive": True,
        },
    )
    assert expansion_response.status_code == 200, expansion_response.text
    expansion = expansion_response.json()
    assert {
        precondition["source_type"]
        for rule in expansion["effective_rules"]
        for precondition in rule["preconditions"]
    } <= {"self_activity_rule"}


@pytest.mark.asyncio
async def test_network_editor_activity_depth_two_hides_nested_atomic_refs(client):
    ids = await _seed_network_editor_graph(client)

    graph = await _load_network_graph(
        client,
        ids["machine_type_id"],
        activity_scope_node_ids=[ids["activity_root_id"]],
        activity_depth=2,
    )

    activity_ids = {node["id"] for node in graph["activity_nodes"]}
    assert activity_ids == {f"atomic_activity:{ids['atomic_id']}:ref:{ids['atomic_ref_id']}"}

    child_graph = await _load_network_graph(
        client,
        ids["machine_type_id"],
        activity_scope_node_ids=[ids["activity_package_id"]],
        activity_depth=2,
    )
    child_activity_ids = {node["id"] for node in child_graph["activity_nodes"]}
    assert child_activity_ids == {f"atomic_activity:{ids['atomic_id']}:ref:{ids['atomic_ref_id']}"}

    expanded_graph = await _load_network_graph(
        client,
        ids["machine_type_id"],
        activity_scope_node_ids=[ids["activity_root_id"]],
        activity_depth=3,
    )
    expanded_atomic = next(
        node for node in expanded_graph["activity_nodes"]
        if node["canonical_id"] == f"atomic_activity:{ids['atomic_id']}"
    )
    assert ids["atomic_ref_id"] in expanded_atomic["reference_ids"]


@pytest.mark.asyncio
async def test_network_editor_commit_writes_back_and_reloads_from_database(client, db_session):
    ids = await _seed_network_editor_graph(client)
    graph = await _load_network_graph(client, ids["machine_type_id"])

    commit_response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": False,
            "allow_warnings": True,
            "validation_payload": {
                "state_root_ids": [],
                "activity_scope_node_ids": [],
                "view_mode": "implementation",
                "include_inactive": True,
                "state_depth": 0,
                "activity_depth": 0,
            },
            "changes": [
                {
                    "client_id": "move-existing-atomic-ref",
                    "entity_type": "activity_package_atomic_ref",
                    "operation": "update",
                    "entity_id": ids["atomic_ref_id"],
                    "payload": {
                        "atomic_activity_id": ids["atomic_id"],
                        "sort_order": 20,
                        "is_active": True,
                        "metadata_json": {
                            "ref_note": "moved",
                            "_network_editor_layout": {"x": 740, "y": 310},
                        },
                    },
                    "label": "move existing ref",
                },
                {
                    "client_id": "draft-state",
                    "entity_type": "state_node",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "parent_id": ids["root_state_id"],
                        "level": 2,
                        "code": "STATE_REVIEW",
                        "name": "Review leaf",
                        "feature_key": "review_flag",
                        "operator": "eq",
                        "target_value": "true",
                        "state_kind": "atomic",
                        "sort_order": 30,
                        "is_active": True,
                        "metadata_json": {
                            "keep": "state",
                            "_network_editor_layout": {"x": 210, "y": 360},
                        },
                    },
                    "label": "create review state",
                },
                {
                    "client_id": "draft-state-reference",
                    "entity_type": "state_node_reference",
                    "operation": "create",
                    "payload": {
                        "state_node_id": {"_draft_ref": "draft-state"},
                        "parent_state_node_id": ids["reuse_parent_id"],
                        "sort_order": 31,
                        "is_active": True,
                        "metadata_json": {
                            "ref_note": "draft-state-reference",
                            "_network_editor_layout": {"x": 180, "y": 560},
                        },
                    },
                    "label": "reference review state",
                },
                {
                    "client_id": "draft-atomic",
                    "entity_type": "atomic_activity",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "package_id": ids["activity_package_id"],
                        "code": "AA_REVIEW",
                        "name": "Review atomic",
                        "description": None,
                        "activity_category": "normal",
                        "sort_order": 30,
                        "is_active": True,
                        "metadata_json": {
                            "library_note": "created-from-editor",
                            "_network_editor_layout": {"x": 990, "y": 990},
                        },
                        "package_ref_metadata_json": {
                            "ref_note": "created-instance",
                            "_network_editor_layout": {"x": 760, "y": 390},
                        },
                    },
                    "label": "create review atomic",
                },
                {
                    "client_id": "draft-binding",
                    "entity_type": "activity_state_binding",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "atomic_activity_id": {"_draft_ref": "draft-atomic"},
                        "activity_node_id": None,
                        "op_rule_id": None,
                        "state_node_id": {"_draft_ref": "draft-state"},
                        "binding_role": "output",
                        "covered_leaf_state_ids": [{"_draft_ref": "draft-state"}],
                        "is_inherited": False,
                        "is_active": True,
                        "metadata_json": {"binding_note": "draft-ref-resolution"},
                    },
                    "label": "bind review output",
                },
            ],
        },
    )
    assert commit_response.status_code == 200, commit_response.text
    data = commit_response.json()
    assert data["applied_change_count"] == 5
    assert data["revision"] and data["revision"] != graph["revision"]

    existing_ref = await db_session.get(ActivityPackageAtomicRef, ids["atomic_ref_id"])
    assert existing_ref.sort_order == 20
    assert existing_ref.metadata_json["_network_editor_layout"] == {"x": 740, "y": 310}

    created_atomic = (
        await db_session.execute(select(AtomicActivity).where(AtomicActivity.code == "AA_REVIEW"))
    ).scalar_one()
    assert created_atomic.metadata_json == {"library_note": "created-from-editor"}
    created_ref = (
        await db_session.execute(
            select(ActivityPackageAtomicRef).where(
                ActivityPackageAtomicRef.atomic_activity_id == created_atomic.id
            )
        )
    ).scalar_one()
    assert created_ref.activity_node_id == ids["activity_package_id"]
    assert created_ref.metadata_json["_network_editor_layout"] == {"x": 760, "y": 390}

    created_state = (
        await db_session.execute(select(StateNode).where(StateNode.code == "STATE_REVIEW"))
    ).scalar_one()
    assert created_state.parent_id is None
    assert created_state.level == 1
    assert created_state.metadata_json == {"keep": "state"}
    created_root_ref = (
        await db_session.execute(
            select(StateNodeReference).where(
                StateNodeReference.state_node_id == created_state.id,
                StateNodeReference.parent_state_node_id == ids["root_state_id"],
            )
        )
    ).scalar_one()
    assert created_root_ref.metadata_json["_network_editor_layout"] == {"x": 210, "y": 360}
    created_state_ref = (
        await db_session.execute(
            select(StateNodeReference).where(
                StateNodeReference.state_node_id == created_state.id,
                StateNodeReference.parent_state_node_id == ids["reuse_parent_id"],
            )
        )
    ).scalar_one()
    assert created_state_ref.sort_order == 31
    assert created_state_ref.metadata_json["_network_editor_layout"] == {"x": 180, "y": 560}
    created_binding = (
        await db_session.execute(
            select(ActivityStateBinding).where(
                ActivityStateBinding.atomic_activity_id == created_atomic.id,
                ActivityStateBinding.state_node_id == created_state.id,
            )
        )
    ).scalar_one()
    assert created_binding.covered_leaf_state_ids == [created_state.id]
    assert created_binding.metadata_json == {"binding_note": "draft-ref-resolution"}

    reloaded = await _load_network_graph(client, ids["machine_type_id"])
    reloaded_atomic = next(
        node for node in reloaded["activity_nodes"]
        if node["atomic_activity_id"] == created_atomic.id
    )
    assert reloaded_atomic["metadata_json"]["_network_editor_layout"] == {"x": 760, "y": 390}
    assert reloaded_atomic["atomic_metadata_json"] == {"library_note": "created-from-editor"}


@pytest.mark.asyncio
async def test_network_editor_commit_adds_atomic_ref_to_new_activity_package(client, db_session):
    ids = await _seed_network_editor_graph(client)
    graph = await _load_network_graph(client, ids["machine_type_id"])

    commit_response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": False,
            "allow_warnings": True,
            "validation_payload": {
                "state_root_ids": [],
                "activity_scope_node_ids": [],
                "view_mode": "implementation",
                "include_inactive": True,
                "state_depth": 0,
                "activity_depth": 0,
            },
            "changes": [
                {
                    "client_id": "draft-parent-activity",
                    "entity_type": "activity_node",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "parent_id": None,
                        "level": 1,
                        "code": "VA_NEW_PARENT",
                        "name": "New parent activity",
                        "description": None,
                        "activity_category": "normal",
                        "sort_order": 90,
                        "is_active": True,
                        "metadata_json": {"_network_editor_layout": {"x": 540, "y": 540}},
                    },
                    "label": "create parent activity",
                },
                {
                    "client_id": "draft-child-package",
                    "entity_type": "activity_node",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "parent_id": {"_draft_ref": "draft-parent-activity"},
                        "level": 2,
                        "code": "VA_NEW_CHILD",
                        "name": "New child activity package",
                        "description": None,
                        "activity_category": "normal",
                        "sort_order": 91,
                        "is_active": True,
                        "metadata_json": {"_network_editor_layout": {"x": 600, "y": 620}},
                    },
                    "label": "create child package",
                },
                {
                    "client_id": "draft-existing-atomic-ref",
                    "entity_type": "activity_package_atomic_ref",
                    "operation": "create",
                    "payload": {
                        "package_id": {"_draft_ref": "draft-child-package"},
                        "atomic_activity_id": ids["atomic_id"],
                        "sort_order": 1,
                        "is_active": True,
                        "metadata_json": {
                            "ref_note": "existing-atomic-on-new-package",
                            "_network_editor_layout": {"x": 680, "y": 700},
                        },
                    },
                    "label": "reference existing atomic activity",
                },
            ],
        },
    )
    assert commit_response.status_code == 200, commit_response.text
    data = commit_response.json()
    assert data["applied_change_count"] == 3

    parent_activity = (
        await db_session.execute(select(ActivityNode).where(ActivityNode.code == "VA_NEW_PARENT"))
    ).scalar_one()
    child_package = (
        await db_session.execute(select(ActivityNode).where(ActivityNode.code == "VA_NEW_CHILD"))
    ).scalar_one()
    assert child_package.parent_id == parent_activity.id
    assert child_package.level == 2

    created_ref = (
        await db_session.execute(
            select(ActivityPackageAtomicRef).where(
                ActivityPackageAtomicRef.activity_node_id == child_package.id,
                ActivityPackageAtomicRef.atomic_activity_id == ids["atomic_id"],
            )
        )
    ).scalar_one()
    assert created_ref.metadata_json["ref_note"] == "existing-atomic-on-new-package"
    assert created_ref.metadata_json["_network_editor_layout"] == {"x": 680, "y": 700}

    reloaded = await _load_network_graph(client, ids["machine_type_id"], activity_scope_node_ids=[parent_activity.id], activity_depth=0)
    referenced_atomic = next(
        node for node in reloaded["activity_nodes"]
        if node.get("reference_id") == created_ref.id
    )
    assert referenced_atomic["atomic_activity_id"] == ids["atomic_id"]
    assert referenced_atomic["parent_graph_id"] == f"activity_node:{child_package.id}"
    assert referenced_atomic["metadata_json"]["_network_editor_layout"] == {"x": 680, "y": 700}


@pytest.mark.asyncio
async def test_network_editor_commit_normalizes_object_id_payloads(client, db_session):
    ids = await _seed_network_editor_graph(client)
    review_state = await _post_json(
        client,
        f"/api/v1/machine-types/{ids['machine_type_id']}/state-nodes",
        {
            "machine_type_id": ids["machine_type_id"],
            "parent_id": None,
            "level": 1,
            "code": "STATE_OBJECT_ID_REVIEW",
            "name": "Object id review",
            "feature_key": "review_flag",
            "operator": "eq",
            "target_value": "true",
            "state_kind": "atomic",
            "sort_order": 80,
            "is_active": True,
            "metadata_json": None,
        },
    )
    graph = await _load_network_graph(client, ids["machine_type_id"])

    response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": False,
            "allow_warnings": True,
            "validation_payload": {
                "state_root_ids": [],
                "activity_scope_node_ids": [],
                "view_mode": "implementation",
                "include_inactive": True,
                "state_depth": 0,
                "activity_depth": 0,
            },
            "changes": [
                {
                    "client_id": "object-id-binding",
                    "entity_type": "activity_state_binding",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "atomic_activity_id": {"atomic_activity_id": ids["atomic_id"]},
                        "activity_node_id": None,
                        "op_rule_id": {"id": ids["op_rule_id"]},
                        "state_node_id": {"state_node_id": f"state_node:{review_state['id']}:ref:999"},
                        "binding_role": "input",
                        "covered_leaf_state_ids": [{"state_node_id": f"state_node:{review_state['id']}"}],
                        "is_inherited": False,
                        "is_active": True,
                        "metadata_json": {"binding_note": "object-id-normalized"},
                    },
                    "label": "object id binding",
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    created_binding = (
        await db_session.execute(
            select(ActivityStateBinding).where(
                ActivityStateBinding.state_node_id == review_state["id"],
                ActivityStateBinding.atomic_activity_id == ids["atomic_id"],
            )
        )
    ).scalar_one()
    assert created_binding.op_rule_id == ids["op_rule_id"]
    assert created_binding.covered_leaf_state_ids == [review_state["id"]]


@pytest.mark.asyncio
async def test_blockage_reason_options_come_from_global_feature_definition(client, db_session):
    db_session.add(
        FeatureDefinition(
            feature_key="blockage_reason",
            value_type="enum",
            allowed_values=["none", "hardware_fault", "material_shortage"],
            description="Configured Strategy B reasons",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/features/blockage-reasons")

    assert response.status_code == 200
    assert response.json() == ["hardware_fault", "material_shortage"]


@pytest.mark.asyncio
async def test_network_editor_commit_rejects_stale_base_revision_before_writing(client, db_session):
    ids = await _seed_network_editor_graph(client)
    graph = await _load_network_graph(client, ids["machine_type_id"])

    await _post_json(
        client,
        f"/api/v1/machine-types/{ids['machine_type_id']}/state-nodes",
        {
            "machine_type_id": ids["machine_type_id"],
            "parent_id": None,
            "level": 1,
            "code": "STATE_EXTERNAL",
            "name": "External change",
            "feature_key": "review_flag",
            "operator": "eq",
            "target_value": "false",
            "state_kind": "atomic",
            "sort_order": 99,
            "is_active": True,
            "metadata_json": None,
        },
    )

    response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": False,
            "allow_warnings": True,
            "validation_payload": {},
            "changes": [
                {
                    "client_id": "stale-update",
                    "entity_type": "state_node",
                    "operation": "update",
                    "entity_id": ids["ready_state_id"],
                    "payload": {
                        "parent_id": ids["root_state_id"],
                        "level": 2,
                        "code": "STATE_READY",
                        "name": "Should not persist",
                        "feature_key": "ready_flag",
                        "operator": "eq",
                        "target_value": "true",
                        "state_kind": "atomic",
                        "sort_order": 10,
                        "is_active": True,
                        "metadata_json": None,
                    },
                    "label": "stale update",
                },
            ],
        },
    )
    assert response.status_code == 409
    error_payload = response.json()["error_message"]
    assert error_payload["base_revision"] == graph["revision"]
    assert error_payload["current_revision"] != graph["revision"]

    ready_state = await db_session.get(StateNode, ids["ready_state_id"])
    assert ready_state.name == "Ready leaf"


@pytest.mark.asyncio
async def test_network_editor_validation_review_rolls_back_unaccepted_changes(client, db_session):
    ids = await _seed_network_editor_graph(client)
    graph = await _load_network_graph(client, ids["machine_type_id"])

    response = await client.post(
        f"/api/v1/machine-types/{ids['machine_type_id']}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": True,
            "allow_warnings": False,
            "validation_payload": {
                "state_root_ids": [ids["root_state_id"]],
                "activity_scope_node_ids": [],
                "view_mode": "implementation",
                "include_inactive": True,
                "state_depth": 0,
                "activity_depth": 0,
            },
            "changes": [
                {
                    "client_id": "duplicate-state",
                    "entity_type": "state_node",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": ids["machine_type_id"],
                        "parent_id": ids["root_state_id"],
                        "level": 2,
                        "code": "STATE_READY_DUP",
                        "name": "Ready leaf",
                        "feature_key": "review_flag",
                        "operator": "eq",
                        "target_value": "true",
                        "state_kind": "atomic",
                        "sort_order": 40,
                        "is_active": True,
                        "metadata_json": {"_network_editor_layout": {"x": 240, "y": 440}},
                    },
                    "label": "duplicate state warning",
                },
            ],
        },
    )
    assert response.status_code == 422
    error_payload = response.json()["error_message"]
    assert error_payload["warning_count"] > 0
    assert any(
        issue["code"] == "DUPLICATE_STATE_NAME"
        for issue in error_payload["validation"]["modeling_issues"]
    )

    duplicate_state = (
        await db_session.execute(select(StateNode).where(StateNode.code == "STATE_READY_DUP"))
    ).scalar_one_or_none()
    assert duplicate_state is None


@pytest.mark.asyncio
async def test_state_node_template_dimension_creates_concrete_feature_def(client, db_session):
    machine_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "TEMPLATE_DIM_MT", "name": "Template Dimension MT"},
    )
    assert machine_resp.status_code == 201
    machine_type_id = machine_resp.json()["id"]

    template_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "module_dim_installed",
            "feature_name": "Module installed",
            "value_type": "enum",
            "allowed_values": ["false", "true"],
        },
    )
    assert template_resp.status_code == 201

    state_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_MODULE_A_INSTALLED",
            "name": "Module A",
            "feature_key": "module_dim_installed__module_a",
            "operator": "eq",
            "target_value": "true",
            "state_kind": "atomic",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "dimension_template_key": "module_dim_installed",
                "state_object_name": "Module A",
            },
        },
    )
    assert state_resp.status_code == 201, state_resp.text

    concrete = (
        await db_session.execute(
            select(StateFeatureDef).where(
                StateFeatureDef.machine_type_id == machine_type_id,
                StateFeatureDef.feature_key == "module_dim_installed__module_a",
            )
        )
    ).scalar_one()
    assert concrete.feature_name == "Module A / Module installed"
    assert concrete.allowed_values == ["false", "true"]
    global_def = await db_session.get(FeatureDefinition, "module_dim_installed__module_a")
    assert global_def is not None
    assert global_def.allowed_values == ["false", "true"]


@pytest.mark.asyncio
async def test_state_node_template_dimension_keeps_chinese_objects_distinct(client):
    machine_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "TEMPLATE_DIM_CN_MT", "name": "Template Dimension CN MT"},
    )
    assert machine_resp.status_code == 201
    machine_type_id = machine_resp.json()["id"]

    template_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "cn_dim_installed",
            "feature_name": "安装状态",
            "value_type": "enum",
            "allowed_values": ["未安装", "已安装"],
        },
    )
    assert template_resp.status_code == 201

    module_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_MODULE_B_INSTALLED",
            "name": "模块B已安装",
            "feature_key": "cn_dim_installed__u6a21_u5757_b",
            "operator": "eq",
            "target_value": "已安装",
            "state_kind": "atomic",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "dimension_template_key": "cn_dim_installed",
                "state_object_name": "模块B",
            },
        },
    )
    assert module_resp.status_code == 201, module_resp.text

    fixture_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_FIXTURE_B_INSTALLED",
            "name": "工装B已安装",
            "feature_key": "cn_dim_installed__u5de5_u88c5_b",
            "operator": "eq",
            "target_value": "已安装",
            "state_kind": "atomic",
            "sort_order": 20,
            "is_active": True,
            "metadata_json": {
                "dimension_template_key": "cn_dim_installed",
                "state_object_name": "工装B",
            },
        },
    )
    assert fixture_resp.status_code == 201, fixture_resp.text

    stale_key_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_BAD_FIXTURE_B_INSTALLED",
            "name": "错误工装B已安装",
            "feature_key": "cn_dim_installed__b",
            "operator": "eq",
            "target_value": "已安装",
            "state_kind": "atomic",
            "sort_order": 30,
            "is_active": True,
            "metadata_json": {
                "dimension_template_key": "cn_dim_installed",
                "state_object_name": "工装B",
            },
        },
    )
    assert stale_key_resp.status_code == 422


@pytest.mark.asyncio
async def test_state_node_template_dimension_rejects_invalid_target(client):
    machine_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "TEMPLATE_DIM_INVALID_MT", "name": "Template Dimension Invalid MT"},
    )
    assert machine_resp.status_code == 201
    machine_type_id = machine_resp.json()["id"]
    template_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "pipe_dim_connected",
            "feature_name": "Pipe connected",
            "value_type": "enum",
            "allowed_values": ["false", "true"],
        },
    )
    assert template_resp.status_code == 201

    state_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "parent_id": None,
            "level": 1,
            "code": "STATE_PIPE_CONNECTED",
            "name": "Pipe A",
            "feature_key": "pipe_dim_connected__pipe_a",
            "operator": "eq",
            "target_value": "done",
            "state_kind": "atomic",
            "sort_order": 10,
            "is_active": True,
            "metadata_json": {
                "dimension_template_key": "pipe_dim_connected",
                "state_object_name": "Pipe A",
            },
        },
    )
    assert state_resp.status_code == 422


@pytest.mark.asyncio
async def test_network_editor_commit_reuses_exact_template_state_as_reference(client, db_session):
    machine_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "TEMPLATE_DIM_REUSE_MT", "name": "Template Dimension Reuse MT"},
    )
    assert machine_resp.status_code == 201
    machine_type_id = machine_resp.json()["id"]
    feature_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "fixture_dim_ready",
            "feature_name": "Fixture ready",
            "value_type": "enum",
            "allowed_values": ["false", "true"],
        },
    )
    assert feature_resp.status_code == 201

    parent_a = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "parent_id": None,
                "level": 1,
                "code": "PKG_A",
                "name": "Package A",
                "feature_key": None,
                "operator": "eq",
                "target_value": None,
                "state_kind": "aggregate",
                "sort_order": 1,
                "is_active": True,
                "metadata_json": None,
            },
        )
    ).json()
    parent_b = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "parent_id": None,
                "level": 1,
                "code": "PKG_B",
                "name": "Package B",
                "feature_key": None,
                "operator": "eq",
                "target_value": None,
                "state_kind": "aggregate",
                "sort_order": 2,
                "is_active": True,
                "metadata_json": None,
            },
        )
    ).json()
    existing = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "parent_id": None,
                "level": 1,
                "code": "STATE_FIXTURE_A_READY",
                "name": "Fixture A",
                "feature_key": "fixture_dim_ready__fixture_a",
                "operator": "eq",
                "target_value": "true",
                "state_kind": "atomic",
                "sort_order": 10,
                "is_active": True,
                "metadata_json": {
                    "dimension_template_key": "fixture_dim_ready",
                    "state_object_name": "Fixture A",
                },
            },
        )
    ).json()
    await _post_json(
        client,
        f"/api/v1/state-nodes/{existing['id']}/references",
        {
            "parent_state_node_id": parent_a["id"],
            "sort_order": 10,
            "is_active": True,
            "metadata_json": None,
        },
    )

    graph = await _load_network_graph(client, machine_type_id)
    response = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/network-editor/commit",
        json={
            "base_revision": graph["revision"],
            "validate_after_apply": False,
            "allow_warnings": True,
            "validation_payload": {
                "state_root_ids": [],
                "activity_scope_node_ids": [],
                "view_mode": "implementation",
                "include_inactive": True,
                "state_depth": 0,
                "activity_depth": 0,
            },
            "changes": [
                {
                    "client_id": "exact-state",
                    "entity_type": "state_node",
                    "operation": "create",
                    "payload": {
                        "machine_type_id": machine_type_id,
                        "parent_id": parent_b["id"],
                        "level": 2,
                        "code": "STATE_FIXTURE_A_READY_DUP",
                        "name": "Fixture A",
                        "feature_key": "fixture_dim_ready__fixture_a",
                        "operator": "eq",
                        "target_value": "true",
                        "state_kind": "atomic",
                        "sort_order": 20,
                        "is_active": True,
                        "metadata_json": {
                            "dimension_template_key": "fixture_dim_ready",
                            "state_object_name": "Fixture A",
                        },
                    },
                    "label": "reuse exact state",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["id"] == existing["id"]

    same_name_states = (
        await db_session.execute(
            select(StateNode).where(
                StateNode.machine_type_id == machine_type_id,
                StateNode.name == "Fixture A",
            )
        )
    ).scalars().all()
    assert len(same_name_states) == 1
    ref = (
        await db_session.execute(
            select(StateNodeReference).where(
                StateNodeReference.state_node_id == existing["id"],
                StateNodeReference.parent_state_node_id == parent_b["id"],
            )
        )
    ).scalar_one()
    assert ref.metadata_json["_network_editor_reuse"]["source"] == "atomic_state_library_create"

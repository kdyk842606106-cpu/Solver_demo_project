"""Integration tests for layered activity/state master-data APIs."""

import pytest


@pytest.mark.asyncio
async def test_layered_nodes_auto_generate_codes_and_preserve_them_on_update(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "Pump Type!", "name": "Pump Type", "description": None},
    )
    assert mt_resp.status_code == 201
    machine_type_id = mt_resp.json()["id"]

    state_pkg_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 1,
            "parent_id": None,
            "name": "Installation Complete",
            "state_kind": "aggregate",
        },
    )
    assert state_pkg_resp.status_code == 201
    state_pkg = state_pkg_resp.json()
    assert state_pkg["code"] == "pump_type_sp_0001"

    second_state_pkg_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 1,
            "parent_id": None,
            "name": "Commissioning Complete",
            "state_kind": "aggregate",
        },
    )
    assert second_state_pkg_resp.status_code == 201
    assert second_state_pkg_resp.json()["code"] == "pump_type_sp_0002"

    state_leaf_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 2,
            "parent_id": state_pkg["id"],
            "name": "Pump Installed",
            "feature_key": "pump.installation",
            "operator": "eq",
            "target_value": "installed",
            "state_kind": "atomic",
        },
    )
    assert state_leaf_resp.status_code == 201
    assert state_leaf_resp.json()["code"] == "pump_type_sa_0001"

    feature_defs_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/feature-defs")
    assert feature_defs_resp.status_code == 200
    installation_def = next(
        item for item in feature_defs_resp.json() if item["feature_key"] == "pump.installation"
    )
    invalid_values_resp = await client.put(
        f"/api/v1/feature-defs/{installation_def['id']}",
        json={
            "feature_key": "pump.installation",
            "feature_name": "Pump Installation",
            "value_type": "enum",
            "allowed_values": ["not_installed", "removed"],
        },
    )
    assert invalid_values_resp.status_code == 409
    delete_dimension_resp = await client.delete(f"/api/v1/feature-defs/{installation_def['id']}")
    assert delete_dimension_resp.status_code == 409

    template_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "pump_type_dim_0001",
            "feature_name": "Module Installation",
            "value_type": "enum",
            "allowed_values": ["installed", "not_installed"],
        },
    )
    assert template_resp.status_code == 201
    template = template_resp.json()
    concrete_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "pump_type_dim_0001__module_a",
            "feature_name": "Module A / Module Installation",
            "value_type": "enum",
            "allowed_values": ["installed", "not_installed"],
        },
    )
    assert concrete_resp.status_code == 201
    concrete_leaf_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 2,
            "parent_id": state_pkg["id"],
            "name": "Module A Installed",
            "feature_key": "pump_type_dim_0001__module_a",
            "operator": "eq",
            "target_value": "installed",
            "state_kind": "atomic",
            "metadata_json": {
                "state_object_name": "Module A",
                "dimension_template_key": "pump_type_dim_0001",
            },
        },
    )
    assert concrete_leaf_resp.status_code == 201
    invalid_template_values_resp = await client.put(
        f"/api/v1/feature-defs/{template['id']}",
        json={
            "feature_key": "pump_type_dim_0001",
            "feature_name": "Module Installation",
            "value_type": "enum",
            "allowed_values": ["not_installed", "removed"],
        },
    )
    assert invalid_template_values_resp.status_code == 409
    delete_template_resp = await client.delete(f"/api/v1/feature-defs/{template['id']}")
    assert delete_template_resp.status_code == 409

    renamed_state_resp = await client.put(
        f"/api/v1/state-nodes/{state_pkg['id']}",
        json={
            "parent_id": None,
            "level": 1,
            "name": "Installation Package Renamed",
            "state_kind": "aggregate",
            "sort_order": 0,
            "is_active": True,
            "metadata_json": None,
        },
    )
    assert renamed_state_resp.status_code == 200
    assert renamed_state_resp.json()["code"] == state_pkg["code"]

    explicit_state_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 1,
            "parent_id": None,
            "code": "CUSTOM_STATE",
            "name": "Custom Code State",
            "state_kind": "aggregate",
        },
    )
    assert explicit_state_resp.status_code == 201
    assert explicit_state_resp.json()["code"] == "CUSTOM_STATE"

    activity_l1_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 1,
            "parent_id": None,
            "name": "Install Capability",
            "activity_category": "normal",
        },
    )
    assert activity_l1_resp.status_code == 201
    activity_l1 = activity_l1_resp.json()
    assert activity_l1["code"] == "pump_type_ap_0001"

    activity_l2_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 2,
            "parent_id": activity_l1["id"],
            "name": "Detailed Install Capability",
            "activity_category": "normal",
        },
    )
    assert activity_l2_resp.status_code == 201
    assert activity_l2_resp.json()["code"] == "pump_type_ap_0002"

    renamed_activity_resp = await client.put(
        f"/api/v1/activity-nodes/{activity_l1['id']}",
        json={
            "parent_id": None,
            "level": 1,
            "name": "Install Capability Renamed",
            "activity_category": "normal",
            "sort_order": 0,
            "is_active": True,
            "metadata_json": None,
        },
    )
    assert renamed_activity_resp.status_code == 200
    assert renamed_activity_resp.json()["code"] == activity_l1["code"]

    atomic_activity_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/atomic-activities",
        json={
            "machine_type_id": machine_type_id,
            "name": "Tighten Pump Bolts",
            "activity_category": "normal",
        },
    )
    assert atomic_activity_resp.status_code == 201
    atomic_activity = atomic_activity_resp.json()
    assert atomic_activity["code"] == "pump_type_aa_0001"

    rule_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        json={
            "machine_type_id": machine_type_id,
            "atomic_activity_id": atomic_activity["id"],
            "name": "Tighten Pump Bolts",
            "duration_min": 20,
            "is_active": True,
            "effects": [{"feature_key": "pump.installation", "new_value": "installed"}],
            "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}],
        },
    )
    assert rule_resp.status_code == 201
    op_rule = rule_resp.json()
    assert op_rule["code"] == "pump_type_or_0001"

    renamed_rule_resp = await client.put(
        f"/api/v1/op-rules/{op_rule['id']}",
        json={
            "machine_type_id": machine_type_id,
            "atomic_activity_id": atomic_activity["id"],
            "name": "Tighten Pump Bolts Renamed",
            "duration_min": 25,
            "is_active": True,
            "effects": [{"feature_key": "pump.installation", "new_value": "installed"}],
            "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 2, "is_required": True}],
        },
    )
    assert renamed_rule_resp.status_code == 200
    assert renamed_rule_resp.json()["code"] == op_rule["code"]
    assert renamed_rule_resp.json()["duration_min"] == 25

    renamed_atomic_resp = await client.put(
        f"/api/v1/atomic-activities/{atomic_activity['id']}",
        json={
            "name": "Tighten Pump Bolts Renamed",
            "activity_category": "normal",
            "sort_order": 0,
            "is_active": True,
            "metadata_json": None,
        },
    )
    assert renamed_atomic_resp.status_code == 200
    assert renamed_atomic_resp.json()["code"] == atomic_activity["code"]

    other_mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "Pump Type 2", "name": "Pump Type 2", "description": None},
    )
    assert other_mt_resp.status_code == 201
    other_machine_type_id = other_mt_resp.json()["id"]
    other_state_resp = await client.post(
        f"/api/v1/machine-types/{other_machine_type_id}/state-nodes",
        json={
            "machine_type_id": other_machine_type_id,
            "level": 1,
            "parent_id": None,
            "name": "Other Installation Complete",
            "state_kind": "aggregate",
        },
    )
    assert other_state_resp.status_code == 201
    assert other_state_resp.json()["code"] == "pump_type_2_sp_0001"


@pytest.mark.asyncio
async def test_layered_activity_state_foundation_and_rule_binding(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "PUMP", "name": "Pump", "description": None},
    )
    assert mt_resp.status_code == 201
    machine_type_id = mt_resp.json()["id"]

    feature_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "vacuum_ready",
            "feature_name": "Vacuum Ready",
            "value_type": "enum",
            "allowed_values": ["no", "yes"],
        },
    )
    assert feature_resp.status_code == 201

    # Activity hierarchy: level-1 -> level-2 -> level-3.
    l1_activity = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "parent_id": None,
                "code": "VAC",
                "name": "Vacuum System",
                "activity_category": "normal",
            },
        )
    ).json()
    l2_activity = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": l1_activity["id"],
                "code": "VAC_REPAIR",
                "name": "Vacuum Repair Capability",
                "activity_category": "repair",
            },
        )
    ).json()
    l3_activity_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 3,
            "parent_id": l2_activity["id"],
            "code": "VAC_TEST",
            "name": "Leak Test",
            "activity_category": "repair",
        },
    )
    assert l3_activity_resp.status_code == 201
    l3_activity = l3_activity_resp.json()

    invalid_parent_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 3,
            "parent_id": l1_activity["id"],
            "code": "BAD_CHILD",
            "name": "Bad Child",
        },
    )
    assert invalid_parent_resp.status_code == 422

    # State hierarchy: level-1/2 aggregate, level-3 atomic leaf.
    l1_state = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "parent_id": None,
                "code": "VAC_COMPLETE",
                "name": "Vacuum Complete",
                "state_kind": "aggregate",
            },
        )
    ).json()
    l2_state = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": l1_state["id"],
                "code": "VAC_READY_GROUP",
                "name": "Vacuum Ready Group",
                "state_kind": "aggregate",
            },
        )
    ).json()
    l3_state_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 3,
            "parent_id": l2_state["id"],
            "code": "VAC_READY_YES",
            "name": "Vacuum Ready Yes",
            "feature_key": "vacuum_ready",
            "operator": "eq",
            "target_value": "yes",
            "state_kind": "atomic",
        },
    )
    assert l3_state_resp.status_code == 201
    l3_state = l3_state_resp.json()

    invalid_leaf_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 3,
            "parent_id": l2_state["id"],
            "code": "BAD_LEAF",
            "name": "Bad Leaf",
            "state_kind": "atomic",
        },
    )
    assert invalid_leaf_resp.status_code == 422

    # Level-1 activity Scope Guard can only reference level-1 state.
    invalid_guard_resp = await client.post(
        f"/api/v1/activity-nodes/{l1_activity['id']}/scope-guards",
        json={
            "activity_node_id": l1_activity["id"],
            "name": "Invalid low-level reference",
            "preconditions": [{"state_node_id": l3_state["id"], "operator": "completed"}],
        },
    )
    assert invalid_guard_resp.status_code == 422

    guard_resp = await client.post(
        f"/api/v1/activity-nodes/{l1_activity['id']}/scope-guards",
        json={
            "activity_node_id": l1_activity["id"],
            "name": "Vacuum complete guard",
            "preconditions": [{"state_node_id": l1_state["id"], "operator": "completed"}],
        },
    )
    assert guard_resp.status_code == 201
    assert guard_resp.json()["preconditions"][0]["state_node_level"] == 1

    l2_guard_resp = await client.post(
        f"/api/v1/activity-nodes/{l2_activity['id']}/scope-guards",
        json={
            "activity_node_id": l2_activity["id"],
            "name": "Detailed guard",
            "preconditions": [{"state_node_id": l3_state["id"], "operator": "completed"}],
        },
    )
    assert l2_guard_resp.status_code == 201

    bad_rule_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        json={
            "machine_type_id": machine_type_id,
            "activity_node_id": l2_activity["id"],
            "code": "BAD_RULE",
            "name": "Bad Rule",
            "duration_min": 10,
            "is_active": True,
            "effects": [{"feature_key": "vacuum_ready", "new_value": "yes"}],
        },
    )
    assert bad_rule_resp.status_code == 422

    rule_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        json={
            "machine_type_id": machine_type_id,
            "activity_node_id": l3_activity["id"],
            "code": "OP_LEAK_TEST",
            "name": "Leak Test",
            "duration_min": 10,
            "is_active": True,
            "effects": [{"feature_key": "vacuum_ready", "new_value": "yes"}],
        },
    )
    assert rule_resp.status_code == 201
    assert rule_resp.json()["activity_node_id"] == l3_activity["id"]

    delete_activity_resp = await client.delete(f"/api/v1/activity-nodes/{l3_activity['id']}")
    assert delete_activity_resp.status_code == 409


@pytest.mark.asyncio
async def test_existing_solve_flow_remains_compatible_without_activity_nodes(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "LEGACY", "name": "Legacy Machine", "description": None},
    )
    machine_type_id = mt_resp.json()["id"]

    for feature_key, values in {
        "power_state": ["off", "on"],
        "qa_state": ["pending", "passed"],
    }.items():
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": values,
            },
        )
        assert resp.status_code == 201

    machine_resp = await client.post(
        "/api/v1/machines",
        json={
            "machine_type_id": machine_type_id,
            "code": "LEGACY-001",
            "name": "Legacy 001",
            "location": None,
        },
    )
    machine_id = machine_resp.json()["id"]

    resource_resp = await client.post(
        "/api/v1/resources",
        json={
            "machine_id": machine_id,
            "code": "TECH-LEGACY",
            "name": "Technician",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
    )
    assert resource_resp.status_code == 201

    for rule in [
        {
            "code": "OP_POWER_ON",
            "name": "Power On",
            "duration_min": 5,
            "preconditions": [{"feature_key": "power_state", "operator": "eq", "feature_value": "off"}],
            "effects": [{"feature_key": "power_state", "new_value": "on"}],
        },
        {
            "code": "OP_QA",
            "name": "QA",
            "duration_min": 5,
            "preconditions": [{"feature_key": "power_state", "operator": "eq", "feature_value": "on"}],
            "effects": [{"feature_key": "qa_state", "new_value": "passed"}],
        },
    ]:
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/op-rules",
            json={
                "machine_type_id": machine_type_id,
                "is_active": True,
                "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}],
                **rule,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["activity_node_id"] is None

    current_resp = await client.post(
        f"/api/v1/machines/{machine_id}/states",
        json={
            "machine_id": machine_id,
            "state_type": "current",
            "label": "Current",
            "features": {"power_state": "off", "qa_state": "pending"},
        },
    )
    target_resp = await client.post(
        f"/api/v1/machines/{machine_id}/states",
        json={
            "machine_id": machine_id,
            "state_type": "target",
            "label": "Target",
            "features": {"power_state": "on", "qa_state": "passed"},
        },
    )

    solve_resp = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": machine_id,
            "current_state_id": current_resp.json()["state_id"],
            "target_state_id": target_resp.json()["state_id"],
            "objective": "minimize_makespan",
        },
    )
    assert solve_resp.status_code == 200
    data = solve_resp.json()
    assert data["status"] == "done"
    assert [task["op_rule_code"] for task in data["schedule"]["tasks"]] == ["OP_POWER_ON", "OP_QA"]


@pytest.mark.asyncio
async def test_layered_expansion_returns_goal_facts_and_effective_rules(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "EXPAND", "name": "Expansion Machine", "description": None},
    )
    machine_type_id = mt_resp.json()["id"]

    for feature_key in ("vacuum_ready", "access_ready"):
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": ["no", "yes"],
            },
        )
        assert resp.status_code == 201

    a1 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "SYS",
                "name": "System",
                "activity_category": "normal",
            },
        )
    ).json()
    a2 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "REPAIR_PACK",
                "name": "Repair Pack",
                "activity_category": "repair",
            },
        )
    ).json()
    a3 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": a2["id"],
                "code": "LEAK_TEST_STEP",
                "name": "Leak Test Step",
                "activity_category": "repair",
            },
        )
    ).json()

    s1 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "SYS_DONE",
                "name": "System Done",
                "state_kind": "aggregate",
            },
        )
    ).json()
    s2 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": s1["id"],
                "code": "VAC_DONE",
                "name": "Vacuum Done",
                "state_kind": "aggregate",
            },
        )
    ).json()
    s3 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": s2["id"],
                "code": "VAC_READY",
                "name": "Vacuum Ready",
                "feature_key": "vacuum_ready",
                "operator": "eq",
                "target_value": "yes",
                "state_kind": "atomic",
            },
        )
    ).json()

    l1_guard = await client.post(
        f"/api/v1/activity-nodes/{a1['id']}/scope-guards",
        json={
            "activity_node_id": a1["id"],
            "name": "Top guard",
            "preconditions": [{"state_node_id": s1["id"], "operator": "completed"}],
        },
    )
    assert l1_guard.status_code == 201
    l2_guard = await client.post(
        f"/api/v1/activity-nodes/{a2['id']}/scope-guards",
        json={
            "activity_node_id": a2["id"],
            "name": "Repair guard",
            "preconditions": [{"state_node_id": s3["id"], "operator": "completed"}],
        },
    )
    assert l2_guard.status_code == 201

    rule_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        json={
            "machine_type_id": machine_type_id,
            "activity_node_id": a3["id"],
            "code": "OP_LEAK_TEST_EXPAND",
            "name": "Leak Test Expand",
            "duration_min": 12,
            "is_active": True,
            "preconditions": [{"feature_key": "access_ready", "operator": "eq", "feature_value": "yes"}],
            "effects": [{"feature_key": "vacuum_ready", "new_value": "yes"}],
        },
    )
    assert rule_resp.status_code == 201

    expand_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/layered-expansion",
        json={
            "target_state_node_ids": [s1["id"]],
            "activity_scope_node_ids": [a2["id"]],
        },
    )
    assert expand_resp.status_code == 200
    data = expand_resp.json()

    assert data["goal_facts"] == [
        {
            "source_state_node_id": s1["id"],
            "state_node_id": s3["id"],
            "state_node_code": "VAC_READY",
            "state_node_name": "Vacuum Ready",
            "feature_key": "vacuum_ready",
            "operator": "eq",
            "target_value": "yes",
            "source_path": [
                {"id": s1["id"], "code": "SYS_DONE", "name": "System Done", "level": 1},
                {"id": s2["id"], "code": "VAC_DONE", "name": "Vacuum Done", "level": 2},
                {"id": s3["id"], "code": "VAC_READY", "name": "Vacuum Ready", "level": 3},
            ],
        }
    ]
    assert len(data["candidate_activities"]) == 1
    assert data["candidate_activities"][0]["activity_node_id"] == a3["id"]
    assert data["candidate_activities"][0]["op_rule_ids"] == [rule_resp.json()["id"]]

    assert len(data["effective_rules"]) == 1
    effective = data["effective_rules"][0]
    assert effective["op_rule_code"] == "OP_LEAK_TEST_EXPAND"
    assert effective["effects"] == [
        {
            "feature_key": "vacuum_ready",
            "new_value": "yes",
            "effect_type": "set",
            "delta_value": None,
        }
    ]
    source_types = {item["source_type"] for item in effective["preconditions"]}
    assert source_types == {
        "self_activity_rule",
        "parent_level_1_scope_guard",
        "parent_level_2_scope_guard",
    }
    self_precondition = next(item for item in effective["preconditions"] if item["source_type"] == "self_activity_rule")
    assert self_precondition["feature_key"] == "access_ready"
    level2_precondition = next(item for item in effective["preconditions"] if item["source_type"] == "parent_level_2_scope_guard")
    assert level2_precondition["feature_key"] == "vacuum_ready"
    assert level2_precondition["feature_value"] == "yes"
    level1_precondition = next(item for item in effective["preconditions"] if item["source_type"] == "parent_level_1_scope_guard")
    assert level1_precondition["feature_key"] is None
    assert level1_precondition["state_node_id"] == s1["id"]


@pytest.mark.asyncio
async def test_layered_health_check_reports_provider_consumer_diagnostics(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "HEALTH", "name": "Health Machine", "description": None},
    )
    machine_type_id = mt_resp.json()["id"]

    for feature_key, values in {
        "ready": ["no", "yes"],
        "access": ["no", "yes"],
        "clean": ["no", "yes"],
        "missing": ["no", "yes"],
        "mode": ["safe", "run"],
    }.items():
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": values,
            },
        )
        assert resp.status_code == 201

    a1 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "SYS_HEALTH",
                "name": "System Health",
                "activity_category": "normal",
            },
        )
    ).json()
    a2 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "REPAIR_HEALTH",
                "name": "Repair Health",
                "activity_category": "repair",
            },
        )
    ).json()

    activities = {}
    for code, name in {
        "PROVIDE_READY": "Provide Ready",
        "PROVIDE_READY_ALT": "Provide Ready Alt",
        "PROVIDE_CLEAN": "Provide Clean",
    }.items():
        activities[code] = (
            await client.post(
                f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
                json={
                    "machine_type_id": machine_type_id,
                    "level": 3,
                    "parent_id": a2["id"],
                    "code": code,
                    "name": name,
                    "activity_category": "repair",
                },
            )
        ).json()

    state_root = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "HEALTH_TARGETS",
                "name": "Health Targets",
                "state_kind": "aggregate",
            },
        )
    ).json()
    state_group = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": state_root["id"],
                "code": "HEALTH_GROUP",
                "name": "Health Group",
                "state_kind": "aggregate",
            },
        )
    ).json()

    states = {}
    for code, feature_key, target_value in [
        ("READY_YES", "ready", "yes"),
        ("CLEAN_YES", "clean", "yes"),
        ("MISSING_YES", "missing", "yes"),
        ("MODE_SAFE", "mode", "safe"),
        ("MODE_RUN", "mode", "run"),
    ]:
        states[code] = (
            await client.post(
                f"/api/v1/machine-types/{machine_type_id}/state-nodes",
                json={
                    "machine_type_id": machine_type_id,
                    "level": 3,
                    "parent_id": state_group["id"],
                    "code": code,
                    "name": code,
                    "feature_key": feature_key,
                    "operator": "eq",
                    "target_value": target_value,
                    "state_kind": "atomic",
                },
            )
        ).json()

    guard_resp = await client.post(
        f"/api/v1/activity-nodes/{a2['id']}/scope-guards",
        json={
            "activity_node_id": a2["id"],
            "name": "Clean before repair",
            "preconditions": [{"state_node_id": states["CLEAN_YES"]["id"], "operator": "completed"}],
        },
    )
    assert guard_resp.status_code == 201

    rules = [
        {
            "activity_node_id": activities["PROVIDE_READY"]["id"],
            "code": "OP_PROVIDE_READY",
            "name": "Provide Ready",
            "preconditions": [{"feature_key": "access", "operator": "eq", "feature_value": "yes"}],
            "effects": [{"feature_key": "ready", "new_value": "yes"}],
        },
        {
            "activity_node_id": activities["PROVIDE_READY_ALT"]["id"],
            "code": "OP_PROVIDE_READY_ALT",
            "name": "Provide Ready Alt",
            "effects": [{"feature_key": "ready", "new_value": "yes"}],
        },
        {
            "activity_node_id": activities["PROVIDE_CLEAN"]["id"],
            "code": "OP_PROVIDE_CLEAN",
            "name": "Provide Clean",
            "effects": [{"feature_key": "clean", "new_value": "yes"}],
        },
    ]
    for rule in rules:
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/op-rules",
            json={
                "machine_type_id": machine_type_id,
                "duration_min": 5,
                "is_active": True,
                **rule,
            },
        )
        assert resp.status_code == 201

    health_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/layered-health-check",
        json={
            "target_state_node_ids": [
                states["READY_YES"]["id"],
                states["MISSING_YES"]["id"],
                states["MODE_SAFE"]["id"],
                states["MODE_RUN"]["id"],
            ],
            "activity_scope_node_ids": [a2["id"]],
        },
    )
    assert health_resp.status_code == 200
    data = health_resp.json()

    assert data["status"] == "blocked"
    assert data["summary"]["goal_fact_count"] == 4
    assert data["summary"]["candidate_activity_count"] == 3
    assert data["summary"]["effective_rule_count"] == 3
    assert data["summary"]["provider_fact_count"] == 2

    codes = {item["code"] for item in data["diagnostics"]}
    assert {
        "NO_PROVIDER",
        "AMBIGUOUS_PROVIDER",
        "BROKEN_CHAIN",
        "SELF_DEPENDENCY",
        "CONFLICTING_GOAL",
    } <= codes

    ready_node = next(item for item in data["provider_graph"] if item["feature_key"] == "ready")
    assert ready_node["target_value"] == "yes"
    assert len(ready_node["providers"]) == 2
    assert ready_node["goal_state_node_ids"] == [states["READY_YES"]["id"]]

    clean_node = next(item for item in data["provider_graph"] if item["feature_key"] == "clean")
    assert len(clean_node["providers"]) == 1
    assert len(clean_node["consumers"]) == 3

    broken = next(item for item in data["diagnostics"] if item["code"] == "BROKEN_CHAIN")
    assert broken["feature_key"] == "access"
    assert broken["op_rule_id"] is not None

    self_dependency = next(item for item in data["diagnostics"] if item["code"] == "SELF_DEPENDENCY")
    assert self_dependency["feature_key"] == "clean"
    assert self_dependency["details"]["guarded_activity_node_id"] == a2["id"]


@pytest.mark.asyncio
async def test_layered_solve_consumes_scope_guards_and_schedules_level3_activities(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "LAYER_SOLVE", "name": "Layered Solve Machine", "description": None},
    )
    machine_type_id = mt_resp.json()["id"]

    for feature_key in ("access", "ready"):
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": ["no", "yes"],
            },
        )
        assert resp.status_code == 201

    machine_resp = await client.post(
        "/api/v1/machines",
        json={
            "machine_type_id": machine_type_id,
            "code": "LAYER-001",
            "name": "Layered 001",
            "location": None,
        },
    )
    machine_id = machine_resp.json()["id"]

    resource_resp = await client.post(
        "/api/v1/resources",
        json={
            "machine_id": machine_id,
            "code": "TECH-LAYERED",
            "name": "Layered Technician",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
    )
    assert resource_resp.status_code == 201

    current_resp = await client.post(
        f"/api/v1/machines/{machine_id}/states",
        json={
            "machine_id": machine_id,
            "state_type": "current",
            "label": "Current",
            "features": {"access": "no", "ready": "no"},
        },
    )
    current_state_id = current_resp.json()["state_id"]

    a1 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "SYS_SOLVE",
                "name": "System Solve",
                "activity_category": "normal",
            },
        )
    ).json()
    prep_pack = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "PREP_PACK",
                "name": "Preparation Pack",
                "activity_category": "normal",
            },
        )
    ).json()
    work_pack = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "WORK_PACK",
                "name": "Work Pack",
                "activity_category": "normal",
            },
        )
    ).json()
    prep_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": prep_pack["id"],
                "code": "POWER_ON_STEP",
                "name": "Power On Step",
                "activity_category": "normal",
            },
        )
    ).json()
    work_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": work_pack["id"],
                "code": "READY_STEP",
                "name": "Ready Step",
                "activity_category": "normal",
            },
        )
    ).json()
    unused_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": work_pack["id"],
                "code": "UNUSED_STEP",
                "name": "Unused Step",
                "activity_category": "normal",
            },
        )
    ).json()

    state_root = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "SOLVE_DONE",
                "name": "Solve Done",
                "state_kind": "aggregate",
            },
        )
    ).json()
    state_group = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": state_root["id"],
                "code": "SOLVE_GROUP",
                "name": "Solve Group",
                "state_kind": "aggregate",
            },
        )
    ).json()
    access_state = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": state_group["id"],
                "code": "ACCESS_YES",
                "name": "Access Yes",
                "feature_key": "access",
                "operator": "eq",
                "target_value": "yes",
                "state_kind": "atomic",
            },
        )
    ).json()
    ready_state = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": state_group["id"],
                "code": "READY_YES",
                "name": "Ready Yes",
                "feature_key": "ready",
                "operator": "eq",
                "target_value": "yes",
                "state_kind": "atomic",
            },
        )
    ).json()

    guard_resp = await client.post(
        f"/api/v1/activity-nodes/{work_pack['id']}/scope-guards",
        json={
            "activity_node_id": work_pack["id"],
            "name": "Access required",
            "preconditions": [{"state_node_id": access_state["id"], "operator": "completed"}],
        },
    )
    assert guard_resp.status_code == 201

    for rule in [
        {
            "activity_node_id": prep_step["id"],
            "code": "OP_LAYER_POWER_ON",
            "name": "Layer Power On",
            "duration_min": 5,
            "effects": [{"feature_key": "access", "new_value": "yes"}],
        },
        {
            "activity_node_id": work_step["id"],
            "code": "OP_LAYER_READY",
            "name": "Layer Ready",
            "duration_min": 5,
            "effects": [{"feature_key": "ready", "new_value": "yes"}],
        },
        {
            "activity_node_id": unused_step["id"],
            "code": "OP_LAYER_UNUSED",
            "name": "Layer Unused",
            "duration_min": 5,
            "effects": [{"feature_key": "ready", "new_value": "no"}],
        },
    ]:
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/op-rules",
            json={
                "machine_type_id": machine_type_id,
                "is_active": True,
                "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}],
                **rule,
            },
        )
        assert resp.status_code == 201

    solve_resp = await client.post(
        "/api/v1/solve/layered",
        json={
            "machine_id": machine_id,
            "current_state_id": current_state_id,
            "target_state_node_ids": [ready_state["id"]],
            "activity_scope_node_ids": [prep_pack["id"], work_pack["id"]],
        },
    )
    assert solve_resp.status_code == 200
    data = solve_resp.json()
    assert data["status"] == "done"
    assert data["synthetic_target_state_id"] is not None
    assert data["diagnostics"]["layered_health"]["status"] == "ok"
    assert data["layered"]["preflight_health"]["status"] == "ok"
    assert data["layered"]["preflight_health"]["summary"]["goal_fact_count"] == 1
    assert data["layered"]["preflight_health"]["summary"]["effective_rule_count"] == 3
    assert data["layered"]["preflight_health"]["blocking_count"] == 0
    assert data["layered"]["preflight_health"]["warning_count"] == 0

    tasks = data["schedule"]["tasks"]
    assert [task["op_rule_code"] for task in tasks] == ["OP_LAYER_POWER_ON", "OP_LAYER_READY"]
    assert tasks[1]["predecessors"] == [tasks[0]["step_order"]]
    assert all(task["op_rule_code"] != "OP_LAYER_UNUSED" for task in tasks)

    assert data["layered"]["state_replay"]["status"] == "ok"
    assert data["layered"]["state_replay"]["satisfied_goal_count"] == 1
    ready_summary = next(
        item for item in data["layered"]["state_summary"] if item["state_node_id"] == ready_state["id"]
    )
    assert ready_summary["status"] == "complete"

    activity_codes = {item["activity_node_code"] for item in data["layered"]["activity_summary"]}
    assert {"PREP_PACK", "WORK_PACK", "POWER_ON_STEP", "READY_STEP"} <= activity_codes
    state_tree = data["layered"]["state_tree"]
    assert len(state_tree) == 1
    assert state_tree[0]["state_node_code"] == "SOLVE_DONE"
    assert state_tree[0]["status"] == "complete"
    assert state_tree[0]["goal_leaf_count"] == 1
    assert state_tree[0]["children"][0]["state_node_code"] == "SOLVE_GROUP"
    ready_leaf = state_tree[0]["children"][0]["children"][0]
    assert ready_leaf["state_node_code"] == "READY_YES"
    assert ready_leaf["source_op_rule_codes"] == ["OP_LAYER_READY"]
    assert ready_leaf["source_step_orders"] == [tasks[1]["step_order"]]
    ready_goal = data["layered"]["state_replay"]["goal_results"][0]
    assert ready_goal["source"]["source_type"] == "activity"
    assert ready_goal["source"]["op_rule_code"] == "OP_LAYER_READY"

    activity_tree = data["layered"]["activity_tree"]
    assert len(activity_tree) == 1
    assert activity_tree[0]["activity_node_code"] == "SYS_SOLVE"
    assert activity_tree[0]["scheduled_task_count"] == 2
    activity_children = {item["activity_node_code"]: item for item in activity_tree[0]["children"]}
    assert set(activity_children) == {"PREP_PACK", "WORK_PACK"}
    assert activity_children["PREP_PACK"]["children"][0]["activity_node_code"] == "POWER_ON_STEP"
    assert activity_children["WORK_PACK"]["children"][0]["activity_node_code"] == "READY_STEP"
    assert activity_children["WORK_PACK"]["children"][0]["scheduled_task_count"] == 1

    ready_explanation = next(
        item for item in data["layered"]["effective_preconditions"] if item["op_rule_code"] == "OP_LAYER_READY"
    )
    source_types = {item["source_type"] for item in ready_explanation["preconditions"]}
    assert "parent_level_2_scope_guard" in source_types


@pytest.mark.asyncio
async def test_maintenance_solve_merges_intents_and_reuses_shared_provider(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "MAINT_SOLVE", "name": "Maintenance Solve Machine", "description": None},
    )
    machine_type_id = mt_resp.json()["id"]

    for feature_key in ("safe", "pump_fixed", "valve_fixed"):
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/feature-defs",
            json={
                "machine_type_id": machine_type_id,
                "feature_key": feature_key,
                "feature_name": feature_key,
                "value_type": "enum",
                "allowed_values": ["no", "yes"],
            },
        )
        assert resp.status_code == 201

    machine_resp = await client.post(
        "/api/v1/machines",
        json={
            "machine_type_id": machine_type_id,
            "code": "MAINT-001",
            "name": "Maintenance 001",
            "location": None,
        },
    )
    machine_id = machine_resp.json()["id"]

    resource_resp = await client.post(
        "/api/v1/resources",
        json={
            "machine_id": machine_id,
            "code": "TECH-MAINT",
            "name": "Maintenance Technician",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
    )
    assert resource_resp.status_code == 201

    current_resp = await client.post(
        f"/api/v1/machines/{machine_id}/states",
        json={
            "machine_id": machine_id,
            "state_type": "current",
            "label": "Current",
            "features": {"safe": "no", "pump_fixed": "no", "valve_fixed": "no"},
        },
    )
    current_state_id = current_resp.json()["state_id"]

    a1 = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "MAINT_SYS",
                "name": "Maintenance System",
                "activity_category": "maintenance",
            },
        )
    ).json()
    prep_pack = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "SAFETY_PREP",
                "name": "Safety Preparation",
                "activity_category": "maintenance",
            },
        )
    ).json()
    pump_pack = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "PUMP_MAINT",
                "name": "Pump Maintenance",
                "activity_category": "maintenance",
            },
        )
    ).json()
    valve_pack = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": a1["id"],
                "code": "VALVE_MAINT",
                "name": "Valve Maintenance",
                "activity_category": "maintenance",
            },
        )
    ).json()

    prep_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": prep_pack["id"],
                "code": "MAKE_SAFE",
                "name": "Make Safe",
                "activity_category": "maintenance",
            },
        )
    ).json()
    pump_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": pump_pack["id"],
                "code": "FIX_PUMP",
                "name": "Fix Pump",
                "activity_category": "maintenance",
            },
        )
    ).json()
    valve_step = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": valve_pack["id"],
                "code": "FIX_VALVE",
                "name": "Fix Valve",
                "activity_category": "maintenance",
            },
        )
    ).json()

    state_root = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "code": "MAINT_DONE",
                "name": "Maintenance Done",
                "state_kind": "aggregate",
            },
        )
    ).json()
    state_group = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": state_root["id"],
                "code": "MAINT_GROUP",
                "name": "Maintenance Group",
                "state_kind": "aggregate",
            },
        )
    ).json()

    async def create_leaf(code: str, feature_key: str):
        return (
            await client.post(
                f"/api/v1/machine-types/{machine_type_id}/state-nodes",
                json={
                    "machine_type_id": machine_type_id,
                    "level": 3,
                    "parent_id": state_group["id"],
                    "code": code,
                    "name": code,
                    "feature_key": feature_key,
                    "operator": "eq",
                    "target_value": "yes",
                    "state_kind": "atomic",
                },
            )
        ).json()

    safe_state = await create_leaf("SAFE_YES", "safe")
    pump_state = await create_leaf("PUMP_FIXED_YES", "pump_fixed")
    valve_state = await create_leaf("VALVE_FIXED_YES", "valve_fixed")

    for pack in (pump_pack, valve_pack):
        guard_resp = await client.post(
            f"/api/v1/activity-nodes/{pack['id']}/scope-guards",
            json={
                "activity_node_id": pack["id"],
                "name": "Safe required",
                "preconditions": [{"state_node_id": safe_state["id"], "operator": "completed"}],
            },
        )
        assert guard_resp.status_code == 201

    for rule in [
        {
            "activity_node_id": prep_step["id"],
            "code": "OP_MAKE_SAFE",
            "name": "Make Safe",
            "duration_min": 5,
            "effects": [{"feature_key": "safe", "new_value": "yes"}],
        },
        {
            "activity_node_id": pump_step["id"],
            "code": "OP_FIX_PUMP",
            "name": "Fix Pump",
            "duration_min": 7,
            "effects": [{"feature_key": "pump_fixed", "new_value": "yes"}],
        },
        {
            "activity_node_id": valve_step["id"],
            "code": "OP_FIX_VALVE",
            "name": "Fix Valve",
            "duration_min": 9,
            "effects": [{"feature_key": "valve_fixed", "new_value": "yes"}],
        },
    ]:
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/op-rules",
            json={
                "machine_type_id": machine_type_id,
                "is_active": True,
                "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}],
                **rule,
            },
        )
        assert resp.status_code == 201

    template_payloads = [
        {
            "issue_type": "pump_fault",
            "name": "Pump Fault",
            "scope_activity_node_id": pump_pack["id"],
            "target_state_node_ids": [pump_state["id"]],
            "candidate_activity_scope_ids": [prep_pack["id"], pump_pack["id"]],
            "observed_fact_templates": [
                {"feature_key": "pump_fixed", "operator": "eq", "value": "no", "value_list": None}
            ],
        },
        {
            "issue_type": "valve_fault",
            "name": "Valve Fault",
            "scope_activity_node_id": valve_pack["id"],
            "target_state_node_ids": [valve_state["id"]],
            "candidate_activity_scope_ids": [prep_pack["id"], valve_pack["id"]],
            "observed_fact_templates": [
                {"feature_key": "valve_fixed", "operator": "eq", "value": "no", "value_list": None}
            ],
        },
    ]
    template_ids = []
    for payload in template_payloads:
        resp = await client.post(
            f"/api/v1/machine-types/{machine_type_id}/maintenance-intent-templates",
            json={
                "machine_type_id": machine_type_id,
                "description": None,
                "desired_fact_templates": [],
                "is_active": True,
                "metadata_json": None,
                **payload,
            },
        )
        assert resp.status_code == 201
        template_ids.append(resp.json()["id"])

    list_resp = await client.get(
        f"/api/v1/machine-types/{machine_type_id}/maintenance-intent-templates"
    )
    assert list_resp.status_code == 200
    assert {item["issue_type"] for item in list_resp.json()} == {"pump_fault", "valve_fault"}

    solve_resp = await client.post(
        "/api/v1/solve/maintenance",
        json={
            "machine_id": machine_id,
            "current_state_id": current_state_id,
            "intent_template_ids": template_ids,
            "objectives": [
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_activity_group_span", "weight": 1.25},
                {"type": "minimize_activity_group_gaps", "weight": 1.5},
                {"type": "minimize_activity_group_interruptions", "weight": 2.0},
            ],
        },
    )
    assert solve_resp.status_code == 200
    data = solve_resp.json()
    assert data["status"] == "done", data
    assert data["maintenance"]["merged_intent_count"] == 2
    assert data["diagnostics"]["layered_health"]["status"] == "ok"
    assert data["layered"]["preflight_health"]["status"] == "ok"
    assert data["layered"]["preflight_health"]["summary"]["goal_fact_count"] == 2
    assert data["layered"]["preflight_health"]["blocking_count"] == 0

    op_codes = [task["op_rule_code"] for task in data["schedule"]["tasks"]]
    assert op_codes.count("OP_MAKE_SAFE") == 1
    assert op_codes.count("OP_FIX_PUMP") == 1
    assert op_codes.count("OP_FIX_VALVE") == 1
    group_codes = {task["op_rule_code"]: task["activity_group_code"] for task in data["schedule"]["tasks"]}
    assert group_codes["OP_MAKE_SAFE"] == "SAFETY_PREP"
    assert group_codes["OP_FIX_PUMP"] == "PUMP_MAINT"
    assert group_codes["OP_FIX_VALVE"] == "VALVE_MAINT"

    schedule_diagnostics = data["diagnostics"]["schedule"]
    assert {
        item["type"] for item in schedule_diagnostics["objective_terms"]
    } == {
        "minimize_makespan",
        "minimize_activity_group_span",
        "minimize_activity_group_gaps",
        "minimize_activity_group_interruptions",
    }
    continuity = schedule_diagnostics["activity_group_continuity"]
    assert continuity["objective_weights"]["minimize_activity_group_span"] == 1.25
    assert continuity["objective_weights"]["minimize_activity_group_gaps"] == 1.5
    assert continuity["objective_weights"]["minimize_activity_group_interruptions"] == 2.0
    selection = {
        item["op_rule_code"]: item
        for item in data["layered"]["activity_selection"]
    }
    assert selection["OP_MAKE_SAFE"]["status"] == "selected"
    assert selection["OP_MAKE_SAFE"]["is_shared_provider"] is True
    assert {
        consumer["op_rule_code"]
        for consumer in selection["OP_MAKE_SAFE"]["consumers"]
        if consumer["type"] == "scheduled_precondition"
    } == {"OP_FIX_PUMP", "OP_FIX_VALVE"}

    safe_step_order = next(
        task["step_order"] for task in data["schedule"]["tasks"] if task["op_rule_code"] == "OP_MAKE_SAFE"
    )
    for task in data["schedule"]["tasks"]:
        if task["op_rule_code"] in {"OP_FIX_PUMP", "OP_FIX_VALVE"}:
            assert safe_step_order in task["predecessors"]

    assert data["layered"]["state_replay"]["status"] == "ok"
    final_state = data["layered"]["state_replay"]["final_state"]
    assert final_state["safe"] == "yes"
    assert final_state["pump_fixed"] == "yes"
    assert final_state["valve_fixed"] == "yes"
    goal_sources = {
        item["state_node_code"]: item["source"]["op_rule_code"]
        for item in data["layered"]["state_replay"]["goal_results"]
    }
    assert goal_sources == {
        "PUMP_FIXED_YES": "OP_FIX_PUMP",
        "VALVE_FIXED_YES": "OP_FIX_VALVE",
    }

    already_safe_resp = await client.post(
        "/api/v1/solve/maintenance",
        json={
            "machine_id": machine_id,
            "current_state_id": current_state_id,
            "intent_template_ids": template_ids,
            "extra_observed_facts": [
                {"feature_key": "safe", "operator": "eq", "value": "yes", "value_list": None}
            ],
        },
    )
    assert already_safe_resp.status_code == 200
    already_safe_data = already_safe_resp.json()
    assert already_safe_data["status"] == "done", already_safe_data
    already_safe_codes = [task["op_rule_code"] for task in already_safe_data["schedule"]["tasks"]]
    assert "OP_MAKE_SAFE" not in already_safe_codes
    assert already_safe_codes.count("OP_FIX_PUMP") == 1
    assert already_safe_codes.count("OP_FIX_VALVE") == 1
    already_safe_selection = {
        item["op_rule_code"]: item
        for item in already_safe_data["layered"]["activity_selection"]
    }
    assert already_safe_selection["OP_MAKE_SAFE"]["status"] == "skipped"
    assert already_safe_selection["OP_MAKE_SAFE"]["reason"] == "effects_already_satisfied"


@pytest.mark.asyncio
async def test_state_tree_supports_deep_atomic_leaves_and_auto_feature_defs(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "DEEP_STATE", "name": "Deep State", "description": None},
    )
    assert mt_resp.status_code == 201
    machine_type_id = mt_resp.json()["id"]

    root = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "parent_id": None,
                "code": "ASSEMBLY",
                "name": "Assembly",
                "state_kind": "aggregate",
            },
        )
    ).json()
    branch = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": root["id"],
                "code": "MODULE",
                "name": "Module",
                "state_kind": "aggregate",
            },
        )
    ).json()
    sub_branch = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/state-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 3,
                "parent_id": branch["id"],
                "code": "MECH",
                "name": "Mechanical",
                "state_kind": "aggregate",
            },
        )
    ).json()
    leaf_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 4,
            "parent_id": sub_branch["id"],
            "code": "MECH_INSTALLED",
            "name": "Mechanical Installed",
            "feature_key": "mechanical_installation",
            "operator": "eq",
            "target_value": "installed",
            "state_kind": "atomic",
        },
    )
    assert leaf_resp.status_code == 201

    feature_defs = (await client.get(f"/api/v1/machine-types/{machine_type_id}/feature-defs")).json()
    assert {item["feature_key"] for item in feature_defs} == {"mechanical_installation"}

    expansion_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/layered-expansion",
        json={"target_state_node_ids": [root["id"]], "activity_scope_node_ids": []},
    )
    assert expansion_resp.status_code == 200
    expansion = expansion_resp.json()
    assert expansion["goal_facts"][0]["state_node_code"] == "MECH_INSTALLED"
    assert expansion["goal_facts"][0]["source_path"][-1]["level"] == 4

    conflict_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/state-nodes",
        json={
            "machine_type_id": machine_type_id,
            "level": 4,
            "parent_id": sub_branch["id"],
            "code": "MECH_NOT_INSTALLED",
            "name": "Mechanical Not Installed",
            "feature_key": "mechanical_installation",
            "operator": "eq",
            "target_value": "not_installed",
            "state_kind": "atomic",
        },
    )
    assert conflict_resp.status_code == 201
    conflict_expansion = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/layered-expansion",
            json={"target_state_node_ids": [root["id"]], "activity_scope_node_ids": []},
        )
    ).json()
    assert any(item["code"] == "CONFLICTING_GOAL" and item["severity"] == "error" for item in conflict_expansion["diagnostics"])


@pytest.mark.asyncio
async def test_atomic_activity_refs_expand_from_packages_and_dedupe_reuse(client):
    mt_resp = await client.post(
        "/api/v1/machine-types",
        json={"code": "ATOMIC_REUSE", "name": "Atomic Reuse", "description": None},
    )
    assert mt_resp.status_code == 201
    machine_type_id = mt_resp.json()["id"]

    await client.post(
        f"/api/v1/machine-types/{machine_type_id}/feature-defs",
        json={
            "machine_type_id": machine_type_id,
            "feature_key": "calibrated",
            "feature_name": "Calibrated",
            "value_type": "enum",
            "allowed_values": ["no", "yes"],
        },
    )
    root_activity = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 1,
                "parent_id": None,
                "code": "INTEGRATION",
                "name": "Integration",
                "activity_category": "normal",
            },
        )
    ).json()
    package_a = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": root_activity["id"],
                "code": "PKG_A",
                "name": "Package A",
                "activity_category": "normal",
            },
        )
    ).json()
    package_b = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/activity-nodes",
            json={
                "machine_type_id": machine_type_id,
                "level": 2,
                "parent_id": root_activity["id"],
                "code": "PKG_B",
                "name": "Package B",
                "activity_category": "normal",
            },
        )
    ).json()
    atomic = (
        await client.post(
            f"/api/v1/machine-types/{machine_type_id}/atomic-activities",
            json={
                "machine_type_id": machine_type_id,
                "code": "CALIBRATE",
                "name": "Calibrate",
                "activity_category": "normal",
            },
        )
    ).json()

    for package in (package_a, package_b):
        ref_resp = await client.post(
            f"/api/v1/activity-nodes/{package['id']}/atomic-activity-refs",
            json={"atomic_activity_id": atomic["id"], "sort_order": 10, "is_active": True},
        )
        assert ref_resp.status_code == 201

    duplicate_resp = await client.post(
        f"/api/v1/activity-nodes/{package_a['id']}/atomic-activity-refs",
        json={"atomic_activity_id": atomic["id"], "sort_order": 20, "is_active": True},
    )
    assert duplicate_resp.status_code == 409

    rule_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/op-rules",
        json={
            "machine_type_id": machine_type_id,
            "atomic_activity_id": atomic["id"],
            "code": "OP_CALIBRATE",
            "name": "Calibrate",
            "duration_min": 15,
            "is_active": True,
            "effects": [{"feature_key": "calibrated", "new_value": "yes"}],
        },
    )
    assert rule_resp.status_code == 201

    expansion_resp = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/layered-expansion",
        json={"target_state_node_ids": [], "activity_scope_node_ids": [root_activity["id"]]},
    )
    assert expansion_resp.status_code == 200
    expansion = expansion_resp.json()
    assert len(expansion["candidate_activities"]) == 1
    assert expansion["candidate_activities"][0]["atomic_activity_id"] == atomic["id"]
    assert expansion["effective_rules"][0]["atomic_activity_id"] == atomic["id"]

    delete_resp = await client.delete(f"/api/v1/atomic-activities/{atomic['id']}")
    assert delete_resp.status_code == 204

    atomic_list = (await client.get(f"/api/v1/machine-types/{machine_type_id}/atomic-activities")).json()
    package_a_refs = (await client.get(f"/api/v1/activity-nodes/{package_a['id']}/atomic-activity-refs")).json()
    package_b_refs = (await client.get(f"/api/v1/activity-nodes/{package_b['id']}/atomic-activity-refs")).json()
    rules = (await client.get(f"/api/v1/machine-types/{machine_type_id}/op-rules")).json()

    assert atomic_list == []
    assert package_a_refs == []
    assert package_b_refs == []
    assert all(rule["id"] != rule_resp.json()["id"] for rule in rules)

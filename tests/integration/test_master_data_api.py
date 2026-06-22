"""
Integration tests for master-data CRUD APIs.

Focus: verify that user-managed data can be written through the API and then
consumed by the existing /solve pipeline without seed SQL.
"""

import pytest


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
            "machine_id": machine_id,
            "code": "TECH-01",
            "name": "Tech Alice",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
        {
            "machine_id": machine_id,
            "code": "TECH-02",
            "name": "Tech Bob",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
        {
            "machine_id": machine_id,
            "code": "CLEAN-01",
            "name": "Cleaner",
            "resource_type": "CLEANER",
            "capacity": 1,
            "is_available": True,
            "meta": None,
        },
    ]
    for item in resources:
        resource_resp = await client.post("/api/v1/resources", json=item)
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


@pytest.mark.asyncio
async def test_resources_are_scoped_to_machine(client):
    mt_resp = await client.post("/api/v1/machine-types", json={
        "code": "RESOURCE_SCOPE",
        "name": "Resource Scope",
        "description": None,
    })
    assert mt_resp.status_code == 201
    machine_type_id = mt_resp.json()["id"]

    machine_a = await client.post("/api/v1/machines", json={
        "machine_type_id": machine_type_id,
        "code": "RS-A",
        "name": "Resource Scope A",
        "location": None,
    })
    machine_b = await client.post("/api/v1/machines", json={
        "machine_type_id": machine_type_id,
        "code": "RS-B",
        "name": "Resource Scope B",
        "location": None,
    })
    assert machine_a.status_code == 201
    assert machine_b.status_code == 201
    machine_a_id = machine_a.json()["id"]
    machine_b_id = machine_b.json()["id"]

    payload = {
        "machine_id": machine_a_id,
        "code": "TECH-01",
        "name": "Tech A",
        "resource_type": "TECHNICIAN",
        "capacity": 1,
        "is_available": True,
        "meta": None,
    }
    first = await client.post("/api/v1/resources", json=payload)
    duplicate_same_machine = await client.post("/api/v1/resources", json=payload)
    duplicate_other_machine = await client.post(
        "/api/v1/resources",
        json={**payload, "machine_id": machine_b_id, "name": "Tech B"},
    )

    assert first.status_code == 201
    assert duplicate_same_machine.status_code == 409
    assert duplicate_other_machine.status_code == 201

    missing_scope = await client.get("/api/v1/resources")
    machine_a_resources = await client.get(f"/api/v1/resources?machine_id={machine_a_id}")
    machine_b_resources = await client.get(f"/api/v1/resources?machine_id={machine_b_id}")

    assert missing_scope.status_code == 422
    assert [item["machine_id"] for item in machine_a_resources.json()] == [machine_a_id]
    assert [item["machine_id"] for item in machine_b_resources.json()] == [machine_b_id]

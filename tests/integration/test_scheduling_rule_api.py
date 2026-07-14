import pytest

from app.db.models import AtomicActivity, MachineType


@pytest.mark.asyncio
async def test_rule_type_registry_and_atomic_responsibility_contract(client):
    descriptors = await client.get("/api/v1/scheduling-rule-types")
    assert descriptors.status_code == 200
    assert {item["type"] for item in descriptors.json()} == {
        "group_continuity",
        "scope_exclusivity",
        "state_package_continuity",
        "shift_restriction",
    }

    created = await client.post("/api/v1/machine-types", json={
        "code": "RULE_MT",
        "name": "Rule machine type",
        "scheduling_config": {
            "responsible_subsystems": [{"code": "PROPULSION", "name": "推进子系统"}],
            "rules": [
                {
                    "code": "CRANE_EXCLUSIVE",
                    "name": "Crane exclusive",
                    "type": "scope_exclusivity",
                    "enabled": True,
                    "activation_mode": "required",
                    "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                    "enforcement": {"mode": "hard", "overridable": False},
                    "parameters": {"against": "all_other_tasks"},
                    "presentation": {
                        "gantt_marker": {"text": "吊", "color": "#F59E0B"}
                    },
                }
            ],
        },
    })
    assert created.status_code == 201
    assert created.json()["scheduling_config"]["rules"][0]["presentation"] == {
        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
    }
    machine_type_id = created.json()["id"]

    atomic = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/atomic-activities",
        json={
            "machine_type_id": machine_type_id,
            "name": "Inspect propulsion",
            "activity_category": "normal",
            "metadata_json": {"responsible_subsystem": "PROPULSION"},
        },
    )
    assert atomic.status_code == 201
    assert atomic.json()["metadata_json"]["responsible_subsystem"] == "PROPULSION"

    invalid = await client.post(
        f"/api/v1/machine-types/{machine_type_id}/atomic-activities",
        json={
            "machine_type_id": machine_type_id,
            "name": "Unknown subsystem",
            "metadata_json": {"responsible_subsystem": "UNKNOWN"},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error_message"]["error_code"] == "RESPONSIBLE_SUBSYSTEM_INVALID"

    removal = await client.put(
        f"/api/v1/machine-types/{machine_type_id}",
        json={
            "code": "RULE_MT",
            "name": "Rule machine type",
            "scheduling_config": {"responsible_subsystems": [], "rules": []},
        },
    )
    assert removal.status_code == 409
    assert removal.json()["error_message"]["error_code"] == "RESPONSIBLE_SUBSYSTEM_IN_USE"


@pytest.mark.asyncio
async def test_unified_validation_reports_scheduling_rule_configuration_debt(client, db_session):
    machine_type = MachineType(
        code="RULE_VALIDATE_MT",
        name="Rule validation machine type",
        scheduling_config={
            "responsible_subsystems": [{"code": "PROPULSION", "name": "推进子系统"}],
            "rules": [
                {
                    "code": "CRANE_EXCLUSIVE",
                    "name": "行吊独占",
                    "type": "scope_exclusivity",
                    "enabled": True,
                    "activation_mode": "required",
                    "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                    "enforcement": {"mode": "hard", "overridable": False},
                    "parameters": {"against": "all_other_tasks"},
                },
                {
                    "code": "FUNCTION_TEST_EXCLUSIVE",
                    "name": "功能调测独占",
                    "type": "scope_exclusivity",
                    "enabled": True,
                    "activation_mode": "default_on",
                    "selector": {"effect_dimension_keys": ["function_test_dim"]},
                    "enforcement": {"mode": "soft"},
                    "parameters": {"against": "all_other_tasks"},
                },
                {
                    "code": "CRANE_DAY_ONLY",
                    "name": "行吊白班限制",
                    "type": "shift_restriction",
                    "enabled": True,
                    "activation_mode": "required",
                    "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                    "enforcement": {"mode": "hard", "overridable": True},
                    "parameters": {"allowed_shift_codes": ["DAY_SHIFT_1"]},
                },
            ],
        },
    )
    db_session.add(machine_type)
    await db_session.flush()
    db_session.add(
        AtomicActivity(
            machine_type_id=machine_type.id,
            code="STALE_SUBSYSTEM_ACTIVITY",
            name="失效责任子系统活动",
            metadata_json={"responsible_subsystem": "REMOVED_SUBSYSTEM"},
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/machine-types/{machine_type.id}/network-editor/validate",
        json={},
    )
    assert response.status_code == 200
    payload = response.json()
    codes = {
        issue["code"]
        for issue in [*payload["modeling_issues"], *payload["solver_ready_issues"]]
    }
    assert {
        "RESPONSIBLE_SUBSYSTEM_INVALID",
        "SCHEDULING_RULE_RESOURCE_REFERENCE_INVALID",
        "SCHEDULING_RULE_DIMENSION_REFERENCE_INVALID",
        "SCHEDULING_RULE_SHIFT_REFERENCE_INVALID",
        "SCHEDULING_RULE_NO_MATCH",
    } <= codes
    assert payload["status"] == "blocked"

    machine_type.scheduling_config = {
        "responsible_subsystems": [],
        "rules": [
            {
                "code": "REQUIRED_DISABLED",
                "name": "必选规则被关闭",
                "type": "scope_exclusivity",
                "enabled": False,
                "activation_mode": "required",
                "selector": {"match": "all"},
                "enforcement": {"mode": "hard"},
                "parameters": {},
            }
        ],
    }
    await db_session.commit()

    invalid_response = await client.post(
        f"/api/v1/machine-types/{machine_type.id}/network-editor/validate",
        json={},
    )
    assert invalid_response.status_code == 200
    invalid_codes = {
        issue["code"] for issue in invalid_response.json()["solver_ready_issues"]
    }
    assert "SCHEDULING_RULE_CONFIG_INVALID" in invalid_codes

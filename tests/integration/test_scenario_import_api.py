from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.services.scenario_import import ParsedRow, _parse_effects


FULL_CHAIN_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "full_chain_complex_scenario"
    / "full_chain_complex_scenario.xlsx"
)


def test_scenario_import_effect_parser_accepts_sub_and_reset():
    row = ParsedRow(sheet="rules", row_number=2, data={})
    errors = []

    effects = _parse_effects("cleanliness:sub:25;cleanliness:reset:100", row, errors)

    assert errors == []
    assert effects == [
        {
            "feature_key": "cleanliness",
            "effect_type": "sub",
            "new_value": "25",
            "delta_value": 25.0,
        },
        {
            "feature_key": "cleanliness",
            "effect_type": "reset",
            "new_value": "100",
            "delta_value": None,
        },
    ]


def _scenario_workbook(*, broken_effect: bool = False) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "meta": ["scenario_code", "scenario_name", "version", "mode"],
        "feature_catalog": ["feature_key", "value_type", "allowed_values", "unit", "description"],
        "machine_type": ["code", "name", "description"],
        "machines": ["code", "machine_type_code", "name", "location"],
        "state_feature_defs": ["machine_type_code", "feature_key", "feature_name", "value_type", "allowed_values"],
        "resources": ["machine_code", "code", "name", "resource_type", "capacity", "is_available", "meta_json"],
        "rules": [
            "code",
            "machine_type_code",
            "name",
            "duration_min",
            "description",
            "is_active",
            "is_repair",
            "preconditions",
            "effects",
            "resource_reqs",
        ],
        "states": ["machine_code", "state_code", "state_type", "label", "features"],
        "solve_cases": [
            "case_code",
            "machine_code",
            "current_state_code",
            "target_state_code",
            "objective",
            "objectives_json",
            "constraints_json",
            "expected_min_steps",
            "expected_max_makespan_min",
        ],
        "instructions": ["section", "description"],
    }
    for name, header in sheets.items():
        sheet = workbook.create_sheet(name)
        sheet.append(header)

    workbook["meta"].append(["E2E_SCENARIO", "Scenario Import E2E", "v1", "scenario_upsert"])
    workbook["feature_catalog"].append(["prep_done", "enum", "false,true", "", ""])
    workbook["feature_catalog"].append(["delivery_ready", "enum", "false,true", "", ""])
    workbook["machine_type"].append(["IMPORT_MACHINE", "Import Machine", ""])
    workbook["machines"].append(["IMPORT-001", "IMPORT_MACHINE", "Import Test Machine", "Line A"])
    workbook["state_feature_defs"].append(["IMPORT_MACHINE", "prep_done", "Prep Done", "enum", "false,true"])
    workbook["state_feature_defs"].append(["IMPORT_MACHINE", "delivery_ready", "Delivery Ready", "enum", "false,true"])
    workbook["resources"].append(["IMPORT-001", "TECH-IMPORT-01", "Import Tech 01", "TECHNICIAN", 1, "true", ""])
    workbook["resources"].append(["IMPORT-001", "QA-IMPORT-01", "Import QA 01", "QA", 1, "true", ""])
    workbook["rules"].append([
        "OP_IMPORT_PREP",
        "IMPORT_MACHINE",
        "Prepare",
        10,
        "",
        "true",
        "false",
        "prep_done:eq:false",
        "prep_done:set:true",
        "TECHNICIAN:1:true",
    ])
    workbook["rules"].append([
        "OP_IMPORT_DELIVER",
        "IMPORT_MACHINE",
        "Deliver",
        15,
        "",
        "true",
        "false",
        "prep_done:eq:true",
        "missing_feature:set:true" if broken_effect else "delivery_ready:set:true",
        "QA:1:true",
    ])
    workbook["states"].append(["IMPORT-001", "START", "current", "Start", "prep_done:false;delivery_ready:false"])
    workbook["states"].append(["IMPORT-001", "TARGET", "target", "Target", "prep_done:true;delivery_ready:true"])
    workbook["solve_cases"].append(["FULL_FLOW", "IMPORT-001", "START", "TARGET", "minimize_makespan", "", "", 2, 25])
    workbook["instructions"].append(["example", "Fill sheets from left to right."])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _layered_scenario_workbook() -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "meta": ["scenario_code", "scenario_name", "version", "mode"],
        "feature_catalog": ["feature_key", "value_type", "allowed_values", "unit", "description"],
        "machine_type": ["code", "name", "description"],
        "machines": ["code", "machine_type_code", "name", "location"],
        "state_feature_defs": ["machine_type_code", "feature_key", "feature_name", "value_type", "allowed_values"],
        "resources": ["machine_code", "code", "name", "resource_type", "capacity", "is_available", "meta_json"],
        "activity_nodes": [
            "machine_type_code",
            "code",
            "parent_code",
            "level",
            "name",
            "activity_category",
            "sort_order",
            "is_active",
            "metadata_json",
        ],
        "state_nodes": [
            "machine_type_code",
            "code",
            "parent_code",
            "level",
            "name",
            "feature_key",
            "operator",
            "target_value",
            "state_kind",
            "sort_order",
            "is_active",
            "metadata_json",
        ],
        "scope_guards": [
            "machine_type_code",
            "activity_node_code",
            "name",
            "description",
            "is_active",
            "preconditions",
            "metadata_json",
        ],
        "rules": [
            "code",
            "machine_type_code",
            "name",
            "duration_min",
            "description",
            "is_active",
            "is_repair",
            "preconditions",
            "effects",
            "resource_reqs",
            "activity_node_code",
        ],
        "states": ["machine_code", "state_code", "state_type", "label", "features"],
        "solve_cases": [
            "case_code",
            "machine_code",
            "current_state_code",
            "target_state_code",
            "objective",
            "objectives_json",
            "constraints_json",
            "expected_min_steps",
            "expected_max_makespan_min",
        ],
        "instructions": ["section", "description"],
    }
    for name, header in sheets.items():
        sheet = workbook.create_sheet(name)
        sheet.append(header)

    workbook["meta"].append(["LAYERED_IMPORT", "Layered Import", "v1", "scenario_upsert"])
    workbook["feature_catalog"].append(["access", "enum", "no,yes", "", ""])
    workbook["feature_catalog"].append(["ready", "enum", "no,yes", "", ""])
    workbook["machine_type"].append(["LAYER_IMPORT_MACHINE", "Layer Import Machine", ""])
    workbook["machines"].append(["LAYER-001", "LAYER_IMPORT_MACHINE", "Layered Import 001", "Line L"])
    workbook["state_feature_defs"].append(["LAYER_IMPORT_MACHINE", "access", "Access", "enum", "no,yes"])
    workbook["state_feature_defs"].append(["LAYER_IMPORT_MACHINE", "ready", "Ready", "enum", "no,yes"])
    workbook["resources"].append(["LAYER-001", "TECH-LAYER-01", "Layer Tech 01", "TECHNICIAN", 1, "true", ""])

    workbook["activity_nodes"].append(["LAYER_IMPORT_MACHINE", "SYS", "", 1, "System", "normal", 0, "true", ""])
    workbook["activity_nodes"].append(["LAYER_IMPORT_MACHINE", "PREP_PACK", "SYS", 2, "Prep Pack", "normal", 10, "true", ""])
    workbook["activity_nodes"].append(["LAYER_IMPORT_MACHINE", "WORK_PACK", "SYS", 2, "Work Pack", "normal", 20, "true", ""])
    workbook["activity_nodes"].append(["LAYER_IMPORT_MACHINE", "PREP_STEP", "PREP_PACK", 3, "Prep Step", "normal", 10, "true", ""])
    workbook["activity_nodes"].append(["LAYER_IMPORT_MACHINE", "READY_STEP", "WORK_PACK", 3, "Ready Step", "normal", 20, "true", ""])

    workbook["state_nodes"].append(["LAYER_IMPORT_MACHINE", "DONE", "", 1, "Done", "", "", "", "aggregate", 0, "true", ""])
    workbook["state_nodes"].append(["LAYER_IMPORT_MACHINE", "DONE_GROUP", "DONE", 2, "Done Group", "", "", "", "aggregate", 0, "true", ""])
    workbook["state_nodes"].append(["LAYER_IMPORT_MACHINE", "ACCESS_YES", "DONE_GROUP", 3, "Access Yes", "access", "eq", "yes", "atomic", 10, "true", ""])
    workbook["state_nodes"].append(["LAYER_IMPORT_MACHINE", "READY_YES", "DONE_GROUP", 3, "Ready Yes", "ready", "eq", "yes", "atomic", 20, "true", ""])
    workbook["scope_guards"].append(["LAYER_IMPORT_MACHINE", "WORK_PACK", "Access required", "", "true", "ACCESS_YES:completed", ""])

    workbook["rules"].append([
        "OP_LAYER_IMPORT_ACCESS",
        "LAYER_IMPORT_MACHINE",
        "Provide Access",
        5,
        "",
        "true",
        "false",
        "",
        "access:set:yes",
        "TECHNICIAN:1:true",
        "PREP_STEP",
    ])
    workbook["rules"].append([
        "OP_LAYER_IMPORT_READY",
        "LAYER_IMPORT_MACHINE",
        "Provide Ready",
        7,
        "",
        "true",
        "false",
        "",
        "ready:set:yes",
        "TECHNICIAN:1:true",
        "READY_STEP",
    ])
    workbook["states"].append(["LAYER-001", "START", "current", "Start", "access:no;ready:no"])
    workbook["states"].append(["LAYER-001", "TARGET", "target", "Target", "access:yes;ready:yes"])
    workbook["solve_cases"].append(["LAYERED_FLOW", "LAYER-001", "START", "TARGET", "minimize_makespan", "", "", 2, 12])
    workbook["instructions"].append(["example", "Layered scenario import fixture."])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _layered_maintenance_scenario_workbook() -> bytes:
    workbook = load_workbook(BytesIO(_layered_scenario_workbook()))
    sheet = workbook.create_sheet("maintenance_intents")
    sheet.append([
        "machine_type_code",
        "issue_type",
        "name",
        "scope_activity_node_code",
        "description",
        "target_state_node_codes",
        "candidate_activity_scope_codes",
        "observed_fact_templates",
        "desired_fact_templates",
        "is_active",
        "metadata_json",
    ])
    sheet.append([
        "LAYER_IMPORT_MACHINE",
        "READY_REPAIR",
        "Ready Repair",
        "WORK_PACK",
        "Restore ready state through the minimal maintenance capability set.",
        "READY_YES",
        "PREP_PACK;WORK_PACK",
        "access:eq:no",
        "",
        "true",
        "",
    ])
    health_sheet = workbook.create_sheet("layered_health_checks")
    health_sheet.append([
        "machine_type_code",
        "check_code",
        "name",
        "target_state_node_codes",
        "activity_scope_node_codes",
        "include_inactive",
        "description",
    ])
    health_sheet.append([
        "LAYER_IMPORT_MACHINE",
        "READY_CHECK",
        "Ready layered health",
        "READY_YES",
        "PREP_PACK;WORK_PACK",
        "false",
        "Validate imported layered providers and Scope Guard chain.",
    ])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _large_scenario_workbook(rule_count: int = 105) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "meta": ["scenario_code", "scenario_name", "version", "mode"],
        "feature_catalog": ["feature_key", "value_type", "allowed_values", "unit", "description"],
        "machine_type": ["code", "name", "description"],
        "machines": ["code", "machine_type_code", "name", "location"],
        "state_feature_defs": ["machine_type_code", "feature_key", "feature_name", "value_type", "allowed_values"],
        "resources": ["machine_code", "code", "name", "resource_type", "capacity", "is_available", "meta_json"],
        "rules": [
            "code",
            "machine_type_code",
            "name",
            "duration_min",
            "description",
            "is_active",
            "is_repair",
            "preconditions",
            "effects",
            "resource_reqs",
        ],
        "states": ["machine_code", "state_code", "state_type", "label", "features"],
        "solve_cases": [
            "case_code",
            "machine_code",
            "current_state_code",
            "target_state_code",
            "objective",
            "objectives_json",
            "constraints_json",
            "expected_min_steps",
            "expected_max_makespan_min",
        ],
        "instructions": ["section", "description"],
    }
    for name, header in sheets.items():
        sheet = workbook.create_sheet(name)
        sheet.append(header)

    workbook["meta"].append(["LARGE_SCENARIO", "Large Scenario", "v1", "scenario_upsert"])
    workbook["machine_type"].append(["LARGE_MACHINE", "Large Machine", ""])
    workbook["machines"].append(["LARGE-001", "LARGE_MACHINE", "Large Test Machine", "Line L"])
    workbook["resources"].append(["LARGE-001", "TECH-LARGE-01", "Large Tech 01", "TECHNICIAN", 1, "true", ""])

    start_features = []
    target_features = []
    for index in range(rule_count):
        feature_key = f"step_{index:03d}_done"
        workbook["feature_catalog"].append([feature_key, "enum", "false,true", "", ""])
        workbook["state_feature_defs"].append(["LARGE_MACHINE", feature_key, feature_key, "enum", "false,true"])
        precondition = "" if index == 0 else f"step_{index - 1:03d}_done:eq:true"
        workbook["rules"].append([
            f"OP_LARGE_{index:03d}",
            "LARGE_MACHINE",
            f"Large Step {index:03d}",
            5,
            "",
            "true",
            "false",
            precondition,
            f"{feature_key}:set:true",
            "TECHNICIAN:1:true",
        ])
        start_features.append(f"{feature_key}:false")
        target_features.append(f"{feature_key}:true")

    workbook["states"].append(["LARGE-001", "START", "current", "Start", ";".join(start_features)])
    workbook["states"].append(["LARGE-001", "TARGET", "target", "Target", ";".join(target_features)])
    workbook["solve_cases"].append(["LARGE_FLOW", "LARGE-001", "START", "TARGET", "minimize_makespan", "", "", rule_count, rule_count * 5])
    workbook["instructions"].append(["example", "Large scenario dry-run fixture."])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _full_chain_complex_workbook() -> bytes:
    return FULL_CHAIN_SCENARIO_PATH.read_bytes()


async def _import_full_chain_complex_scenario(client) -> dict:
    content = _full_chain_complex_workbook()
    files = {
        "file": (
            "full_chain_complex_scenario.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "false"},
        files=files,
    )
    assert resp.status_code == 200
    imported = resp.json()
    assert imported["status"] == "imported", imported
    return imported


async def _full_chain_master_data(client) -> tuple[dict, dict, dict, dict]:
    machine_types_resp = await client.get("/api/v1/machine-types")
    assert machine_types_resp.status_code == 200
    machine_type = next(
        item for item in machine_types_resp.json()
        if item["code"] == "COMPLEX_ASSEMBLY_LINE"
    )
    machine_type_id = machine_type["id"]

    activity_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/activity-nodes")
    state_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/state-nodes")
    rules_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/op-rules")
    templates_resp = await client.get(
        f"/api/v1/machine-types/{machine_type_id}/maintenance-intent-templates"
    )
    assert activity_resp.status_code == 200
    assert state_resp.status_code == 200
    assert rules_resp.status_code == 200
    assert templates_resp.status_code == 200

    activities = {item["code"]: item for item in activity_resp.json()}
    states = {item["code"]: item for item in state_resp.json()}
    rules = {item["code"]: item for item in rules_resp.json()}
    templates = {item["issue_type"]: item for item in templates_resp.json()}
    return activities, states, rules, templates


def _op_codes(payload: dict) -> list[str]:
    return [task["op_rule_code"] for task in payload["schedule"]["tasks"]]


def _tasks_by_code(payload: dict, code: str) -> list[dict]:
    return [task for task in payload["schedule"]["tasks"] if task["op_rule_code"] == code]


@pytest.mark.asyncio
async def test_scenario_import_dry_run_import_and_solve(client):
    content = _scenario_workbook()
    files = {
        "file": (
            "scenario.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    data = {"mode": "scenario_upsert", "dry_run": "true"}
    resp = await client.post("/api/v1/imports/scenario", data=data, files=files)
    assert resp.status_code == 200
    dry_run = resp.json()
    assert dry_run["status"] == "validated"
    assert dry_run["summary"]["rules_total"] == 2
    assert dry_run["summary"]["error_count"] == 0
    assert dry_run["preview"]["rules"] == {"create": 2, "update": 0}

    files = {
        "file": (
            "scenario.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post("/api/v1/imports/scenario", data={"mode": "scenario_upsert", "dry_run": "false"}, files=files)
    assert resp.status_code == 200
    imported = resp.json()
    assert imported["status"] == "imported"
    solve_case = imported["solve_cases"][0]
    assert solve_case["machine_id"]
    assert solve_case["current_state_id"]
    assert solve_case["target_state_id"]

    solve_resp = await client.post("/api/v1/solve", json={
        "machine_id": solve_case["machine_id"],
        "current_state_id": solve_case["current_state_id"],
        "target_state_id": solve_case["target_state_id"],
        "objective": "minimize_makespan",
    })
    assert solve_resp.status_code == 200
    solve_data = solve_resp.json()
    assert solve_data["status"] == "done"
    assert solve_data["schedule"]["makespan"] == 25
    assert len(solve_data["schedule"]["tasks"]) == 2


@pytest.mark.asyncio
async def test_scenario_import_layered_nodes_rule_binding_and_layered_solve(client):
    content = _layered_scenario_workbook()
    files = {
        "file": (
            "layered.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    dry_run_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "true"},
        files=files,
    )
    assert dry_run_resp.status_code == 200
    dry_run = dry_run_resp.json()
    assert dry_run["status"] == "validated"
    assert dry_run["summary"]["activity_nodes_total"] == 5
    assert dry_run["summary"]["state_nodes_total"] == 4
    assert dry_run["summary"]["scope_guards_total"] == 1
    assert dry_run["preview"]["activity_nodes"] == {"create": 5, "update": 0}
    assert dry_run["preview"]["state_nodes"] == {"create": 4, "update": 0}
    assert dry_run["preview"]["scope_guards"] == {"create": 1, "update": 0}

    files = {
        "file": (
            "layered.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    import_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "false"},
        files=files,
    )
    assert import_resp.status_code == 200
    imported = import_resp.json()
    assert imported["status"] == "imported"
    solve_case = imported["solve_cases"][0]

    machine_types_resp = await client.get("/api/v1/machine-types")
    machine_type = next(item for item in machine_types_resp.json() if item["code"] == "LAYER_IMPORT_MACHINE")
    machine_type_id = machine_type["id"]

    activity_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/activity-nodes")
    activities = {item["code"]: item for item in activity_resp.json()}
    assert activities["PREP_STEP"]["level"] == 3
    assert activities["READY_STEP"]["level"] == 3

    rules_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/op-rules")
    rules = {item["code"]: item for item in rules_resp.json()}
    assert rules["OP_LAYER_IMPORT_ACCESS"]["activity_node_id"] == activities["PREP_STEP"]["id"]
    assert rules["OP_LAYER_IMPORT_READY"]["activity_node_id"] == activities["READY_STEP"]["id"]

    guard_resp = await client.get(f"/api/v1/activity-nodes/{activities['WORK_PACK']['id']}/scope-guards")
    guards = guard_resp.json()
    assert len(guards) == 1
    assert guards[0]["preconditions"][0]["state_node_code"] == "ACCESS_YES"

    state_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/state-nodes")
    states = {item["code"]: item for item in state_resp.json()}
    solve_resp = await client.post(
        "/api/v1/solve/layered",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_node_ids": [states["READY_YES"]["id"]],
            "activity_scope_node_ids": [
                activities["PREP_PACK"]["id"],
                activities["WORK_PACK"]["id"],
            ],
            "objectives": [
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_activity_group_span", "weight": 1.0},
            ],
        },
    )
    assert solve_resp.status_code == 200
    solve_data = solve_resp.json()
    assert solve_data["status"] == "done", solve_data
    assert [task["op_rule_code"] for task in solve_data["schedule"]["tasks"]] == [
        "OP_LAYER_IMPORT_ACCESS",
        "OP_LAYER_IMPORT_READY",
    ]
    assert solve_data["layered"]["state_replay"]["status"] == "ok"


@pytest.mark.asyncio
async def test_scenario_import_maintenance_intent_template_and_maintenance_solve(client):
    content = _layered_maintenance_scenario_workbook()
    files = {
        "file": (
            "layered-maintenance.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    dry_run_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "true"},
        files=files,
    )
    assert dry_run_resp.status_code == 200
    dry_run = dry_run_resp.json()
    assert dry_run["status"] == "validated"
    assert dry_run["summary"]["maintenance_intents_total"] == 1
    assert dry_run["summary"]["layered_health_checks_total"] == 1
    assert dry_run["preview"]["maintenance_intents"] == {"create": 1, "update": 0}
    assert dry_run["preview"]["layered_health_checks"] == {"create": 1, "update": 0}
    assert dry_run["post_import_health_checks"] == []

    files = {
        "file": (
            "layered-maintenance.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    import_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "false"},
        files=files,
    )
    assert import_resp.status_code == 200
    imported = import_resp.json()
    assert imported["status"] == "imported"
    assert imported["maintenance_intent_templates"][0]["issue_type"] == "READY_REPAIR"
    assert len(imported["post_import_health_checks"]) == 1
    health_check = imported["post_import_health_checks"][0]
    assert health_check["check_code"] == "READY_CHECK"
    assert health_check["status"] == "ok"
    assert health_check["summary"]["goal_fact_count"] == 1
    assert health_check["summary"]["effective_rule_count"] == 2
    assert health_check["blocking_count"] == 0
    assert health_check["diagnostics"] == []
    solve_case = imported["solve_cases"][0]

    machine_types_resp = await client.get("/api/v1/machine-types")
    machine_type = next(item for item in machine_types_resp.json() if item["code"] == "LAYER_IMPORT_MACHINE")
    machine_type_id = machine_type["id"]

    templates_resp = await client.get(f"/api/v1/machine-types/{machine_type_id}/maintenance-intent-templates")
    assert templates_resp.status_code == 200
    templates = {item["issue_type"]: item for item in templates_resp.json()}
    template = templates["READY_REPAIR"]
    assert template["target_state_node_ids"]
    assert len(template["candidate_activity_scope_ids"]) == 2
    assert template["observed_fact_templates"] == [
        {"feature_key": "access", "operator": "eq", "value": "no", "value_list": None}
    ]

    solve_resp = await client.post(
        "/api/v1/solve/maintenance",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "intent_template_ids": [template["id"]],
            "objective": "minimize_makespan",
        },
    )
    assert solve_resp.status_code == 200
    solve_data = solve_resp.json()
    assert solve_data["status"] == "done", solve_data
    assert solve_data["maintenance"]["merged_intent_count"] == 1
    assert [task["op_rule_code"] for task in solve_data["schedule"]["tasks"]] == [
        "OP_LAYER_IMPORT_ACCESS",
        "OP_LAYER_IMPORT_READY",
    ]

    files = {
        "file": (
            "layered-maintenance.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    update_preview_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "true"},
        files=files,
    )
    assert update_preview_resp.status_code == 200
    update_preview = update_preview_resp.json()
    assert update_preview["preview"]["maintenance_intents"] == {"create": 0, "update": 1}


@pytest.mark.asyncio
async def test_scenario_import_layered_validation_error_does_not_write(client):
    workbook = load_workbook(BytesIO(_layered_scenario_workbook()))
    workbook["activity_nodes"]["C3"] = "MISSING_PARENT"
    output = BytesIO()
    workbook.save(output)

    files = {
        "file": (
            "broken-layered.xlsx",
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "false"},
        files=files,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "failed"
    assert any(error["field"] == "parent_code" for error in payload["errors"])

    machine_types_resp = await client.get("/api/v1/machine-types")
    assert all(item["code"] != "LAYER_IMPORT_MACHINE" for item in machine_types_resp.json())


@pytest.mark.asyncio
async def test_scenario_import_validation_error_does_not_write(client):
    files = {
        "file": (
            "broken.xlsx",
            _scenario_workbook(broken_effect=True),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post("/api/v1/imports/scenario", data={"mode": "scenario_upsert", "dry_run": "false"}, files=files)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "failed"
    assert payload["summary"]["error_count"] >= 1
    assert any(error["field"] == "effects" for error in payload["errors"])

    machines_resp = await client.get("/api/v1/machines")
    assert machines_resp.status_code == 200
    assert machines_resp.json() == []


@pytest.mark.asyncio
async def test_scenario_import_dry_run_accepts_100_plus_rules(client):
    files = {
        "file": (
            "large.xlsx",
            _large_scenario_workbook(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post("/api/v1/imports/scenario", data={"mode": "scenario_upsert", "dry_run": "true"}, files=files)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "validated"
    assert payload["summary"]["rules_total"] == 105
    assert payload["summary"]["error_count"] == 0
    assert payload["preview"]["rules"] == {"create": 105, "update": 0}


@pytest.mark.asyncio
async def test_full_chain_complex_scenario_import_layered_maintenance_and_blockage(client):
    content = _full_chain_complex_workbook()
    files = {
        "file": (
            "full-chain-complex.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    dry_run_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "true"},
        files=files,
    )
    assert dry_run_resp.status_code == 200
    dry_run = dry_run_resp.json()
    assert dry_run["status"] == "validated", dry_run
    assert dry_run["summary"]["feature_catalog_total"] == 12
    assert dry_run["summary"]["activity_nodes_total"] == 21
    assert dry_run["summary"]["state_nodes_total"] == 20
    assert dry_run["summary"]["scope_guards_total"] == 6
    assert dry_run["summary"]["rules_total"] == 12
    assert dry_run["summary"]["maintenance_intents_total"] == 1
    assert dry_run["summary"]["layered_health_checks_total"] == 1
    assert dry_run["preview"]["rules"] == {"create": 12, "update": 0}
    assert dry_run["post_import_health_checks"] == []

    imported = await _import_full_chain_complex_scenario(client)
    assert imported["maintenance_intent_templates"][0]["issue_type"] == "SENSOR_FAULT"
    assert len(imported["post_import_health_checks"]) == 1
    health = imported["post_import_health_checks"][0]
    assert health["check_code"] == "FULL_CHAIN_DELIVERY_HEALTH"
    assert health["status"] == "ok", health
    assert health["summary"]["goal_fact_count"] >= 1
    assert health["blocking_count"] == 0

    solve_case = imported["solve_cases"][0]
    activities, states, rules, templates = await _full_chain_master_data(client)
    assert rules["OP_CAL_SPARE_FIXTURE_CHECK"]["is_active"] is False

    activity_scope_node_ids = [
        activities[code]["id"]
        for code in (
            "PREP_PACK",
            "MECH_PACK",
            "ELECTRIC_PACK",
            "HYDRAULIC_PACK",
            "CLEAN_PACK",
            "INTEGRATION_PACK",
            "QA_PACK",
            "DELIVERY_PACK",
        )
    ]
    layered_resp = await client.post(
        "/api/v1/solve/layered",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_node_ids": [
                states["DELIVERY_READY"]["id"],
            ],
            "activity_scope_node_ids": activity_scope_node_ids,
            "objectives": [
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_activity_group_span", "weight": 1.0},
                {"type": "minimize_activity_group_gaps", "weight": 1.0},
            ],
        },
    )
    assert layered_resp.status_code == 200
    layered = layered_resp.json()
    assert layered["status"] == "done", layered
    assert layered["layered"]["preflight_health"]["status"] == "ok"
    assert layered["layered"]["activity_tree"]
    assert layered["layered"]["state_tree"]
    assert layered["layered"]["activity_selection"]
    assert layered["layered"]["state_replay"]["status"] == "ok"

    layered_codes = _op_codes(layered)
    assert layered_codes.count("OP_CAL_COMMON_PREP") == 1
    assert "OP_CAL_SPARE_FIXTURE_CHECK" not in layered_codes
    assert len({task["step_order"] for task in layered["schedule"]["tasks"]}) == len(layered["schedule"]["tasks"])
    assert all(task["step_id"] is not None for task in layered["schedule"]["tasks"])
    assert layered["schedule"]["makespan"] <= 180
    assert any(
        item["op_rule_code"] == "OP_CAL_COMMON_PREP" and item.get("is_shared_provider")
        for item in layered["layered"]["activity_selection"]
    )
    integration_task = _tasks_by_code(layered, "OP_CAL_INTEGRATION")[0]
    assigned_types = {resource["resource_type"] for resource in integration_task["resources"]}
    assert {"technician", "fixture", "calibration_bench"} <= assigned_types

    maintenance_resp = await client.post(
        "/api/v1/solve/maintenance",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "intent_template_ids": [templates["SENSOR_FAULT"]["id"]],
            "objective": "minimize_makespan",
        },
    )
    assert maintenance_resp.status_code == 200
    maintenance = maintenance_resp.json()
    assert maintenance["status"] == "done", maintenance
    assert maintenance["maintenance"]["merged_intent_count"] == 1
    maintenance_codes = _op_codes(maintenance)
    assert "OP_CAL_REPAIR_SENSOR" in maintenance_codes
    assert maintenance["layered"]["preflight_health"]["status"] in {"ok", "blocked", "warning"}
    assert maintenance["layered"]["activity_selection"]

    base_resp = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_id": solve_case["target_state_id"],
            "objective": "minimize_makespan",
        },
    )
    assert base_resp.status_code == 200
    base = base_resp.json()
    assert base["status"] == "done", base
    base_clean_tasks = _tasks_by_code(base, "OP_CAL_CLEAN_INCREMENT")
    assert len(base_clean_tasks) == 4
    assert base["schedule"]["makespan"] <= 180
    blocked_clean_task = base_clean_tasks[1]

    strategy_a_resp = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_id": solve_case["target_state_id"],
            "objective": "minimize_makespan",
            "parent_plan_id": base["candidate_plan_id"],
            "blockage_constraints": {
                "strategy": "A",
                "blocked_step_id": blocked_clean_task["step_id"],
                "strategy_a": {"not_before_offset": 120},
            },
        },
    )
    assert strategy_a_resp.status_code == 200
    strategy_a = strategy_a_resp.json()
    assert strategy_a["status"] == "done", strategy_a
    delayed_clean = next(
        task for task in _tasks_by_code(strategy_a, "OP_CAL_CLEAN_INCREMENT")
        if task["step_order"] == blocked_clean_task["step_order"]
    )
    assert delayed_clean["not_before"] == 120
    assert delayed_clean["start_min"] >= 120

    strategy_b_resp = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_id": solve_case["target_state_id"],
            "objective": "minimize_makespan",
            "parent_plan_id": base["candidate_plan_id"],
            "blockage_constraints": {
                "strategy": "B",
                "strategy_b": {"blockage_reason": "sensor_fault"},
            },
        },
    )
    assert strategy_b_resp.status_code == 200
    strategy_b = strategy_b_resp.json()
    assert strategy_b["status"] == "done", strategy_b
    repair_tasks = _tasks_by_code(strategy_b, "OP_CAL_REPAIR_SENSOR")
    assert len(repair_tasks) == 1
    assert repair_tasks[0]["step_role"] == "repair"

    strategy_ab_resp = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": solve_case["machine_id"],
            "current_state_id": solve_case["current_state_id"],
            "target_state_id": solve_case["target_state_id"],
            "objective": "minimize_makespan",
            "parent_plan_id": base["candidate_plan_id"],
            "blockage_constraints": {
                "strategy": "AB",
                "blocked_step_id": blocked_clean_task["step_id"],
                "strategy_a": {"not_before_offset": 140},
                "strategy_b": {"blockage_reason": "sensor_fault"},
            },
        },
    )
    assert strategy_ab_resp.status_code == 200
    strategy_ab = strategy_ab_resp.json()
    assert strategy_ab["status"] == "done", strategy_ab
    assert len(_tasks_by_code(strategy_ab, "OP_CAL_REPAIR_SENSOR")) == 1
    blocked_after_ab = next(
        task for task in _tasks_by_code(strategy_ab, "OP_CAL_CLEAN_INCREMENT")
        if task["step_order"] == blocked_clean_task["step_order"]
    )
    assert blocked_after_ab["not_before"] == 140
    assert blocked_after_ab["start_min"] >= 140

    files = {
        "file": (
            "full-chain-complex.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    update_preview_resp = await client.post(
        "/api/v1/imports/scenario",
        data={"mode": "scenario_upsert", "dry_run": "true"},
        files=files,
    )
    assert update_preview_resp.status_code == 200
    update_preview = update_preview_resp.json()
    assert update_preview["preview"]["rules"] == {"create": 0, "update": 12}
    assert update_preview["preview"]["maintenance_intents"] == {"create": 0, "update": 1}


@pytest.mark.asyncio
async def test_scenario_template_download(client):
    resp = await client.get("/api/v1/imports/scenario-template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(resp.content) > 1000

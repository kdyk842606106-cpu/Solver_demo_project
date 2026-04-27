"""
Integration test for 007 Pump Body Mechanical Integration Seed.

Validates that the pump body seed produces the expected solver behavior:
- Main line operations are planned in correct dependency order
- Cleanliness generation constraints trigger exactly 2 chamber cleaning steps
- Branch operations are included and can parallelize with main line
- Resource constraints produce correct scheduling
- Critical path reflects the resource-contended longest chain
"""

import pytest


# ============================================================
# Pump Body Seed Data Helper
# ============================================================

async def _seed_pump_body_data(client):
    """Seed the full pump body integration scenario via API.

    Returns dict with: mt_id, machine_id, current_state_id, target_state_id,
    plus a mapping of op_rule_code -> id.
    """
    # 1) Machine type
    r = await client.post("/api/v1/machine-types", json={
        "code": "PUMP_BODY_INTEGRATION",
        "name": "Pump Body Mechanical Integration Cell",
        "description": "Pump body mechanical integration scenario with cleanliness and resource constraints",
    })
    assert r.status_code == 201, r.text
    mt_id = r.json()["id"]

    # 2) Feature definitions
    feature_defs = [
        {"feature_key": "pump_casing_status", "feature_name": "Pump Casing Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_impeller_status", "feature_name": "Pump Impeller Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_shaft_status", "feature_name": "Pump Shaft Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_seal_status", "feature_name": "Pump Seal Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_bearing_status", "feature_name": "Pump Bearing Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_coupling_status", "feature_name": "Pump Coupling Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_cooling_jacket_status", "feature_name": "Cooling Jacket Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_vibration_sensor_status", "feature_name": "Vibration Sensor Status",
         "value_type": "enum", "allowed_values": ["pending", "installed"]},
        {"feature_key": "pump_lubrication_line_status", "feature_name": "Lubrication Line Status",
         "value_type": "enum", "allowed_values": ["pending", "connected"]},
        {"feature_key": "pump_cleanliness_generation", "feature_name": "Chamber Cleanliness Generation",
         "value_type": "enum", "allowed_values": ["gen_0", "gen_1", "gen_2"]},
        {"feature_key": "pump_integration_test_status", "feature_name": "Integration Test Status",
         "value_type": "enum", "allowed_values": ["pending", "passed"]},
        {"feature_key": "pump_blockage_reason", "feature_name": "Blockage Reason",
         "value_type": "enum",
         "allowed_values": ["none", "seal_misalignment", "bearing_overheat",
                            "coupling_runout", "cooling_leak", "sensor_wiring_error"]},
    ]
    for fd in feature_defs:
        r = await client.post(
            f"/api/v1/machine-types/{mt_id}/feature-defs",
            json={"machine_type_id": mt_id, **fd},
        )
        assert r.status_code == 201, r.text

    # 3) Machine instance
    r = await client.post("/api/v1/machines", json={
        "machine_type_id": mt_id,
        "code": "PMP-BDY-001",
        "name": "Pump Body Assembly Station #1",
        "location": "Workshop B - Precision Assembly Line",
    })
    assert r.status_code == 201, r.text
    machine_id = r.json()["id"]

    # 4) Resources
    resources = [
        {"code": "PMP-MEA-01", "name": "Pump Mechanical Team A",
         "resource_type": "PUMP_MECH_TEAM_A", "capacity": 1, "is_available": True,
         "meta": {"skill": "casing_impeller_bearing"}},
        {"code": "PMP-MEB-01", "name": "Pump Mechanical Team B",
         "resource_type": "PUMP_MECH_TEAM_B", "capacity": 1, "is_available": True,
         "meta": {"skill": "shaft_seal_coupling"}},
        {"code": "PMP-PRS-01", "name": "Pump Precision Instrument Team",
         "resource_type": "PUMP_PRECISION_TEAM", "capacity": 1, "is_available": True,
         "meta": {"skill": "sensor_integration_test"}},
        {"code": "PMP-COL-01", "name": "Pump Cooling System Tech",
         "resource_type": "PUMP_COOLING_TECH", "capacity": 1, "is_available": True,
         "meta": {"skill": "cooling_lubrication"}},
        {"code": "PMP-CLN-01", "name": "Pump Chamber Cleaning Crew",
         "resource_type": "PUMP_CLEANING_CREW", "capacity": 1, "is_available": True,
         "meta": {"skill": "chamber_cleaning"}},
        {"code": "PMP-QA-01", "name": "Pump QA Inspector",
         "resource_type": "PUMP_QA_INSPECTOR", "capacity": 1, "is_available": True,
         "meta": {"skill": "final_test"}},
        {"code": "PMP-RPR-01", "name": "Pump Repair Team",
         "resource_type": "PUMP_REPAIR_TEAM", "capacity": 1, "is_available": True,
         "meta": {"skill": "fault_recovery"}},
    ]
    for res in resources:
        r = await client.post("/api/v1/resources", json=res)
        assert r.status_code == 201, r.text

    # 5) States
    # Current state: all pending, cleanliness gen_0
    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "current",
        "label": "Pump Body Assembly Start State",
        "features": {
            "pump_casing_status": "pending",
            "pump_impeller_status": "pending",
            "pump_shaft_status": "pending",
            "pump_seal_status": "pending",
            "pump_bearing_status": "pending",
            "pump_coupling_status": "pending",
            "pump_cooling_jacket_status": "pending",
            "pump_vibration_sensor_status": "pending",
            "pump_lubrication_line_status": "pending",
            "pump_cleanliness_generation": "gen_0",
            "pump_integration_test_status": "pending",
            "pump_blockage_reason": "none",
        },
    })
    assert r.status_code == 201, r.text
    current_state_id = r.json()["state_id"]

    # Target state: all installed/connected/passed, cleanliness gen_2
    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Pump Body Assembly Ready for Delivery",
        "features": {
            "pump_casing_status": "installed",
            "pump_impeller_status": "installed",
            "pump_shaft_status": "installed",
            "pump_seal_status": "installed",
            "pump_bearing_status": "installed",
            "pump_coupling_status": "installed",
            "pump_cooling_jacket_status": "installed",
            "pump_vibration_sensor_status": "installed",
            "pump_lubrication_line_status": "connected",
            "pump_cleanliness_generation": "gen_2",
            "pump_integration_test_status": "passed",
            "pump_blockage_reason": "none",
        },
    })
    assert r.status_code == 201, r.text
    target_state_id = r.json()["state_id"]

    # 6) Operation rules helper
    async def add_rule(code, name, duration, preconditions, effects,
                       resource_types, is_repair=False):
        resource_reqs = [
            {"resource_type": rt, "quantity": 1, "is_required": True}
            for rt in resource_types
        ]
        r = await client.post(f"/api/v1/machine-types/{mt_id}/op-rules", json={
            "machine_type_id": mt_id,
            "code": code,
            "name": name,
            "duration_min": duration,
            "is_active": True,
            "is_repair": is_repair,
            "preconditions": preconditions,
            "effects": effects,
            "resource_reqs": resource_reqs,
        })
        assert r.status_code == 201, r.text
        return r.json()["id"]

    op_ids = {}

    # Main line normal operations
    op_ids["OP_PMP_810_INSTALL_CASING"] = await add_rule(
        "OP_PMP_810_INSTALL_CASING", "Install Pump Casing", 90,
        [{"feature_key": "pump_casing_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_casing_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_A"],
    )
    op_ids["OP_PMP_820_INSTALL_IMPELLER"] = await add_rule(
        "OP_PMP_820_INSTALL_IMPELLER", "Install Impeller", 75,
        [{"feature_key": "pump_casing_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_impeller_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_impeller_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_A"],
    )
    op_ids["OP_PMP_830_INSTALL_SHAFT"] = await add_rule(
        "OP_PMP_830_INSTALL_SHAFT", "Install Shaft Assembly", 85,
        [{"feature_key": "pump_impeller_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_shaft_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_shaft_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_B"],
    )
    op_ids["OP_PMP_835_CLEAN_CHAMBER_FIRST"] = await add_rule(
        "OP_PMP_835_CLEAN_CHAMBER_FIRST", "First Chamber Cleaning", 40,
        [{"feature_key": "pump_shaft_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_0"}],
        [{"feature_key": "pump_cleanliness_generation", "new_value": "gen_1"}],
        ["PUMP_CLEANING_CREW"],
    )
    op_ids["OP_PMP_840_INSTALL_SEAL"] = await add_rule(
        "OP_PMP_840_INSTALL_SEAL", "Install Mechanical Seal", 70,
        [{"feature_key": "pump_shaft_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_seal_status", "operator": "eq", "feature_value": "pending"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_1"}],
        [{"feature_key": "pump_seal_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_B"],
    )
    op_ids["OP_PMP_850_INSTALL_BEARING"] = await add_rule(
        "OP_PMP_850_INSTALL_BEARING", "Install Bearing Housing", 80,
        [{"feature_key": "pump_seal_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_bearing_status", "operator": "eq", "feature_value": "pending"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_1"}],
        [{"feature_key": "pump_bearing_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_A"],
    )
    op_ids["OP_PMP_855_CLEAN_CHAMBER_SECOND"] = await add_rule(
        "OP_PMP_855_CLEAN_CHAMBER_SECOND", "Second Chamber Cleaning", 40,
        [{"feature_key": "pump_coupling_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_1"}],
        [{"feature_key": "pump_cleanliness_generation", "new_value": "gen_2"}],
        ["PUMP_CLEANING_CREW"],
    )
    op_ids["OP_PMP_860_INSTALL_COUPLING"] = await add_rule(
        "OP_PMP_860_INSTALL_COUPLING", "Install Drive Coupling", 60,
        [{"feature_key": "pump_bearing_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_coupling_status", "operator": "eq", "feature_value": "pending"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_1"}],
        [{"feature_key": "pump_coupling_status", "new_value": "installed"}],
        ["PUMP_MECH_TEAM_B"],
    )
    op_ids["OP_PMP_890_INTEGRATION_TEST"] = await add_rule(
        "OP_PMP_890_INTEGRATION_TEST", "Final Integration Test", 50,
        [{"feature_key": "pump_coupling_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_cooling_jacket_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_vibration_sensor_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_lubrication_line_status", "operator": "eq", "feature_value": "connected"},
         {"feature_key": "pump_cleanliness_generation", "operator": "eq", "feature_value": "gen_2"},
         {"feature_key": "pump_integration_test_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_integration_test_status", "new_value": "passed"}],
        ["PUMP_QA_INSPECTOR", "PUMP_PRECISION_TEAM"],
    )

    # Branch operations
    op_ids["OP_PMP_870_INSTALL_COOLING"] = await add_rule(
        "OP_PMP_870_INSTALL_COOLING", "Install Cooling Jacket", 55,
        [{"feature_key": "pump_casing_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_cooling_jacket_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_cooling_jacket_status", "new_value": "installed"}],
        ["PUMP_COOLING_TECH"],
    )
    op_ids["OP_PMP_880_INSTALL_VIBRATION"] = await add_rule(
        "OP_PMP_880_INSTALL_VIBRATION", "Install Vibration Sensor", 35,
        [{"feature_key": "pump_impeller_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_vibration_sensor_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_vibration_sensor_status", "new_value": "installed"}],
        ["PUMP_PRECISION_TEAM"],
    )
    op_ids["OP_PMP_885_CONNECT_LUBRICATION"] = await add_rule(
        "OP_PMP_885_CONNECT_LUBRICATION", "Connect Lubrication Lines", 45,
        [{"feature_key": "pump_bearing_status", "operator": "eq", "feature_value": "installed"},
         {"feature_key": "pump_lubrication_line_status", "operator": "eq", "feature_value": "pending"}],
        [{"feature_key": "pump_lubrication_line_status", "new_value": "connected"}],
        ["PUMP_COOLING_TECH"],
    )

    # Repair operations
    op_ids["OP_PMP_9R0_REPAIR_SEAL"] = await add_rule(
        "OP_PMP_9R0_REPAIR_SEAL", "Repair Seal Misalignment", 50,
        [{"feature_key": "pump_blockage_reason", "operator": "eq", "feature_value": "seal_misalignment"}],
        [{"feature_key": "pump_blockage_reason", "new_value": "none"}],
        ["PUMP_REPAIR_TEAM"], is_repair=True,
    )
    op_ids["OP_PMP_9R1_REPAIR_BEARING"] = await add_rule(
        "OP_PMP_9R1_REPAIR_BEARING", "Repair Bearing Overheat", 60,
        [{"feature_key": "pump_blockage_reason", "operator": "eq", "feature_value": "bearing_overheat"}],
        [{"feature_key": "pump_blockage_reason", "new_value": "none"}],
        ["PUMP_REPAIR_TEAM"], is_repair=True,
    )
    op_ids["OP_PMP_9R2_REPAIR_COUPLING"] = await add_rule(
        "OP_PMP_9R2_REPAIR_COUPLING", "Repair Coupling Runout", 45,
        [{"feature_key": "pump_blockage_reason", "operator": "eq", "feature_value": "coupling_runout"}],
        [{"feature_key": "pump_blockage_reason", "new_value": "none"}],
        ["PUMP_REPAIR_TEAM"], is_repair=True,
    )
    op_ids["OP_PMP_9R3_REPAIR_COOLING"] = await add_rule(
        "OP_PMP_9R3_REPAIR_COOLING", "Repair Cooling Leak", 40,
        [{"feature_key": "pump_blockage_reason", "operator": "eq", "feature_value": "cooling_leak"}],
        [{"feature_key": "pump_blockage_reason", "new_value": "none"}],
        ["PUMP_REPAIR_TEAM"], is_repair=True,
    )
    op_ids["OP_PMP_9R4_REPAIR_SENSOR"] = await add_rule(
        "OP_PMP_9R4_REPAIR_SENSOR", "Repair Sensor Wiring Error", 30,
        [{"feature_key": "pump_blockage_reason", "operator": "eq", "feature_value": "sensor_wiring_error"}],
        [{"feature_key": "pump_blockage_reason", "new_value": "none"}],
        ["PUMP_REPAIR_TEAM"], is_repair=True,
    )

    return {
        "mt_id": mt_id,
        "machine_id": machine_id,
        "current_state_id": current_state_id,
        "target_state_id": target_state_id,
        "op_ids": op_ids,
    }


# ============================================================
# Test Class
# ============================================================

class TestPumpBodyIntegrationSeed:
    """End-to-end validation of the pump body seed through the solver."""

    @pytest.mark.asyncio
    async def test_solve_produces_valid_plan(self, client):
        """The solver should produce a feasible/optimal plan for pump body."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "done", f"Solve failed: {body.get('error_message')}"
        assert body["candidate_plan_id"] is not None
        assert body["schedule"]["makespan"] > 0

    @pytest.mark.asyncio
    async def test_main_line_operations_present(self, client):
        """All main line operations (including 2 cleans) must appear in plan."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        codes = [t["op_rule_code"] for t in body["schedule"]["tasks"]]
        main_line = [
            "OP_PMP_810_INSTALL_CASING",
            "OP_PMP_820_INSTALL_IMPELLER",
            "OP_PMP_830_INSTALL_SHAFT",
            "OP_PMP_835_CLEAN_CHAMBER_FIRST",
            "OP_PMP_840_INSTALL_SEAL",
            "OP_PMP_850_INSTALL_BEARING",
            "OP_PMP_855_CLEAN_CHAMBER_SECOND",
            "OP_PMP_860_INSTALL_COUPLING",
            "OP_PMP_890_INTEGRATION_TEST",
        ]
        for code in main_line:
            assert code in codes, f"Main line operation {code} missing from plan"

    @pytest.mark.asyncio
    async def test_branch_operations_present(self, client):
        """All 3 branch operations must appear in plan."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        codes = [t["op_rule_code"] for t in body["schedule"]["tasks"]]
        branch = [
            "OP_PMP_870_INSTALL_COOLING",
            "OP_PMP_880_INSTALL_VIBRATION",
            "OP_PMP_885_CONNECT_LUBRICATION",
        ]
        for code in branch:
            assert code in codes, f"Branch operation {code} missing from plan"

    @pytest.mark.asyncio
    async def test_cleanliness_steps_count(self, client):
        """Exactly 2 chamber cleaning steps must be present."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        clean_codes = [
            t["op_rule_code"] for t in body["schedule"]["tasks"]
            if "CLEAN_CHAMBER" in t["op_rule_code"]
        ]
        assert len(clean_codes) == 2, (
            f"Expected 2 cleaning steps, got {len(clean_codes)}: {clean_codes}"
        )

    @pytest.mark.asyncio
    async def test_main_line_dependency_order(self, client):
        """Main line operations must respect the dependency chain."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        tasks = {t["op_rule_code"]: t for t in body["schedule"]["tasks"]}

        # Casing before Impeller
        assert tasks["OP_PMP_810_INSTALL_CASING"]["end_min"] <= tasks["OP_PMP_820_INSTALL_IMPELLER"]["start_min"]
        # Impeller before Shaft
        assert tasks["OP_PMP_820_INSTALL_IMPELLER"]["end_min"] <= tasks["OP_PMP_830_INSTALL_SHAFT"]["start_min"]
        # Shaft before Clean 1
        assert tasks["OP_PMP_830_INSTALL_SHAFT"]["end_min"] <= tasks["OP_PMP_835_CLEAN_CHAMBER_FIRST"]["start_min"]
        # Clean 1 before Seal
        assert tasks["OP_PMP_835_CLEAN_CHAMBER_FIRST"]["end_min"] <= tasks["OP_PMP_840_INSTALL_SEAL"]["start_min"]
        # Seal before Bearing
        assert tasks["OP_PMP_840_INSTALL_SEAL"]["end_min"] <= tasks["OP_PMP_850_INSTALL_BEARING"]["start_min"]
        # Bearing before Coupling
        assert tasks["OP_PMP_850_INSTALL_BEARING"]["end_min"] <= tasks["OP_PMP_860_INSTALL_COUPLING"]["start_min"]
        # Coupling before Clean 2
        assert tasks["OP_PMP_860_INSTALL_COUPLING"]["end_min"] <= tasks["OP_PMP_855_CLEAN_CHAMBER_SECOND"]["start_min"]
        # Clean 2 before Test
        assert tasks["OP_PMP_855_CLEAN_CHAMBER_SECOND"]["end_min"] <= tasks["OP_PMP_890_INTEGRATION_TEST"]["start_min"]

    @pytest.mark.asyncio
    async def test_resource_constraints_mechanical_a(self, client):
        """Mechanical Team A operations [1,2,5] must be sequential (capacity=1)."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        tasks = {t["op_rule_code"]: t for t in body["schedule"]["tasks"]}
        mech_a_ops = [
            "OP_PMP_810_INSTALL_CASING",
            "OP_PMP_820_INSTALL_IMPELLER",
            "OP_PMP_850_INSTALL_BEARING",
        ]
        # With capacity=1, these should not overlap
        for i in range(len(mech_a_ops) - 1):
            op1 = mech_a_ops[i]
            op2 = mech_a_ops[i + 1]
            assert tasks[op1]["end_min"] <= tasks[op2]["start_min"], (
                f"{op1} and {op2} overlap but share PUMP_MECH_TEAM_A (capacity=1)"
            )

    @pytest.mark.asyncio
    async def test_resource_constraints_mechanical_b(self, client):
        """Mechanical Team B operations [3,4,6] must be sequential (capacity=1)."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        tasks = {t["op_rule_code"]: t for t in body["schedule"]["tasks"]}
        mech_b_ops = [
            "OP_PMP_830_INSTALL_SHAFT",
            "OP_PMP_840_INSTALL_SEAL",
            "OP_PMP_860_INSTALL_COUPLING",
        ]
        for i in range(len(mech_b_ops) - 1):
            op1 = mech_b_ops[i]
            op2 = mech_b_ops[i + 1]
            assert tasks[op1]["end_min"] <= tasks[op2]["start_min"], (
                f"{op1} and {op2} overlap but share PUMP_MECH_TEAM_B (capacity=1)"
            )

    @pytest.mark.asyncio
    async def test_branch_parallel_potential(self, client):
        """Branch cooling jacket should start after casing but can overlap with later main line."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        tasks = {t["op_rule_code"]: t for t in body["schedule"]["tasks"]}
        # Cooling starts after casing
        assert tasks["OP_PMP_810_INSTALL_CASING"]["end_min"] <= tasks["OP_PMP_870_INSTALL_COOLING"]["start_min"]
        # Cooling can in theory overlap with impeller/shaft (no shared resources)
        # We verify it's not forced to wait for impeller (predecessor check)
        assert "OP_PMP_820_INSTALL_IMPELLER" not in tasks["OP_PMP_870_INSTALL_COOLING"].get("predecessors", [])

    @pytest.mark.asyncio
    async def test_critical_path_not_empty(self, client):
        """Critical path should be computed and non-empty."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        cp = body.get("critical_path", [])
        assert len(cp) > 0, "Critical path should not be empty"
        # Last element should be the integration test (final step)
        assert cp[-1] == "OP_PMP_890_INTEGRATION_TEST", (
            f"Expected critical path to end with integration test, got {cp[-1]}"
        )

    @pytest.mark.asyncio
    async def test_makespan_reasonable(self, client):
        """Makespan should account for the main line + resource contention."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        makespan = body["schedule"]["makespan"]
        # Minimum possible (all main line sequential): 90+75+85+40+70+80+40+60+50 = 590
        min_possible = 590
        assert makespan >= min_possible, (
            f"Makespan {makespan} is less than minimum possible {min_possible}"
        )
        # With branches adding some parallel overlap, should not exceed a loose upper bound
        assert makespan <= 900, (
            f"Makespan {makespan} exceeds reasonable upper bound of 900 minutes"
        )

    @pytest.mark.asyncio
    async def test_state_delta_reported(self, client):
        """State delta should list all changed features."""
        seed = await _seed_pump_body_data(client)

        r = await client.post("/api/v1/solve", json={
            "machine_id": seed["machine_id"],
            "current_state_id": seed["current_state_id"],
            "target_state_id": seed["target_state_id"],
        })
        body = r.json()
        assert body["status"] == "done"

        delta = body.get("state_delta", [])
        delta_keys = {d["feature_key"] for d in delta}
        # At minimum, these should appear
        assert "pump_casing_status" in delta_keys
        assert "pump_integration_test_status" in delta_keys
        assert "pump_cleanliness_generation" in delta_keys
        assert len(delta) >= 5, f"Expected meaningful state delta, got {delta}"

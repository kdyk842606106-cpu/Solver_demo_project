"""
Integration tests for STEP 3 API extensions.

Tests:
- POST /api/v1/solve — enriched response (state_delta, critical_path, step_role, not_before)
- GET /api/v1/plans/{id}/versions — version chain query
- GET /api/v1/plans/{id}/diff/{other_id} — step-level diff
- PLAN_NOT_SCHEDULED dual coverage (ANCHOR constraint 9)
- blockage_constraints=None zero-intrusion regression (ANCHOR constraint 2)
"""

import pytest


# ============================================================
# Shared seed helper (reused across test classes)
# ============================================================

async def _seed_base_data(client):
    """Create machine type, features, machine, resources, states, and op-rules.

    Returns a dict with key IDs used by test methods.
    """
    # Machine type
    r = await client.post("/api/v1/machine-types", json={
        "code": "CNC_TEST", "name": "CNC Test", "description": "Test type",
    })
    assert r.status_code == 201
    mt_id = r.json()["id"]

    # Feature definitions
    for item in [
        {"feature_key": "temperature_level", "feature_name": "Temperature",
         "value_type": "enum", "allowed_values": ["cold", "hot"]},
        {"feature_key": "clean_level", "feature_name": "Cleanliness",
         "value_type": "enum", "allowed_values": ["dirty", "clean"]},
        {"feature_key": "calibration", "feature_name": "Calibration",
         "value_type": "enum", "allowed_values": ["off", "on"]},
    ]:
        r = await client.post(
            f"/api/v1/machine-types/{mt_id}/feature-defs",
            json={"machine_type_id": mt_id, **item},
        )
        assert r.status_code == 201

    # Machine
    r = await client.post("/api/v1/machines", json={
        "machine_type_id": mt_id, "code": "M-T01",
        "name": "Test Machine", "location": "Lab",
    })
    assert r.status_code == 201
    machine_id = r.json()["id"]

    # Resources
    for res in [
        {"machine_id": machine_id, "code": "TECH-01", "name": "Tech Alice", "resource_type": "TECHNICIAN",
         "capacity": 1, "is_available": True, "meta": None},
        {"machine_id": machine_id, "code": "TECH-02", "name": "Tech Bob", "resource_type": "TECHNICIAN",
         "capacity": 1, "is_available": True, "meta": None},
        {"machine_id": machine_id, "code": "CLEAN-01", "name": "Cleaner", "resource_type": "CLEANER",
         "capacity": 1, "is_available": True, "meta": None},
    ]:
        r = await client.post("/api/v1/resources", json=res)
        assert r.status_code == 201

    # Current state: cold / dirty / off
    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id, "state_type": "current", "label": "Cold Standby",
        "features": {"temperature_level": "cold", "clean_level": "dirty", "calibration": "off"},
    })
    assert r.status_code == 201
    current_state_id = r.json()["state_id"]

    # Target state: hot / clean / on
    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id, "state_type": "target", "label": "Ready for Production",
        "features": {"temperature_level": "hot", "clean_level": "clean", "calibration": "on"},
    })
    assert r.status_code == 201
    target_state_id = r.json()["state_id"]

    # Op rules
    async def add_rule(code, name, duration, preconditions, effects, resource_type,
                       is_repair=False):
        r = await client.post(f"/api/v1/machine-types/{mt_id}/op-rules", json={
            "machine_type_id": mt_id, "code": code, "name": name,
            "duration_min": duration, "is_active": True, "is_repair": is_repair,
            "preconditions": preconditions,
            "effects": effects,
            "resource_reqs": [{"resource_type": resource_type, "quantity": 1,
                               "is_required": True}],
        })
        assert r.status_code == 201, r.text
        return r.json()["id"]

    await add_rule(
        "OP_WARMUP", "Warm Up", 30,
        [{"feature_key": "temperature_level", "operator": "eq",
          "feature_value": "cold"}],
        [{"feature_key": "temperature_level", "new_value": "hot",
          "effect_type": "set"}],
        "TECHNICIAN",
    )
    await add_rule(
        "OP_CLEANING", "Clean", 20,
        [{"feature_key": "clean_level", "operator": "eq", "feature_value": "dirty"}],
        [{"feature_key": "clean_level", "new_value": "clean", "effect_type": "set"}],
        "CLEANER",
    )
    await add_rule(
        "OP_CALIBRATE", "Calibrate", 15,
        [
            {"feature_key": "temperature_level", "operator": "eq",
             "feature_value": "hot"},
            {"feature_key": "calibration", "operator": "eq",
             "feature_value": "off"},
        ],
        [{"feature_key": "calibration", "new_value": "on", "effect_type": "set"}],
        "TECHNICIAN",
    )

    return {
        "machine_type_id": mt_id,
        "machine_id": machine_id,
        "current_state_id": current_state_id,
        "target_state_id": target_state_id,
    }


async def _seed_numeric_api_data(client):
    """Create numeric planning data through APIs for solve response tests."""
    r = await client.post("/api/v1/machine-types", json={
        "code": "NUMERIC_API", "name": "Numeric API Machine", "description": "Numeric API test",
    })
    assert r.status_code == 201
    mt_id = r.json()["id"]

    for item in [
        {"feature_key": "water_level", "feature_name": "Water", "value_type": "number", "allowed_values": None},
        {"feature_key": "pressure", "feature_name": "Pressure", "value_type": "number", "allowed_values": None},
        {"feature_key": "calibration", "feature_name": "Calibration", "value_type": "enum", "allowed_values": ["off", "on"]},
    ]:
        r = await client.post(
            f"/api/v1/machine-types/{mt_id}/feature-defs",
            json={"machine_type_id": mt_id, **item},
        )
        assert r.status_code == 201, r.text

    r = await client.post("/api/v1/machines", json={
        "machine_type_id": mt_id, "code": "M-NAPI-01", "name": "Numeric API Machine", "location": "Lab",
    })
    assert r.status_code == 201
    machine_id = r.json()["id"]

    for res in [
        {"machine_id": machine_id, "code": "TECH-N1", "name": "Tech One", "resource_type": "TECHNICIAN", "capacity": 1, "is_available": True, "meta": None},
        {"machine_id": machine_id, "code": "TECH-N2", "name": "Tech Two", "resource_type": "TECHNICIAN", "capacity": 1, "is_available": True, "meta": None},
    ]:
        r = await client.post("/api/v1/resources", json=res)
        assert r.status_code == 201

    async def add_rule(code, name, duration, preconditions, effects):
        r = await client.post(f"/api/v1/machine-types/{mt_id}/op-rules", json={
            "machine_type_id": mt_id,
            "code": code,
            "name": name,
            "duration_min": duration,
            "is_active": True,
            "preconditions": preconditions,
            "effects": effects,
            "resource_reqs": [{"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}],
        })
        assert r.status_code == 201, r.text
        return r.json()["id"]

    fill_rule_id = await add_rule(
        "OP_FILL_WATER",
        "Fill Water",
        5,
        [{"feature_key": "pressure", "operator": "gte", "feature_value": "2"}],
        [{"feature_key": "water_level", "new_value": "1", "effect_type": "increment", "delta_value": 20}],
    )
    await add_rule(
        "OP_PRESSURIZE",
        "Pressurize",
        3,
        [],
        [{"feature_key": "pressure", "new_value": "1", "effect_type": "increment", "delta_value": 1}],
    )
    await add_rule(
        "OP_CALIBRATE_NUM",
        "Calibrate Numeric",
        8,
        [{"feature_key": "calibration", "operator": "eq", "feature_value": "off"}],
        [{"feature_key": "calibration", "new_value": "on", "effect_type": "set"}],
    )

    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "current",
        "label": "Numeric Current",
        "features": {"water_level": "0", "pressure": "0", "calibration": "off"},
    })
    assert r.status_code == 201
    current_state_id = r.json()["state_id"]

    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Numeric Target",
        "features": {"water_level": "40", "pressure": "0", "calibration": "off"},
    })
    assert r.status_code == 201
    target_state_id = r.json()["state_id"]

    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Numeric Mixed Target",
        "features": {"water_level": "40", "pressure": "0", "calibration": "on"},
    })
    assert r.status_code == 201
    mixed_target_state_id = r.json()["state_id"]

    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Numeric Unreachable Target",
        "features": {"water_level": "25", "pressure": "0", "calibration": "off"},
    })
    assert r.status_code == 201
    unreachable_target_state_id = r.json()["state_id"]

    return {
        "machine_type_id": mt_id,
        "machine_id": machine_id,
        "current_state_id": current_state_id,
        "target_state_id": target_state_id,
        "mixed_target_state_id": mixed_target_state_id,
        "unreachable_target_state_id": unreachable_target_state_id,
        "fill_rule_id": fill_rule_id,
    }


async def _do_solve(client, ids, **extra):
    """POST /api/v1/solve with standard params, return response JSON."""
    payload = {
        "machine_id": ids["machine_id"],
        "current_state_id": ids["current_state_id"],
        "target_state_id": ids["target_state_id"],
        "objective": "minimize_makespan",
    }
    payload.update(extra)
    r = await client.post("/api/v1/solve", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================
# Test: enriched POST /solve response
# ============================================================


class TestSolveEnrichedResponse:
    """Verify that POST /solve returns the new state_delta, critical_path,
    and per-step not_before / step_role fields."""

    @pytest.mark.asyncio
    async def test_initial_solve_has_state_delta(self, client):
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        state_delta = data.get("state_delta")
        assert isinstance(state_delta, list)
        assert len(state_delta) == 3  # temperature_level, clean_level, calibration
        keys = {d["feature_key"] for d in state_delta}
        assert keys == {"temperature_level", "clean_level", "calibration"}
        for d in state_delta:
            assert "from_value" in d and "to_value" in d

    @pytest.mark.asyncio
    async def test_initial_solve_has_critical_path(self, client):
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        critical_path = data.get("critical_path")
        assert isinstance(critical_path, list)
        assert len(critical_path) >= 1
        # critical path must contain valid op_codes
        task_codes = {t["op_rule_code"] for t in data["schedule"]["tasks"]}
        for code in critical_path:
            assert code in task_codes

    @pytest.mark.asyncio
    async def test_initial_solve_tasks_have_step_role_and_not_before(self, client):
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        tasks = data["schedule"]["tasks"]
        assert len(tasks) >= 1
        for t in tasks:
            assert "step_role" in t, f"task {t} missing step_role"
            assert "not_before" in t, f"task {t} missing not_before"
            # Initial solve: no parent, so all roles should be 'normal'
            assert t["step_role"] == "normal", \
                f"Expected normal, got {t['step_role']} for {t['op_rule_code']}"
            assert t["not_before"] is None

    @pytest.mark.asyncio
    async def test_strategy_a_produces_delayed_or_pulled_forward(self, client):
        ids = await _seed_base_data(client)

        # Initial solve to get a plan
        initial = await _do_solve(client, ids)
        assert initial["status"] == "done"
        plan_id = initial["candidate_plan_id"]

        # Find OP_CALIBRATE task from the initial solve result
        tasks = initial["schedule"]["tasks"]
        calibrate_task = next(
            (t for t in tasks if t["op_rule_code"] == "OP_CALIBRATE"), None
        )
        assert calibrate_task is not None

        # Re-solve with strategy A using blocked_op_rule_id (the correct frontend path).
        # This verifies the full not_before constraint pipeline end-to-end.
        replan = await _do_solve(client, ids,
            parent_plan_id=plan_id,
            blockage_constraints={
                "strategy": "A",
                "blocked_op_rule_id": calibrate_task["op_rule_id"],
                "strategy_a": {"not_before_offset": 120},
            },
        )
        assert replan["status"] == "done"

        # After replan, state_delta should still be present
        assert isinstance(replan.get("state_delta"), list)
        assert len(replan["state_delta"]) == 3

        # Verify not_before constraint was applied to the blocked step
        replan_tasks = replan["schedule"]["tasks"]
        replan_calibrate = next(
            (t for t in replan_tasks if t["op_rule_code"] == "OP_CALIBRATE"), None
        )
        assert replan_calibrate is not None

        # The blocked step's not_before must be set in the response
        assert replan_calibrate["not_before"] == 120, (
            f"Expected not_before=120 on OP_CALIBRATE, got {replan_calibrate['not_before']}"
        )

        # The blocked step must start at or after the not_before constraint
        assert replan_calibrate["start_min"] >= 120, (
            f"Expected OP_CALIBRATE start_min >= 120, got {replan_calibrate['start_min']}"
        )


class TestNumericSolveApi:
    """API coverage for numeric planning Phase 1 closeout."""

    @pytest.mark.asyncio
    async def test_numeric_target_success_returns_repeated_tasks(self, client):
        ids = await _seed_numeric_api_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        tasks = data["schedule"]["tasks"]
        fill_tasks = [t for t in tasks if t["op_rule_code"] == "OP_FILL_WATER"]
        pressurize_tasks = [t for t in tasks if t["op_rule_code"] == "OP_PRESSURIZE"]

        assert len(fill_tasks) == 2
        assert len(pressurize_tasks) == 2
        assert all(t.get("step_id") is not None for t in tasks)

    @pytest.mark.asyncio
    async def test_numeric_repeated_step_blockage_uses_step_id(self, client):
        ids = await _seed_numeric_api_data(client)
        data = await _do_solve(client, ids)
        assert data["status"] == "done"

        tasks = data["schedule"]["tasks"]
        fill_tasks = [t for t in tasks if t["op_rule_code"] == "OP_FILL_WATER"]
        assert len(fill_tasks) == 2

        target_task = fill_tasks[1]
        assert target_task["step_id"] is not None

        replan = await _do_solve(
            client,
            ids,
            parent_plan_id=data["candidate_plan_id"],
            blockage_constraints={
                "strategy": "A",
                "blocked_step_id": target_task["step_id"],
                "strategy_a": {"not_before_offset": 120},
            },
        )
        assert replan["status"] == "done", replan.get("error_message")

        replan_tasks = replan["schedule"]["tasks"]
        replan_fill_tasks = [t for t in replan_tasks if t["op_rule_code"] == "OP_FILL_WATER"]
        assert len(replan_fill_tasks) == 2
        blocked = next(t for t in replan_fill_tasks if t["step_order"] == target_task["step_order"])
        other = next(t for t in replan_fill_tasks if t["step_order"] != target_task["step_order"])
        assert blocked["not_before"] == 120
        assert other["not_before"] is None

    @pytest.mark.asyncio
    async def test_unreachable_numeric_target_returns_failed(self, client):
        ids = await _seed_numeric_api_data(client)
        data = await _do_solve(client, ids, target_state_id=ids["unreachable_target_state_id"])

        assert data["status"] == "failed"
        assert data["error_message"] is not None

    @pytest.mark.asyncio
    async def test_existing_enum_scenario_still_succeeds(self, client):
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        assert {t["op_rule_code"] for t in data["schedule"]["tasks"]} == {
            "OP_WARMUP", "OP_CLEANING", "OP_CALIBRATE"
        }

    @pytest.mark.asyncio
    async def test_mixed_numeric_and_enum_target_returns_both_task_types(self, client):
        ids = await _seed_numeric_api_data(client)
        data = await _do_solve(client, ids, target_state_id=ids["mixed_target_state_id"])

        assert data["status"] == "done"
        codes = [t["op_rule_code"] for t in data["schedule"]["tasks"]]
        assert codes.count("OP_FILL_WATER") == 2
        assert codes.count("OP_PRESSURIZE") == 2
        assert codes.count("OP_CALIBRATE_NUM") == 1


# ============================================================
# Test: GET /plans/{id}/versions
# ============================================================


class TestPlanVersions:
    """Verify version chain queries."""

    @pytest.mark.asyncio
    async def test_initial_plan_versions_returns_one(self, client):
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)
        assert data["status"] == "done"
        plan_id = data["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/{plan_id}/versions")
        assert r.status_code == 200
        versions = r.json()
        assert len(versions) == 1
        v = versions[0]
        assert v["id"] == plan_id
        assert v["version"] == 1
        assert v["replan_reason"] == "initial"
        assert v["parent_plan_id"] is None

    @pytest.mark.asyncio
    async def test_replan_versions_returns_two(self, client):
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        assert initial["status"] == "done"
        parent_plan_id = initial["candidate_plan_id"]

        # Re-solve with parent_plan_id
        replan = await _do_solve(client, ids, parent_plan_id=parent_plan_id)
        assert replan["status"] == "done"
        new_plan_id = replan["candidate_plan_id"]

        # Check versions from child plan
        r = await client.get(f"/api/v1/plans/{new_plan_id}/versions")
        assert r.status_code == 200
        versions = r.json()
        assert len(versions) == 2
        # Sorted by version ascending
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[1]["parent_plan_id"] == parent_plan_id

    @pytest.mark.asyncio
    async def test_versions_from_parent_returns_same_chain(self, client):
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        parent_plan_id = initial["candidate_plan_id"]
        replan = await _do_solve(client, ids, parent_plan_id=parent_plan_id)
        child_plan_id = replan["candidate_plan_id"]

        # Querying from parent should return the same chain
        r = await client.get(f"/api/v1/plans/{parent_plan_id}/versions")
        assert r.status_code == 200
        versions = r.json()
        assert len(versions) == 2
        ids_in_chain = {v["id"] for v in versions}
        assert parent_plan_id in ids_in_chain
        assert child_plan_id in ids_in_chain

    @pytest.mark.asyncio
    async def test_nonexistent_plan_returns_404(self, client):
        r = await client.get("/api/v1/plans/9999/versions")
        assert r.status_code == 404


# ============================================================
# Shared helper: seed base data + repair rule
# ============================================================


async def _seed_with_repair_rule(client):
    """Extend _seed_base_data with a hardware-fault repair rule.

    Also creates a blockage-aware target state (same as original target but
    with blockage_reason="" added) so that strategy-B solves can produce a
    delta that naturally includes the repair op.

    Returns same dict as _seed_base_data plus:
      blockage_target_state_id — target state that includes blockage_reason=""
    """
    ids = await _seed_base_data(client)
    mt_id = ids["machine_type_id"]
    machine_id = ids["machine_id"]

    # Feature definition for blockage_reason
    r = await client.post(f"/api/v1/machine-types/{mt_id}/feature-defs", json={
        "machine_type_id": mt_id,
        "feature_key": "blockage_reason",
        "feature_name": "Blockage Reason",
        "value_type": "string",
    })
    assert r.status_code == 201

    # Target state that includes blockage_reason="" (cleared).
    # Strategy B injects blockage_reason=hardware_fault into current state via
    # current_state_override.  For the RAGBuilder to include OP_REPAIR_HW the
    # target state must also carry blockage_reason so that a delta exists.
    r = await client.post(f"/api/v1/machines/{machine_id}/states", json={
        "machine_id": machine_id,
        "state_type": "target",
        "label": "Ready for Production (blockage cleared)",
        "features": {
            "temperature_level": "hot",
            "clean_level": "clean",
            "calibration": "on",
            "blockage_reason": "none",
        },
    })
    assert r.status_code == 201
    blockage_target_state_id = r.json()["state_id"]

    # Repair rule: clears hardware_fault blockage
    r = await client.post(f"/api/v1/machine-types/{mt_id}/op-rules", json={
        "machine_type_id": mt_id,
        "code": "OP_REPAIR_HW",
        "name": "Hardware Repair",
        "duration_min": 40,
        "is_active": True,
        "is_repair": True,
        "preconditions": [
            {"feature_key": "blockage_reason", "operator": "eq",
             "feature_value": "hardware_fault"},
        ],
        "effects": [
            {"feature_key": "blockage_reason", "new_value": "none", "effect_type": "set"},
        ],
        "resource_reqs": [
            {"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True},
        ],
    })
    assert r.status_code == 201

    return {**ids, "blockage_target_state_id": blockage_target_state_id}


# ============================================================
# Test: GET /plans/{id}/diff/{other_id}
# ============================================================


class TestPlanDiff:
    """Verify step-level diff between two plan versions."""

    @pytest.mark.asyncio
    async def test_diff_same_plan_all_normal(self, client):
        """Diff of a plan against itself: all steps normal, base == new."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        assert initial["status"] == "done"
        plan_id = initial["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/{plan_id}/diff/{plan_id}")
        assert r.status_code == 200
        data = r.json()

        assert data["base_plan_id"] == plan_id
        assert data["new_plan_id"] == plan_id
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) >= 1

        for step in data["steps"]:
            assert step["base_start"] == step["new_start"]
            assert step["base_end"] == step["new_end"]
            assert step["step_role"] == "normal"
            assert step["not_before"] is None

    @pytest.mark.asyncio
    async def test_diff_initial_vs_replan_has_makespan(self, client):
        """Diff returns base_makespan and new_makespan."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        parent_id = initial["candidate_plan_id"]
        replan = await _do_solve(client, ids, parent_plan_id=parent_id)
        new_id = replan["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/{parent_id}/diff/{new_id}")
        assert r.status_code == 200
        data = r.json()

        assert data["base_plan_id"] == parent_id
        assert data["new_plan_id"] == new_id
        assert isinstance(data["base_makespan"], int)
        assert isinstance(data["new_makespan"], int)

    @pytest.mark.asyncio
    async def test_diff_steps_cover_all_op_codes(self, client):
        """Every op_code from both plans appears in diff steps."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        parent_id = initial["candidate_plan_id"]
        replan = await _do_solve(client, ids, parent_plan_id=parent_id)
        new_id = replan["candidate_plan_id"]

        # Collect op_codes from each plan's schedule
        base_codes = {t["op_rule_code"] for t in initial["schedule"]["tasks"]}
        new_codes = {t["op_rule_code"] for t in replan["schedule"]["tasks"]}
        expected_codes = base_codes | new_codes

        r = await client.get(f"/api/v1/plans/{parent_id}/diff/{new_id}")
        assert r.status_code == 200
        diff_codes = {s["op_code"] for s in r.json()["steps"]}

        assert diff_codes == expected_codes

    @pytest.mark.asyncio
    async def test_diff_nonexistent_base_returns_404(self, client):
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        plan_id = initial["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/9999/diff/{plan_id}")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_nonexistent_new_returns_404(self, client):
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        plan_id = initial["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/{plan_id}/diff/9999")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_sorted_by_new_start(self, client):
        """Steps in diff are sorted by new_start ascending."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        parent_id = initial["candidate_plan_id"]
        replan = await _do_solve(client, ids, parent_plan_id=parent_id)
        new_id = replan["candidate_plan_id"]

        r = await client.get(f"/api/v1/plans/{parent_id}/diff/{new_id}")
        assert r.status_code == 200
        steps = r.json()["steps"]

        # new_start values should be non-decreasing (None at the end)
        starts = [s["new_start"] for s in steps]
        non_null = [s for s in starts if s is not None]
        assert non_null == sorted(non_null)

    @pytest.mark.asyncio
    async def test_diff_repair_step_only_in_new_has_null_base_start(self, client):
        """Repair op inserted by strategy B must have base_start=null in diff.

        base plan: normal solve — OP_REPAIR_HW is absent.
        new plan:  strategy-B replan — OP_REPAIR_HW is inserted.
        Expected:  diff step for OP_REPAIR_HW has base_start=null, new_start is set.
        """
        ids = await _seed_with_repair_rule(client)

        base = await _do_solve(client, ids)
        assert base["status"] == "done"
        base_id = base["candidate_plan_id"]
        assert "OP_REPAIR_HW" not in {t["op_rule_code"] for t in base["schedule"]["tasks"]}

        # Strategy B: inject blockage_reason into current state + target must have
        # blockage_reason="" so the RAGBuilder sees a delta for the repair rule.
        new_plan = await _do_solve(
            client, ids,
            parent_plan_id=base_id,
            target_state_id=ids["blockage_target_state_id"],
            blockage_constraints={
                "strategy": "B",
                "strategy_b": {"blockage_reason": "hardware_fault"},
            },
        )
        assert new_plan["status"] == "done", new_plan.get("error_message")
        new_id = new_plan["candidate_plan_id"]
        assert "OP_REPAIR_HW" in {t["op_rule_code"] for t in new_plan["schedule"]["tasks"]}, \
            "Strategy-B plan must contain the repair op"

        r = await client.get(f"/api/v1/plans/{base_id}/diff/{new_id}")
        assert r.status_code == 200
        steps_by_code = {s["op_code"]: s for s in r.json()["steps"]}

        assert "OP_REPAIR_HW" in steps_by_code, "Repair op must appear in diff"
        repair = steps_by_code["OP_REPAIR_HW"]
        assert repair["base_start"] is None, \
            "Repair op absent from base plan → base_start must be null"
        assert repair["base_end"] is None, \
            "Repair op absent from base plan → base_end must be null"
        assert repair["new_start"] is not None, \
            "Repair op present in new plan → new_start must not be null"
        assert repair["step_role"] == "repair"

    @pytest.mark.asyncio
    async def test_diff_step_only_in_base_has_null_new_start(self, client):
        """Op present in base plan but absent from new plan must have new_start=null.

        base plan: strategy-B replan — OP_REPAIR_HW is present.
        new plan:  normal solve (no blockage) — OP_REPAIR_HW is absent.
        Expected:  diff step for OP_REPAIR_HW has new_start=null, base_start is set,
                   and the step appears last in the sorted list (null-start sorts last).
        """
        ids = await _seed_with_repair_rule(client)

        base = await _do_solve(
            client, ids,
            target_state_id=ids["blockage_target_state_id"],
            blockage_constraints={
                "strategy": "B",
                "strategy_b": {"blockage_reason": "hardware_fault"},
            },
        )
        assert base["status"] == "done", base.get("error_message")
        base_id = base["candidate_plan_id"]
        assert "OP_REPAIR_HW" in {t["op_rule_code"] for t in base["schedule"]["tasks"]}

        new_plan = await _do_solve(client, ids, parent_plan_id=base_id)
        assert new_plan["status"] == "done"
        new_id = new_plan["candidate_plan_id"]
        assert "OP_REPAIR_HW" not in {t["op_rule_code"] for t in new_plan["schedule"]["tasks"]}

        r = await client.get(f"/api/v1/plans/{base_id}/diff/{new_id}")
        assert r.status_code == 200
        diff_data = r.json()
        steps_by_code = {s["op_code"]: s for s in diff_data["steps"]}

        assert "OP_REPAIR_HW" in steps_by_code, "Repair op must appear in diff"
        repair = steps_by_code["OP_REPAIR_HW"]
        assert repair["new_start"] is None, \
            "Repair op absent from new plan → new_start must be null"
        assert repair["new_end"] is None, \
            "Repair op absent from new plan → new_end must be null"
        assert repair["base_start"] is not None, \
            "Repair op present in base plan → base_start must not be null"

        # null-new_start steps must sort to the end
        all_starts = [s["new_start"] for s in diff_data["steps"]]
        assert all_starts[-1] is None, \
            "Step with null new_start must appear last in sorted diff output"


# ============================================================
# Test: PLAN_NOT_SCHEDULED — dual coverage (#3, ANCHOR constraint 9)
# ============================================================


class TestPlanNotScheduled:
    """Verify that diff returns 422 when either plan has no ScheduleResult.

    Covers ANCHOR constraint 9: "求解失败必须可诊断".
    Tests both directions: base-unscheduled and new-unscheduled.
    """

    async def _create_bare_plan(self, db_session, ids: dict) -> int:
        """Insert a CandidatePlan without a ScheduleResult into the DB.

        Uses db_session directly because there is no API endpoint that creates
        a plan without a schedule.
        """
        from app.db.models import CandidatePlan, SolveRequest

        sr = SolveRequest(
            machine_id=ids["machine_id"],
            current_state_id=ids["current_state_id"],
            target_state_id=ids["target_state_id"],
            objective="minimize_makespan",
            status="done",
        )
        db_session.add(sr)
        await db_session.flush()

        plan = CandidatePlan(
            solve_request_id=sr.id,
            search_method="forward_bfs",
            version=1,
            status="draft",
        )
        db_session.add(plan)
        await db_session.commit()
        return plan.id

    @pytest.mark.asyncio
    async def test_diff_base_not_scheduled_returns_422(self, client, db_session):
        """base plan has no ScheduleResult → 422 PLAN_NOT_SCHEDULED."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        scheduled_id = initial["candidate_plan_id"]

        bare_id = await self._create_bare_plan(db_session, ids)

        r = await client.get(f"/api/v1/plans/{bare_id}/diff/{scheduled_id}")
        assert r.status_code == 422
        assert "PLAN_NOT_SCHEDULED" in r.text

    @pytest.mark.asyncio
    async def test_diff_new_not_scheduled_returns_422(self, client, db_session):
        """new plan has no ScheduleResult → 422 PLAN_NOT_SCHEDULED."""
        ids = await _seed_base_data(client)
        initial = await _do_solve(client, ids)
        scheduled_id = initial["candidate_plan_id"]

        bare_id = await self._create_bare_plan(db_session, ids)

        r = await client.get(f"/api/v1/plans/{scheduled_id}/diff/{bare_id}")
        assert r.status_code == 422
        assert "PLAN_NOT_SCHEDULED" in r.text


# ============================================================
# Test: blockage_constraints=None zero-intrusion (#5, ANCHOR constraint 2)
# ============================================================


class TestZeroIntrusionRegression:
    """Verify blockage_constraints=None / absent leaves the solve pipeline unchanged.

    Covers ANCHOR constraint 2: "blockage_constraints=None 时，求解流程与上一版本完全相同".
    """

    @pytest.mark.asyncio
    async def test_no_blockage_constraints_all_steps_normal(self, client):
        """Without blockage_constraints, every step_role must be 'normal'."""
        ids = await _seed_base_data(client)
        data = await _do_solve(client, ids)

        assert data["status"] == "done"
        for task in data["schedule"]["tasks"]:
            assert task["step_role"] == "normal", (
                f"Expected normal for {task['op_code']}, got {task['step_role']}"
            )
            assert task["not_before"] is None

    @pytest.mark.asyncio
    async def test_explicit_null_blockage_constraints_equals_omitted(self, client):
        """Passing blockage_constraints=null produces identical output to omitting it.

        Both calls must return the same number of steps and the same state_delta.
        This is the direct assertion for ANCHOR zero-intrusion guarantee.
        """
        ids = await _seed_base_data(client)

        omitted = await _do_solve(client, ids)
        with_null = await _do_solve(client, ids, blockage_constraints=None)

        assert omitted["status"] == with_null["status"] == "done"

        # Same state_delta (content, order-independent)
        assert sorted(omitted["state_delta"], key=lambda d: d["feature_key"]) == \
               sorted(with_null["state_delta"], key=lambda d: d["feature_key"])

        # Same number of steps
        assert len(omitted["schedule"]["tasks"]) == len(with_null["schedule"]["tasks"])

        # All step_roles normal in both
        for task in with_null["schedule"]["tasks"]:
            assert task["step_role"] == "normal"

    @pytest.mark.asyncio
    async def test_blockage_constraints_none_no_repair_steps(self, client):
        """Without blockage_constraints, no repair steps appear even if repair rules exist.

        Seeds a repair rule (is_repair=True) alongside normal rules, then solves
        without blockage_constraints. The repair rule must NOT appear in the plan.
        """
        ids = await _seed_base_data(client)

        # Add a repair rule that would trigger on blockage_reason=hardware_fault
        mt_id = ids["machine_type_id"]
        r = await client.post(f"/api/v1/machine-types/{mt_id}/feature-defs", json={
            "machine_type_id": mt_id,
            "feature_key": "blockage_reason",
            "feature_name": "Blockage Reason",
            "value_type": "string",
        })
        assert r.status_code == 201

        r = await client.post(f"/api/v1/machine-types/{mt_id}/op-rules", json={
            "machine_type_id": mt_id,
            "code": "OP_REPAIR_HW",
            "name": "Hardware Repair",
            "duration_min": 40,
            "is_active": True,
            "is_repair": True,
            "preconditions": [
                {"feature_key": "blockage_reason", "operator": "eq",
                 "feature_value": "hardware_fault"}
            ],
            "effects": [
                {"feature_key": "blockage_reason", "new_value": "none", "effect_type": "set"}
            ],
            "resource_reqs": [
                {"resource_type": "TECHNICIAN", "quantity": 1, "is_required": True}
            ],
        })
        assert r.status_code == 201

        # Solve WITHOUT blockage_constraints
        data = await _do_solve(client, ids)
        assert data["status"] == "done"

        op_codes = {t["op_rule_code"] for t in data["schedule"]["tasks"]}
        assert "OP_REPAIR_HW" not in op_codes, (
            "Repair op must not appear when blockage_constraints is absent"
        )

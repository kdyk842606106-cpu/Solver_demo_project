"""E2E tests for numeric planning Phase 1."""

import pytest


class TestNumericPlanning:
    """Full HTTP -> Planner -> Scheduler numeric planning scenarios."""

    @pytest.fixture(autouse=True)
    async def setup(self, numeric_scenario):
        """Seed numeric scenario data before each test."""

    async def test_numeric_repeated_steps_are_scheduled(self, client):
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 10,
            "target_state_id": 11,
            "objective": "minimize_makespan",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"

        tasks = data["schedule"]["tasks"]
        fill_20_tasks = [t for t in tasks if t["op_rule_code"] == "OP_FILL_WATER"]
        fill_10_tasks = [t for t in tasks if t["op_rule_code"] == "OP_FILL_EXACT_10"]
        assert len(fill_20_tasks) == 2 or len(fill_10_tasks) == 4
        assert all(t["step_role"] == "normal" for t in tasks)

    async def test_mixed_enum_and_numeric_target(self, client):
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 10,
            "target_state_id": 12,
            "objective": "minimize_makespan",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"

        codes = [t["op_rule_code"] for t in data["schedule"]["tasks"]]
        assert (
            codes.count("OP_FILL_WATER") == 2 and codes.count("OP_PRESSURIZE") == 2
        ) or codes.count("OP_FILL_EXACT_10") == 4
        assert codes.count("OP_CALIBRATE") == 1

    async def test_numeric_dependencies_are_preserved_when_preconditions_are_used(self, client):
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 10,
            "target_state_id": 11,
            "objective": "minimize_makespan",
        })

        tasks = resp.json()["schedule"]["tasks"]
        by_order = {t["step_order"]: t for t in tasks}
        fill_tasks = [t for t in tasks if t["op_rule_code"] == "OP_FILL_WATER"]

        if not fill_tasks:
            assert [t["op_rule_code"] for t in tasks].count("OP_FILL_EXACT_10") == 4
            return

        first_fill = min(fill_tasks, key=lambda t: t["step_order"])
        assert first_fill["predecessors"]
        assert any(by_order[p]["op_rule_code"] == "OP_PRESSURIZE" for p in first_fill["predecessors"])

    async def test_unreachable_numeric_target_is_diagnostic_failure(self, client):
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 10,
            "target_state_id": 13,
            "objective": "minimize_makespan",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_code"] == "NO_SOLUTION"
        assert data["error_message"]

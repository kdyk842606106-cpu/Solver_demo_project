"""
E2E Test — Serial Scenario.

Scenario:
    Current state: cold, dirty, off
    Target state:  hot, dirty, on  (only temperature + calibration change)

Expected RAG:  WARMUP(30 min) → CALIBRATE(15 min)  — strictly sequential
Expected makespan: 45 min
"""

import pytest


class TestSerialSolve:
    """Full HTTP → Planner → Scheduler pipeline for serial workload."""

    @pytest.fixture(autouse=True)
    async def setup(self, serial_scenario):
        """Seed serial scenario data before each test."""

    # ----------------------------------------------------------------
    # Happy path
    # ----------------------------------------------------------------

    async def test_solve_returns_200(self, client):
        """POST /api/v1/solve returns 200 with schedule."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "done"
        assert data["solve_request_id"] is not None
        assert data["candidate_plan_id"] is not None
        assert "schedule" in data

    async def test_serial_makespan(self, client):
        """Makespan equals sum of durations (no parallelism)."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        schedule = resp.json()["schedule"]

        # WARMUP=30 + CALIBRATE=15 = 45
        assert schedule["makespan"] == 45

    async def test_serial_task_count(self, client):
        """Exactly 2 operations: WARMUP and CALIBRATE."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks = resp.json()["schedule"]["tasks"]
        assert len(tasks) == 2

        codes = {t["op_rule_code"] for t in tasks}
        assert codes == {"OP_WARMUP", "OP_CALIBRATE"}

    async def test_serial_task_ordering(self, client):
        """CALIBRATE starts only after WARMUP ends."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks_by_code = {t["op_rule_code"]: t for t in resp.json()["schedule"]["tasks"]}

        warmup = tasks_by_code["OP_WARMUP"]
        calibrate = tasks_by_code["OP_CALIBRATE"]

        assert warmup["start_min"] == 0
        assert warmup["end_min"] == 30
        assert calibrate["start_min"] >= warmup["end_min"]
        assert calibrate["end_min"] == 45

    async def test_serial_resource_assignment(self, client):
        """Each task has an assigned resource."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        for task in resp.json()["schedule"]["tasks"]:
            assert len(task["resources"]) > 0

    # ----------------------------------------------------------------
    # Lifecycle & query endpoints
    # ----------------------------------------------------------------

    async def test_solve_request_status_done(self, client):
        """solve_request transitions to 'done' with solved_at timestamp."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        req_id = resp.json()["solve_request_id"]

        resp2 = await client.get(f"/api/v1/solve-requests/{req_id}")
        assert resp2.status_code == 200

        req_data = resp2.json()
        assert req_data["status"] == "done"
        assert req_data["solved_at"] is not None

    # ----------------------------------------------------------------
    # Error paths
    # ----------------------------------------------------------------

    async def test_invalid_machine_id(self, client):
        """Non-existent machine returns 422."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 999,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        assert resp.status_code == 422

    async def test_invalid_objective(self, client):
        """Unknown objective string is accepted (V0.2: objectives array drives behavior).

        V0.1 used to reject unknown objective values with 422.
        V0.2 removed that validation — the 'objective' field is stored as metadata
        while the actual solver uses the 'objectives' array.
        A solve with an unknown objective string therefore succeeds (returns 200).
        """
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "maximize_profit",
        })
        assert resp.status_code == 200

    async def test_state_not_belonging_to_machine(self, client):
        """State belonging to a different machine returns 422."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 999,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        assert resp.status_code == 422

    async def test_nonexistent_solve_request(self, client):
        """GET for non-existent solve request returns 404."""
        resp = await client.get("/api/v1/solve-requests/9999")
        assert resp.status_code == 404

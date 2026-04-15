"""
E2E Test — Parallel Scenario.

Scenario:
    Current state: cold, dirty, off
    Target state:  hot, clean, on  (all 3 features change)

Expected RAG:
    WARMUP(30 min) ──→ CALIBRATE(15 min)
    CLEANING(20 min)   (independent — parallel with WARMUP)

Expected makespan: 45 min  (better than serial 65 min)
"""

import pytest


class TestParallelSolve:
    """Full HTTP → Planner → Scheduler pipeline for parallel workload."""

    @pytest.fixture(autouse=True)
    async def setup(self, parallel_scenario):
        """Seed parallel scenario data before each test."""

    # ----------------------------------------------------------------
    # Happy path
    # ----------------------------------------------------------------

    async def test_solve_returns_200(self, client):
        """POST /api/v1/solve succeeds."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    async def test_parallel_task_count(self, client):
        """3 operations: WARMUP, CLEANING, CALIBRATE."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks = resp.json()["schedule"]["tasks"]
        assert len(tasks) == 3

        codes = {t["op_rule_code"] for t in tasks}
        assert codes == {"OP_WARMUP", "OP_CLEANING", "OP_CALIBRATE"}

    async def test_parallel_makespan_better_than_serial(self, client):
        """Makespan is strictly less than serial total (30+20+15=65)."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        makespan = resp.json()["schedule"]["makespan"]
        serial_total = 30 + 20 + 15  # 65

        assert makespan < serial_total
        assert makespan == 45  # WARMUP(30) + CALIBRATE(15)

    async def test_warmup_and_cleaning_start_together(self, client):
        """WARMUP and CLEANING both start at time 0 (parallel)."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks = {t["op_rule_code"]: t for t in resp.json()["schedule"]["tasks"]}

        assert tasks["OP_WARMUP"]["start_min"] == 0
        assert tasks["OP_CLEANING"]["start_min"] == 0

    async def test_calibrate_after_warmup(self, client):
        """CALIBRATE starts only after WARMUP finishes."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks = {t["op_rule_code"]: t for t in resp.json()["schedule"]["tasks"]}

        assert tasks["OP_CALIBRATE"]["start_min"] >= tasks["OP_WARMUP"]["end_min"]

    async def test_parallel_groups_detected(self, client):
        """Solver detects WARMUP and CLEANING as overlapping."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        groups = resp.json()["schedule"]["parallel_groups"]

        assert groups is not None
        assert len(groups) >= 1

    async def test_resource_types_matched(self, client):
        """WARMUP/CALIBRATE get TECHNICIAN, CLEANING gets CLEANER."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        })
        tasks = {t["op_rule_code"]: t for t in resp.json()["schedule"]["tasks"]}

        # WARMUP and CALIBRATE should get TECH-xx
        assert tasks["OP_WARMUP"]["resources"][0]["resource_code"] in ("TECH-01", "TECH-02")
        assert tasks["OP_CALIBRATE"]["resources"][0]["resource_code"] in ("TECH-01", "TECH-02")

        # CLEANING should get CLEAN-xx
        assert tasks["OP_CLEANING"]["resources"][0]["resource_code"] == "CLEAN-01"

    # ----------------------------------------------------------------
    # State query
    # ----------------------------------------------------------------

    async def test_machine_state_query(self, client):
        """GET /machines/{id}/state returns current features."""
        resp = await client.get("/api/v1/machines/1/state")
        assert resp.status_code == 200

        data = resp.json()
        assert data["machine_id"] == 1
        features = data["current_state"]["features"]
        assert features["temperature_level"] == "cold"
        assert features["clean_level"] == "dirty"
        assert features["calibration"] == "off"

    async def test_nonexistent_machine_query(self, client):
        """GET for non-existent machine returns 404."""
        resp = await client.get("/api/v1/machines/999/state")
        assert resp.status_code == 404

    # ----------------------------------------------------------------
    # Same-state (no-op) scenario
    # ----------------------------------------------------------------

    async def test_same_state_returns_failed(self, client):
        """Solving with current == target returns failed status."""
        resp = await client.post("/api/v1/solve", json={
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 1,
            "objective": "minimize_makespan",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_code"] == "NO_SOLUTION"

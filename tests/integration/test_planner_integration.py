"""
Integration tests for the Planner module with real database.

Tests the full RAG construction pipeline using seed data.
"""

import pytest
from sqlalchemy import select

from app.core.planner.state import load_state, compute_state_delta, is_goal
from app.core.planner.matcher import load_rules, check_preconditions, find_ops_for_delta
from app.core.planner.search import build_rag, save_candidate_plan, format_rag, find_parallel_groups
from app.db.models import Machine, MachineState, OpRule, SolveRequest


class TestRAGConstructionIntegration:
    """Integration tests for RAG construction with seed data."""

    async def test_load_current_state(self, async_session):
        """Test loading the current state from seed data."""
        # State ID 1 is "Cold Standby State"
        state = await load_state(1, async_session)
        
        assert state is not None
        assert state["temperature_level"] == "cold"
        assert state["clean_level"] == "dirty"
        assert state["calibration"] == "off"

    async def test_load_target_state(self, async_session):
        """Test loading the target state from seed data."""
        # State ID 2 is "Ready for Production"
        state = await load_state(2, async_session)
        
        assert state is not None
        assert state["temperature_level"] == "hot"
        assert state["clean_level"] == "clean"
        assert state["calibration"] == "on"

    async def test_compute_state_delta(self, async_session):
        """Test computing state delta between current and target."""
        current = await load_state(1, async_session)
        target = await load_state(2, async_session)
        
        delta = compute_state_delta(current, target)
        
        assert len(delta) == 3
        assert delta["temperature_level"] == ("cold", "hot")
        assert delta["clean_level"] == ("dirty", "clean")
        assert delta["calibration"] == ("off", "on")

    async def test_load_operation_rules(self, async_session):
        """Test loading operation rules for machine type."""
        # Machine type 1 is CNC_LATHE
        rules = await load_rules(1, async_session)
        
        assert len(rules) == 5
        
        # Check that rules have preconditions and effects loaded
        for rule in rules:
            assert rule.code is not None
            assert rule.duration_min > 0

    async def test_find_ops_for_temperature(self, async_session):
        """Test finding operations that can set temperature to hot."""
        rules = await load_rules(1, async_session)
        
        matching = find_ops_for_delta("temperature_level", "hot", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_WARMUP"

    async def test_find_ops_for_clean(self, async_session):
        """Test finding operations that can set clean_level to clean."""
        rules = await load_rules(1, async_session)
        
        matching = find_ops_for_delta("clean_level", "clean", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_CLEANING"

    async def test_find_ops_for_calibration(self, async_session):
        """Test finding operations that can set calibration to on."""
        rules = await load_rules(1, async_session)
        
        matching = find_ops_for_delta("calibration", "on", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_CALIBRATE"

    async def test_build_rag_full(self, async_session):
        """Test full RAG construction from current to target state."""
        result = await build_rag(1, 2, async_session)
        
        assert result.status == "success"
        assert result.rag is not None
        
        rag = result.rag
        
        # Should have 3 nodes (WARMUP, CLEANING, CALIBRATE)
        assert len(rag.nodes) == 3
        
        # Check node codes
        codes = {n.op_rule_code for n in rag.nodes}
        assert "OP_WARMUP" in codes
        assert "OP_CLEANING" in codes
        assert "OP_CALIBRATE" in codes
        
        # Check for parallel opportunities
        parallel_groups = find_parallel_groups(rag)
        
        # WARMUP and CLEANING should be parallel (both have no predecessors in current state)
        # Actually, they both have preconditions satisfied by current state
        # So they should have no predecessors and can run in parallel
        assert len(parallel_groups) >= 1

    async def test_rag_dependencies(self, async_session):
        """Test that RAG correctly identifies dependencies."""
        result = await build_rag(1, 2, async_session)
        
        assert result.status == "success"
        rag = result.rag
        
        # Find CALIBRATE node
        calibrate_node = next(n for n in rag.nodes if n.op_rule_code == "OP_CALIBRATE")
        
        # CALIBRATE should have WARMUP as predecessor (needs hot temperature)
        assert len(calibrate_node.predecessors) > 0
        
        # Find WARMUP node
        warmup_node = next(n for n in rag.nodes if n.op_rule_code == "OP_WARMUP")
        
        # WARMUP should have no predecessors (cold is satisfied by current state)
        assert len(warmup_node.predecessors) == 0

    async def test_rag_format(self, async_session):
        """Test RAG formatting."""
        result = await build_rag(1, 2, async_session)
        
        assert result.status == "success"
        
        formatted = format_rag(result.rag)
        
        assert "RAG Structure" in formatted
        assert "OP_WARMUP" in formatted
        assert "OP_CLEANING" in formatted
        assert "OP_CALIBRATE" in formatted

    async def test_save_candidate_plan(self, async_session):
        """Test saving RAG to database."""
        # First create a solve request
        solve_request = SolveRequest(
            machine_id=1,
            current_state_id=1,
            target_state_id=2,
            objective="minimize_makespan",
            status="running"
        )
        async_session.add(solve_request)
        await async_session.commit()
        await async_session.refresh(solve_request)
        
        # Build RAG
        result = await build_rag(1, 2, async_session)
        assert result.status == "success"
        
        # Save to database
        plan_id = await save_candidate_plan(result.rag, solve_request.id, async_session)
        
        assert plan_id > 0
        
        # Verify the plan was saved
        from app.db.models import CandidatePlan, CandidatePlanStep
        
        plan = await async_session.get(CandidatePlan, plan_id)
        assert plan is not None
        assert plan.total_steps == 3
        assert plan.search_method == "state_inference"
        
        # Verify steps
        steps_result = await async_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
            .order_by(CandidatePlanStep.step_order)
        )
        steps = steps_result.scalars().all()
        
        assert len(steps) == 3

    async def test_no_solution_same_state(self, async_session):
        """Test that same state returns no_solution."""
        result = await build_rag(1, 1, async_session)
        
        assert result.status == "no_solution"
        assert "already at target" in result.error_message.lower()

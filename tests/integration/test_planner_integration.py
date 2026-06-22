"""
Integration tests for the Planner module with real database.

Tests the full RAG construction pipeline using seed data.
"""

import pytest
from sqlalchemy import select

from app.core.planner.state import load_state, compute_state_delta, is_goal
from app.core.planner.matcher import load_rules, check_preconditions, find_ops_for_delta
from app.core.planner.search import build_rag, save_candidate_plan, format_rag, find_parallel_groups
from app.db.models import (
    CandidatePlanStep,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    SolveRequest,
    StateFeatureDef,
)


async def _seed_numeric_planner_data(session):
    """Seed a small numeric exact-target planning scenario."""
    session.add(MachineType(id=20, code="NUMERIC_PLANNER", name="Numeric Planner Machine"))
    session.add(Machine(id=20, machine_type_id=20, code="M-NUM-020", name="Numeric Machine"))
    session.add_all([
        StateFeatureDef(
            id=200,
            machine_type_id=20,
            feature_key="water_level",
            feature_name="Water Level",
            value_type="number",
        ),
        StateFeatureDef(
            id=201,
            machine_type_id=20,
            feature_key="calibration",
            feature_name="Calibration",
            value_type="enum",
        ),
    ])

    session.add(MachineState(id=200, machine_id=20, state_type="current", label="Empty"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=200, feature_key="water_level", feature_value="0"),
        MachineStateFeature(machine_state_id=200, feature_key="calibration", feature_value="off"),
    ])

    session.add(MachineState(id=201, machine_id=20, state_type="target", label="Filled"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=201, feature_key="water_level", feature_value="80"),
        MachineStateFeature(machine_state_id=201, feature_key="calibration", feature_value="off"),
    ])

    session.add(MachineState(id=202, machine_id=20, state_type="target", label="Filled And Calibrated"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=202, feature_key="water_level", feature_value="40"),
        MachineStateFeature(machine_state_id=202, feature_key="calibration", feature_value="on"),
    ])

    session.add(OpRule(id=200, machine_type_id=20, code="OP_FILL_WATER",
                       name="Fill Water", duration_min=5, is_active=True))
    session.add(OpRuleEffect(op_rule_id=200, feature_key="water_level",
                             new_value="", effect_type="increment", delta_value=20))
    session.add(OpRuleResourceReq(op_rule_id=200, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=201, machine_type_id=20, code="OP_CALIBRATE_NUM",
                       name="Calibrate Numeric Machine", duration_min=10, is_active=True))
    session.add(OpRuleEffect(op_rule_id=201, feature_key="calibration",
                             new_value="on", effect_type="set"))
    session.add(OpRuleResourceReq(op_rule_id=201, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


async def _seed_numeric_precondition_data(session):
    """Seed numeric scenario that requires implicit numeric preconditions."""
    session.add(MachineType(id=30, code="NUMERIC_PRECOND", name="Numeric Precondition Machine"))
    session.add(Machine(id=30, machine_type_id=30, code="M-NUM-030", name="Numeric Precondition Machine"))
    session.add_all([
        StateFeatureDef(
            id=300,
            machine_type_id=30,
            feature_key="water_level",
            feature_name="Water Level",
            value_type="number",
        ),
        StateFeatureDef(
            id=301,
            machine_type_id=30,
            feature_key="pressure",
            feature_name="Pressure",
            value_type="number",
        ),
    ])

    session.add(MachineState(id=300, machine_id=30, state_type="current", label="Low Pressure Empty"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=300, feature_key="water_level", feature_value="0"),
        MachineStateFeature(machine_state_id=300, feature_key="pressure", feature_value="0"),
    ])

    session.add(MachineState(id=301, machine_id=30, state_type="target", label="Filled"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=301, feature_key="water_level", feature_value="40"),
        MachineStateFeature(machine_state_id=301, feature_key="pressure", feature_value="0"),
    ])

    session.add(OpRule(id=300, machine_type_id=30, code="OP_FILL_WATER_PRECOND",
                       name="Fill Water With Pressure", duration_min=5, is_active=True))
    session.add(OpRulePrecond(op_rule_id=300, feature_key="pressure", operator="gte", feature_value="2"))
    session.add(OpRuleEffect(op_rule_id=300, feature_key="water_level",
                             new_value="", effect_type="increment", delta_value=20))
    session.add(OpRuleResourceReq(op_rule_id=300, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=301, machine_type_id=30, code="OP_PRESSURIZE",
                       name="Pressurize", duration_min=3, is_active=True))
    session.add(OpRuleEffect(op_rule_id=301, feature_key="pressure",
                             new_value="", effect_type="increment", delta_value=1))
    session.add(OpRuleResourceReq(op_rule_id=301, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


async def _seed_numeric_precondition_cycle_data(session):
    """Seed numeric scenario that creates an implicit goal cycle."""
    await _seed_numeric_precondition_data(session)
    session.add(OpRulePrecond(op_rule_id=301, feature_key="water_level", operator="gte", feature_value="20"))
    await session.commit()


class TestRAGConstructionIntegration:
    """Integration tests for RAG construction with seed data."""

    async def test_load_current_state(self, integration_session):
        """Test loading the current state from seed data."""
        # State ID 1 is "Cold Standby State"
        state = await load_state(1, integration_session)
        
        assert state is not None
        assert state["temperature_level"] == "cold"
        assert state["clean_level"] == "dirty"
        assert state["calibration"] == "off"

    async def test_load_target_state(self, integration_session):
        """Test loading the target state from seed data."""
        # State ID 2 is "Ready for Production"
        state = await load_state(2, integration_session)
        
        assert state is not None
        assert state["temperature_level"] == "hot"
        assert state["clean_level"] == "clean"
        assert state["calibration"] == "on"

    async def test_compute_state_delta(self, integration_session):
        """Test computing state delta between current and target."""
        current = await load_state(1, integration_session)
        target = await load_state(2, integration_session)
        
        delta = compute_state_delta(current, target)
        
        assert len(delta) == 3
        assert delta["temperature_level"] == ("cold", "hot")
        assert delta["clean_level"] == ("dirty", "clean")
        assert delta["calibration"] == ("off", "on")

    async def test_load_operation_rules(self, integration_session):
        """Test loading operation rules for machine type."""
        # Machine type 1 is CNC_LATHE
        rules = await load_rules(1, integration_session)
        
        assert len(rules) == 5
        
        # Check that rules have preconditions and effects loaded
        for rule in rules:
            assert rule.code is not None
            assert rule.duration_min > 0

    async def test_find_ops_for_temperature(self, integration_session):
        """Test finding operations that can set temperature to hot."""
        rules = await load_rules(1, integration_session)
        
        matching = find_ops_for_delta("temperature_level", "hot", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_WARMUP"

    async def test_find_ops_for_clean(self, integration_session):
        """Test finding operations that can set clean_level to clean."""
        rules = await load_rules(1, integration_session)
        
        matching = find_ops_for_delta("clean_level", "clean", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_CLEANING"

    async def test_find_ops_for_calibration(self, integration_session):
        """Test finding operations that can set calibration to on."""
        rules = await load_rules(1, integration_session)
        
        matching = find_ops_for_delta("calibration", "on", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_CALIBRATE"

    async def test_build_rag_full(self, integration_session):
        """Test full RAG construction from current to target state."""
        result = await build_rag(1, 2, integration_session)
        
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

    async def test_rag_dependencies(self, integration_session):
        """Test that RAG correctly identifies dependencies."""
        result = await build_rag(1, 2, integration_session)
        
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

    async def test_rag_format(self, integration_session):
        """Test RAG formatting."""
        result = await build_rag(1, 2, integration_session)
        
        assert result.status == "success"
        
        formatted = format_rag(result.rag)
        
        assert "RAG Structure" in formatted
        assert "OP_WARMUP" in formatted
        assert "OP_CLEANING" in formatted
        assert "OP_CALIBRATE" in formatted

    async def test_save_candidate_plan(self, integration_session):
        """Test saving RAG to database."""
        # First create a solve request
        solve_request = SolveRequest(
            machine_id=1,
            current_state_id=1,
            target_state_id=2,
            objective="minimize_makespan",
            status="running"
        )
        integration_session.add(solve_request)
        await integration_session.commit()
        await integration_session.refresh(solve_request)
        
        # Build RAG
        result = await build_rag(1, 2, integration_session)
        assert result.status == "success"
        
        # Save to database
        plan_id = await save_candidate_plan(result.rag, solve_request.id, integration_session)
        
        assert plan_id > 0
        
        # Verify the plan was saved
        from app.db.models import CandidatePlan, CandidatePlanStep
        
        plan = await integration_session.get(CandidatePlan, plan_id)
        assert plan is not None
        assert plan.total_steps == 3
        assert plan.search_method == "partial_order"
        
        # Verify steps
        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
            .order_by(CandidatePlanStep.step_order)
        )
        steps = steps_result.scalars().all()
        
        assert len(steps) == 3

    async def test_no_solution_same_state(self, integration_session):
        """Test that same state returns no_solution."""
        result = await build_rag(1, 1, integration_session)
        
        assert result.status == "no_solution"
        assert "already at target" in result.error_message.lower()


class TestNumericRAGConstructionIntegration:
    """Integration tests for numeric Phase 1 build_rag integration."""

    async def test_build_rag_generates_repeated_numeric_nodes(self, integration_session):
        await _seed_numeric_planner_data(integration_session)

        result = await build_rag(200, 201, integration_session)

        assert result.status == "success"
        assert result.rag is not None
        assert len(result.rag.nodes) == 4
        assert [node.op_rule_code for node in result.rag.nodes] == ["OP_FILL_WATER"] * 4
        assert len({node.op_rule_id for node in result.rag.nodes}) == 1

    async def test_numeric_steps_are_serialized_by_predecessors(self, integration_session):
        await _seed_numeric_planner_data(integration_session)

        result = await build_rag(200, 201, integration_session)

        assert result.status == "success"
        assert [node.predecessors for node in result.rag.nodes] == [[], [1], [2], [3]]
        assert result.rag.edges == [(1, 2), (2, 3), (3, 4)]

    async def test_save_candidate_plan_preserves_duplicate_op_rule_ids(self, integration_session):
        await _seed_numeric_planner_data(integration_session)
        solve_request = SolveRequest(
            machine_id=20,
            current_state_id=200,
            target_state_id=201,
            objective="minimize_makespan",
            status="running",
        )
        integration_session.add(solve_request)
        await integration_session.commit()
        await integration_session.refresh(solve_request)

        result = await build_rag(200, 201, integration_session)
        assert result.status == "success"

        plan_id = await save_candidate_plan(result.rag, solve_request.id, integration_session)
        await integration_session.flush()

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
            .order_by(CandidatePlanStep.step_order)
        )
        steps = list(steps_result.scalars().all())

        assert len(steps) == 4
        assert [step.step_order for step in steps] == [1, 2, 3, 4]
        assert len({step.op_rule_id for step in steps}) == 1
        assert [step.predecessor_ids for step in steps] == [[], [1], [2], [3]]

    async def test_mixed_enum_and_numeric_target_keeps_both_paths(self, integration_session):
        await _seed_numeric_planner_data(integration_session)

        result = await build_rag(200, 202, integration_session)

        assert result.status == "success"
        codes = [node.op_rule_code for node in result.rag.nodes]

        assert codes.count("OP_FILL_WATER") == 2
        assert codes.count("OP_CALIBRATE_NUM") == 1

    async def test_implicit_numeric_precondition_inserts_support_steps(self, integration_session):
        await _seed_numeric_precondition_data(integration_session)

        result = await build_rag(300, 301, integration_session)

        assert result.status == "success"
        codes = [node.op_rule_code for node in result.rag.nodes]
        assert codes.count("OP_PRESSURIZE") == 2
        assert codes.count("OP_FILL_WATER_PRECOND") == 2
        fill_nodes = [node for node in result.rag.nodes if node.op_rule_code == "OP_FILL_WATER_PRECOND"]
        assert fill_nodes[0].predecessors == [2]

    async def test_implicit_numeric_goal_cycle_returns_no_solution(self, integration_session):
        await _seed_numeric_precondition_cycle_data(integration_session)

        result = await build_rag(300, 301, integration_session)

        assert result.status == "no_solution"
        assert "provider" in (result.error_message or "").lower()

    async def test_scheduler_supports_repeated_numeric_steps(self, integration_session):
        from app.core.scheduler.solver import solve_schedule

        await _seed_numeric_planner_data(integration_session)
        solve_request = SolveRequest(
            machine_id=20,
            current_state_id=200,
            target_state_id=201,
            objective="minimize_makespan",
            status="running",
        )
        integration_session.add(solve_request)
        await integration_session.commit()
        await integration_session.refresh(solve_request)

        result = await build_rag(200, 201, integration_session)
        plan_id = await save_candidate_plan(result.rag, solve_request.id, integration_session)
        await integration_session.flush()

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible")
        assert len(sched_result.tasks or []) == 4
        assert [task.step_order for task in sched_result.tasks] == [1, 2, 3, 4]

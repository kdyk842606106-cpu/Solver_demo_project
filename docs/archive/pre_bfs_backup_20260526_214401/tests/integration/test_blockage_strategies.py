"""
Integration tests for blockage handling strategies A/B/AB.

Tests:
- Strategy A: not_before constraint enforcement in CP-SAT scheduler
- Strategy B: repair sequence insertion via blockage_reason state injection
- Strategy AB: combined A+B constraints
- Numeric gte/lte comparisons in preconditions
"""

import pytest
from sqlalchemy import select

from app.core.planner.search import build_rag, save_candidate_plan
from app.core.scheduler.solver import solve_schedule, save_schedule_result
from app.core.solver.step_role import compute_step_role_diff
from app.api.v1.solve import _resolve_blocked_step_for_new_plan
from app.db.models import (
    OpRule,
    OpRulePrecond,
    OpRuleEffect,
    OpRuleResourceReq,
    SolveRequest,
    CandidatePlan,
    CandidatePlanStep,
    MachineStateFeature,
)


async def _seed_numeric_gte_lte_data(session):
    """Seed data for numeric gte/lte comparison tests."""
    from app.db.models import MachineType, Machine, MachineState, StateFeatureDef

    session.add(MachineType(id=10, code="NUM_MT", name="Numeric Test Machine"))
    session.add(Machine(id=10, machine_type_id=10, code="M-010",
                        name="Numeric Test Machine", location="Test Lab"))

    session.add(StateFeatureDef(
        id=100, machine_type_id=10, feature_key="temperature",
        feature_name="Temperature", value_type="number"
    ))
    session.add(StateFeatureDef(
        id=101, machine_type_id=10, feature_key="pressure",
        feature_name="Pressure", value_type="number"
    ))

    session.add(MachineState(id=100, machine_id=10, state_type="current", label="Low Temp"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=100, feature_key="temperature", feature_value="20"),
        MachineStateFeature(machine_state_id=100, feature_key="pressure", feature_value="1.0"),
    ])

    session.add(MachineState(id=101, machine_id=10, state_type="target", label="High Temp"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=101, feature_key="temperature", feature_value="80"),
        MachineStateFeature(machine_state_id=101, feature_key="pressure", feature_value="2.0"),
    ])

    session.add(OpRule(id=200, machine_type_id=10, code="OP_HEAT",
                       name="Heat Machine", duration_min=30, is_active=True))
    session.add(OpRulePrecond(op_rule_id=200, feature_key="temperature",
                              operator="gte", feature_value="20"))
    session.add(OpRuleEffect(op_rule_id=200, feature_key="temperature",
                             new_value="80"))
    session.add(OpRuleResourceReq(op_rule_id=200, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=201, machine_type_id=10, code="OP_INCREASE_PRESSURE",
                       name="Increase Pressure", duration_min=15, is_active=True))
    session.add(OpRulePrecond(op_rule_id=201, feature_key="pressure",
                              operator="lte", feature_value="1.5"))
    session.add(OpRuleEffect(op_rule_id=201, feature_key="pressure",
                             new_value="2.0"))
    session.add(OpRuleResourceReq(op_rule_id=201, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


async def _seed_repair_rules_only(session):
    """Seed repair rules only (no state changes)."""
    from app.db.models import StateFeatureDef

    session.add(StateFeatureDef(
        id=50, machine_type_id=1, feature_key="blockage_reason",
        feature_name="Blockage Reason", value_type="string"
    ))

    session.add(OpRule(id=50, machine_type_id=1, code="OP_REPAIR_WORN",
                       name="Repair Worn Parts", duration_min=40, is_active=True,
                       is_repair=True))
    session.add(OpRulePrecond(op_rule_id=50, feature_key="blockage_reason",
                              operator="eq", feature_value="mechanical_wear"))
    session.add(OpRuleEffect(op_rule_id=50, feature_key="blockage_reason",
                             new_value=""))
    session.add(OpRuleResourceReq(op_rule_id=50, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


async def _seed_repair_strategy_data(session):
    """Seed data for Strategy B/C repair tests - blockage_reason as actual state feature."""
    from app.db.models import MachineState, StateFeatureDef

    session.add(StateFeatureDef(
        id=50, machine_type_id=1, feature_key="blockage_reason",
        feature_name="Blockage Reason", value_type="string"
    ))

    session.add(OpRule(id=50, machine_type_id=1, code="OP_REPAIR_WORN",
                       name="Repair Worn Parts", duration_min=40, is_active=True,
                       is_repair=True))
    session.add(OpRulePrecond(op_rule_id=50, feature_key="blockage_reason",
                              operator="eq", feature_value="mechanical_wear"))
    session.add(OpRuleEffect(op_rule_id=50, feature_key="blockage_reason",
                             new_value=""))
    session.add(OpRuleResourceReq(op_rule_id=50, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.flush()

    session.add(MachineState(id=3, machine_id=1, state_type="current",
                             label="Cold Standby with Blockage"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=3, feature_key="temperature_level",
                            feature_value="cold"),
        MachineStateFeature(machine_state_id=3, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=3, feature_key="calibration",
                            feature_value="off"),
        MachineStateFeature(machine_state_id=3, feature_key="blockage_reason",
                            feature_value="mechanical_wear"),
    ])

    session.add(MachineState(id=4, machine_id=1, state_type="target",
                             label="Ready for Production with Blockage"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=4, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=4, feature_key="clean_level",
                            feature_value="clean"),
        MachineStateFeature(machine_state_id=4, feature_key="calibration",
                            feature_value="on"),
        MachineStateFeature(machine_state_id=4, feature_key="blockage_reason",
                            feature_value=""),
    ])

    await session.commit()


async def _seed_numeric_blockage_data(session):
    """Seed numeric repeated-step data for blockage compatibility tests."""
    from app.db.models import MachineState, StateFeatureDef

    session.add(StateFeatureDef(
        id=60, machine_type_id=1, feature_key="water_level",
        feature_name="Water Level", value_type="number"
    ))
    session.add(StateFeatureDef(
        id=61, machine_type_id=1, feature_key="pressure",
        feature_name="Pressure", value_type="number"
    ))

    session.add(MachineState(id=60, machine_id=1, state_type="current", label="Numeric Current"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=60, feature_key="water_level", feature_value="0"),
        MachineStateFeature(machine_state_id=60, feature_key="pressure", feature_value="0"),
    ])

    session.add(MachineState(id=61, machine_id=1, state_type="target", label="Numeric Target"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=61, feature_key="water_level", feature_value="40"),
        MachineStateFeature(machine_state_id=61, feature_key="pressure", feature_value="0"),
    ])

    session.add(OpRule(id=60, machine_type_id=1, code="OP_FILL_WATER_NUM",
                       name="Fill Water Numeric", duration_min=5, is_active=True))
    session.add(OpRulePrecond(op_rule_id=60, feature_key="pressure",
                              operator="gte", feature_value="2"))
    session.add(OpRuleEffect(op_rule_id=60, feature_key="water_level",
                             new_value="", effect_type="increment", delta_value=20))
    session.add(OpRuleResourceReq(op_rule_id=60, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=61, machine_type_id=1, code="OP_PRESSURIZE_NUM",
                       name="Pressurize Numeric", duration_min=3, is_active=True))
    session.add(OpRuleEffect(op_rule_id=61, feature_key="pressure",
                             new_value="", effect_type="increment", delta_value=1))
    session.add(OpRuleResourceReq(op_rule_id=61, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=62, machine_type_id=1, code="OP_REPAIR_NUMERIC",
                       name="Numeric Repair", duration_min=12, is_active=True,
                       is_repair=True))
    session.add(OpRulePrecond(op_rule_id=62, feature_key="blockage_reason",
                              operator="eq", feature_value="numeric_fault"))
    session.add(OpRuleEffect(op_rule_id=62, feature_key="blockage_reason",
                             new_value="none", effect_type="set"))
    session.add(OpRuleResourceReq(op_rule_id=62, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


# ============================================================
# Strategy A: not_before constraint
# ============================================================


class TestStrategyA:
    """Tests for Strategy A (not_before constraint)."""

    async def test_not_before_offset_delays_step(self, integration_session):
        """Strategy A: not_before constraint should delay the blocked step."""
        result = await build_rag(1, 2, integration_session)
        assert result.status == "success"

        solve_req = SolveRequest(
            machine_id=1,
            current_state_id=1,
            target_state_id=2,
            objective="minimize_makespan",
            status="running",
        )
        integration_session.add(solve_req)
        await integration_session.flush()

        plan_id = await save_candidate_plan(result.rag, solve_req.id, integration_session)

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
        )
        steps = list(steps_result.scalars().all())
        blocked_step = steps[0]
        blocked_step.not_before = 100

        await integration_session.flush()

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )

        blocked_task = next(t for t in sched_result.tasks if t.step_order == blocked_step.step_order)
        assert blocked_task.start_min >= 100

    async def test_strategy_a_full_flow(self, integration_session):
        """Test full solve flow with Strategy A blockage_constraints."""
        result = await build_rag(1, 2, integration_session)
        assert result.status == "success"

        solve_req = SolveRequest(
            machine_id=1,
            current_state_id=1,
            target_state_id=2,
            objective="minimize_makespan",
            status="running",
            blockage_constraints={
                "strategy": "A",
                "strategy_a": {"not_before_offset": 50},
            },
        )
        integration_session.add(solve_req)
        await integration_session.flush()

        plan_id = await save_candidate_plan(
            result.rag, solve_req.id, integration_session,
            version=1, replan_reason="blockage_strategy_a"
        )

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
        )
        steps = list(steps_result.scalars().all())
        if steps:
            steps[0].not_before = 50

        await integration_session.flush()

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )


# ============================================================
# Strategy B: repair sequence insertion
# ============================================================


class TestStrategyB:
    """Tests for Strategy B (repair sequence via blockage_reason injection)."""

    async def test_repair_rule_included_when_blockage_reason_in_current_state(self, integration_session):
        """When blockage_reason is in current state, repair rule should be included in RAG."""
        await _seed_repair_strategy_data(integration_session)

        result = await build_rag(3, 4, integration_session, include_repair=True)
        assert result.status == "success"

        codes = {n.op_rule_code for n in result.rag.nodes}
        assert "OP_REPAIR_WORN" in codes

    async def test_no_repair_without_include_repair_flag(self, integration_session):
        """Without include_repair=True, repair rules should NOT be in RAG."""
        from app.core.planner.matcher import load_rules
        from sqlalchemy import select

        await _seed_repair_strategy_data(integration_session)

        rules_with_repair = await load_rules(1, integration_session, include_repair=True)
        repair_rule_codes_with = {r.code for r in rules_with_repair if getattr(r, 'is_repair', False)}

        rules_without_repair = await load_rules(1, integration_session, include_repair=False)
        repair_rule_codes_without = {r.code for r in rules_without_repair if getattr(r, 'is_repair', False)}

        assert "OP_REPAIR_WORN" in repair_rule_codes_with
        assert "OP_REPAIR_WORN" not in repair_rule_codes_without

    async def test_strategy_b_full_flow(self, integration_session):
        """Test full Strategy B flow: repair rule → plan → schedule."""
        await _seed_repair_strategy_data(integration_session)

        result = await build_rag(3, 4, integration_session, include_repair=True)
        assert result.status == "success"

        codes = {n.op_rule_code for n in result.rag.nodes}
        assert "OP_REPAIR_WORN" in codes

        solve_req = SolveRequest(
            machine_id=1,
            current_state_id=3,
            target_state_id=4,
            objective="minimize_makespan",
            status="running",
            blockage_constraints={
                "strategy": "B",
                "strategy_b": {"blockage_reason": "mechanical_wear"},
            },
        )
        integration_session.add(solve_req)
        await integration_session.flush()

        plan_id = await save_candidate_plan(
            result.rag, solve_req.id, integration_session,
            version=1, replan_reason="blockage_strategy_b"
        )

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )


# ============================================================
# Strategy AB: combined A + B
# ============================================================


# ============================================================
# Numeric gte/lte comparison
# ============================================================


class TestNumericComparisons:
    """Integration tests for numeric gte/lte precondition comparisons."""

    async def test_gte_numeric_precondition_heats_above_threshold(self, integration_session):
        """gte operator should correctly match numeric preconditions for heating."""
        await _seed_numeric_gte_lte_data(integration_session)

        result = await build_rag(100, 101, integration_session)
        assert result.status == "success", (
            f"Expected successful RAG build, got {result.status}: {result.error_message}"
        )

        codes = {n.op_rule_code for n in result.rag.nodes}
        assert "OP_HEAT" in codes

    async def test_lte_numeric_precondition_pressure_within_limit(self, integration_session):
        """lte operator should correctly match numeric preconditions for pressure."""
        await _seed_numeric_gte_lte_data(integration_session)

        result = await build_rag(100, 101, integration_session)
        assert result.status == "success", (
            f"Expected successful RAG build, got {result.status}: {result.error_message}"
        )

        codes = {n.op_rule_code for n in result.rag.nodes}
        assert "OP_INCREASE_PRESSURE" in codes

    async def test_gte_boundary_exactly_at_value(self):
        """gte should be satisfied when current equals threshold."""
        from app.core.solver.operators import OperatorRegistry

        assert OperatorRegistry.evaluate_precond("50", "gte", "50", None) is True
        assert OperatorRegistry.evaluate_precond("49", "gte", "50", None) is False

    async def test_lte_boundary_exactly_at_value(self):
        """lte should be satisfied when current equals threshold."""
        from app.core.solver.operators import OperatorRegistry

        assert OperatorRegistry.evaluate_precond("50", "lte", "50", None) is True
        assert OperatorRegistry.evaluate_precond("51", "lte", "50", None) is False

    async def test_gte_strictly_greater(self):
        """gte should return False when current is less than threshold."""
        from app.core.solver.operators import OperatorRegistry

        assert OperatorRegistry.evaluate_precond("100", "gte", "50", None) is True
        assert OperatorRegistry.evaluate_precond("49.9", "gte", "50", None) is False

    async def test_lte_strictly_less(self):
        """lte should return False when current is greater than threshold."""
        from app.core.solver.operators import OperatorRegistry

        assert OperatorRegistry.evaluate_precond("0", "lte", "50", None) is True
        assert OperatorRegistry.evaluate_precond("50.1", "lte", "50", None) is False


# ============================================================
# Strategy AB: combined A + B (continued)
# ============================================================


class TestStrategyAB:
    """Tests for Strategy AB (combined not_before + repair)."""

    async def test_strategy_ab_combined(self, integration_session):
        """Strategy AB should apply both not_before constraint and repair insertion."""
        await _seed_repair_strategy_data(integration_session)

        result = await build_rag(3, 4, integration_session, include_repair=True)
        assert result.status == "success"

        codes = {n.op_rule_code for n in result.rag.nodes}
        assert "OP_REPAIR_WORN" in codes

        solve_req = SolveRequest(
            machine_id=1,
            current_state_id=3,
            target_state_id=4,
            objective="minimize_makespan",
            status="running",
            blockage_constraints={
                "strategy": "AB",
                "strategy_a": {"not_before_offset": 20},
                "strategy_b": {"blockage_reason": "mechanical_wear"},
            },
        )
        integration_session.add(solve_req)
        await integration_session.flush()

        plan_id = await save_candidate_plan(
            result.rag, solve_req.id, integration_session,
            version=1, replan_reason="blockage_strategy_ab"
        )

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
        )
        steps = list(steps_result.scalars().all())
        blocked_step_order = None
        if len(steps) > 1:
            steps[1].not_before = 20
            blocked_step_order = steps[1].step_order

        await integration_session.flush()

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )

        task_codes = {t.op_rule_code for t in sched_result.tasks}
        assert "OP_REPAIR_WORN" in task_codes

        if blocked_step_order is not None:
            blocked_task = next(
                (t for t in sched_result.tasks if t.step_order == blocked_step_order),
                None,
            )
            if blocked_task is not None:
                assert blocked_task.start_min >= 20

    async def test_strategy_ab_step_roles(self, integration_session):
        """Strategy AB child plan should show repair step + delayed step roles vs parent."""
        await _seed_repair_strategy_data(integration_session)

        parent_result = await build_rag(1, 2, integration_session)
        assert parent_result.status == "success"

        parent_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(parent_solve_req)
        await integration_session.flush()

        parent_plan_id = await save_candidate_plan(
            parent_result.rag, parent_solve_req.id, integration_session
        )

        parent_sched = await solve_schedule(parent_plan_id, integration_session)
        assert parent_sched.status in ("optimal", "feasible"), (
            f"Expected feasible parent schedule, got {parent_sched.status}: {parent_sched.error_message}"
        )

        await save_schedule_result(parent_sched, parent_solve_req.id, parent_plan_id, integration_session)

        new_result = await build_rag(3, 4, integration_session, include_repair=True)
        assert new_result.status == "success"

        new_solve_req = SolveRequest(
            machine_id=1, current_state_id=3, target_state_id=4,
            objective="minimize_makespan", status="running",
            parent_plan_id=parent_plan_id,
        )
        integration_session.add(new_solve_req)
        await integration_session.flush()

        new_plan_id = await save_candidate_plan(
            new_result.rag, new_solve_req.id, integration_session,
            version=2, parent_plan_id=parent_plan_id, replan_reason="blockage_strategy_ab"
        )

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
        )
        steps = list(steps_result.scalars().all())
        if len(steps) > 1:
            steps[1].not_before = 20

        await integration_session.flush()

        new_sched = await solve_schedule(new_plan_id, integration_session)
        assert new_sched.status in ("optimal", "feasible"), (
            f"Expected feasible new plan schedule, got {new_sched.status}: {new_sched.error_message}"
        )

        await save_schedule_result(new_sched, new_solve_req.id, new_plan_id, integration_session)

        roles = await compute_step_role_diff(new_plan_id, parent_plan_id, integration_session)

        assert "repair" in roles.values(), (
            f"Expected 'repair' in step_roles, got: {roles}"
        )

        delayed_roles = [r for r in roles.values() if r == "delayed"]
        assert len(delayed_roles) >= 1, (
            f"Expected at least one 'delayed' step (not_before applied), got: {roles}"
        )


class TestStepRoleIntegration:
    """Integration tests for step_role computation with real DB data."""

    async def test_step_role_delayed_when_not_before_applied(self, integration_session):
        """
        When child plan adds not_before to a step that had no constraint in parent,
        the step should be labeled 'delayed'.
        """
        parent_result = await build_rag(1, 2, integration_session)
        assert parent_result.status == "success"

        parent_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(parent_solve_req)
        await integration_session.flush()

        parent_plan_id = await save_candidate_plan(
            parent_result.rag, parent_solve_req.id, integration_session
        )

        parent_sched = await solve_schedule(parent_plan_id, integration_session)
        assert parent_sched.status in ("optimal", "feasible"), (
            f"Expected feasible parent schedule, got {parent_sched.status}: {parent_sched.error_message}"
        )

        await save_schedule_result(parent_sched, parent_solve_req.id, parent_plan_id, integration_session)

        new_result = await build_rag(1, 2, integration_session)
        assert new_result.status == "success"

        new_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
            parent_plan_id=parent_plan_id,
        )
        integration_session.add(new_solve_req)
        await integration_session.flush()

        new_plan_id = await save_candidate_plan(
            new_result.rag, new_solve_req.id, integration_session,
            version=2, parent_plan_id=parent_plan_id, replan_reason="blockage_strategy_a"
        )

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
        )
        steps = list(steps_result.scalars().all())
        first_step = steps[0]
        first_step.not_before = 100

        await integration_session.flush()

        new_sched = await solve_schedule(new_plan_id, integration_session)
        assert new_sched.status in ("optimal", "feasible"), (
            f"Expected feasible child plan schedule, got {new_sched.status}: {new_sched.error_message}"
        )

        await save_schedule_result(new_sched, new_solve_req.id, new_plan_id, integration_session)

        roles = await compute_step_role_diff(new_plan_id, parent_plan_id, integration_session)

        parent_start_map = {t.step_order: t.start_min for t in parent_sched.tasks}
        new_start_map = {t.step_order: t.start_min for t in new_sched.tasks}

        for step in steps:
            new_start = new_start_map.get(step.step_order)
            parent_start = parent_start_map.get(step.step_order)
            if new_start is not None and parent_start is not None:
                if step.not_before is not None and new_start > parent_start:
                    assert roles.get(step.step_order) == "delayed"

    async def test_step_role_pulled_forward_when_parent_had_not_before(self, integration_session):
        """
        When parent plan had not_before on a step and child plan removes it,
        the step should be labeled 'pulled_forward'.
        """
        parent_result = await build_rag(1, 2, integration_session)
        assert parent_result.status == "success"

        parent_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(parent_solve_req)
        await integration_session.flush()

        parent_plan_id = await save_candidate_plan(
            parent_result.rag, parent_solve_req.id, integration_session,
        )

        steps_result = await integration_session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == parent_plan_id)
        )
        parent_steps = list(steps_result.scalars().all())
        if parent_steps:
            parent_steps[0].not_before = 100

        await integration_session.flush()

        parent_sched = await solve_schedule(parent_plan_id, integration_session)
        assert parent_sched.status in ("optimal", "feasible"), (
            f"Expected feasible parent schedule, got {parent_sched.status}: {parent_sched.error_message}"
        )

        await save_schedule_result(parent_sched, parent_solve_req.id, parent_plan_id, integration_session)

        new_result = await build_rag(1, 2, integration_session)
        assert new_result.status == "success"

        new_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
            parent_plan_id=parent_plan_id,
        )
        integration_session.add(new_solve_req)
        await integration_session.flush()

        new_plan_id = await save_candidate_plan(
            new_result.rag, new_solve_req.id, integration_session,
            version=2, parent_plan_id=parent_plan_id, replan_reason="blockage_strategy_a"
        )

        new_sched = await solve_schedule(new_plan_id, integration_session)
        assert new_sched.status in ("optimal", "feasible"), (
            f"Expected feasible child plan schedule, got {new_sched.status}: {new_sched.error_message}"
        )

        await save_schedule_result(new_sched, new_solve_req.id, new_plan_id, integration_session)

        roles = await compute_step_role_diff(new_plan_id, parent_plan_id, integration_session)

        parent_start_map = {t.step_order: t.start_min for t in parent_sched.tasks}
        new_start_map = {t.step_order: t.start_min for t in new_sched.tasks}

        found_pulled_forward = False
        for step in parent_steps:
            new_start = new_start_map.get(step.step_order)
            parent_start = parent_start_map.get(step.step_order)
            if new_start is not None and parent_start is not None:
                if new_start < parent_start:
                    assert roles.get(step.step_order) == "pulled_forward", (
                        f"Step {step.step_order}: new_start={new_start} < parent_start={parent_start}, "
                        f"expected 'pulled_forward', got '{roles.get(step.step_order)}'"
                    )
                    found_pulled_forward = True

        assert found_pulled_forward, (
            f"Expected at least one 'pulled_forward' step; roles={roles}, "
            f"parent_starts={parent_start_map}, new_starts={new_start_map}"
        )


class TestNumericBlockageCompatibility:
    """Cross-validation tests for blockage + numeric repeated steps."""

    async def test_strategy_a_can_target_numeric_repeated_step(self, integration_session):
        await _seed_numeric_blockage_data(integration_session)

        initial_result = await build_rag(60, 61, integration_session)
        assert initial_result.status == "success", initial_result.error_message

        initial_solve_req = SolveRequest(
            machine_id=1,
            current_state_id=60,
            target_state_id=61,
            objective="minimize_makespan",
            status="running",
        )
        integration_session.add(initial_solve_req)
        await integration_session.flush()

        initial_plan_id = await save_candidate_plan(initial_result.rag, initial_solve_req.id, integration_session)
        initial_steps_result = await integration_session.execute(
            select(CandidatePlanStep).where(CandidatePlanStep.candidate_plan_id == initial_plan_id)
        )
        initial_steps = list(initial_steps_result.scalars().all())
        initial_sched = await solve_schedule(initial_plan_id, integration_session)
        assert initial_sched.status in ("optimal", "feasible")
        await save_schedule_result(initial_sched, initial_solve_req.id, initial_plan_id, integration_session)

        fill_step = next(step for step in initial_steps if step.op_rule_id == 60)

        replan_result = await build_rag(60, 61, integration_session)
        assert replan_result.status == "success", replan_result.error_message

        replan_req = SolveRequest(
            machine_id=1,
            current_state_id=60,
            target_state_id=61,
            objective="minimize_makespan",
            status="running",
            parent_plan_id=initial_plan_id,
            blockage_constraints={
                "strategy": "A",
                "blocked_step_id": fill_step.id,
                "strategy_a": {"not_before_offset": 25},
            },
        )
        integration_session.add(replan_req)
        await integration_session.flush()

        replan_id = await save_candidate_plan(replan_result.rag, replan_req.id, integration_session,
                                              version=2, parent_plan_id=initial_plan_id,
                                              replan_reason="blockage_strategy_a")

        blocked_step = await _resolve_blocked_step_for_new_plan(
            db=integration_session,
            plan_id=replan_id,
            blocked_step_id=fill_step.id,
            blocked_op_rule_id=fill_step.op_rule_id,
        )
        assert blocked_step is not None
        blocked_step.not_before = 25
        await integration_session.flush()

        sched_result = await solve_schedule(replan_id, integration_session)
        assert sched_result.status in ("optimal", "feasible"), sched_result.error_message

    async def test_strategy_b_keeps_numeric_repeat_chain_intact(self, integration_session):
        await _seed_numeric_blockage_data(integration_session)

        result = await build_rag(60, 61, integration_session, include_repair=True,
                                 current_state_override={"blockage_reason": "numeric_fault"})
        assert result.status == "success", result.error_message

        codes = [node.op_rule_code for node in result.rag.nodes]
        assert codes.count("OP_FILL_WATER_NUM") == 2
        assert "OP_REPAIR_NUMERIC" in codes

    async def test_strategy_ab_numeric_repeated_steps_have_stable_roles(self, integration_session):
        await _seed_numeric_blockage_data(integration_session)

        parent_result = await build_rag(60, 61, integration_session)
        assert parent_result.status == "success", parent_result.error_message

        parent_req = SolveRequest(
            machine_id=1, current_state_id=60, target_state_id=61,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(parent_req)
        await integration_session.flush()

        parent_plan_id = await save_candidate_plan(parent_result.rag, parent_req.id, integration_session)
        parent_sched = await solve_schedule(parent_plan_id, integration_session)
        assert parent_sched.status in ("optimal", "feasible")
        await save_schedule_result(parent_sched, parent_req.id, parent_plan_id, integration_session)

        child_result = await build_rag(60, 61, integration_session, include_repair=True,
                                      current_state_override={"blockage_reason": "numeric_fault"})
        assert child_result.status == "success", child_result.error_message

        child_req = SolveRequest(
            machine_id=1, current_state_id=60, target_state_id=61,
            objective="minimize_makespan", status="running",
            parent_plan_id=parent_plan_id,
            blockage_constraints={
                "strategy": "AB",
                "blocked_step_id": parent_plan_id,
                "strategy_a": {"not_before_offset": 20},
                "strategy_b": {"blockage_reason": "numeric_fault"},
            },
        )
        integration_session.add(child_req)
        await integration_session.flush()

        child_plan_id = await save_candidate_plan(child_result.rag, child_req.id, integration_session,
                                                  version=2, parent_plan_id=parent_plan_id,
                                                  replan_reason="blockage_strategy_ab")

        child_steps_result = await integration_session.execute(
            select(CandidatePlanStep).where(CandidatePlanStep.candidate_plan_id == child_plan_id)
        )
        child_steps = list(child_steps_result.scalars().all())
        assert child_steps
        blocked_child_step = next((s for s in child_steps if s.op_rule_id == 60), None)
        assert blocked_child_step is not None
        blocked_child_step.not_before = 20
        await integration_session.flush()

        child_sched = await solve_schedule(child_plan_id, integration_session)
        assert child_sched.status in ("optimal", "feasible"), child_sched.error_message
        await save_schedule_result(child_sched, child_req.id, child_plan_id, integration_session)

        child_steps_result = await integration_session.execute(
            select(CandidatePlanStep).where(CandidatePlanStep.candidate_plan_id == child_plan_id)
        )
        child_steps = list(child_steps_result.scalars().all())
        blocked_child_step = next((s for s in child_steps if s.op_rule_id == 60), None)
        assert blocked_child_step is not None
        assert blocked_child_step.not_before == 20

        roles = await compute_step_role_diff(child_plan_id, parent_plan_id, integration_session)
        assert roles
        assert any(role in {"repair", "delayed", "pulled_forward"} for role in roles.values())

    async def test_step_role_normal_for_initial_plan(self, integration_session):
        """Parent None → all steps should be 'normal'."""
        result = await build_rag(1, 2, integration_session)
        assert result.status == "success"

        solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(solve_req)
        await integration_session.flush()

        plan_id = await save_candidate_plan(result.rag, solve_req.id, integration_session)

        sched_result = await solve_schedule(plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )

        await save_schedule_result(sched_result, solve_req.id, plan_id, integration_session)

        roles = await compute_step_role_diff(plan_id, None, integration_session)

        for step_order, role in roles.items():
            assert role == "normal"

    async def test_step_role_repair_detected_in_new_plan(self, integration_session):
        """New repair steps (is_repair=TRUE) not in parent should be labeled 'repair'."""
        await _seed_repair_strategy_data(integration_session)

        parent_result = await build_rag(1, 2, integration_session, include_repair=False)
        assert parent_result.status == "success", (
            f"Expected successful parent RAG build, got {parent_result.status}: {parent_result.error_message}"
        )

        parent_solve_req = SolveRequest(
            machine_id=1, current_state_id=1, target_state_id=2,
            objective="minimize_makespan", status="running",
        )
        integration_session.add(parent_solve_req)
        await integration_session.flush()

        parent_plan_id = await save_candidate_plan(
            parent_result.rag, parent_solve_req.id, integration_session
        )

        new_result = await build_rag(3, 4, integration_session, include_repair=True)
        assert new_result.status == "success", (
            f"Expected successful new RAG build, got {new_result.status}: {new_result.error_message}"
        )

        new_solve_req = SolveRequest(
            machine_id=1, current_state_id=3, target_state_id=4,
            objective="minimize_makespan", status="running",
            parent_plan_id=parent_plan_id,
        )
        integration_session.add(new_solve_req)
        await integration_session.flush()

        new_plan_id = await save_candidate_plan(
            new_result.rag, new_solve_req.id, integration_session,
            version=2, parent_plan_id=parent_plan_id, replan_reason="blockage_strategy_b"
        )

        sched_result = await solve_schedule(new_plan_id, integration_session)

        assert sched_result.status in ("optimal", "feasible"), (
            f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
        )

        await save_schedule_result(sched_result, new_solve_req.id, new_plan_id, integration_session)

        roles = await compute_step_role_diff(new_plan_id, parent_plan_id, integration_session)

        codes = {n.op_rule_code for n in new_result.rag.nodes}
        if "OP_REPAIR_WORN" in codes:
            repair_nodes = [n for n in new_result.rag.nodes if n.op_rule_code == "OP_REPAIR_WORN"]
            if repair_nodes:
                repair_node = repair_nodes[0]
                repair_order = repair_node.id
                if repair_order in roles:
                    assert roles[repair_order] == "repair"

"""Unit regressions for compact, relative-order plan adjustments."""

from ortools.sat.python import cp_model

from app.core.scheduler.adjustments import build_stability_stages
from app.core.scheduler.loader import RagData, ResourceData, StepData
from app.core.scheduler.model import build_model
from app.services.plan_adjustment import _compile_base_order_pairs


def _solve_stages(schedule_model, context):
    solver = cp_model.CpSolver()
    stages = build_stability_stages(schedule_model, context)
    metadata = []
    for stage in stages:
        expression = stage["expression"]
        if isinstance(expression, int):
            optimum = expression
        else:
            schedule_model.model.minimize(expression)
            status = solver.solve(schedule_model.model)
            assert status == cp_model.OPTIMAL
            optimum = int(solver.value(expression))
            schedule_model.model.add(expression == optimum)
        metadata.append((stage["type"], optimum))
    return solver, metadata


def _step(step_order: int, duration_min: int) -> StepData:
    return StepData(
        step_order=step_order,
        op_rule_id=100 + step_order,
        op_rule_code=f"OP_{step_order}",
        op_rule_name=f"Task {step_order}",
        duration_min=duration_min,
        resource_reqs=[{"resource_type": "TECH", "quantity": 1}],
    )


def test_base_order_pairs_keep_meaningful_serial_order_without_ordering_parallel_tasks():
    common = {
        "resources": [{"resource_id": 1}],
        "activity_group_id": 7,
        "state_continuity_groups": [{"state_group_id": 9}],
        "responsible_subsystem": "TOP",
        "matched_scheduling_rules": ["SUBSYSTEM_CONTINUITY"],
    }
    task_map = {
        1: {"step_order": 1, "start_min": 0, "end_min": 10, **common},
        2: {"step_order": 2, "start_min": 10, "end_min": 20, **common},
        3: {"step_order": 3, "start_min": 0, "end_min": 20, **common},
        4: {
            "step_order": 4,
            "start_min": 20,
            "end_min": 30,
            "resources": [],
            "state_continuity_groups": [],
        },
    }

    pairs = _compile_base_order_pairs(task_map)

    assert pairs == [{
        "predecessor_step_order": 1,
        "successor_step_order": 2,
        "sources": [
            "activity_group:7",
            "resource:1",
            "responsible_subsystem:TOP",
            "state_group:9",
        ],
    }]


def test_adjustment_left_compacts_avoidable_baseline_gaps():
    rag = RagData(
        candidate_plan_id=1,
        edges=[],
        steps=[_step(1, 10), _step(2, 10)],
    )
    resources = [ResourceData(1, "TECH-01", "Tech", "TECH", 1)]
    context = {
        "scope_step_orders": [1],
        "base_starts": {1: 20, 2: 40},
        "base_order_pairs": [{
            "predecessor_step_order": 1,
            "successor_step_order": 2,
            "sources": ["resource:1"],
        }],
        "priority_by_step": {},
        "constraints": [],
    }
    schedule_model = build_model(
        rag,
        resources,
        adjustment_context=context,
        defer_objective=True,
    )

    solver, metadata = _solve_stages(schedule_model, context)

    assert [item[0] for item in metadata] == [
        "minimize_makespan",
        "minimize_outside_order_inversions",
        "minimize_all_order_inversions",
        "minimize_priority_weighted_start",
    ]
    assert solver.value(schedule_model.makespan) == 20
    assert solver.value(schedule_model.task_vars[1].start) == 0
    assert solver.value(schedule_model.task_vars[2].start) == 10


def test_adjustment_minimizes_makespan_before_preserving_baseline_order():
    rag = RagData(
        candidate_plan_id=1,
        edges=[],
        steps=[_step(1, 20), _step(2, 10)],
    )
    resources = [ResourceData(1, "TECH-01", "Tech", "TECH", 1)]
    context = {
        "scope_step_orders": [1],
        "base_starts": {1: 0, 2: 20},
        "base_order_pairs": [{
            "predecessor_step_order": 1,
            "successor_step_order": 2,
            "sources": ["resource:1"],
        }],
        "priority_by_step": {},
        "constraints": [{
            "id": "delay-first",
            "type": "not_before",
            "step_orders": [1],
            "value_min": 10,
        }],
    }
    schedule_model = build_model(
        rag,
        resources,
        adjustment_context=context,
        defer_objective=True,
    )

    solver, metadata = _solve_stages(schedule_model, context)

    assert metadata[0] == ("minimize_makespan", 30)
    assert dict(metadata)["minimize_all_order_inversions"] == 1
    assert solver.value(schedule_model.task_vars[2].start) == 0
    assert solver.value(schedule_model.task_vars[1].start) == 10

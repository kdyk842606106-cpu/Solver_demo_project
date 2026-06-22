"""Tests for multi-resource scheduling constraints and assignment."""

from ortools.sat.python import cp_model

from app.core.scheduler.loader import RagData, ResourceData, StepData
from app.core.scheduler.model import build_model
from app.core.scheduler.solver import TaskResult, _assign_resources


def test_build_model_constrains_all_required_resource_types():
    """Two independent tasks sharing only CRANE must serialize on CRANE."""
    rag = RagData(
        candidate_plan_id=1,
        edges=[],
        steps=[
            StepData(
                step_order=1,
                op_rule_id=101,
                op_rule_code="A",
                op_rule_name="A",
                duration_min=10,
                resource_reqs=[
                    {"resource_type": "TECH", "quantity": 1},
                    {"resource_type": "CRANE", "quantity": 1},
                ],
                resource_type="TECH",
                resource_qty=1,
            ),
            StepData(
                step_order=2,
                op_rule_id=102,
                op_rule_code="B",
                op_rule_name="B",
                duration_min=10,
                resource_reqs=[
                    {"resource_type": "TECH", "quantity": 1},
                    {"resource_type": "CRANE", "quantity": 1},
                ],
                resource_type="TECH",
                resource_qty=1,
            ),
        ],
    )
    resources = [
        ResourceData(1, "TECH-POOL", "Tech Pool", "TECH", 2),
        ResourceData(2, "CRANE-01", "Crane", "CRANE", 1),
    ]

    schedule_model = build_model(rag, resources)
    solver = cp_model.CpSolver()
    status = solver.solve(schedule_model.model)

    assert status == cp_model.OPTIMAL
    assert solver.value(schedule_model.makespan) == 20

    t1 = schedule_model.task_vars[1]
    t2 = schedule_model.task_vars[2]
    intervals_overlap = (
        solver.value(t1.start) < solver.value(t2.end)
        and solver.value(t2.start) < solver.value(t1.end)
    )
    assert intervals_overlap is False


def test_build_model_keeps_default_makespan_objective_with_activity_groups():
    rag = RagData(
        candidate_plan_id=1,
        edges=[],
        steps=[
            StepData(
                step_order=1,
                op_rule_id=101,
                op_rule_code="A1",
                op_rule_name="A1",
                duration_min=10,
                resource_type="TECH",
                resource_qty=1,
                activity_group_id=200,
                activity_group_code="GROUP_A",
                activity_group_name="Group A",
            ),
            StepData(
                step_order=2,
                op_rule_id=102,
                op_rule_code="A2",
                op_rule_name="A2",
                duration_min=10,
                resource_type="TECH",
                resource_qty=1,
                activity_group_id=200,
                activity_group_code="GROUP_A",
                activity_group_name="Group A",
            ),
        ],
    )
    resources = [ResourceData(1, "TECH-01", "Tech", "TECH", 1)]

    schedule_model = build_model(rag, resources)
    solver = cp_model.CpSolver()
    status = solver.solve(schedule_model.model)

    assert status == cp_model.OPTIMAL
    assert solver.value(schedule_model.makespan) == 20
    assert schedule_model.activity_groups == {200: [1, 2]}
    assert schedule_model.objective_cache["metadata"] == [
        {"type": "minimize_makespan", "weight": 1.0, "weight_int": 1000}
    ]


def test_activity_group_continuity_objectives_prefer_compact_group_window():
    rag = RagData(
        candidate_plan_id=1,
        edges=[],
        steps=[
            StepData(
                step_order=1,
                op_rule_id=101,
                op_rule_code="A1",
                op_rule_name="A1",
                duration_min=10,
                resource_type="TECH",
                resource_qty=1,
                activity_group_id=200,
                activity_group_code="GROUP_A",
                activity_group_name="Group A",
            ),
            StepData(
                step_order=2,
                op_rule_id=102,
                op_rule_code="B",
                op_rule_name="B",
                duration_min=10,
                resource_type="TECH",
                resource_qty=1,
            ),
            StepData(
                step_order=3,
                op_rule_id=103,
                op_rule_code="A2",
                op_rule_name="A2",
                duration_min=10,
                resource_type="TECH",
                resource_qty=1,
                activity_group_id=200,
                activity_group_code="GROUP_A",
                activity_group_name="Group A",
            ),
        ],
    )
    resources = [ResourceData(1, "TECH-01", "Tech", "TECH", 1)]
    objectives = [
        {"type": "minimize_makespan", "weight": 1.0},
        {"type": "minimize_activity_group_span", "weight": 1.0},
        {"type": "minimize_activity_group_gaps", "weight": 1.0},
        {"type": "minimize_activity_group_interruptions", "weight": 1.0},
    ]

    schedule_model = build_model(rag, resources, objectives=objectives)
    solver = cp_model.CpSolver()
    status = solver.solve(schedule_model.model)

    assert status == cp_model.OPTIMAL
    assert solver.value(schedule_model.makespan) == 30
    assert {item["type"] for item in schedule_model.objective_cache["metadata"]} == {
        "minimize_makespan",
        "minimize_activity_group_span",
        "minimize_activity_group_gaps",
        "minimize_activity_group_interruptions",
    }

    group_tasks = [schedule_model.task_vars[1], schedule_model.task_vars[3]]
    group_start = min(solver.value(task.start) for task in group_tasks)
    group_end = max(solver.value(task.end) for task in group_tasks)
    outside_task = schedule_model.task_vars[2]

    assert group_end - group_start == 20
    assert not (
        solver.value(outside_task.start) >= group_start
        and solver.value(outside_task.end) <= group_end
    )


def test_assign_resources_fills_every_required_resource_type_with_capacity():
    tasks = [
        TaskResult(
            step_order=1,
            op_rule_id=101,
            op_rule_code="A",
            op_rule_name="A",
            start_min=0,
            end_min=10,
            duration_min=10,
            predecessors=[],
            resources=[],
            resource_type="WORKER",
            resource_reqs=[
                {"resource_type": "WORKER", "quantity": 3},
                {"resource_type": "SPACE", "quantity": 1},
            ],
        ),
        TaskResult(
            step_order=2,
            op_rule_id=102,
            op_rule_code="B",
            op_rule_name="B",
            start_min=0,
            end_min=10,
            duration_min=10,
            predecessors=[],
            resources=[],
            resource_type="WORKER",
            resource_reqs=[
                {"resource_type": "WORKER", "quantity": 2},
            ],
        ),
    ]
    resources = [
        ResourceData(1, "WORKER-POOL", "Worker Pool", "WORKER", 5),
        ResourceData(2, "SPACE-01", "Space", "SPACE", 1),
    ]

    _assign_resources(tasks, resources)

    assert tasks[0].resources == [
        {
            "resource_id": 1,
            "resource_code": "WORKER-POOL",
            "resource_type": "WORKER",
            "quantity": 3,
        },
        {
            "resource_id": 2,
            "resource_code": "SPACE-01",
            "resource_type": "SPACE",
            "quantity": 1,
        },
    ]
    assert tasks[1].resources == [
        {
            "resource_id": 1,
            "resource_code": "WORKER-POOL",
            "resource_type": "WORKER",
            "quantity": 2,
        },
    ]


def test_assign_resources_splits_quantity_across_unit_resources():
    task = TaskResult(
        step_order=1,
        op_rule_id=101,
        op_rule_code="A",
        op_rule_name="A",
        start_min=0,
        end_min=10,
        duration_min=10,
        predecessors=[],
        resources=[],
        resource_type="TECH",
        resource_reqs=[{"resource_type": "TECH", "quantity": 2}],
    )
    resources = [
        ResourceData(1, "TECH-01", "Tech 1", "TECH", 1),
        ResourceData(2, "TECH-02", "Tech 2", "TECH", 1),
    ]

    _assign_resources([task], resources)

    assert task.resources == [
        {
            "resource_id": 1,
            "resource_code": "TECH-01",
            "resource_type": "TECH",
            "quantity": 1,
        },
        {
            "resource_id": 2,
            "resource_code": "TECH-02",
            "resource_type": "TECH",
            "quantity": 1,
        },
    ]

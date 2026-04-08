"""
CP-SAT constraint model builder.

Translates the RAG structure and resource constraints into a CP-SAT model:
- Task interval variables (start, end, interval)
- Precedence constraints from RAG edges
- Cumulative resource capacity constraints
- Minimize makespan objective
"""

from dataclasses import dataclass
from typing import Any

from ortools.sat.python import cp_model

from app.core.scheduler.loader import RagData, ResourceData, get_resource_capacity


@dataclass
class TaskVar:
    """CP-SAT variables for a single task."""
    step_order: int
    start: Any  # cp_model.IntVar
    end: Any    # cp_model.IntVar
    interval: Any  # cp_model.IntervalVar
    duration: int
    resource_type: str


@dataclass
class ScheduleModel:
    """Packaged CP-SAT model ready for solving."""
    model: cp_model.CpModel
    task_vars: dict[int, TaskVar]  # step_order -> TaskVar
    makespan: Any  # cp_model.IntVar
    horizon: int


def build_model(
    rag_data: RagData,
    resources: list[ResourceData],
) -> ScheduleModel:
    """
    Build a CP-SAT model from RAG data and resources.

    Args:
        rag_data: RAG structure with step durations and resource types
        resources: Available resource instances

    Returns:
        ScheduleModel ready for solving
    """
    model = cp_model.CpModel()

    # Compute horizon (upper bound on makespan = sum of all durations)
    horizon = sum(s.duration_min for s in rag_data.steps)

    # ================================================================
    # 1. Create task variables
    # ================================================================
    task_vars: dict[int, TaskVar] = {}

    for step in rag_data.steps:
        so = step.step_order
        start = model.new_int_var(0, horizon, f"start_{so}")
        end = model.new_int_var(0, horizon, f"end_{so}")
        interval = model.new_interval_var(
            start, step.duration_min, end, f"interval_{so}"
        )

        task_vars[so] = TaskVar(
            step_order=so,
            start=start,
            end=end,
            interval=interval,
            duration=step.duration_min,
            resource_type=step.resource_type,
        )

    # ================================================================
    # 2. Precedence constraints (from RAG edges)
    # ================================================================
    for pred_so, succ_so in rag_data.edges:
        if pred_so in task_vars and succ_so in task_vars:
            # successor can only start after predecessor finishes
            model.add(task_vars[succ_so].start >= task_vars[pred_so].end)

    # ================================================================
    # 3. Resource capacity constraints (cumulative)
    # ================================================================
    # Group tasks by resource type
    resource_type_set = {s.resource_type for s in rag_data.steps if s.resource_type != "NONE"}

    for res_type in resource_type_set:
        capacity = get_resource_capacity(resources, res_type)
        if capacity <= 0:
            capacity = 1  # fallback: at least 1

        intervals = []
        demands = []

        for step in rag_data.steps:
            if step.resource_type == res_type:
                tv = task_vars[step.step_order]
                intervals.append(tv.interval)
                demands.append(step.resource_qty if step.resource_qty > 0 else 1)

        if intervals:
            model.add_cumulative(intervals, demands, capacity)

    # ================================================================
    # 4. Objective: minimize makespan
    # ================================================================
    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, [tv.end for tv in task_vars.values()])
    model.minimize(makespan)

    return ScheduleModel(
        model=model,
        task_vars=task_vars,
        makespan=makespan,
        horizon=horizon,
    )

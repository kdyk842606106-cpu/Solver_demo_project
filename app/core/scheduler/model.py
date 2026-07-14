"""
CP-SAT constraint model builder.

Translates the RAG structure and resource constraints into a CP-SAT model:
- Task interval variables (start, end, interval)
- Precedence constraints from RAG edges
- Cumulative resource capacity constraints
- Minimize makespan objective
"""

from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from app.core.scheduler.loader import RagData, ResourceData, get_resource_capacity


@dataclass
class SegmentVar:
    index: int
    start: Any
    end: Any
    duration: Any
    interval: Any
    present: Any
    window_start: int
    window_end: int


@dataclass
class TaskVar:
    """CP-SAT variables for a single task."""
    step_order: int
    start: Any  # cp_model.IntVar
    end: Any    # cp_model.IntVar
    interval: Any  # cp_model.IntervalVar
    duration: int
    resource_type: str
    work_intervals: list[Any] = field(default_factory=list)
    segments: list[SegmentVar] = field(default_factory=list)


def step_resource_requirements(step: Any) -> dict[str, int]:
    """Return normalized required resource quantities for one step.

    `resource_reqs` is the canonical multi-resource contract.  The legacy
    `resource_type/resource_qty` pair is retained as a fallback so older tests
    and persisted rows still schedule the same way.
    """
    requirements: dict[str, int] = {}

    for req in getattr(step, "resource_reqs", []) or []:
        resource_type = req.get("resource_type") or "NONE"
        if resource_type == "NONE":
            continue

        quantity = int(req.get("quantity") or 1)
        if quantity <= 0:
            quantity = 1
        requirements[resource_type] = requirements.get(resource_type, 0) + quantity

    if not requirements:
        resource_type = getattr(step, "resource_type", "NONE")
        if resource_type != "NONE":
            quantity = getattr(step, "resource_qty", 0) or 1
            requirements[resource_type] = max(int(quantity), 1)

    return requirements


@dataclass
class ScheduleModel:
    """Packaged CP-SAT model ready for solving."""
    model: cp_model.CpModel
    task_vars: dict[int, TaskVar]  # step_order -> TaskVar
    makespan: Any  # cp_model.IntVar
    horizon: int
    activity_groups: dict[int, list[int]] = field(default_factory=dict)
    state_groups: dict[int, list[int]] = field(default_factory=dict)
    objective_cache: dict[str, Any] = field(default_factory=dict)
    calendar_enabled: bool = False
    adjustment_assumption_map: dict[int, dict[str, Any]] = field(default_factory=dict)


def build_model(
    rag_data: RagData,
    resources: list[ResourceData],
    objectives: list[dict] | None = None,
    calendar_context: Any | None = None,
    scheduling_rule_context: Any | None = None,
    adjustment_context: dict[str, Any] | None = None,
    defer_objective: bool = False,
) -> ScheduleModel:
    """
    Build a CP-SAT model from RAG data and resources.

    Args:
        rag_data: RAG structure with step durations and resource types
        resources: Available resource instances
        objectives: List of objective dicts, e.g. [{"type": "minimize_makespan", "weight": 1.0}]

    Returns:
        ScheduleModel ready for solving
    """
    model = cp_model.CpModel()

    horizon = calendar_context.horizon if calendar_context is not None else sum(s.duration_min for s in rag_data.steps)
    if adjustment_context:
        from app.core.scheduler.adjustments import adjustment_horizon_floor
        horizon = max(horizon, adjustment_horizon_floor(adjustment_context) + sum(s.duration_min for s in rag_data.steps))
    max_not_before = max(
        (s.not_before for s in rag_data.steps if s.not_before is not None),
        default=0,
    )
    if max_not_before > 0 and calendar_context is None:
        horizon = max_not_before + horizon

    task_vars: dict[int, TaskVar] = {}
    activity_groups: dict[int, list[int]] = {}
    state_groups: dict[int, list[int]] = {}

    for step in rag_data.steps:
        so = step.step_order
        start = model.new_int_var(0, horizon, f"start_{so}")
        end = model.new_int_var(0, horizon, f"end_{so}")
        segments: list[SegmentVar] = []
        if calendar_context is None:
            interval = model.new_interval_var(start, step.duration_min, end, f"interval_{so}")
            work_intervals = [interval]
        else:
            span = model.new_int_var(step.duration_min, horizon, f"span_{so}")
            model.add(span == end - start)
            model.add(span == step.duration_min)
            interval = model.new_interval_var(start, span, end, f"span_interval_{so}")
            windows = calendar_context.windows_by_step.get(so, [])
            if not windows:
                raise ValueError(f"Step {so} has no calendar windows")
            used = []
            first = []
            last = []
            durations = []
            work_intervals = []
            for index, (window_start, window_end) in enumerate(windows):
                length = window_end - window_start
                present = model.new_bool_var(f"segment_{so}_{index}_present")
                is_first = model.new_bool_var(f"segment_{so}_{index}_first")
                is_last = model.new_bool_var(f"segment_{so}_{index}_last")
                segment_start = model.new_int_var(window_start, window_end, f"segment_{so}_{index}_start")
                segment_end = model.new_int_var(window_start, window_end, f"segment_{so}_{index}_end")
                segment_duration = model.new_int_var(0, length, f"segment_{so}_{index}_duration")
                segment_interval = model.new_optional_interval_var(
                    segment_start,
                    segment_duration,
                    segment_end,
                    present,
                    f"segment_{so}_{index}",
                )
                model.add(segment_duration == 0).only_enforce_if(present.Not())
                model.add(segment_duration >= 1).only_enforce_if(present)
                model.add(is_first <= present)
                model.add(is_last <= present)
                model.add(segment_end == window_end).only_enforce_if([present, is_last.Not()])
                model.add(segment_start == window_start).only_enforce_if([present, is_first.Not()])
                model.add(start == segment_start).only_enforce_if(is_first)
                model.add(end == segment_end).only_enforce_if(is_last)
                used.append(present)
                first.append(is_first)
                last.append(is_last)
                durations.append(segment_duration)
                work_intervals.append(segment_interval)
                segments.append(SegmentVar(
                    index=index,
                    start=segment_start,
                    end=segment_end,
                    duration=segment_duration,
                    interval=segment_interval,
                    present=present,
                    window_start=window_start,
                    window_end=window_end,
                ))
            model.add(sum(first) == 1)
            model.add(sum(last) == 1)
            model.add(used[0] == first[0])
            for index in range(1, len(used)):
                model.add(used[index] == used[index - 1] + first[index] - last[index - 1])
            model.add(sum(durations) == step.duration_min)

        task_vars[so] = TaskVar(
            step_order=so,
            start=start,
            end=end,
            interval=interval,
            duration=step.duration_min,
            resource_type=step.resource_type,
            work_intervals=work_intervals,
            segments=segments,
        )
        if step.activity_group_id is not None:
            activity_groups.setdefault(step.activity_group_id, []).append(so)
        seen_state_groups: set[int] = set()
        for group in getattr(step, "state_continuity_groups", []) or []:
            group_id = group.get("state_group_id")
            if group_id is None:
                continue
            try:
                group_id_int = int(group_id)
            except (TypeError, ValueError):
                continue
            if group_id_int in seen_state_groups:
                continue
            seen_state_groups.add(group_id_int)
            state_groups.setdefault(group_id_int, []).append(so)

    for pred_so, succ_so in rag_data.edges:
        if pred_so in task_vars and succ_so in task_vars:
            model.add(task_vars[succ_so].start >= task_vars[pred_so].end)

    requirements_by_step = {
        s.step_order: step_resource_requirements(s)
        for s in rag_data.steps
    }
    resource_type_set = sorted({
        resource_type
        for requirements in requirements_by_step.values()
        for resource_type in requirements
    })

    for res_type in resource_type_set:
        capacity = get_resource_capacity(resources, res_type)
        if capacity <= 0:
            capacity = 1

        intervals = []
        demands = []

        for step in rag_data.steps:
            demand = requirements_by_step[step.step_order].get(res_type)
            if demand is not None:
                tv = task_vars[step.step_order]
                intervals.extend(tv.work_intervals)
                demands.extend([demand] * len(tv.work_intervals))

        if intervals:
            model.add_cumulative(intervals, demands, capacity)

    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, [tv.end for tv in task_vars.values()])

    for step in rag_data.steps:
        if step.not_before is not None:
            model.add(task_vars[step.step_order].start >= step.not_before)

    schedule_model = ScheduleModel(
        model=model,
        task_vars=task_vars,
        makespan=makespan,
        horizon=horizon,
        activity_groups={
            group_id: step_orders
            for group_id, step_orders in activity_groups.items()
            if len(step_orders) >= 2
        },
        state_groups={
            group_id: step_orders
            for group_id, step_orders in state_groups.items()
            if len(step_orders) >= 2
        },
        calendar_enabled=calendar_context is not None,
    )

    if adjustment_context:
        from app.core.scheduler.adjustments import apply_adjustment_constraints
        apply_adjustment_constraints(schedule_model, adjustment_context)

    if objectives is None:
        objectives = [{"type": "minimize_makespan", "weight": 1.0}]
    if scheduling_rule_context is not None:
        from app.core.scheduler.rules import apply_scheduling_rules
        apply_scheduling_rules(schedule_model, scheduling_rule_context)
    if not defer_objective:
        from app.core.solver.objectives import ObjectiveRegistry
        ObjectiveRegistry.apply_all(
            objectives,
            schedule_model,
            additional_terms=schedule_model.objective_cache.get("scheduling_rule_terms", []),
        )

    return schedule_model

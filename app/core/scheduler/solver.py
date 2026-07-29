"""
Schedule solver module.

Orchestrates the full scheduling pipeline:
1. Load RAG and resources from DB
2. Build CP-SAT model
3. Solve
4. Assign resources to tasks
5. Detect actual parallel groups
6. Persist results to DB
"""

from dataclasses import dataclass, field
from datetime import timedelta
from zoneinfo import ZoneInfo
from itertools import combinations
from typing import Any, Optional
import asyncio

from ortools.sat.python import cp_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScheduleResult
from app.core.scheduler.loader import (
    RagData,
    ResourceData,
    StepData,
    load_rag,
    load_resources,
)
from app.core.scheduler.model import ScheduleModel, build_model, step_resource_requirements
from app.core.scheduler.calendar import CalendarError
from app.core.scheduler.diagnostics import diagnose_schedule_inputs
from app.core.scheduler.rules import (
    SchedulingRuleError,
    resolve_scheduling_rules,
    scheduling_rule_result_diagnostics,
)
from app.core.scheduler.schedule_graph import (
    ScheduleGraph,
    build_schedule_graph,
    compute_critical_path,
)


# ============================================================
# Data structures
# ============================================================


@dataclass
class TaskResult:
    """Solved task with timing and resource assignment."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    start_min: int
    end_min: int
    duration_min: int
    predecessors: list[int]
    resources: list[dict[str, Any]]  # [{"resource_id": 1, "resource_code": "TECH-01"}]
    resource_type: str = "NONE"  # Required resource type for assignment
    resource_reqs: list[dict[str, Any]] = field(default_factory=list)
    activity_node_id: int | None = None
    activity_node_code: str | None = None
    activity_node_level: int | None = None
    activity_group_id: int | None = None
    activity_group_code: str | None = None
    activity_group_name: str | None = None
    state_continuity_groups: list[dict[str, Any]] = field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    elapsed_min: int | None = None
    calendar_pause_min: int = 0
    segments: list[dict[str, Any]] = field(default_factory=list)
    calendar_resolution: dict[str, Any] | None = None
    responsible_subsystem: str | None = None
    effect_dimension_keys: list[str] = field(default_factory=list)
    matched_scheduling_rules: list[str] = field(default_factory=list)
    scheduling_rule_violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SolverStats:
    """CP-SAT solver statistics."""
    solver_status: str
    wall_time_sec: float
    branches: int


@dataclass
class ScheduleResultData:
    """Complete schedule result."""
    status: str  # "optimal" | "feasible" | "infeasible" | "error"
    makespan: Optional[int] = None
    tasks: Optional[list[TaskResult]] = None
    parallel_groups: Optional[list[list[int]]] = None
    solver_stats: Optional[SolverStats] = None
    error_message: Optional[str] = None
    schedule_graph: Optional[ScheduleGraph] = None
    critical_path: Optional[list[str]] = None
    critical_path_segments: Optional[list[dict[str, Any]]] = None
    diagnostics: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    calendar_summary: Optional[dict[str, Any]] = None


def _normalize_state_group_membership(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and deduplicate state package continuity group metadata."""
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for group in groups or []:
        group_id = group.get("state_group_id")
        if group_id is None:
            continue
        try:
            group_id_int = int(group_id)
        except (TypeError, ValueError):
            continue
        if group_id_int in seen:
            continue
        seen.add(group_id_int)
        normalized.append({
            "state_group_id": group_id_int,
            "state_group_code": group.get("state_group_code"),
            "state_group_name": group.get("state_group_name"),
            "state_group_level": group.get("state_group_level"),
            "parent_state_group_id": group.get("parent_state_group_id"),
        })
    return normalized


def _apply_state_continuity_groups(
    rag_data: RagData,
    groups_by_step: dict[int, list[dict[str, Any]]],
) -> None:
    """Attach in-memory state package continuity memberships to RAG steps."""
    for step in rag_data.steps:
        step.state_continuity_groups = _normalize_state_group_membership(
            groups_by_step.get(step.step_order, [])
        )


# ============================================================
# Core solver
# ============================================================


async def solve_schedule(
    candidate_plan_id: int,
    session: AsyncSession,
    max_time_seconds: float = 30.0,
    objectives: list[dict] | None = None,
    state_continuity_groups_by_step: dict[int, list[dict[str, Any]]] | None = None,
    adjustment_context: dict[str, Any] | None = None,
) -> ScheduleResultData:
    """
    Main entry point: solve a schedule for a candidate plan.

    Args:
        candidate_plan_id: ID of the candidate plan (from Planner)
        session: SQLAlchemy async session
        max_time_seconds: CP-SAT time limit
        objectives: List of objective dicts for CP-SAT (default: minimize_makespan)
        state_continuity_groups_by_step: Optional in-memory state package
            continuity membership keyed by step_order.

    Returns:
        ScheduleResultData with full results or error
    """
    # ---- 1. Load RAG ----
    rag_data = await load_rag(candidate_plan_id, session)
    if rag_data is None:
        return ScheduleResultData(
            status="error",
            error_message=f"Candidate plan {candidate_plan_id} not found",
        )

    if not rag_data.steps:
        return ScheduleResultData(
            status="error",
            error_message="Candidate plan has no steps",
        )
    if state_continuity_groups_by_step:
        _apply_state_continuity_groups(rag_data, state_continuity_groups_by_step)

    try:
        scheduling_rule_context = await resolve_scheduling_rules(rag_data, session)
    except SchedulingRuleError as exc:
        return ScheduleResultData(
            status="error",
            error_code=exc.code,
            error_message=str(exc),
            diagnostics={"scheduling_rules": {"error_code": exc.code}},
        )

    # ---- 2. Load resources ----
    resource_types = sorted({
        resource_type
        for step in rag_data.steps
        for resource_type in step_resource_requirements(step)
    })
    resources = await load_resources(resource_types, session, rag_data.machine_id)
    diagnostics = diagnose_schedule_inputs(rag_data, resources)
    diagnostics["scheduling_rules"] = scheduling_rule_context.diagnostics()

    calendar_context = None
    if rag_data.calendar_enabled:
        from app.services.work_calendar import persist_calendar_snapshot, resolve_scheduler_calendar
        try:
            calendar_context = await resolve_scheduler_calendar(
                rag_data,
                session,
                scheduling_rule_context=scheduling_rule_context,
            )
            if calendar_context is not None:
                await persist_calendar_snapshot(rag_data.solve_request_id, calendar_context, session)
                diagnostics["calendar"] = {
                    "enabled": True,
                    "warnings": calendar_context.warnings,
                    "horizon_min": calendar_context.horizon,
                }
        except CalendarError as exc:
            return ScheduleResultData(
                status="error",
                error_code=exc.code,
                error_message=str(exc),
                diagnostics={
                    **diagnostics,
                    "calendar": {"enabled": True, "error_code": exc.code, **exc.details},
                },
            )

    # ---- 3. Build model ----
    schedule_model = build_model(
        rag_data,
        resources,
        objectives,
        calendar_context=calendar_context,
        scheduling_rule_context=scheduling_rule_context,
        adjustment_context=adjustment_context,
        defer_objective=adjustment_context is not None,
    )
    diagnostics["model_horizon"] = schedule_model.horizon

    # ---- 4. Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    stability_metadata: list[dict[str, Any]] = []
    lexicographic_proven = True

    if adjustment_context is not None:
        from app.core.scheduler.adjustments import build_stability_stages
        from app.core.solver.objectives import ObjectiveRegistry

        status = cp_model.UNKNOWN
        for stage in build_stability_stages(schedule_model, adjustment_context):
            expression = stage["expression"]
            if isinstance(expression, int):
                optimum = expression
                proven = True
            else:
                schedule_model.model.minimize(expression)
                status = await asyncio.to_thread(solver.solve, schedule_model.model)
                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    break
                optimum = int(solver.value(expression))
                proven = status == cp_model.OPTIMAL
                schedule_model.model.add(expression == optimum)
            lexicographic_proven = lexicographic_proven and proven
            stability_metadata.append({
                "type": stage["type"],
                "optimum": optimum,
                "is_proven_optimal": proven,
            })
        if status in (cp_model.UNKNOWN, cp_model.OPTIMAL, cp_model.FEASIBLE):
            ObjectiveRegistry.apply_all(
                objectives or [{"type": "minimize_makespan", "weight": 1.0}],
                schedule_model,
                additional_terms=schedule_model.objective_cache.get("scheduling_rule_terms", []),
            )
            status = await asyncio.to_thread(solver.solve, schedule_model.model)
    else:
        status = await asyncio.to_thread(solver.solve, schedule_model.model)

    # ---- 5. Interpret result ----
    status_name = solver.status_name(status)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result_status = (
            "optimal"
            if status == cp_model.OPTIMAL and lexicographic_proven
            else "feasible"
        )
        makespan_val = solver.value(schedule_model.makespan)

        # Build predecessor lookup from edges
        pred_map: dict[int, list[int]] = {s.step_order: [] for s in rag_data.steps}
        for pred_so, succ_so in rag_data.edges:
            pred_map.setdefault(succ_so, []).append(pred_so)
        for item in (adjustment_context or {}).get("constraints", []):
            if item.get("type") == "precedence":
                predecessor = int(item["predecessor_step_order"])
                successor = int(item["successor_step_order"])
                if predecessor not in pred_map.setdefault(successor, []):
                    pred_map[successor].append(predecessor)

        # Build step lookup
        step_map: dict[int, StepData] = {s.step_order: s for s in rag_data.steps}

        # Extract task results
        tasks: list[TaskResult] = []
        for so in sorted(schedule_model.task_vars):
            tv = schedule_model.task_vars[so]
            sd = step_map[so]

            start_value = solver.value(tv.start)
            end_value = solver.value(tv.end)
            segments: list[dict[str, Any]] = []
            if calendar_context is None:
                segments.append({
                    "segment_index": 1,
                    "start_min": start_value,
                    "end_min": end_value,
                    "duration_min": sd.duration_min,
                    "start_at": None,
                    "end_at": None,
                    "resources": [],
                })
                start_at = end_at = None
            else:
                display_zone = ZoneInfo(calendar_context.display_timezone)
                for segment in tv.segments:
                    if solver.value(segment.present):
                        segment_start = solver.value(segment.start)
                        segment_end = solver.value(segment.end)
                        window_metadata = calendar_context.window_metadata_by_step.get(so, [])[segment.index]
                        segments.append({
                            "segment_index": len(segments) + 1,
                            "start_min": segment_start,
                            "end_min": segment_end,
                            "duration_min": solver.value(segment.duration),
                            "start_at": (calendar_context.schedule_start_at + timedelta(minutes=segment_start)).astimezone(display_zone).isoformat(),
                            "end_at": (calendar_context.schedule_start_at + timedelta(minutes=segment_end)).astimezone(display_zone).isoformat(),
                            "resources": [],
                            **window_metadata,
                        })
                start_at = (calendar_context.schedule_start_at + timedelta(minutes=start_value)).astimezone(display_zone).isoformat()
                end_at = (calendar_context.schedule_start_at + timedelta(minutes=end_value)).astimezone(display_zone).isoformat()

            tasks.append(TaskResult(
                step_order=so,
                op_rule_id=sd.op_rule_id,
                op_rule_code=sd.op_rule_code,
                op_rule_name=sd.op_rule_name,
                start_min=start_value,
                end_min=end_value,
                duration_min=sd.duration_min,
                predecessors=pred_map.get(so, []),
                resources=[],  # filled next
                resource_type=sd.resource_type,
                resource_reqs=sd.resource_reqs,
                activity_node_id=sd.activity_node_id,
                activity_node_code=sd.activity_node_code,
                activity_node_level=sd.activity_node_level,
                activity_group_id=sd.activity_group_id,
                activity_group_code=sd.activity_group_code,
                activity_group_name=sd.activity_group_name,
                state_continuity_groups=sd.state_continuity_groups,
                start_at=start_at,
                end_at=end_at,
                elapsed_min=end_value - start_value,
                calendar_pause_min=max(0, end_value - start_value - sd.duration_min),
                segments=segments,
                calendar_resolution=(
                    calendar_context.resolution_by_step.get(so) if calendar_context is not None else None
                ),
                responsible_subsystem=sd.responsible_subsystem,
                effect_dimension_keys=sd.effect_dimension_keys,
                matched_scheduling_rules=scheduling_rule_context.matched_rule_codes_by_step.get(so, []),
            ))

        # Sort by start_min, then step_order
        tasks.sort(key=lambda t: (t.start_min, t.step_order))

        # ---- 6. Assign resources ----
        _assign_resources(tasks, resources)

        # ---- 7. Detect actual parallel groups ----
        parallel_groups = _detect_actual_parallel(tasks)

        # ---- 8. Build schedule graph and compute critical path ----
        schedule_graph = build_schedule_graph(tasks, rag_data.edges, makespan_val)
        if calendar_context is not None:
            critical_path, critical_path_segments = _segment_critical_path(
                tasks, rag_data.edges, makespan_val
            )
        else:
            critical_path = compute_critical_path(schedule_graph)
            critical_path_segments = _critical_path_segment_details(tasks, critical_path)
        activity_continuity = _activity_group_continuity_diagnostics(tasks, objectives)
        state_continuity = _state_group_continuity_diagnostics(tasks, objectives)
        rule_diagnostics = scheduling_rule_result_diagnostics(scheduling_rule_context, tasks)
        violations_by_step: dict[int, list[dict[str, Any]]] = {}
        for violation in rule_diagnostics.get("violations", []):
            for step_order in violation.get("step_orders", []):
                violations_by_step.setdefault(step_order, []).append(violation)
        for task in tasks:
            task.scheduling_rule_violations = violations_by_step.get(task.step_order, [])

        stats = SolverStats(
            solver_status=status_name,
            wall_time_sec=round(solver.wall_time, 4),
            branches=solver.num_branches,
        )

        return ScheduleResultData(
            status=result_status,
            makespan=makespan_val,
            tasks=tasks,
            parallel_groups=parallel_groups,
            solver_stats=stats,
            schedule_graph=schedule_graph,
            critical_path=critical_path,
            critical_path_segments=critical_path_segments,
            diagnostics={
                **diagnostics,
                "solver_status": status_name,
                "solver_wall_time_sec": round(solver.wall_time, 4),
                "solver_branches": solver.num_branches,
                "objective_terms": schedule_model.objective_cache.get("metadata", []),
                "adjustment_optimization": stability_metadata,
                "activity_group_continuity": activity_continuity,
                "state_group_continuity": state_continuity,
                "scheduling_rules": rule_diagnostics,
            },
            calendar_summary=(
                {
                    "enabled": True,
                    "revision_ids": sorted(
                        item["revision_id"] for item in calendar_context.snapshot["calendars"].values()
                    ),
                    "fallback_step_orders": sorted(
                        step_order
                        for step_order, item in calendar_context.resolution_by_step.items()
                        if item.get("fallback_to_default")
                    ),
                    "inherits_system_default": bool(
                        calendar_context.snapshot.get("inherits_system_default")
                    ),
                    "effective_default_work_calendar_id": calendar_context.snapshot.get(
                        "default_calendar_id"
                    ),
                    "schedule_start_at": calendar_context.schedule_start_at.astimezone(
                        ZoneInfo(calendar_context.display_timezone)
                    ).isoformat(),
                    "schedule_end_at": (
                        calendar_context.schedule_start_at + timedelta(minutes=makespan_val)
                    ).astimezone(ZoneInfo(calendar_context.display_timezone)).isoformat(),
                }
                if calendar_context is not None else {"enabled": False}
            ),
        )

    elif status == cp_model.INFEASIBLE:
        conflict_constraints = []
        if adjustment_context is not None:
            from app.core.scheduler.adjustments import infeasible_constraint_core
            conflict_constraints = infeasible_constraint_core(solver, schedule_model)
        return ScheduleResultData(
            status="infeasible",
            error_message="Resource constraints cannot be satisfied",
            diagnostics={
                **diagnostics,
                "solver_status": status_name,
                "solver_wall_time_sec": round(solver.wall_time, 4),
                "solver_branches": solver.num_branches,
                "adjustment": {
                    "conflict_constraints": conflict_constraints,
                    "optimization": stability_metadata,
                },
            },
        )
    else:
        return ScheduleResultData(
            status="error",
            error_message=f"Solver returned: {status_name}",
            diagnostics={
                **diagnostics,
                "solver_status": status_name,
                "solver_wall_time_sec": round(solver.wall_time, 4),
                "solver_branches": solver.num_branches,
            },
        )


# ============================================================
# Resource assignment
# ============================================================


def _assign_resources(
    tasks: list[TaskResult],
    resources: list[ResourceData],
) -> None:
    """
    Assign concrete resource instances to tasks.

    Assign every required resource type for a task.  Resource instances may have
    capacity > 1, so occupancy is tracked as used capacity over time intervals
    rather than a binary busy/free flag.
    Mutates tasks in place.
    """
    # Build per-resource-type pools
    pools: dict[str, list[ResourceData]] = {}
    for r in resources:
        pools.setdefault(r.resource_type, []).append(r)

    # Track resource busy intervals: resource_id -> list of (start, end, quantity)
    busy: dict[int, list[tuple[int, int, int]]] = {r.id: [] for r in resources}

    for task in tasks:
        segments = task.segments or [{
            "segment_index": 1,
            "start_min": task.start_min,
            "end_min": task.end_min,
            "duration_min": task.duration_min,
            "resources": [],
        }]
        if not task.segments:
            task.segments = segments
        for segment in segments:
            segment_resources: list[dict[str, Any]] = segment.setdefault("resources", [])
            for req in _task_resource_requirements(task):
                resource_type = req["resource_type"]
                quantity_remaining = req["quantity"]
                pool = pools.get(resource_type, [])

                for res in pool:
                    if quantity_remaining <= 0:
                        break

                    capacity = max(int(res.capacity), 1)
                    available = _available_capacity(
                        busy[res.id],
                        segment["start_min"],
                        segment["end_min"],
                        capacity,
                    )
                    if available <= 0:
                        continue

                    assigned_quantity = min(quantity_remaining, available)
                    assignment = {
                        "resource_id": res.id,
                        "resource_code": res.code,
                        "resource_type": resource_type,
                        "quantity": assigned_quantity,
                    }
                    segment_resources.append(assignment)
                    if not any(
                        item["resource_id"] == res.id
                        and item["resource_type"] == resource_type
                        for item in task.resources
                    ):
                        task.resources.append(dict(assignment))
                    busy[res.id].append((
                        segment["start_min"],
                        segment["end_min"],
                        assigned_quantity,
                    ))
                    quantity_remaining -= assigned_quantity
                # If no full assignment is found, leave the remaining quantity
                # unassigned as degraded mode; CP-SAT should normally prevent this.


def _task_resource_requirements(task: TaskResult) -> list[dict[str, Any]]:
    """Return normalized resource requirements for solved task assignment."""
    requirements: dict[str, int] = {}

    for req in task.resource_reqs or []:
        resource_type = req.get("resource_type") or "NONE"
        if resource_type == "NONE":
            continue
        quantity = int(req.get("quantity") or 1)
        if quantity <= 0:
            quantity = 1
        requirements[resource_type] = requirements.get(resource_type, 0) + quantity

    if not requirements and task.resource_type != "NONE":
        requirements[task.resource_type] = 1

    return [
        {"resource_type": resource_type, "quantity": quantity}
        for resource_type, quantity in requirements.items()
    ]


def _available_capacity(
    intervals: list[tuple[int, int, int]],
    start: int,
    end: int,
    capacity: int,
) -> int:
    """Return remaining resource capacity during [start, end)."""
    used = 0
    for busy_start, busy_end, quantity in intervals:
        if start < busy_end and end > busy_start:
            used += quantity
    return capacity - used


# ============================================================
# Parallel detection
# ============================================================


def _detect_actual_parallel(tasks: list[TaskResult]) -> list[list[int]]:
    """
    Detect groups of tasks that actually execute in parallel.

    Two tasks are parallel if their time intervals overlap.
    """
    parallel_groups: list[list[int]] = []

    for t1, t2 in combinations(tasks, 2):
        if any(
            left["start_min"] < right["end_min"] and right["start_min"] < left["end_min"]
            for left in t1.segments
            for right in t2.segments
        ):
            group = sorted([t1.step_order, t2.step_order])
            if group not in parallel_groups:
                parallel_groups.append(group)

    return parallel_groups


def _critical_path_segment_details(
    tasks: list[TaskResult],
    critical_path: list[str],
) -> list[dict[str, Any]]:
    """Expose work and calendar-wait portions for critical tasks."""
    critical_codes = set(critical_path)
    details: list[dict[str, Any]] = []
    for task in sorted(
        (item for item in tasks if item.op_rule_code in critical_codes),
        key=lambda item: (item.start_min, item.step_order),
    ):
        segments = sorted(task.segments, key=lambda item: item["start_min"])
        for index, segment in enumerate(segments):
            if index:
                previous = segments[index - 1]
                if segment["start_min"] > previous["end_min"]:
                    details.append({
                        "kind": "calendar_wait",
                        "step_order": task.step_order,
                        "op_rule_code": task.op_rule_code,
                        "start_min": previous["end_min"],
                        "end_min": segment["start_min"],
                        "duration_min": segment["start_min"] - previous["end_min"],
                    })
            details.append({
                "kind": "work",
                "step_order": task.step_order,
                "op_rule_code": task.op_rule_code,
                "segment_index": segment.get("segment_index"),
                "start_min": segment["start_min"],
                "end_min": segment["end_min"],
                "duration_min": segment["duration_min"],
            })
    return details


def _segment_critical_path(
    tasks: list[TaskResult],
    rag_edges: list[tuple[int, int]],
    makespan: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Trace one critical path through work segments and lag-bearing edges."""
    nodes: dict[tuple[int, int], dict[str, Any]] = {}
    first_by_step: dict[int, tuple[int, int]] = {}
    last_by_step: dict[int, tuple[int, int]] = {}
    predecessors: dict[tuple[int, int], list[tuple[tuple[int, int], str]]] = {}
    task_by_step = {task.step_order: task for task in tasks}
    for task in tasks:
        ordered = sorted(task.segments, key=lambda item: item["start_min"])
        previous_key = None
        for segment in ordered:
            key = (task.step_order, int(segment.get("segment_index") or len(nodes) + 1))
            nodes[key] = {**segment, "step_order": task.step_order, "op_rule_code": task.op_rule_code}
            predecessors.setdefault(key, [])
            first_by_step.setdefault(task.step_order, key)
            last_by_step[task.step_order] = key
            if previous_key is not None:
                predecessors[key].append((previous_key, "calendar_wait"))
            previous_key = key
    for left, right in rag_edges:
        if left in last_by_step and right in first_by_step:
            predecessors[first_by_step[right]].append((last_by_step[left], "precedence_wait"))
    usage: dict[int, list[tuple[int, int, tuple[int, int]]]] = {}
    for key, node in nodes.items():
        for resource in node.get("resources", []):
            usage.setdefault(resource["resource_id"], []).append(
                (node["start_min"], node["end_min"], key)
            )
    for resource_segments in usage.values():
        ordered = sorted(resource_segments)
        for left, right in zip(ordered, ordered[1:]):
            if left[1] <= right[0] and left[2] != right[2]:
                predecessors[right[2]].append((left[2], "resource_wait"))
    if not nodes:
        return [], []
    current = max(nodes, key=lambda key: (nodes[key]["end_min"], nodes[key]["start_min"]))
    reverse_details: list[dict[str, Any]] = []
    reverse_codes: list[str] = []
    visited: set[tuple[int, int]] = set()
    priority = {"calendar_wait": 3, "resource_wait": 2, "precedence_wait": 1}
    while current not in visited:
        visited.add(current)
        node = nodes[current]
        reverse_details.append({
            "kind": "work",
            "step_order": node["step_order"],
            "op_rule_code": node["op_rule_code"],
            "segment_index": node.get("segment_index"),
            "start_min": node["start_min"],
            "end_min": node["end_min"],
            "duration_min": node["duration_min"],
        })
        reverse_codes.append(node["op_rule_code"])
        candidates = predecessors.get(current, [])
        if not candidates:
            if node["start_min"] > 0:
                reverse_details.append({
                    "kind": "calendar_wait",
                    "step_order": node["step_order"],
                    "op_rule_code": node["op_rule_code"],
                    "start_min": 0,
                    "end_min": node["start_min"],
                    "duration_min": node["start_min"],
                })
            break
        previous, edge_kind = max(
            candidates,
            key=lambda item: (nodes[item[0]]["end_min"], priority[item[1]]),
        )
        previous_node = nodes[previous]
        if node["start_min"] > previous_node["end_min"]:
            reverse_details.append({
                "kind": edge_kind,
                "from_step_order": previous_node["step_order"],
                "step_order": node["step_order"],
                "start_min": previous_node["end_min"],
                "end_min": node["start_min"],
                "duration_min": node["start_min"] - previous_node["end_min"],
            })
        current = previous
    details = list(reversed(reverse_details))
    codes: list[str] = []
    for code in reversed(reverse_codes):
        if not codes or codes[-1] != code:
            codes.append(code)
    return codes, details


def _activity_group_continuity_diagnostics(
    tasks: list[TaskResult],
    objectives: list[dict] | None,
) -> dict[str, Any]:
    """Summarize compactness of scheduled tasks by level-2 activity group."""
    groups: dict[int, list[TaskResult]] = {}
    for task in tasks:
        if task.activity_group_id is None:
            continue
        groups.setdefault(task.activity_group_id, []).append(task)

    objective_weights = {
        item.get("type"): item.get("weight", 1.0)
        for item in objectives or [{"type": "minimize_makespan", "weight": 1.0}]
    }

    summaries = []
    for group_id, group_tasks in sorted(groups.items()):
        if len(group_tasks) < 2:
            continue
        start = min(task.start_min for task in group_tasks)
        end = max(task.end_min for task in group_tasks)
        duration_sum = sum(task.duration_min for task in group_tasks)
        span = end - start
        internal_gap = max(0, span - duration_sum)
        group_step_orders = {task.step_order for task in group_tasks}
        interruptions = [
            task
            for task in tasks
            if task.step_order not in group_step_orders
            and task.start_min >= start
            and task.end_min <= end
        ]
        summaries.append({
            "activity_group_id": group_id,
            "activity_group_code": group_tasks[0].activity_group_code,
            "activity_group_name": group_tasks[0].activity_group_name,
            "task_count": len(group_tasks),
            "task_step_orders": [task.step_order for task in sorted(group_tasks, key=lambda t: (t.start_min, t.step_order))],
            "window_start_min": start,
            "window_end_min": end,
            "span_min": span,
            "duration_sum_min": duration_sum,
            "internal_gap_min": internal_gap,
            "interruption_count": len(interruptions),
            "interruption_step_orders": [
                task.step_order for task in sorted(interruptions, key=lambda t: (t.start_min, t.step_order))
            ],
            "is_compact": internal_gap == 0 and not interruptions,
        })

    return {
        "objective_weights": objective_weights,
        "group_count": len(summaries),
        "groups": summaries,
    }


def _state_group_continuity_diagnostics(
    tasks: list[TaskResult],
    objectives: list[dict] | None,
) -> dict[str, Any]:
    """Summarize compactness of scheduled tasks by target state package."""
    groups: dict[int, list[TaskResult]] = {}
    group_meta: dict[int, dict[str, Any]] = {}
    for task in tasks:
        seen_for_task: set[int] = set()
        for group in task.state_continuity_groups or []:
            group_id = group.get("state_group_id")
            if group_id is None:
                continue
            try:
                group_id_int = int(group_id)
            except (TypeError, ValueError):
                continue
            if group_id_int in seen_for_task:
                continue
            seen_for_task.add(group_id_int)
            groups.setdefault(group_id_int, []).append(task)
            group_meta.setdefault(group_id_int, group)

    objective_weights = {
        item.get("type"): item.get("weight", 1.0)
        for item in objectives or [{"type": "minimize_makespan", "weight": 1.0}]
    }

    summaries = []
    for group_id, group_tasks in sorted(groups.items()):
        if len(group_tasks) < 2:
            continue
        start = min(task.start_min for task in group_tasks)
        end = max(task.end_min for task in group_tasks)
        duration_sum = sum(task.duration_min for task in group_tasks)
        span = end - start
        internal_gap = max(0, span - duration_sum)
        group_step_orders = {task.step_order for task in group_tasks}
        interruptions = [
            task
            for task in tasks
            if task.step_order not in group_step_orders
            and task.start_min >= start
            and task.end_min <= end
        ]
        meta = group_meta.get(group_id, {})
        summaries.append({
            "state_group_id": group_id,
            "state_group_code": meta.get("state_group_code"),
            "state_group_name": meta.get("state_group_name"),
            "state_group_level": meta.get("state_group_level"),
            "parent_state_group_id": meta.get("parent_state_group_id"),
            "task_count": len(group_tasks),
            "task_step_orders": [
                task.step_order for task in sorted(group_tasks, key=lambda t: (t.start_min, t.step_order))
            ],
            "window_start_min": start,
            "window_end_min": end,
            "span_min": span,
            "duration_sum_min": duration_sum,
            "internal_gap_min": internal_gap,
            "interruption_count": len(interruptions),
            "interruption_step_orders": [
                task.step_order for task in sorted(interruptions, key=lambda t: (t.start_min, t.step_order))
            ],
            "is_compact": internal_gap == 0 and not interruptions,
        })

    return {
        "objective_weights": objective_weights,
        "group_count": len(summaries),
        "groups": summaries,
    }


# ============================================================
# Persistence
# ============================================================


async def save_schedule_result(
    result: ScheduleResultData,
    solve_request_id: int,
    candidate_plan_id: int,
    session: AsyncSession,
) -> int:
    """
    Persist schedule result to database.

    Args:
        result: Solved schedule result
        solve_request_id: ID of the solve request
        candidate_plan_id: ID of the candidate plan
        session: SQLAlchemy async session

    Returns:
        ID of the created schedule_result record
    """
    tasks_json = []
    if result.tasks:
        for t in result.tasks:
            tasks_json.append({
                "step_order": t.step_order,
                "op_rule_id": t.op_rule_id,
                "op_rule_code": t.op_rule_code,
                "op_rule_name": t.op_rule_name,
                "start_min": t.start_min,
                "end_min": t.end_min,
                "duration_min": t.duration_min,
                "predecessors": t.predecessors,
                "resources": t.resources,
                "resource_type": t.resource_type,
                "resource_reqs": t.resource_reqs,
                "activity_node_id": t.activity_node_id,
                "activity_node_code": t.activity_node_code,
                "activity_node_level": t.activity_node_level,
                "activity_group_id": t.activity_group_id,
                "activity_group_code": t.activity_group_code,
                "activity_group_name": t.activity_group_name,
                "state_continuity_groups": t.state_continuity_groups,
                "start_at": t.start_at,
                "end_at": t.end_at,
                "elapsed_min": t.elapsed_min,
                "calendar_pause_min": t.calendar_pause_min,
                "segments": t.segments,
                "calendar_resolution": t.calendar_resolution,
                "responsible_subsystem": t.responsible_subsystem,
                "effect_dimension_keys": t.effect_dimension_keys,
                "matched_scheduling_rules": t.matched_scheduling_rules,
                "scheduling_rule_violations": t.scheduling_rule_violations,
            })

    record = ScheduleResult(
        solve_request_id=solve_request_id,
        candidate_plan_id=candidate_plan_id,
        makespan=result.makespan,
        solver_status=result.solver_stats.solver_status if result.solver_stats else None,
        tasks=tasks_json,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)

    return record.id


# ============================================================
# Formatting
# ============================================================


def format_schedule(result: ScheduleResultData) -> str:
    """Format schedule result as a human-readable string."""
    if result.status not in ("optimal", "feasible"):
        return f"Schedule failed: {result.status} — {result.error_message}"

    lines = [
        f"Schedule ({result.status})",
        f"  Makespan: {result.makespan} min",
        "",
        "  Tasks:",
    ]

    for t in result.tasks or []:
        preds = f" (after {t.predecessors})" if t.predecessors else ""
        res_str = ", ".join(r["resource_code"] for r in t.resources) or "unassigned"
        lines.append(
            f"    {t.op_rule_code:16s}  "
            f"start={t.start_min:3d}  end={t.end_min:3d}  "
            f"dur={t.duration_min:2d}  "
            f"res={res_str}{preds}"
        )

    if result.parallel_groups:
        lines.append("")
        lines.append("  Parallel groups:")
        for g in result.parallel_groups:
            lines.append(f"    Steps {g}")

    return "\n".join(lines)

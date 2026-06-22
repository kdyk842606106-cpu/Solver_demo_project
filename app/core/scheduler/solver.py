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
from app.core.scheduler.diagnostics import diagnose_schedule_inputs
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
    diagnostics: Optional[dict[str, Any]] = None


# ============================================================
# Core solver
# ============================================================


async def solve_schedule(
    candidate_plan_id: int,
    session: AsyncSession,
    max_time_seconds: float = 30.0,
    objectives: list[dict] | None = None,
) -> ScheduleResultData:
    """
    Main entry point: solve a schedule for a candidate plan.

    Args:
        candidate_plan_id: ID of the candidate plan (from Planner)
        session: SQLAlchemy async session
        max_time_seconds: CP-SAT time limit
        objectives: List of objective dicts for CP-SAT (default: minimize_makespan)

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

    # ---- 2. Load resources ----
    resource_types = sorted({
        resource_type
        for step in rag_data.steps
        for resource_type in step_resource_requirements(step)
    })
    resources = await load_resources(resource_types, session, rag_data.machine_id)
    diagnostics = diagnose_schedule_inputs(rag_data, resources)

    # ---- 3. Build model ----
    schedule_model = build_model(rag_data, resources, objectives)
    diagnostics["model_horizon"] = schedule_model.horizon

    # ---- 4. Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds

    status = await asyncio.to_thread(solver.solve, schedule_model.model)

    # ---- 5. Interpret result ----
    status_name = solver.status_name(status)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result_status = "optimal" if status == cp_model.OPTIMAL else "feasible"
        makespan_val = solver.value(schedule_model.makespan)

        # Build predecessor lookup from edges
        pred_map: dict[int, list[int]] = {s.step_order: [] for s in rag_data.steps}
        for pred_so, succ_so in rag_data.edges:
            pred_map.setdefault(succ_so, []).append(pred_so)

        # Build step lookup
        step_map: dict[int, StepData] = {s.step_order: s for s in rag_data.steps}

        # Extract task results
        tasks: list[TaskResult] = []
        for so in sorted(schedule_model.task_vars):
            tv = schedule_model.task_vars[so]
            sd = step_map[so]

            tasks.append(TaskResult(
                step_order=so,
                op_rule_id=sd.op_rule_id,
                op_rule_code=sd.op_rule_code,
                op_rule_name=sd.op_rule_name,
                start_min=solver.value(tv.start),
                end_min=solver.value(tv.end),
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
            ))

        # Sort by start_min, then step_order
        tasks.sort(key=lambda t: (t.start_min, t.step_order))

        # ---- 6. Assign resources ----
        _assign_resources(tasks, resources)

        # ---- 7. Detect actual parallel groups ----
        parallel_groups = _detect_actual_parallel(tasks)

        # ---- 8. Build schedule graph and compute critical path ----
        schedule_graph = build_schedule_graph(tasks, rag_data.edges, makespan_val)
        critical_path = compute_critical_path(schedule_graph)
        continuity = _activity_group_continuity_diagnostics(tasks, objectives)

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
            diagnostics={
                **diagnostics,
                "solver_status": status_name,
                "solver_wall_time_sec": round(solver.wall_time, 4),
                "solver_branches": solver.num_branches,
                "objective_terms": schedule_model.objective_cache.get("metadata", []),
                "activity_group_continuity": continuity,
            },
        )

    elif status == cp_model.INFEASIBLE:
        return ScheduleResultData(
            status="infeasible",
            error_message="Resource constraints cannot be satisfied",
            diagnostics={
                **diagnostics,
                "solver_status": status_name,
                "solver_wall_time_sec": round(solver.wall_time, 4),
                "solver_branches": solver.num_branches,
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
                    task.start_min,
                    task.end_min,
                    capacity,
                )
                if available <= 0:
                    continue

                assigned_quantity = min(quantity_remaining, available)
                task.resources.append({
                    "resource_id": res.id,
                    "resource_code": res.code,
                    "resource_type": resource_type,
                    "quantity": assigned_quantity,
                })
                busy[res.id].append((
                    task.start_min,
                    task.end_min,
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
        if t1.start_min < t2.end_min and t2.start_min < t1.end_min:
            group = sorted([t1.step_order, t2.step_order])
            if group not in parallel_groups:
                parallel_groups.append(group)

    return parallel_groups


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

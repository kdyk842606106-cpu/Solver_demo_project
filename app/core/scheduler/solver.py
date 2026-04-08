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

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Optional

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
from app.core.scheduler.model import ScheduleModel, build_model


# ============================================================
# Data structures
# ============================================================


@dataclass
class TaskResult:
    """Solved task with timing and resource assignment."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    start_min: int
    end_min: int
    duration_min: int
    predecessors: list[int]
    resources: list[dict[str, Any]]  # [{"resource_id": 1, "resource_code": "TECH-01"}]
    resource_type: str = "NONE"  # Required resource type for assignment


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


# ============================================================
# Core solver
# ============================================================


async def solve_schedule(
    candidate_plan_id: int,
    session: AsyncSession,
    max_time_seconds: float = 30.0,
) -> ScheduleResultData:
    """
    Main entry point: solve a schedule for a candidate plan.

    Args:
        candidate_plan_id: ID of the candidate plan (from Planner)
        session: SQLAlchemy async session
        max_time_seconds: CP-SAT time limit

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
    resource_types = list({s.resource_type for s in rag_data.steps if s.resource_type != "NONE"})
    resources = await load_resources(resource_types, session)

    # ---- 3. Build model ----
    schedule_model = build_model(rag_data, resources)

    # ---- 4. Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds

    status = solver.solve(schedule_model.model)

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
                start_min=solver.value(tv.start),
                end_min=solver.value(tv.end),
                duration_min=sd.duration_min,
                predecessors=pred_map.get(so, []),
                resources=[],  # filled next
                resource_type=sd.resource_type,
            ))

        # Sort by start_min, then step_order
        tasks.sort(key=lambda t: (t.start_min, t.step_order))

        # ---- 6. Assign resources ----
        _assign_resources(tasks, resources)

        # ---- 7. Detect actual parallel groups ----
        parallel_groups = _detect_actual_parallel(tasks)

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
        )

    elif status == cp_model.INFEASIBLE:
        return ScheduleResultData(
            status="infeasible",
            error_message="Resource constraints cannot be satisfied",
        )
    else:
        return ScheduleResultData(
            status="error",
            error_message=f"Solver returned: {status_name}",
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

    MVP strategy: for each task, assign the first available resource
    of the required type that is not already busy at that time.
    Mutates tasks in place.
    """
    # Build per-resource-type pools
    pools: dict[str, list[ResourceData]] = {}
    for r in resources:
        pools.setdefault(r.resource_type, []).append(r)

    # Track resource busy intervals: resource_id -> list of (start, end)
    busy: dict[int, list[tuple[int, int]]] = {r.id: [] for r in resources}

    for task in tasks:
        if task.resource_type == "NONE":
            continue

        pool = pools.get(task.resource_type, [])

        for res in pool:
            if _is_resource_free(busy[res.id], task.start_min, task.end_min):
                task.resources.append({
                    "resource_id": res.id,
                    "resource_code": res.code,
                })
                busy[res.id].append((task.start_min, task.end_min))
                break
        # If no resource found in pool, leave empty (degraded mode)


def _is_resource_free(
    intervals: list[tuple[int, int]],
    start: int,
    end: int,
) -> bool:
    """Check if a resource is free during [start, end)."""
    for busy_start, busy_end in intervals:
        if start < busy_end and end > busy_start:
            return False  # overlap
    return True


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
                "start_min": t.start_min,
                "end_min": t.end_min,
                "duration_min": t.duration_min,
                "predecessors": t.predecessors,
                "resources": t.resources,
            })

    record = ScheduleResult(
        solve_request_id=solve_request_id,
        candidate_plan_id=candidate_plan_id,
        makespan=result.makespan,
        solver_status=result.solver_stats.solver_status if result.solver_stats else None,
        tasks=tasks_json,
    )
    session.add(record)
    await session.commit()
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

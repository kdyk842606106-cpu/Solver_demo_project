"""
Solve API endpoint.

POST /api/v1/solve — Submit a solve request, run Planner → Scheduler, return result.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BlockageEvent,
    CandidatePlan,
    CandidatePlanStep,
    Machine,
    MachineState,
    SolveRequest,
)
from app.db.schemas import SolveRequestCreate
from app.db.session import get_db_session
from app.core.planner.search import build_rag, save_candidate_plan
from app.core.planner.state import load_state, compute_state_delta
from app.core.scheduler.solver import (
    TaskResult,
    solve_schedule,
    save_schedule_result,
)
from app.core.solver.step_role import compute_step_role_diff

router = APIRouter(tags=["solve"])


class AmbiguousBlockedStepError(Exception):
    """Raised when a legacy blockage request cannot identify one instance."""


async def _resolve_blocked_step_for_new_plan(
    db: AsyncSession,
    plan_id: int,
    blocked_step_id: int | None,
    blocked_op_rule_id: int | None,
) -> CandidatePlanStep | None:
    """Resolve which step in the new plan should receive the blockage.

    Prefer an explicit parent blocked_step_id because it identifies a concrete
    step instance. For legacy callers that only pass blocked_op_rule_id, fall
    back to the unique matching step when possible.
    """
    parent_step: CandidatePlanStep | None = None
    if blocked_step_id is not None:
        parent_step = await db.get(CandidatePlanStep, blocked_step_id)
        if parent_step is not None:
            step_result = await db.execute(
                select(CandidatePlanStep)
                .where(CandidatePlanStep.candidate_plan_id == plan_id)
                .where(CandidatePlanStep.step_order == parent_step.step_order)
            )
            blocked_step = step_result.scalar_one_or_none()
            if blocked_step is not None:
                return blocked_step
            blocked_op_rule_id = parent_step.op_rule_id

    if blocked_op_rule_id is None:
        return None

    step_result = await db.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id == plan_id)
        .where(CandidatePlanStep.op_rule_id == blocked_op_rule_id)
        .order_by(CandidatePlanStep.step_order)
    )
    matching_steps = step_result.scalars().all()
    if not matching_steps:
        return None

    if len(matching_steps) == 1:
        return matching_steps[0]

    if parent_step is not None:
        for step in matching_steps:
            if step.step_order == parent_step.step_order:
                return step

    raise AmbiguousBlockedStepError(
        "AMBIGUOUS_BLOCKED_STEP: repeated task requires blocked_step_id"
    )


def _compute_critical_path(tasks: list[TaskResult]) -> list[str]:
    """Return op_codes on the critical path, in chronological order.

    Algorithm: from tasks that end at makespan, trace backwards through
    "tight" edges (task.start_min == predecessor.end_min).
    """
    if not tasks:
        return []

    by_order: dict[int, TaskResult] = {t.step_order: t for t in tasks}
    makespan = max(t.end_min for t in tasks)

    on_path: set[int] = set()
    stack = [t.step_order for t in tasks if t.end_min == makespan]

    while stack:
        order = stack.pop()
        if order in on_path:
            continue
        task = by_order.get(order)
        if task is None:
            continue
        on_path.add(order)
        for pred_order in task.predecessors:
            pred = by_order.get(pred_order)
            if pred is not None and pred.end_min == task.start_min:
                stack.append(pred_order)

    path_tasks = sorted(
        [by_order[o] for o in on_path],
        key=lambda t: t.start_min,
    )
    return [t.op_rule_code for t in path_tasks]


@router.post("/solve")
async def solve(
    request: SolveRequestCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submit a solve request.

    Orchestrates: input validation → Planner (RAG) → Scheduler (CP-SAT) → result.
    """

    machine = await db.get(Machine, request.machine_id)
    if machine is None:
        raise HTTPException(
            status_code=422,
            detail=f"Machine with id={request.machine_id} not found",
        )

    current_state = await db.get(MachineState, request.current_state_id)
    if current_state is None:
        raise HTTPException(
            status_code=422,
            detail=f"State with id={request.current_state_id} not found",
        )
    if current_state.machine_id != request.machine_id:
        raise HTTPException(
            status_code=422,
            detail=f"State {request.current_state_id} does not belong to machine {request.machine_id}",
        )

    target_state = await db.get(MachineState, request.target_state_id)
    if target_state is None:
        raise HTTPException(
            status_code=422,
            detail=f"State with id={request.target_state_id} not found",
        )
    if target_state.machine_id != request.machine_id:
        raise HTTPException(
            status_code=422,
            detail=f"State {request.target_state_id} does not belong to machine {request.machine_id}",
        )

    blockage_constraints = request.blockage_constraints
    strategy: str | None = blockage_constraints.get("strategy") if blockage_constraints else None
    strategy_b_reason: str | None = (
        blockage_constraints.get("strategy_b", {}).get("blockage_reason")
        if blockage_constraints else None
    )
    strategy_a_offset: int | None = (
        blockage_constraints.get("strategy_a", {}).get("not_before_offset")
        if blockage_constraints else None
    )
    blocked_step_id: int | None = (
        blockage_constraints.get("blocked_step_id")
        if blockage_constraints else None
    )
    blocked_op_rule_id: int | None = (
        blockage_constraints.get("blocked_op_rule_id")
        if blockage_constraints else None
    )

    replan_reason_map = {
        "A": "blockage_strategy_a",
        "B": "blockage_strategy_b",
        "AB": "blockage_strategy_ab",
    }
    replan_reason = replan_reason_map.get(strategy) if strategy else "initial"

    objectives = request.objectives or [{"type": "minimize_makespan", "weight": 1.0}]

    solve_req = SolveRequest(
        machine_id=request.machine_id,
        current_state_id=request.current_state_id,
        target_state_id=request.target_state_id,
        objective=request.objective,
        objectives=objectives,
        constraints=request.constraints,
        parent_plan_id=request.parent_plan_id,
        blockage_constraints=blockage_constraints,
        overrides=request.overrides,
        status="running",
    )

    # All solve logic is inside try/except so every failure path returns HTTP 200
    # with a structured error payload instead of propagating as an unhandled 500.
    try:
        db.add(solve_req)
        await db.flush()

        current_state_override: dict[str, str] = {}
        include_repair = False

        if strategy in ("B", "AB") and strategy_b_reason:
            current_state_override["blockage_reason"] = strategy_b_reason
            include_repair = True

        plan_result = await build_rag(
            request.current_state_id,
            request.target_state_id,
            db,
            current_state_override=current_state_override if current_state_override else None,
            include_repair=include_repair,
        )

        if plan_result.status != "success":
            error_code = "NO_SOLUTION" if plan_result.status == "no_solution" else "INTERNAL_ERROR"
            if "circular" in (plan_result.error_message or "").lower():
                error_code = "CIRCULAR_DEPENDENCY"

            req_id = solve_req.id
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "solve_request_id": req_id,
                "status": "failed",
                "error_code": error_code,
                "error_message": plan_result.error_message,
            }

        parent_plan_id = request.parent_plan_id
        version = 1
        if parent_plan_id is not None:
            parent_plan = await db.get(CandidatePlan, parent_plan_id)
            if parent_plan is not None:
                version = (parent_plan.version or 1) + 1

        plan_id = await save_candidate_plan(
            plan_result.rag,
            solve_req.id,
            db,
            version=version,
            parent_plan_id=parent_plan_id,
            replan_reason=replan_reason,
        )

        # Flush pending CandidatePlanStep rows created by save_candidate_plan()
        # into the DB so the SELECT below can find them.  Without this,
        # autoflush=False causes the query to miss the in-memory objects and
        # the not_before assignment is silently skipped.
        await db.flush()

        new_blocked_step_id = None
        if strategy in ("A", "AB") and strategy_a_offset is not None:
            try:
                blocked_step = await _resolve_blocked_step_for_new_plan(
                    db=db,
                    plan_id=plan_id,
                    blocked_step_id=blocked_step_id,
                    blocked_op_rule_id=blocked_op_rule_id,
                )
            except AmbiguousBlockedStepError as exc:
                req_id = solve_req.id
                solve_req.status = "failed"
                solve_req.solved_at = datetime.now(timezone.utc)
                await db.commit()
                return {
                    "solve_request_id": req_id,
                    "status": "failed",
                    "candidate_plan_id": plan_id,
                    "error_code": "AMBIGUOUS_BLOCKED_STEP",
                    "error_message": str(exc),
                }

            if blocked_step is not None:
                blocked_step.not_before = strategy_a_offset
                new_blocked_step_id = blocked_step.id

        if strategy in ("A", "B", "AB"):
            blockage_event = BlockageEvent(
                plan_id=plan_id,
                blocked_step_id=new_blocked_step_id,
                strategy=strategy or "A",
                not_before_offset=strategy_a_offset,
                blockage_reason=strategy_b_reason,
                note=blockage_constraints.get("note") if blockage_constraints else None,
                created_by=blockage_constraints.get("created_by") if blockage_constraints else None,
            )
            db.add(blockage_event)

        await db.flush()

        sched_result = await solve_schedule(
            plan_id,
            db,
            objectives=objectives,
        )

        if sched_result.status not in ("optimal", "feasible"):
            error_code = "INFEASIBLE" if sched_result.status == "infeasible" else "SOLVER_TIMEOUT"

            req_id = solve_req.id
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "solve_request_id": req_id,
                "status": "failed",
                "candidate_plan_id": plan_id,
                "error_code": error_code,
                "error_message": sched_result.error_message,
            }

        result_id = await save_schedule_result(sched_result, solve_req.id, plan_id, db)

        await compute_step_role_diff(plan_id, parent_plan_id, db)

        # Query step metadata (not_before + step_role) written by compute_step_role_diff.
        # Extract to plain dicts immediately — ORM objects expire after db.commit().
        steps_result = await db.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == plan_id)
        )
        plan_steps = {
            s.step_order: {
                "step_id": s.id,
                "not_before": s.not_before,
                "step_role": s.step_role or "normal",
            }
            for s in steps_result.scalars().all()
        }

        # Build response payload while session is still open (avoids post-commit ORM expiry).
        current_state_dict = await load_state(request.current_state_id, db)
        target_state_dict = await load_state(request.target_state_id, db)
        delta = compute_state_delta(current_state_dict or {}, target_state_dict or {})
        state_delta = [
            {"feature_key": k, "from_value": v[0], "to_value": v[1]}
            for k, v in sorted(delta.items())
        ]

        critical_path = _compute_critical_path(sched_result.tasks or [])

        tasks_response = []
        for t in sched_result.tasks:
            step_meta = plan_steps.get(t.step_order)
            tasks_response.append({
                "step_order": t.step_order,
                "step_id": step_meta["step_id"] if step_meta else None,
                "op_rule_id": t.op_rule_id,
                "op_rule_code": t.op_rule_code,
                "op_rule_name": t.op_rule_name,
                "start_min": t.start_min,
                "end_min": t.end_min,
                "duration_min": t.duration_min,
                "resources": t.resources,
                "predecessors": t.predecessors,
                "not_before": step_meta["not_before"] if step_meta else None,
                "step_role": step_meta["step_role"] if step_meta else "normal",
            })

        # Capture plain-int IDs before commit (ORM objects expire on commit).
        req_id = solve_req.id

        solve_req.status = "done"
        solve_req.solved_at = datetime.now(timezone.utc)
        await db.commit()

        return {
            "solve_request_id": req_id,
            "status": "done",
            "candidate_plan_id": plan_id,
            "state_delta": state_delta,
            "critical_path": critical_path,
            "schedule": {
                "makespan": sched_result.makespan,
                "tasks": tasks_response,
                "parallel_groups": sched_result.parallel_groups,
            },
        }

    except Exception as exc:
        await db.rollback()
        req_id: Optional[int] = getattr(solve_req, "id", None)
        try:
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception:
            pass
        return {
            "solve_request_id": req_id,
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "error_message": str(exc),
        }

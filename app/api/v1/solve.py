"""
Solve API endpoint.

POST /api/v1/solve — Submit a solve request, run Planner → Scheduler, return result.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Machine, MachineState, SolveRequest
from app.db.schemas import SolveRequestCreate, ErrorResponse
from app.db.session import get_db_session
from app.core.planner.search import build_rag, save_candidate_plan
from app.core.scheduler.solver import (
    solve_schedule,
    save_schedule_result,
)

router = APIRouter(tags=["solve"])


@router.post("/solve")
async def solve(
    request: SolveRequestCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submit a solve request.

    Orchestrates: input validation → Planner (RAG) → Scheduler (CP-SAT) → result.
    """

    # ================================================================
    # 1. Validate inputs
    # ================================================================

    # Check machine exists
    machine = await db.get(Machine, request.machine_id)
    if machine is None:
        raise HTTPException(
            status_code=422,
            detail=f"Machine with id={request.machine_id} not found",
        )

    # Check current state exists and belongs to machine
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

    # Check target state exists and belongs to machine
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

    # Check objective
    if request.objective != "minimize_makespan":
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported objective: {request.objective}. MVP only supports 'minimize_makespan'",
        )

    # ================================================================
    # 2. Create solve request (status=pending → running)
    # ================================================================

    solve_req = SolveRequest(
        machine_id=request.machine_id,
        current_state_id=request.current_state_id,
        target_state_id=request.target_state_id,
        objective=request.objective,
        overrides=request.overrides,
        status="running",
    )
    db.add(solve_req)
    await db.flush()

    # ================================================================
    # 3. Planner: build RAG
    # ================================================================

    plan_result = await build_rag(
        request.current_state_id,
        request.target_state_id,
        db,
    )

    if plan_result.status != "success":
        # Mark failed
        solve_req.status = "failed"
        solve_req.solved_at = datetime.now(timezone.utc)
        await db.commit()

        error_code = "NO_SOLUTION" if plan_result.status == "no_solution" else "INTERNAL_ERROR"
        if "circular" in (plan_result.error_message or "").lower():
            error_code = "CIRCULAR_DEPENDENCY"

        return {
            "solve_request_id": solve_req.id,
            "status": "failed",
            "error_code": error_code,
            "error_message": plan_result.error_message,
        }

    # Save candidate plan
    plan_id = await save_candidate_plan(plan_result.rag, solve_req.id, db)

    # ================================================================
    # 4. Scheduler: solve schedule
    # ================================================================

    sched_result = await solve_schedule(plan_id, db)

    if sched_result.status not in ("optimal", "feasible"):
        solve_req.status = "failed"
        solve_req.solved_at = datetime.now(timezone.utc)
        await db.commit()

        error_code = "INFEASIBLE" if sched_result.status == "infeasible" else "SOLVER_TIMEOUT"

        return {
            "solve_request_id": solve_req.id,
            "status": "failed",
            "candidate_plan_id": plan_id,
            "error_code": error_code,
            "error_message": sched_result.error_message,
        }

    # Save schedule result
    result_id = await save_schedule_result(sched_result, solve_req.id, plan_id, db)

    # ================================================================
    # 5. Mark done
    # ================================================================

    solve_req.status = "done"
    solve_req.solved_at = datetime.now(timezone.utc)
    await db.commit()

    # ================================================================
    # 6. Build response
    # ================================================================

    tasks_response = []
    for t in sched_result.tasks:
        res_code = t.resources[0]["resource_code"] if t.resources else None
        tasks_response.append({
            "step": t.step_order,
            "op_code": t.op_rule_code,
            "start": t.start_min,
            "end": t.end_min,
            "resource": res_code,
            "predecessors": t.predecessors,
        })

    return {
        "solve_request_id": solve_req.id,
        "status": "done",
        "candidate_plan_id": plan_id,
        "schedule": {
            "makespan": sched_result.makespan,
            "tasks": tasks_response,
            "parallel_groups": sched_result.parallel_groups,
        },
    }

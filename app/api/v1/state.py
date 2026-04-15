"""
State and solve-request query endpoints.

GET /api/v1/machines/{id}/state — Query machine current state
GET /api/v1/solve-requests/{id} — Query solve request result
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Machine,
    MachineState,
    MachineStateFeature,
    SolveRequest,
    ScheduleResult,
    CandidatePlan,
    CandidatePlanStep,
)
from app.db.schemas import (
    MachineCurrentStateResponse,
    MachineStatesListResponse,
    SolveRequestDetailResponse,
)
from app.db.session import get_db_session

router = APIRouter(tags=["query"])


@router.get("/machines/{machine_id}/states", response_model=MachineStatesListResponse)
async def list_machine_states(
    machine_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """List all available states for a machine (for current/target selection)."""

    machine = await db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")

    result = await db.execute(
        select(MachineState)
        .where(MachineState.machine_id == machine_id)
        .options(selectinload(MachineState.features))
        .order_by(MachineState.id)
    )
    states = result.scalars().all()

    return {
        "machine_id": machine.id,
        "machine_code": machine.code,
        "states": [
            {
                "state_id": s.id,
                "state_type": s.state_type,
                "label": s.label,
                "features": {f.feature_key: f.feature_value for f in s.features},
            }
            for s in states
        ],
    }


@router.get("/machines/{machine_id}/state", response_model=MachineCurrentStateResponse)
async def get_machine_state(
    machine_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Query machine's current state."""

    machine = await db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")

    # Find the latest 'current' state
    result = await db.execute(
        select(MachineState)
        .where(
            MachineState.machine_id == machine_id,
            MachineState.state_type == "current",
        )
        .options(selectinload(MachineState.features))
        .order_by(MachineState.created_at.desc())
        .limit(1)
    )
    state = result.scalar_one_or_none()

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No current state found for machine {machine_id}",
        )

    features = {f.feature_key: f.feature_value for f in state.features}

    return {
        "machine_id": machine.id,
        "machine_code": machine.code,
        "current_state": {
            "state_id": state.id,
            "label": state.label,
            "features": features,
        },
    }


@router.get("/solve-requests/{request_id}", response_model=SolveRequestDetailResponse)
async def get_solve_request(
    request_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Query solve request and its result."""

    solve_req = await db.get(SolveRequest, request_id)
    if solve_req is None:
        raise HTTPException(
            status_code=404, detail=f"Solve request {request_id} not found"
        )

    response = {
        "id": solve_req.id,
        "machine_id": solve_req.machine_id,
        "status": solve_req.status,
        "objective": solve_req.objective,
        "created_at": solve_req.created_at.isoformat() if solve_req.created_at else None,
        "solved_at": solve_req.solved_at.isoformat() if solve_req.solved_at else None,
    }

    # If done, attach schedule
    if solve_req.status == "done":
        sched_result = await db.execute(
            select(ScheduleResult)
            .where(ScheduleResult.solve_request_id == request_id)
            .order_by(ScheduleResult.created_at.desc())
            .limit(1)
        )
        sched = sched_result.scalar_one_or_none()

        if sched:
            response["candidate_plan_id"] = sched.candidate_plan_id
            response["schedule"] = {
                "makespan": sched.makespan,
                "solver_status": sched.solver_status,
                "tasks": sched.tasks,
            }

    return response

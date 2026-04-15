"""
Plan management endpoints.

GET /api/v1/plans/{plan_id}/versions        — version chain query
GET /api/v1/plans/{plan_id}/diff/{other_id} — step-level diff between two plans
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CandidatePlan, CandidatePlanStep, OpRule, ScheduleResult
from app.db.schemas import PlanDiffResponse, PlanDiffStep, PlanVersionItem
from app.db.session import get_db_session

router = APIRouter(tags=["plans"])

_MAX_CHAIN_DEPTH = 20


@router.get("/plans/{plan_id}/versions", response_model=list[PlanVersionItem])
async def get_plan_versions(
    plan_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return the complete version chain for the given plan.

    Traces parent_plan_id links upward to the root plan (parent_plan_id = NULL),
    then returns the full chain sorted by version ascending.
    """
    # Verify the requested plan exists
    start_plan = await db.get(CandidatePlan, plan_id)
    if start_plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    # Walk up to the root
    root_id = plan_id
    visited: set[int] = set()
    depth = 0
    current = start_plan
    while current.parent_plan_id is not None and depth < _MAX_CHAIN_DEPTH:
        parent_id = int(current.parent_plan_id)
        if parent_id in visited:
            break  # cycle guard
        visited.add(current.id)
        parent = await db.get(CandidatePlan, parent_id)
        if parent is None:
            break
        current = parent
        root_id = current.id
        depth += 1

    # Load all plans that share the same root by walking down from root
    # Use a simple BFS via solve_request_id: collect plans where the chain
    # includes root_id, by fetching all plans whose parent chain leads to root_id.
    chain: list[CandidatePlan] = []
    queue = [root_id]
    seen: set[int] = set()

    while queue:
        cid = queue.pop(0)
        if cid in seen:
            continue
        seen.add(cid)
        plan = await db.get(CandidatePlan, cid)
        if plan is None:
            continue
        chain.append(plan)
        # Find children
        children_result = await db.execute(
            select(CandidatePlan.id).where(CandidatePlan.parent_plan_id == cid)
        )
        for child_id in children_result.scalars().all():
            if child_id not in seen:
                queue.append(child_id)

    chain.sort(key=lambda p: p.version)
    return chain


async def _load_schedule_tasks(plan_id: int, db: AsyncSession) -> tuple[dict, int | None]:
    """Load the latest ScheduleResult for a plan.

    Returns:
        (op_code -> {"start_min": int, "end_min": int}, makespan)
        Raises HTTPException 422 if no schedule exists.
    """
    result = await db.execute(
        select(ScheduleResult)
        .where(ScheduleResult.candidate_plan_id == plan_id)
        .order_by(ScheduleResult.id.desc())
        .limit(1)
    )
    sched = result.scalar_one_or_none()
    if sched is None:
        raise HTTPException(
            status_code=422,
            detail=f"PLAN_NOT_SCHEDULED: Plan {plan_id} has no schedule result",
        )

    tasks_by_code: dict[str, dict] = {}
    for t in (sched.tasks or []):
        code = t.get("op_rule_code")
        if code:
            # Note: op_rule_code is used as the join key for diff alignment.
            # The current RAGBuilder guarantees each op_rule appears at most once
            # per plan (state-space search consumes each delta exactly once).
            # If a future planner allows repeating ops, this dict must be keyed
            # by (op_rule_code, step_order) instead.
            tasks_by_code[code] = {
                "start_min": t.get("start_min"),
                "end_min": t.get("end_min"),
            }

    return tasks_by_code, sched.makespan


async def _load_step_meta(plan_id: int, db: AsyncSession) -> dict[str, dict]:
    """Load CandidatePlanStep metadata (step_role, not_before) for a plan.

    Returns op_code -> {"step_role": str, "not_before": int|None}.
    """
    result = await db.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id == plan_id)
        .options(selectinload(CandidatePlanStep.op_rule))
    )
    steps = result.scalars().all()
    return {
        s.op_rule.code: {"step_role": s.step_role, "not_before": s.not_before}
        for s in steps
        if s.op_rule is not None
    }


@router.get("/plans/{plan_id}/diff/{other_plan_id}", response_model=PlanDiffResponse)
async def get_plan_diff(
    plan_id: int,
    other_plan_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return a step-level diff between two plans.

    plan_id       = base (older) plan
    other_plan_id = new  (newer) plan

    Each step entry shows base_start/end and new_start/end, plus step_role
    and not_before taken from the NEW plan.
    """
    # Validate both plans exist
    base_plan = await db.get(CandidatePlan, plan_id)
    if base_plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    new_plan = await db.get(CandidatePlan, other_plan_id)
    if new_plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {other_plan_id} not found")

    # Load schedule tasks for both plans
    base_tasks, base_makespan = await _load_schedule_tasks(plan_id, db)
    new_tasks, new_makespan = await _load_schedule_tasks(other_plan_id, db)

    # Load step metadata (step_role, not_before) from NEW plan
    new_step_meta = await _load_step_meta(other_plan_id, db)

    # Build diff over the union of all op_codes
    all_codes = sorted(set(base_tasks) | set(new_tasks))

    diff_steps: list[PlanDiffStep] = []
    for code in all_codes:
        base_t = base_tasks.get(code)
        new_t = new_tasks.get(code)
        meta = new_step_meta.get(code, {})

        diff_steps.append(PlanDiffStep(
            op_code=code,
            base_start=base_t["start_min"] if base_t else None,
            base_end=base_t["end_min"] if base_t else None,
            new_start=new_t["start_min"] if new_t else None,
            new_end=new_t["end_min"] if new_t else None,
            step_role=meta.get("step_role", "normal"),
            not_before=meta.get("not_before"),
        ))

    # Sort: new_start ascending (None last), then op_code alphabetically
    diff_steps.sort(key=lambda s: (s.new_start is None, s.new_start or 0, s.op_code))

    return PlanDiffResponse(
        base_plan_id=plan_id,
        new_plan_id=other_plan_id,
        base_makespan=base_makespan,
        new_makespan=new_makespan,
        steps=diff_steps,
    )

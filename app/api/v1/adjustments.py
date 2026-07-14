"""Plan-adjustment draft, preview, and baseline-confirmation endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CandidatePlan, PlanAdjustment
from app.db.schemas import (
    PlanAdjustmentCreate,
    PlanAdjustmentPreviewResponse,
    PlanAdjustmentResponse,
    PlanAdjustmentUpdate,
)
from app.db.session import get_db_session
from app.services.plan_adjustment import (
    cancel_adjustment,
    confirm_adjustment,
    create_adjustment,
    get_adjustment,
    preview_adjustment,
    update_adjustment,
)


router = APIRouter(tags=["plan-adjustments"])


@router.post(
    "/plans/{baseline_plan_id}/adjustments",
    response_model=PlanAdjustmentResponse,
)
async def create_plan_adjustment(
    baseline_plan_id: int,
    payload: PlanAdjustmentCreate,
    db: AsyncSession = Depends(get_db_session),
):
    adjustment = await create_adjustment(
        baseline_plan_id,
        kind=payload.kind,
        scope_step_ids=payload.scope_step_ids,
        constraints=payload.constraints,
        remove_inherited_constraint_ids=payload.remove_inherited_constraint_ids,
        candidate_plan_id=payload.candidate_plan_id,
        session=db,
    )
    await db.commit()
    await db.refresh(adjustment)
    return adjustment


@router.get("/plan-adjustments/{adjustment_id}", response_model=PlanAdjustmentResponse)
async def read_plan_adjustment(
    adjustment_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    return await get_adjustment(adjustment_id, db)


@router.patch("/plan-adjustments/{adjustment_id}", response_model=PlanAdjustmentResponse)
async def patch_plan_adjustment(
    adjustment_id: int,
    payload: PlanAdjustmentUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    adjustment = await get_adjustment(adjustment_id, db)
    result = await update_adjustment(
        adjustment,
        scope_step_ids=payload.scope_step_ids,
        constraints=payload.constraints,
        remove_inherited_constraint_ids=payload.remove_inherited_constraint_ids,
        session=db,
    )
    await db.commit()
    await db.refresh(result)
    return result


@router.post(
    "/plan-adjustments/{adjustment_id}/preview",
    response_model=PlanAdjustmentPreviewResponse,
)
async def preview_plan_adjustment(
    adjustment_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    adjustment = await get_adjustment(adjustment_id, db)
    result, task_diffs = await preview_adjustment(adjustment, db)
    await db.commit()
    await db.refresh(result)
    return {
        "adjustment": result,
        "candidate_plan_id": result.candidate_plan_id,
        "status": result.status,
        "summary": result.preview_summary,
        "task_diffs": task_diffs,
        "diagnostics": result.diagnostics,
    }


@router.post("/plan-adjustments/{adjustment_id}/confirm", response_model=PlanAdjustmentResponse)
async def confirm_plan_adjustment(
    adjustment_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    adjustment = await get_adjustment(adjustment_id, db)
    result = await confirm_adjustment(adjustment, db)
    await db.commit()
    await db.refresh(result)
    return result


@router.post("/plan-adjustments/{adjustment_id}/cancel", response_model=PlanAdjustmentResponse)
async def cancel_plan_adjustment(
    adjustment_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    adjustment = await get_adjustment(adjustment_id, db)
    result = await cancel_adjustment(adjustment, db)
    await db.commit()
    await db.refresh(result)
    return result


@router.get("/plans/{plan_id}/adjustments", response_model=list[PlanAdjustmentResponse])
async def list_plan_adjustments(
    plan_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    plan = await db.get(CandidatePlan, plan_id)
    if plan is not None and plan.plan_family_id is not None:
        family_id = plan.plan_family_id
        result = await db.execute(
            select(PlanAdjustment)
            .where(PlanAdjustment.plan_family_id == family_id)
            .order_by(PlanAdjustment.created_at.desc(), PlanAdjustment.id.desc())
        )
        return result.scalars().all()
    plan_adjustment = await db.execute(
        select(PlanAdjustment).where(PlanAdjustment.baseline_plan_id == plan_id)
    )
    direct = list(plan_adjustment.scalars().all())
    if direct:
        return direct
    return []

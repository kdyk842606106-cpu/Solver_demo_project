"""
Step role computation for version chain diff.

Computes step_role labels by comparing new plan against parent plan:
- normal: unchanged timing
- pulled_forward: starts earlier than parent
- delayed: starts later than parent
- repair: new repair operation (is_repair=TRUE) not in parent
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CandidatePlan, CandidatePlanStep, OpRule, ScheduleResult


def _build_step_start_map(tasks: list[dict]) -> dict[int, int]:
    """Build step_order -> start_min map from tasks JSON."""
    return {t["step_order"]: t["start_min"] for t in tasks}


async def compute_step_role_diff(
    new_plan_id: int,
    parent_plan_id: Optional[int],
    session: AsyncSession,
) -> dict[int, str]:
    """
    Compute and persist step_role for a new plan vs its parent.

    Algorithm:
      1. parent_plan_id is None → all steps role = 'normal'
      2. Otherwise for each new step:
         a. Find same op_rule_id in parent plan
            - Not found → 'repair'
            - Found → compare start_min
              · new < parent → 'pulled_forward'
              · new > parent → 'delayed'
              · equal → 'normal'
      3. Steps only in parent are ignored (not part of this diff)

    Args:
        new_plan_id: ID of the new candidate plan
        parent_plan_id: ID of the parent candidate plan (None for initial solve)
        session: Database session

    Returns:
        Dict mapping step_order -> step_role string
    """
    if parent_plan_id is None:
        result = await session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
        )
        steps = result.scalars().all()
        step_roles = {s.step_order: "normal" for s in steps}
        for step in steps:
            step.step_role = "normal"
        await session.flush()
        return step_roles

    parent_result = await session.execute(
        select(CandidatePlan)
        .where(CandidatePlan.id == parent_plan_id)
        .options(selectinload(CandidatePlan.steps))
    )
    parent_plan = parent_result.scalar_one_or_none()
    if parent_plan is None:
        result = await session.execute(
            select(CandidatePlanStep)
            .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
        )
        steps = result.scalars().all()
        step_roles = {s.step_order: "normal" for s in steps}
        for step in steps:
            step.step_role = "normal"
        await session.flush()
        return step_roles

    parent_steps_by_rule: dict[int, list[CandidatePlanStep]] = {}
    for step in parent_plan.steps:
        parent_steps_by_rule.setdefault(step.op_rule_id, []).append(step)
    for steps in parent_steps_by_rule.values():
        steps.sort(key=lambda s: s.step_order)

    new_result = await session.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
        .options(selectinload(CandidatePlanStep.op_rule))
    )
    new_steps = new_result.scalars().all()

    rule_ids = [s.op_rule_id for s in new_steps]
    rules_result = await session.execute(
        select(OpRule)
        .where(OpRule.id.in_(rule_ids))
    )
    rules_map: dict[int, OpRule] = {r.id: r for r in rules_result.scalars().all()}

    new_schedule_result = await session.execute(
        select(ScheduleResult)
        .where(ScheduleResult.candidate_plan_id == new_plan_id)
    )
    new_schedule = new_schedule_result.scalar_one_or_none()
    new_start_map: dict[int, int] = {}
    if new_schedule and new_schedule.tasks:
        new_start_map = _build_step_start_map(new_schedule.tasks)

    parent_schedule_result = await session.execute(
        select(ScheduleResult)
        .where(ScheduleResult.candidate_plan_id == parent_plan_id)
    )
    parent_schedule = parent_schedule_result.scalar_one_or_none()
    parent_start_map: dict[int, int] = {}
    if parent_schedule and parent_schedule.tasks:
        parent_start_map = _build_step_start_map(parent_schedule.tasks)

    result_steps = await session.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id == new_plan_id)
    )
    steps_to_update = result_steps.scalars().all()
    steps_by_order: dict[int, CandidatePlanStep] = {s.step_order: s for s in steps_to_update}

    step_roles: dict[int, str] = {}

    for step in new_steps:
        rule = rules_map.get(step.op_rule_id)
        parent_steps = parent_steps_by_rule.get(step.op_rule_id, [])
        if not parent_steps:
            if rule and rule.is_repair:
                role = "repair"
            else:
                role = "normal"
        else:
            new_start = new_start_map.get(step.step_order)
            matched_parent_step = None
            for parent_step in parent_steps:
                if parent_step.step_order == step.step_order:
                    matched_parent_step = parent_step
                    break
            if matched_parent_step is None:
                matched_parent_step = parent_steps[0]
            parent_start = parent_start_map.get(matched_parent_step.step_order)
            if new_start is not None and parent_start is not None:
                if new_start < parent_start:
                    role = "pulled_forward"
                elif new_start > parent_start:
                    role = "delayed"
                else:
                    role = "normal"
            else:
                role = "normal"

        step_roles[step.step_order] = role

    for step_order, role in step_roles.items():
        steps_by_order[step_order].step_role = role

    await session.flush()

    return step_roles

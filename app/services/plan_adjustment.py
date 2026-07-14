"""Application service for persisted, constraint-driven plan adjustments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scheduler.solver import save_schedule_result, solve_schedule
from app.db.models import (
    CandidatePlan,
    CandidatePlanStep,
    PlanAdjustment,
    PlanFamily,
    ScheduleResult,
    SolveRequest,
)


class PlanAdjustmentError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


async def _load_plan(plan_id: int, session: AsyncSession) -> CandidatePlan:
    result = await session.execute(
        select(CandidatePlan)
        .where(CandidatePlan.id == plan_id)
        .options(
            selectinload(CandidatePlan.steps),
            selectinload(CandidatePlan.solve_request),
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise PlanAdjustmentError("PLAN_NOT_FOUND", f"Plan {plan_id} not found")
    return plan


async def _latest_schedule(plan_id: int, session: AsyncSession) -> ScheduleResult:
    result = await session.execute(
        select(ScheduleResult)
        .where(ScheduleResult.candidate_plan_id == plan_id)
        .order_by(ScheduleResult.id.desc())
        .limit(1)
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise PlanAdjustmentError("PLAN_NOT_SCHEDULED", f"Plan {plan_id} has no schedule")
    return schedule


async def ensure_plan_family(plan: CandidatePlan, session: AsyncSession) -> PlanFamily:
    """Return the plan family, lazily upgrading create_all/test data when needed."""
    if plan.plan_family_id is not None:
        family = await session.get(PlanFamily, plan.plan_family_id)
        if family is not None:
            return family
    family = PlanFamily(
        machine_id=plan.solve_request.machine_id,
        baseline_plan_id=plan.id,
        next_version=max(int(plan.version or 1) + 1, 2),
    )
    session.add(family)
    await session.flush()
    plan.plan_family_id = family.id
    plan.status = "baseline"
    await session.flush()
    return family


def _serialize_constraints(constraints: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    seen_ids: set[str] = set()
    for raw in constraints:
        item = raw.model_dump(mode="json", exclude_none=True) if hasattr(raw, "model_dump") else dict(raw)
        constraint_id = str(item.get("id") or uuid4())
        if constraint_id in seen_ids:
            raise PlanAdjustmentError(
                "DUPLICATE_CONSTRAINT_ID",
                f"Duplicate constraint id: {constraint_id}",
            )
        seen_ids.add(constraint_id)
        item["id"] = constraint_id
        item["step_ids"] = sorted({int(value) for value in item.get("step_ids") or []})
        normalized.append(item)
    return normalized


async def create_adjustment(
    baseline_plan_id: int,
    *,
    kind: str,
    scope_step_ids: list[int],
    constraints: list[Any],
    remove_inherited_constraint_ids: list[str],
    candidate_plan_id: int | None = None,
    session: AsyncSession,
) -> PlanAdjustment:
    plan = await _load_plan(baseline_plan_id, session)
    await _latest_schedule(plan.id, session)
    family = await ensure_plan_family(plan, session)
    if family.baseline_plan_id != plan.id:
        raise PlanAdjustmentError("PLAN_NOT_BASELINE", "Adjustments must start from the current baseline")
    candidate = None
    candidate_summary = None
    if candidate_plan_id is not None:
        if kind not in {"blockage", "rule_exception"}:
            raise PlanAdjustmentError(
                "INVALID_ADJUSTMENT_KIND",
                "Only full-replan adjustments may register an existing candidate",
            )
        candidate = await _load_plan(candidate_plan_id, session)
        if candidate.parent_plan_id != plan.id:
            raise PlanAdjustmentError(
                "CANDIDATE_PARENT_MISMATCH",
                "The full-replan candidate must be a direct child of the selected baseline",
            )
        candidate_schedule = await _latest_schedule(candidate.id, session)
        base_schedule = await _latest_schedule(plan.id, session)
        base_tasks = _schedule_task_map(base_schedule)
        candidate_tasks = _schedule_task_map(candidate_schedule)
        changed_count = 0
        total_shift = 0
        for step_order in set(base_tasks) & set(candidate_tasks):
            shift = abs(
                int(candidate_tasks[step_order]["start_min"])
                - int(base_tasks[step_order]["start_min"])
            )
            if shift >= 1:
                changed_count += 1
                total_shift += shift
        candidate_summary = {
            "base_makespan_min": base_schedule.makespan,
            "candidate_makespan_min": candidate_schedule.makespan,
            "makespan_delta_min": (candidate_schedule.makespan or 0) - (base_schedule.makespan or 0),
            "base_task_count": len(base_tasks),
            "candidate_task_count": len(candidate_tasks),
            "shared_changed_task_count": changed_count,
            "shared_total_shift_min": total_shift,
            "candidate_solve_request_id": candidate.solve_request_id,
            "candidate_plan_id": candidate.id,
        }
        candidate.plan_family_id = family.id
        candidate.status = "candidate"
        family.next_version = max(family.next_version, int(candidate.version or 0) + 1)

    adjustment = PlanAdjustment(
        plan_family_id=family.id,
        baseline_plan_id=plan.id,
        kind=kind,
        status="preview_ready" if candidate is not None else "draft",
        scope_step_ids=sorted({int(value) for value in scope_step_ids}),
        constraints=_serialize_constraints(constraints),
        remove_inherited_constraint_ids=sorted(set(remove_inherited_constraint_ids)),
        candidate_plan_id=candidate.id if candidate is not None else None,
        preview_summary=candidate_summary,
        previewed_at=datetime.now(timezone.utc) if candidate is not None else None,
    )
    session.add(adjustment)
    await session.flush()
    return adjustment


async def get_adjustment(adjustment_id: int, session: AsyncSession) -> PlanAdjustment:
    adjustment = await session.get(PlanAdjustment, adjustment_id)
    if adjustment is None:
        raise PlanAdjustmentError("ADJUSTMENT_NOT_FOUND", f"Adjustment {adjustment_id} not found")
    return adjustment


async def update_adjustment(
    adjustment: PlanAdjustment,
    *,
    scope_step_ids: list[int],
    constraints: list[Any],
    remove_inherited_constraint_ids: list[str],
    session: AsyncSession,
) -> PlanAdjustment:
    if adjustment.status not in {"draft", "infeasible", "preview_ready"}:
        raise PlanAdjustmentError("ADJUSTMENT_NOT_EDITABLE", "Adjustment is not editable")
    if adjustment.candidate_plan_id is not None:
        candidate = await session.get(CandidatePlan, adjustment.candidate_plan_id)
        if candidate is not None:
            candidate.status = "discarded"
    adjustment.candidate_plan_id = None
    adjustment.status = "draft"
    adjustment.scope_step_ids = sorted({int(value) for value in scope_step_ids})
    adjustment.constraints = _serialize_constraints(constraints)
    adjustment.remove_inherited_constraint_ids = sorted(set(remove_inherited_constraint_ids))
    adjustment.effective_constraints = None
    adjustment.preview_summary = None
    adjustment.diagnostics = None
    adjustment.previewed_at = None
    await session.flush()
    return adjustment


def _schedule_task_map(schedule: ScheduleResult) -> dict[int, dict[str, Any]]:
    return {
        int(task["step_order"]): dict(task)
        for task in (schedule.tasks or [])
        if task.get("step_order") is not None
    }


def _normalize_absolute_time(
    item: dict[str, Any],
    solve_request: SolveRequest,
) -> dict[str, Any]:
    if item.get("type") not in {"not_before", "finish_not_after", "fixed_start"}:
        return item
    if item.get("value_min") is not None:
        return item
    value_at = item.get("value_at")
    if value_at is None or solve_request.schedule_start_at is None:
        raise PlanAdjustmentError(
            "INVALID_TIME_CONSTRAINT",
            "Absolute adjustment time requires a calendar schedule baseline",
        )
    parsed = datetime.fromisoformat(str(value_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise PlanAdjustmentError("INVALID_TIME_CONSTRAINT", "Absolute time must include timezone")
    delta_seconds = (parsed - solve_request.schedule_start_at).total_seconds()
    if delta_seconds < 0 or delta_seconds % 60:
        raise PlanAdjustmentError(
            "INVALID_TIME_CONSTRAINT",
            "Absolute adjustment time must use minute precision within the plan coordinate",
        )
    result = dict(item)
    result["value_min"] = int(delta_seconds // 60)
    return result


def _has_cycle(step_orders: set[int], edges: set[tuple[int, int]]) -> bool:
    adjacency = {step: [] for step in step_orders}
    indegree = {step: 0 for step in step_orders}
    for left, right in edges:
        if left not in adjacency or right not in adjacency:
            continue
        adjacency[left].append(right)
        indegree[right] += 1
    queue = [step for step, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for successor in adjacency[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    return visited != len(step_orders)


def _compile_context(
    plan: CandidatePlan,
    schedule: ScheduleResult,
    scope_step_ids: list[int],
    effective_constraints: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[int, CandidatePlanStep]]:
    steps_by_id = {step.id: step for step in plan.steps}
    scope = set(scope_step_ids)
    if not scope:
        raise PlanAdjustmentError("EMPTY_CHANGE_SCOPE", "Select at least one activity to adjust")
    unknown = sorted(scope - set(steps_by_id))
    if unknown:
        raise PlanAdjustmentError(
            "STEP_OUTSIDE_BASELINE",
            "Adjustment scope contains tasks outside the baseline plan",
            details={"step_ids": unknown},
        )
    task_map = _schedule_task_map(schedule)
    base_starts = {
        step.step_order: int(task_map[step.step_order]["start_min"])
        for step in plan.steps
        if step.step_order in task_map
    }
    compiled = []
    priority_by_step: dict[int, str] = {}
    edges = {
        (int(predecessor), step.step_order)
        for step in plan.steps
        for predecessor in (step.predecessor_ids or [])
    }
    for raw in effective_constraints:
        item = _normalize_absolute_time(raw, plan.solve_request)
        constraint_type = item.get("type")
        compiled_item = {"id": item["id"], "type": constraint_type}
        if constraint_type == "precedence":
            endpoints = {int(item["predecessor_step_id"]), int(item["successor_step_id"])}
            if not endpoints.issubset(scope):
                raise PlanAdjustmentError(
                    "STEP_OUTSIDE_CHANGE_SCOPE",
                    "Both precedence tasks must be in the selected adjustment scope",
                )
            predecessor = steps_by_id[int(item["predecessor_step_id"])].step_order
            successor = steps_by_id[int(item["successor_step_id"])].step_order
            compiled_item.update({
                "predecessor_step_order": predecessor,
                "successor_step_order": successor,
            })
            edges.add((predecessor, successor))
        else:
            target_ids = {int(value) for value in item.get("step_ids") or []}
            if not target_ids.issubset(scope):
                raise PlanAdjustmentError(
                    "STEP_OUTSIDE_CHANGE_SCOPE",
                    "Constraint tasks must be in the selected adjustment scope",
                    details={"step_ids": sorted(target_ids - scope)},
                )
            step_orders = [steps_by_id[step_id].step_order for step_id in sorted(target_ids)]
            compiled_item["step_orders"] = step_orders
            if item.get("value_min") is not None:
                compiled_item["value_min"] = int(item["value_min"])
            if constraint_type == "priority":
                compiled_item["value"] = item["value"]
                for step_order in step_orders:
                    priority_by_step[step_order] = item["value"]
        compiled.append(compiled_item)
    if _has_cycle({step.step_order for step in plan.steps}, edges):
        raise PlanAdjustmentError("CONSTRAINT_CYCLE", "Artificial precedence creates a dependency cycle")
    return ({
        "scope_step_orders": [steps_by_id[step_id].step_order for step_id in sorted(scope)],
        "base_starts": base_starts,
        "priority_by_step": priority_by_step,
        "constraints": compiled,
    }, steps_by_id)


def _constraint_step_ids(constraint: dict[str, Any]) -> set[int]:
    if constraint.get("type") == "precedence":
        return {
            int(constraint["predecessor_step_id"]),
            int(constraint["successor_step_id"]),
        }
    return {int(value) for value in constraint.get("step_ids") or []}


def _rebase_constraint_step_ids(
    constraints: list[dict[str, Any]],
    step_id_map: dict[int, int],
) -> list[dict[str, Any]]:
    rebased = []
    for raw in constraints:
        item = dict(raw)
        if item.get("type") == "precedence":
            for field in ("predecessor_step_id", "successor_step_id"):
                source_id = int(item[field])
                if source_id not in step_id_map:
                    raise PlanAdjustmentError(
                        "STEP_OUTSIDE_BASELINE",
                        "Inherited adjustment constraint references an unavailable activity",
                        details={"step_ids": [source_id]},
                    )
                item[field] = step_id_map[source_id]
        else:
            source_ids = [int(value) for value in item.get("step_ids") or []]
            missing = sorted(set(source_ids) - set(step_id_map))
            if missing:
                raise PlanAdjustmentError(
                    "STEP_OUTSIDE_BASELINE",
                    "Inherited adjustment constraint references unavailable activities",
                    details={"step_ids": missing},
                )
            item["step_ids"] = sorted({step_id_map[source_id] for source_id in source_ids})
        rebased.append(item)
    return rebased


async def _rebase_inherited_constraints(
    plan: CandidatePlan,
    inherited: list[dict[str, Any]],
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Map inherited snapshot IDs onto the current baseline plan.

    Current snapshots already use the baseline step IDs. Early TICKET-095
    snapshots stored the parent plan IDs; those are recovered through the
    globally stable step order so existing plan families remain editable.
    """
    if not inherited:
        return []
    current_by_order = {step.step_order: step.id for step in plan.steps}
    current_ids = set(current_by_order.values())
    referenced_ids = set().union(*(_constraint_step_ids(item) for item in inherited))
    foreign_ids = referenced_ids - current_ids
    step_id_map = {step_id: step_id for step_id in referenced_ids & current_ids}
    if foreign_ids:
        result = await session.execute(
            select(CandidatePlanStep.id, CandidatePlanStep.step_order).where(
                CandidatePlanStep.id.in_(foreign_ids)
            )
        )
        source_orders = {int(step_id): int(step_order) for step_id, step_order in result.all()}
        missing = sorted(foreign_ids - set(source_orders))
        if missing:
            raise PlanAdjustmentError(
                "STEP_OUTSIDE_BASELINE",
                "Inherited adjustment constraint references unavailable activities",
                details={"step_ids": missing},
            )
        unavailable_orders = sorted(set(source_orders.values()) - set(current_by_order))
        if unavailable_orders:
            raise PlanAdjustmentError(
                "STEP_OUTSIDE_BASELINE",
                "Inherited adjustment activity is unavailable in the current baseline",
                details={"step_orders": unavailable_orders},
            )
        step_id_map.update({
            source_id: current_by_order[step_order]
            for source_id, step_order in source_orders.items()
        })
    return _rebase_constraint_step_ids(inherited, step_id_map)


async def _effective_constraints(
    plan: CandidatePlan,
    adjustment: PlanAdjustment,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    removed = set(adjustment.remove_inherited_constraint_ids or [])
    inherited = [
        dict(item)
        for item in (plan.adjustment_snapshot or {}).get("constraints", [])
        if str(item.get("id")) not in removed
    ]
    inherited = await _rebase_inherited_constraints(plan, inherited, session)
    current_ids = {str(item["id"]) for item in adjustment.constraints or []}
    return [item for item in inherited if str(item.get("id")) not in current_ids] + [
        dict(item) for item in adjustment.constraints or []
    ]


async def _clone_plan(
    baseline: CandidatePlan,
    family: PlanFamily,
    effective_constraints: list[dict[str, Any]],
    session: AsyncSession,
) -> tuple[SolveRequest, CandidatePlan]:
    source = baseline.solve_request
    request = SolveRequest(
        machine_id=source.machine_id,
        current_state_id=source.current_state_id,
        target_state_id=source.target_state_id,
        objective=source.objective,
        objectives=source.objectives,
        constraints=source.constraints,
        parent_plan_id=baseline.id,
        overrides=source.overrides,
        blockage_constraints=None,
        calendar_enabled=source.calendar_enabled,
        schedule_start_at=source.schedule_start_at,
        schedule_timezone=source.schedule_timezone,
        calendar_snapshot=source.calendar_snapshot,
        status="running",
    )
    session.add(request)
    await session.flush()
    candidate = CandidatePlan(
        plan_family_id=family.id,
        solve_request_id=request.id,
        total_steps=baseline.total_steps,
        search_method=baseline.search_method,
        version=family.next_version,
        parent_plan_id=baseline.id,
        replan_reason="manual_adjustment",
        status="candidate",
        adjustment_snapshot=None,
    )
    session.add(candidate)
    await session.flush()
    candidate_steps = []
    for source_step in sorted(baseline.steps, key=lambda step: step.step_order):
        candidate_step = CandidatePlanStep(
            candidate_plan_id=candidate.id,
            step_order=source_step.step_order,
            op_rule_id=source_step.op_rule_id,
            predecessor_ids=list(source_step.predecessor_ids or []),
            not_before=source_step.not_before,
            step_role="normal",
            lineage_key=source_step.lineage_key,
        )
        session.add(candidate_step)
        candidate_steps.append(candidate_step)
    await session.flush()
    candidate_by_order = {step.step_order: step.id for step in candidate_steps}
    snapshot_step_id_map = {
        source_step.id: candidate_by_order[source_step.step_order]
        for source_step in baseline.steps
    }
    candidate.adjustment_snapshot = {
        "constraints": _rebase_constraint_step_ids(effective_constraints, snapshot_step_id_map)
    }
    await session.flush()
    return request, candidate


def _preview_summary(
    base_schedule: ScheduleResult,
    result: Any,
    scope_orders: set[int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_tasks = _schedule_task_map(base_schedule)
    new_tasks = {task.step_order: task for task in result.tasks or []}
    diffs = []
    outside_changed = inside_changed = outside_shift = inside_shift = 0
    for step_order in sorted(set(base_tasks) | set(new_tasks)):
        base = base_tasks.get(step_order)
        new = new_tasks.get(step_order)
        base_start = base.get("start_min") if base else None
        new_start = new.start_min if new else None
        shift = abs(int(new_start) - int(base_start)) if base_start is not None and new_start is not None else None
        changed = shift is None or shift >= 1
        in_scope = step_order in scope_orders
        if changed and shift is not None:
            if in_scope:
                inside_changed += 1
                inside_shift += shift
            else:
                outside_changed += 1
                outside_shift += shift
        diffs.append({
            "step_order": step_order,
            "op_rule_code": (base or {}).get("op_rule_code") or getattr(new, "op_rule_code", None),
            "in_scope": in_scope,
            "base_start_min": base_start,
            "base_end_min": base.get("end_min") if base else None,
            "new_start_min": new_start,
            "new_end_min": new.end_min if new else None,
            "shift_min": shift,
            "changed": changed,
        })
    summary = {
        "base_makespan_min": base_schedule.makespan,
        "candidate_makespan_min": result.makespan,
        "makespan_delta_min": (result.makespan or 0) - (base_schedule.makespan or 0),
        "scope_changed_task_count": inside_changed,
        "scope_total_shift_min": inside_shift,
        "outside_changed_task_count": outside_changed,
        "outside_total_shift_min": outside_shift,
        "critical_path": result.critical_path or [],
    }
    return summary, diffs


async def preview_adjustment(
    adjustment: PlanAdjustment,
    session: AsyncSession,
) -> tuple[PlanAdjustment, list[dict[str, Any]]]:
    if adjustment.status not in {"draft", "infeasible", "preview_ready"}:
        raise PlanAdjustmentError("ADJUSTMENT_NOT_PREVIEWABLE", "Adjustment cannot be previewed")
    baseline = await _load_plan(adjustment.baseline_plan_id, session)
    family_result = await session.execute(
        select(PlanFamily).where(PlanFamily.id == adjustment.plan_family_id).with_for_update()
    )
    family = family_result.scalar_one()
    if family.baseline_plan_id != baseline.id:
        adjustment.status = "stale"
        await session.flush()
        raise PlanAdjustmentError("ADJUSTMENT_STALE", "The baseline plan has changed")
    base_schedule = await _latest_schedule(baseline.id, session)
    effective = await _effective_constraints(baseline, adjustment, session)
    context, _ = _compile_context(
        baseline,
        base_schedule,
        list(adjustment.scope_step_ids or []),
        effective,
    )
    if adjustment.candidate_plan_id is not None:
        previous = await session.get(CandidatePlan, adjustment.candidate_plan_id)
        if previous is not None:
            previous.status = "discarded"
    adjustment.status = "previewing"
    adjustment.candidate_plan_id = None
    await session.flush()
    request, candidate = await _clone_plan(baseline, family, effective, session)
    result = await solve_schedule(
        candidate.id,
        session,
        objectives=request.objectives,
        adjustment_context=context,
    )
    adjustment.previewed_at = datetime.now(timezone.utc)
    adjustment.effective_constraints = effective
    if result.status not in {"optimal", "feasible"}:
        await session.delete(candidate)
        await session.delete(request)
        adjustment.status = "infeasible"
        adjustment.diagnostics = result.diagnostics or {"error_message": result.error_message}
        adjustment.preview_summary = None
        await session.flush()
        return adjustment, []

    await save_schedule_result(result, request.id, candidate.id, session)
    candidate_steps_result = await session.execute(
        select(CandidatePlanStep).where(CandidatePlanStep.candidate_plan_id == candidate.id)
    )
    candidate_steps = {step.step_order: step for step in candidate_steps_result.scalars().all()}
    base_starts = context["base_starts"]
    for task in result.tasks or []:
        candidate_step = candidate_steps.get(task.step_order)
        base_start = base_starts.get(task.step_order)
        if candidate_step is None or base_start is None:
            continue
        if task.start_min > base_start:
            candidate_step.step_role = "delayed"
        elif task.start_min < base_start:
            candidate_step.step_role = "pulled_forward"
        else:
            candidate_step.step_role = "normal"
    for item in context["constraints"]:
        if item.get("type") != "precedence":
            continue
        successor = candidate_steps[int(item["successor_step_order"])]
        predecessor = int(item["predecessor_step_order"])
        successor.predecessor_ids = sorted(set(successor.predecessor_ids or []) | {predecessor})
    request.status = "done"
    request.solved_at = datetime.now(timezone.utc)
    family.next_version += 1
    adjustment.status = "preview_ready"
    adjustment.candidate_plan_id = candidate.id
    summary, diffs = _preview_summary(
        base_schedule,
        result,
        set(context["scope_step_orders"]),
    )
    summary["candidate_solve_request_id"] = request.id
    summary["candidate_plan_id"] = candidate.id
    summary["task_diffs"] = diffs
    adjustment.preview_summary = summary
    adjustment.diagnostics = result.diagnostics
    await session.flush()
    return adjustment, diffs


async def confirm_adjustment(adjustment: PlanAdjustment, session: AsyncSession) -> PlanAdjustment:
    if adjustment.status != "preview_ready" or adjustment.candidate_plan_id is None:
        raise PlanAdjustmentError("PREVIEW_NOT_READY", "Preview a feasible candidate before confirmation")
    family_result = await session.execute(
        select(PlanFamily).where(PlanFamily.id == adjustment.plan_family_id).with_for_update()
    )
    family = family_result.scalar_one()
    if family.baseline_plan_id != adjustment.baseline_plan_id:
        adjustment.status = "stale"
        await session.flush()
        raise PlanAdjustmentError("BASELINE_PLAN_CHANGED", "The plan baseline changed before confirmation")
    baseline = await session.get(CandidatePlan, adjustment.baseline_plan_id)
    candidate = await session.get(CandidatePlan, adjustment.candidate_plan_id)
    if baseline is None or candidate is None:
        raise PlanAdjustmentError("PREVIEW_NOT_READY", "Candidate plan is unavailable")
    baseline.status = "superseded"
    candidate.status = "baseline"
    family.baseline_plan_id = candidate.id
    adjustment.status = "confirmed"
    adjustment.confirmed_at = datetime.now(timezone.utc)
    stale_result = await session.execute(
        select(PlanAdjustment).where(
            PlanAdjustment.plan_family_id == family.id,
            PlanAdjustment.baseline_plan_id == baseline.id,
            PlanAdjustment.id != adjustment.id,
            PlanAdjustment.status.in_(["draft", "infeasible", "preview_ready"]),
        )
    )
    for item in stale_result.scalars().all():
        item.status = "stale"
    await session.flush()
    return adjustment


async def cancel_adjustment(adjustment: PlanAdjustment, session: AsyncSession) -> PlanAdjustment:
    if adjustment.status in {"confirmed", "cancelled"}:
        raise PlanAdjustmentError("ADJUSTMENT_NOT_CANCELLABLE", "Adjustment cannot be cancelled")
    if adjustment.candidate_plan_id is not None:
        candidate = await session.get(CandidatePlan, adjustment.candidate_plan_id)
        if candidate is not None:
            candidate.status = "discarded"
    adjustment.status = "cancelled"
    adjustment.cancelled_at = datetime.now(timezone.utc)
    await session.flush()
    return adjustment

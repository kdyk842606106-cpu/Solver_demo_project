"""Resolve persisted calendar policy into pure Scheduler inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scheduler.calendar import (
    CalendarError,
    consume_contiguous_work,
    expand_definition_with_metadata,
    intersect_calendar_intervals,
    get_zone,
    longest_contiguous_work_window,
)
from app.core.scheduler.loader import RagData
from app.db.models import (
    CandidatePlan,
    Machine,
    MachineStateDimensionCalendar,
    OpRule,
    SolveRequest,
    StateFeatureDef,
    WorkCalendar,
)


@dataclass
class SchedulerCalendarContext:
    schedule_start_at: datetime
    display_timezone: str
    horizon: int
    windows_by_step: dict[int, list[tuple[int, int]]]
    window_metadata_by_step: dict[int, list[dict[str, Any]]]
    resolution_by_step: dict[int, dict[str, Any]]
    snapshot: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _max_horizon_days() -> int:
    raw = os.getenv("SOLVER_CALENDAR_MAX_HORIZON_DAYS", "366")
    try:
        return max(1, int(raw))
    except ValueError as exc:
        raise CalendarError("CALENDAR_HORIZON_EXCEEDED", "Invalid SOLVER_CALENDAR_MAX_HORIZON_DAYS") from exc


async def _parent_snapshot(session: AsyncSession, parent_plan_id: int | None) -> dict[str, Any] | None:
    if not parent_plan_id:
        return None
    result = await session.execute(
        select(CandidatePlan)
        .where(CandidatePlan.id == parent_plan_id)
        .options(selectinload(CandidatePlan.solve_request))
    )
    plan = result.scalar_one_or_none()
    if plan is None or plan.solve_request is None:
        return None
    return plan.solve_request.calendar_snapshot


async def _latest_policy(
    rag_data: RagData,
    session: AsyncSession,
) -> dict[str, Any]:
    machine = await session.get(Machine, rag_data.machine_id)
    if machine is None:
        raise CalendarError("DEFAULT_WORK_CALENDAR_MISSING", "Machine not found")
    configured_default_id = machine.default_work_calendar_id
    inherits_system_default = configured_default_id is None
    default_calendar_id = configured_default_id
    if default_calendar_id is None:
        default_calendar_id = await session.scalar(
            select(WorkCalendar.id).where(
                WorkCalendar.is_system_default.is_(True),
                WorkCalendar.is_active.is_(True),
            )
        )
    if default_calendar_id is None:
        raise CalendarError("DEFAULT_WORK_CALENDAR_MISSING", "Machine and system have no default work calendar")

    binding_result = await session.execute(
        select(MachineStateDimensionCalendar).where(
            MachineStateDimensionCalendar.machine_id == machine.id
        )
    )
    bindings = {
        item.state_dimension_template_id: item.work_calendar_id
        for item in binding_result.scalars().all()
    }
    feature_result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine.machine_type_id)
    )
    feature_dimensions = {
        item.feature_key: (item.id if item.is_dimension_template else item.dimension_template_id)
        for item in feature_result.scalars().all()
        if item.is_dimension_template or item.dimension_template_id is not None
    }
    calendar_ids = {default_calendar_id, *bindings.values()}
    calendar_result = await session.execute(
        select(WorkCalendar)
        .where(WorkCalendar.id.in_(calendar_ids))
        .options(selectinload(WorkCalendar.current_revision))
    )
    calendars: dict[str, Any] = {}
    for calendar in calendar_result.scalars().all():
        revision = calendar.current_revision
        if not calendar.is_active or revision is None:
            raise CalendarError("CALENDAR_REVISION_NOT_FOUND", f"Calendar {calendar.code} has no active revision")
        calendars[str(calendar.id)] = {
            "calendar_id": calendar.id,
            "calendar_code": calendar.code,
            "calendar_name": calendar.name,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "checksum": revision.checksum,
            "timezone": revision.timezone,
            "weekly_windows": revision.weekly_windows,
            "date_exceptions": revision.date_exceptions,
        }
    if str(default_calendar_id) not in calendars:
        raise CalendarError("DEFAULT_WORK_CALENDAR_MISSING", "Default work calendar is unavailable")
    return {
        "configured_default_calendar_id": configured_default_id,
        "default_calendar_id": default_calendar_id,
        "inherits_system_default": inherits_system_default,
        "dimension_bindings": {str(key): value for key, value in bindings.items()},
        "feature_dimensions": feature_dimensions,
        "calendars": calendars,
    }


def _topological_steps(rag_data: RagData) -> list[int]:
    successors: dict[int, list[int]] = {step.step_order: [] for step in rag_data.steps}
    indegree = {step.step_order: 0 for step in rag_data.steps}
    for left, right in rag_data.edges:
        if left in successors and right in indegree:
            successors[left].append(right)
            indegree[right] += 1
    ready = sorted(key for key, value in indegree.items() if value == 0)
    ordered: list[int] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in successors[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    return ordered if len(ordered) == len(indegree) else sorted(indegree)


async def resolve_scheduler_calendar(
    rag_data: RagData,
    session: AsyncSession,
    scheduling_rule_context: Any | None = None,
) -> SchedulerCalendarContext | None:
    if not rag_data.calendar_enabled:
        return None
    if rag_data.schedule_start_at is None:
        raise CalendarError("CALENDAR_START_REQUIRED", "schedule_start_at is required")
    anchor = rag_data.schedule_start_at
    if anchor.tzinfo is None:
        raise CalendarError("CALENDAR_START_REQUIRED", "schedule_start_at must include timezone")
    if anchor.second or anchor.microsecond:
        raise CalendarError("CALENDAR_START_REQUIRED", "schedule_start_at must use minute precision")

    draft = rag_data.calendar_snapshot or {}
    revision_policy = draft.get("revision_policy") or ("inherit" if rag_data.parent_plan_id else "latest")
    inherited = await _parent_snapshot(session, rag_data.parent_plan_id) if revision_policy != "latest" else None
    if inherited:
        policy = {
            "configured_default_calendar_id": inherited.get("configured_default_calendar_id"),
            "default_calendar_id": inherited["default_calendar_id"],
            "inherits_system_default": inherited.get("inherits_system_default", False),
            "dimension_bindings": inherited.get("dimension_bindings", {}),
            "feature_dimensions": inherited.get("feature_dimensions", {}),
            "calendars": inherited.get("calendars", {}),
        }
        anchor = datetime.fromisoformat(inherited["schedule_start_at"])
        display_timezone = inherited.get("display_timezone") or rag_data.schedule_timezone or "UTC"
        inherited_flag = True
    else:
        policy = await _latest_policy(rag_data, session)
        display_timezone = rag_data.schedule_timezone or "UTC"
        inherited_flag = False
    get_zone(display_timezone)

    op_rule_ids = [step.op_rule_id for step in rag_data.steps]
    rule_result = await session.execute(
        select(OpRule).where(OpRule.id.in_(op_rule_ids)).options(selectinload(OpRule.effects))
    )
    rules = {item.id: item for item in rule_result.scalars().all()}
    default_calendar_id = int(policy["default_calendar_id"])
    dimension_bindings = {int(key): int(value) for key, value in policy.get("dimension_bindings", {}).items()}
    feature_dimensions = {str(key): int(value) for key, value in policy.get("feature_dimensions", {}).items()}
    calendars = policy["calendars"]

    resolutions: dict[int, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    if policy.get("inherits_system_default"):
        warnings.append({
            "code": "CALENDAR_SYSTEM_DEFAULT_FALLBACK",
            "machine_id": rag_data.machine_id,
            "calendar_id": default_calendar_id,
        })
    for step in rag_data.steps:
        rule = rules.get(step.op_rule_id)
        feature_keys = sorted({effect.feature_key for effect in rule.effects}) if rule else []
        dimensions = sorted({feature_dimensions[key] for key in feature_keys if key in feature_dimensions})
        calendar_ids: list[int] = []
        fallback = False
        if not dimensions:
            calendar_ids = [default_calendar_id]
            fallback = True
            warnings.append({
                "code": "LEGACY_FEATURE_WITHOUT_DIMENSION",
                "step_order": step.step_order,
                "feature_keys": feature_keys,
            })
        else:
            for dimension_id in dimensions:
                calendar_id = dimension_bindings.get(dimension_id)
                if calendar_id is None:
                    calendar_id = default_calendar_id
                    fallback = True
                    warnings.append({
                        "code": "CALENDAR_DEFAULT_FALLBACK",
                        "step_order": step.step_order,
                        "state_dimension_template_id": dimension_id,
                    })
                calendar_ids.append(calendar_id)
        calendar_ids = sorted(set(calendar_ids))
        if len(calendar_ids) > 1:
            warnings.append({
                "code": "MULTI_DIMENSION_CALENDAR_INTERSECTION",
                "step_order": step.step_order,
                "calendar_ids": calendar_ids,
            })
        for calendar_id in calendar_ids:
            if str(calendar_id) not in calendars:
                raise CalendarError("CALENDAR_REVISION_NOT_FOUND", f"Calendar {calendar_id} is missing from snapshot")
        resolutions[step.step_order] = {
            "feature_keys": feature_keys,
            "dimension_template_ids": dimensions,
            "calendar_ids": calendar_ids,
            "combination": "intersection" if len(calendar_ids) > 1 else "single",
            "fallback_to_default": fallback,
        }

    max_end = anchor + timedelta(days=_max_horizon_days())
    expanded = {
        int(calendar_id): expand_definition_with_metadata(definition, anchor, max_end)
        for calendar_id, definition in calendars.items()
    }
    windows_by_step: dict[int, list[tuple[int, int]]] = {}
    metadata_by_step: dict[int, list[dict[str, Any]]] = {}
    anchor_utc = anchor.astimezone(timezone.utc)
    for step_order, resolution in resolutions.items():
        absolute = intersect_calendar_intervals(
            [expanded[calendar_id] for calendar_id in resolution["calendar_ids"]]
        )
        allowed_shift_codes = (
            scheduling_rule_context.allowed_shift_codes_by_step.get(step_order)
            if scheduling_rule_context is not None else None
        )
        if allowed_shift_codes is not None:
            filtered = []
            for item in absolute:
                shift_codes = {code for code, _name in item.shifts if code}
                if not shift_codes:
                    raise CalendarError(
                        "SCHEDULING_SHIFT_METADATA_REQUIRED",
                        f"Step {step_order} requires shift metadata",
                    )
                if shift_codes.intersection(allowed_shift_codes):
                    filtered.append(item)
            absolute = filtered
            resolution["allowed_shift_codes"] = sorted(allowed_shift_codes)
        windows: list[tuple[int, int]] = []
        metadata: list[dict[str, Any]] = []
        for item in absolute:
            start_min = max(0, int((item.start - anchor_utc).total_seconds() // 60))
            end_min = int((item.end - anchor_utc).total_seconds() // 60)
            if end_min > start_min:
                windows.append((start_min, end_min))
                metadata.append(item.metadata())
        if not windows:
            raise CalendarError("CALENDAR_NO_COMMON_WINDOW", f"Step {step_order} has no common work window")
        windows_by_step[step_order] = windows
        metadata_by_step[step_order] = metadata

    step_map = {step.step_order: step for step in rag_data.steps}
    cursor = 0
    for step_order in _topological_steps(rag_data):
        step = step_map[step_order]
        cursor = max(cursor, step.not_before or 0)
        end = consume_contiguous_work(windows_by_step[step_order], cursor, step.duration_min)
        if end is None:
            longest = longest_contiguous_work_window(windows_by_step[step_order])
            allowed_shifts = resolutions[step_order].get("allowed_shift_codes") or []
            filtering_rules = []
            if scheduling_rule_context is not None:
                filtering_rules = [
                    rule["code"] for rule in scheduling_rule_context.active_rules
                    if rule.get("type") == "shift_restriction"
                    and rule["code"] in scheduling_rule_context.matched_rule_codes_by_step.get(step_order, [])
                ]
            raise CalendarError(
                "CALENDAR_CONTIGUOUS_WINDOW_TOO_SHORT",
                f"Step {step_order} requires {step.duration_min} continuous minutes; longest window is {longest}",
                {
                    "step_order": step_order,
                    "op_rule_code": step.op_rule_code,
                    "required_duration_min": step.duration_min,
                    "longest_contiguous_allowed_min": longest,
                    "allowed_shift_codes": allowed_shifts,
                    "filtering_rule_codes": filtering_rules,
                },
            )
        cursor = end
    horizon = max(cursor, 1)
    trimmed = {
        step_order: [(start, min(end, horizon)) for start, end in windows if start < horizon]
        for step_order, windows in windows_by_step.items()
    }
    trimmed_metadata = {
        step_order: [
            metadata_by_step[step_order][index]
            for index, (start, _end) in enumerate(windows)
            if start < horizon
        ]
        for step_order, windows in windows_by_step.items()
    }
    snapshot = {
        "enabled": True,
        "revision_policy": revision_policy,
        "inherited": inherited_flag,
        "schedule_start_at": anchor.isoformat(),
        "display_timezone": display_timezone,
        "configured_default_calendar_id": policy.get("configured_default_calendar_id"),
        "default_calendar_id": default_calendar_id,
        "inherits_system_default": bool(policy.get("inherits_system_default")),
        "dimension_bindings": {str(key): value for key, value in dimension_bindings.items()},
        "feature_dimensions": feature_dimensions,
        "calendars": calendars,
        "steps": {str(key): value for key, value in resolutions.items()},
        "warnings": warnings,
        "horizon_min": horizon,
    }
    if inherited_flag:
        warnings.append({"code": "CALENDAR_SNAPSHOT_INHERITED"})
    return SchedulerCalendarContext(
        schedule_start_at=anchor,
        display_timezone=display_timezone,
        horizon=horizon,
        windows_by_step=trimmed,
        window_metadata_by_step=trimmed_metadata,
        resolution_by_step=resolutions,
        snapshot=snapshot,
        warnings=warnings,
    )


async def persist_calendar_snapshot(
    solve_request_id: int,
    context: SchedulerCalendarContext,
    session: AsyncSession,
) -> None:
    solve_request = await session.get(SolveRequest, solve_request_id)
    if solve_request is None:
        return
    solve_request.schedule_start_at = context.schedule_start_at
    solve_request.schedule_timezone = context.display_timezone
    solve_request.calendar_snapshot = context.snapshot
    await session.flush()

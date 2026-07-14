"""Work calendar master data and per-machine calendar policy APIs."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scheduler.calendar import (
    CalendarError,
    definition_checksum,
    expand_definition_with_metadata,
    validate_definition,
)
from app.db.models import (
    Machine,
    MachineStateDimensionCalendar,
    StateFeatureDef,
    WorkCalendar,
    WorkCalendarRevision,
)
from app.db.schemas import (
    MachineCalendarPolicyResponse,
    MachineCalendarPolicyUpdate,
    WorkCalendarCreate,
    WorkCalendarPreviewRequest,
    WorkCalendarResponse,
    WorkCalendarRevisionResponse,
    WorkCalendarUpdate,
)
from app.db.session import get_db_session


router = APIRouter(tags=["work-calendars"])


def _definition(payload: WorkCalendarCreate | WorkCalendarUpdate) -> tuple[list[dict], list[dict]]:
    weekly = [item.model_dump(exclude_none=True) for item in payload.weekly_windows]
    exceptions = [item.model_dump(exclude_none=True) for item in payload.date_exceptions]
    try:
        validate_definition(payload.timezone, weekly, exceptions)
    except CalendarError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    return weekly, exceptions


async def _append_revision(
    db: AsyncSession,
    calendar: WorkCalendar,
    *,
    timezone_name: str,
    weekly: list[dict],
    exceptions: list[dict],
) -> WorkCalendarRevision:
    latest = await db.scalar(
        select(func.max(WorkCalendarRevision.revision_no)).where(
            WorkCalendarRevision.work_calendar_id == calendar.id
        )
    )
    revision = WorkCalendarRevision(
        work_calendar_id=calendar.id,
        revision_no=int(latest or 0) + 1,
        timezone=timezone_name,
        weekly_windows=weekly,
        date_exceptions=exceptions,
        checksum=definition_checksum(timezone_name, weekly, exceptions),
    )
    db.add(revision)
    await db.flush()
    calendar.current_revision_id = revision.id
    calendar.current_revision = revision
    await db.flush()
    return revision


async def _calendar_or_404(db: AsyncSession, calendar_id: int) -> WorkCalendar:
    result = await db.execute(
        select(WorkCalendar)
        .where(WorkCalendar.id == calendar_id)
        .options(selectinload(WorkCalendar.current_revision))
    )
    calendar = result.scalar_one_or_none()
    if calendar is None:
        raise HTTPException(status_code=404, detail=f"Work calendar {calendar_id} not found")
    return calendar


async def _system_default_id(db: AsyncSession) -> int | None:
    return await db.scalar(
        select(WorkCalendar.id).where(
            WorkCalendar.is_system_default.is_(True),
            WorkCalendar.is_active.is_(True),
        )
    )


@router.get("/work-calendars", response_model=list[WorkCalendarResponse])
async def list_work_calendars(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(WorkCalendar).options(selectinload(WorkCalendar.current_revision)).order_by(WorkCalendar.code)
    )
    return result.scalars().all()


@router.post("/work-calendars", response_model=WorkCalendarResponse, status_code=status.HTTP_201_CREATED)
async def create_work_calendar(payload: WorkCalendarCreate, db: AsyncSession = Depends(get_db_session)):
    if await db.scalar(select(WorkCalendar.id).where(WorkCalendar.code == payload.code)) is not None:
        raise HTTPException(status_code=409, detail=f"Work calendar code '{payload.code}' already exists")
    weekly, exceptions = _definition(payload)
    calendar = WorkCalendar(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(calendar)
    await db.flush()
    await _append_revision(
        db, calendar, timezone_name=payload.timezone, weekly=weekly, exceptions=exceptions
    )
    await db.commit()
    return await _calendar_or_404(db, calendar.id)


@router.get("/work-calendars/{calendar_id}", response_model=WorkCalendarResponse)
async def get_work_calendar(calendar_id: int, db: AsyncSession = Depends(get_db_session)):
    return await _calendar_or_404(db, calendar_id)


@router.put("/work-calendars/{calendar_id}", response_model=WorkCalendarResponse)
async def update_work_calendar(
    calendar_id: int,
    payload: WorkCalendarUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    calendar = await _calendar_or_404(db, calendar_id)
    weekly, exceptions = _definition(payload)
    if calendar.is_system_default and not payload.is_active:
        raise HTTPException(status_code=409, detail="SYSTEM_DEFAULT_CALENDAR_REQUIRED")
    calendar.name = payload.name
    calendar.description = payload.description
    calendar.is_active = payload.is_active
    await _append_revision(
        db, calendar, timezone_name=payload.timezone, weekly=weekly, exceptions=exceptions
    )
    await db.commit()
    return await _calendar_or_404(db, calendar.id)


@router.get("/work-calendars/{calendar_id}/revisions", response_model=list[WorkCalendarRevisionResponse])
async def list_work_calendar_revisions(calendar_id: int, db: AsyncSession = Depends(get_db_session)):
    await _calendar_or_404(db, calendar_id)
    result = await db.execute(
        select(WorkCalendarRevision)
        .where(WorkCalendarRevision.work_calendar_id == calendar_id)
        .order_by(WorkCalendarRevision.revision_no.desc())
    )
    return result.scalars().all()


@router.post("/work-calendars/{calendar_id}/preview")
async def preview_work_calendar(
    calendar_id: int,
    payload: WorkCalendarPreviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    calendar = await _calendar_or_404(db, calendar_id)
    revision = calendar.current_revision
    if revision is None:
        raise HTTPException(status_code=409, detail="CALENDAR_REVISION_NOT_FOUND")
    if payload.start_at.tzinfo is None or payload.end_at.tzinfo is None or payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="Preview range must be timezone-aware and increasing")
    intervals = expand_definition_with_metadata(
        {
            "timezone": revision.timezone,
            "weekly_windows": revision.weekly_windows,
            "date_exceptions": revision.date_exceptions,
        },
        payload.start_at,
        payload.end_at,
    )
    return {
        "calendar_id": calendar.id,
        "revision_id": revision.id,
        "timezone": revision.timezone,
        "intervals": [
            {
                "start_at": item.start.astimezone(timezone.utc).isoformat(),
                "end_at": item.end.astimezone(timezone.utc).isoformat(),
                **item.metadata(),
            }
            for item in intervals
        ],
    }


@router.post("/work-calendars/{calendar_id}/set-default", response_model=WorkCalendarResponse)
async def set_system_default_calendar(
    calendar_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    calendar = await _calendar_or_404(db, calendar_id)
    if calendar.current_revision is None:
        raise HTTPException(status_code=409, detail="CALENDAR_REVISION_NOT_FOUND")
    await db.execute(update(WorkCalendar).values(is_system_default=False))
    calendar.is_active = True
    calendar.is_system_default = True
    await db.commit()
    return await _calendar_or_404(db, calendar.id)


@router.get("/machines/{machine_id}/calendar-policy", response_model=MachineCalendarPolicyResponse)
async def get_machine_calendar_policy(machine_id: int, db: AsyncSession = Depends(get_db_session)):
    machine = await db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    result = await db.execute(
        select(MachineStateDimensionCalendar)
        .where(MachineStateDimensionCalendar.machine_id == machine_id)
        .options(
            selectinload(MachineStateDimensionCalendar.state_dimension_template),
            selectinload(MachineStateDimensionCalendar.work_calendar),
        )
        .order_by(MachineStateDimensionCalendar.id)
    )
    bindings = result.scalars().all()
    system_default_id = await _system_default_id(db)
    inherits_system_default = machine.default_work_calendar_id is None
    return {
        "machine_id": machine.id,
        "default_work_calendar_id": machine.default_work_calendar_id,
        "effective_default_work_calendar_id": machine.default_work_calendar_id or system_default_id,
        "inherits_system_default": inherits_system_default,
        "dimension_bindings": [
            {
                "state_dimension_template_id": item.state_dimension_template_id,
                "state_dimension_template_key": item.state_dimension_template.feature_key,
                "state_dimension_template_name": item.state_dimension_template.feature_name,
                "work_calendar_id": item.work_calendar_id,
                "work_calendar_code": item.work_calendar.code,
                "work_calendar_name": item.work_calendar.name,
            }
            for item in bindings
        ],
    }


@router.put("/machines/{machine_id}/calendar-policy", response_model=MachineCalendarPolicyResponse)
async def update_machine_calendar_policy(
    machine_id: int,
    payload: MachineCalendarPolicyUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    machine = await db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    if payload.default_work_calendar_id is not None:
        default_calendar = await _calendar_or_404(db, payload.default_work_calendar_id)
        if not default_calendar.is_active:
            raise HTTPException(status_code=422, detail="Default work calendar is inactive")
    elif await _system_default_id(db) is None:
        raise HTTPException(status_code=422, detail="DEFAULT_WORK_CALENDAR_MISSING")
    seen: set[int] = set()
    resolved = []
    for item in payload.dimension_bindings:
        if item.state_dimension_template_id in seen:
            raise HTTPException(status_code=422, detail="Duplicate state dimension template binding")
        seen.add(item.state_dimension_template_id)
        dimension = await db.get(StateFeatureDef, item.state_dimension_template_id)
        if (
            dimension is None
            or dimension.machine_type_id != machine.machine_type_id
            or not dimension.is_dimension_template
        ):
            raise HTTPException(status_code=422, detail="INVALID_DIMENSION_CALENDAR_BINDING")
        calendar = await _calendar_or_404(db, item.work_calendar_id)
        if not calendar.is_active:
            raise HTTPException(status_code=422, detail=f"Work calendar {calendar.code} is inactive")
        resolved.append(item)
    await db.execute(
        delete(MachineStateDimensionCalendar).where(MachineStateDimensionCalendar.machine_id == machine_id)
    )
    machine.default_work_calendar_id = payload.default_work_calendar_id
    db.add_all(
        [
            MachineStateDimensionCalendar(
                machine_id=machine_id,
                state_dimension_template_id=item.state_dimension_template_id,
                work_calendar_id=item.work_calendar_id,
            )
            for item in resolved
        ]
    )
    await db.commit()
    return await get_machine_calendar_policy(machine_id, db)


@router.delete("/work-calendars/{calendar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_work_calendar(calendar_id: int, db: AsyncSession = Depends(get_db_session)):
    calendar = await _calendar_or_404(db, calendar_id)
    if calendar.is_system_default:
        raise HTTPException(status_code=409, detail="SYSTEM_DEFAULT_CALENDAR_REQUIRED")
    calendar.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Run legacy, A*, and GA against one immutable expanded scenario snapshot."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlannerRunRecord, PlannerScenarioRecord
from app.db.session import get_db_session
from app.services.planner_engine_bridge import PlannerEngineUnavailable, planner_available, planner_project_path, run_engine
from app.services.planner_scenarios import PlannerScenarioError, scenario_hash, validate_scenario
from app.services.planner_run_windows import ActivityTimeWindow, freeze_run_windows


router = APIRouter(prefix="/planner-runs", tags=["planner-runs"])

SUPPORTED_OBJECTIVES = {
    "minimize_makespan",
    "minimize_activity_group_span",
    "minimize_activity_group_gaps",
    "minimize_activity_group_interruptions",
    "minimize_state_group_span",
    "minimize_state_group_gaps",
    "minimize_state_group_interruptions",
}
DEFAULT_OBJECTIVES = [{"type": "minimize_makespan", "weight": 1.0}]


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    expected_revision: int
    current_state_ids: list[str] = Field(default_factory=list)
    target_state_ids: list[str] = Field(default_factory=list)
    engine: Literal["LEGACY", "ASTAR", "GA", "JOINT_CP_SAT", "ALL", "ALL_WITH_CP_SAT"] = "ALL"
    seed: int = 42
    budget: dict[str, Any] = Field(default_factory=dict)
    display_start_at: datetime | None = None
    display_timezone: str = "Asia/Shanghai"
    objectives: list[dict[str, Any]] = Field(default_factory=lambda: [dict(item) for item in DEFAULT_OBJECTIVES])
    activity_time_windows: list[ActivityTimeWindow] = Field(default_factory=list)


@router.get("/capabilities")
async def capabilities():
    joint_workers = None
    if planner_available():
        from app.services.planner_engine_bridge import _planner_modules
        _planner_modules()
        from app.core.joint_cpsat import search_worker_count
        joint_workers = search_worker_count()
    return {
        "planner_available": planner_available(),
        "planner_project_path": str(planner_project_path()),
        "engines": ["LEGACY", "ASTAR", "GA", "JOINT_CP_SAT", "ALL", "ALL_WITH_CP_SAT"],
        "async_runs_supported": True,
        "joint_cp_sat": {
            "calendar_supported": True,
            "calendar_scope": "project",
            "calendar_interruption": "pause_resume",
            "fragile_lift_night_restriction_supported": True,
            "crane_exclusivity_supported": True,
            "commissioning_exclusivity_supported": True,
            "exclusivity_scope": "all_activities",
            "scheduling_rules_supported": False,
            "resource_instances_supported": False,
            "execution_modes": ["serial", "parallel"],
            "objectives": ["minimize_makespan"],
            "tie_breaker": "minimize_execution_count",
            "time_windows_supported": True,
            "run_activity_time_windows_supported": True,
            "run_activity_time_windows_scope": "first_occurrence",
            "run_activity_time_windows_optional_bounds": True,
            "automatic_execution_bound_supported": True,
            "automatic_budget_supported": True,
            "state_changing_external_events_supported": False,
            "resource_model": "aggregate_capacity",
            "worker_threads": joint_workers,
            "parallel_search_supported": True,
            "search_counter_scope": "first_subsolver_per_epoch_when_parallel",
            "proof_scope": "input_execution_count_bounds",
        },
        "resource_model": "aggregate_capacity",
        "resource_instances_supported": False,
        "input_schema": "planner-shared-scenario/v2",
        "supported_input_schemas": ["planner-shared-scenario/v1", "planner-shared-scenario/v2"],
        "delete_effects_supported": True,
        "legacy_pipeline": "partial_order_pathfinder+cp_sat_scheduler",
        "legacy_objectives": sorted(SUPPORTED_OBJECTIVES),
        "legacy_calendar_supported": False,
        "legacy_scheduling_rules_supported": False,
    }


@router.get("")
async def list_runs(scenario_id: str | None = None, db: AsyncSession = Depends(get_db_session)):
    statement = select(PlannerRunRecord).order_by(PlannerRunRecord.created_at.desc())
    if scenario_id:
        statement = statement.where(PlannerRunRecord.scenario_id == scenario_id)
    return [_serialize(item, include_result=False, include_snapshot=False) for item in (await db.execute(statement)).scalars().all()]


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await db.get(PlannerRunRecord, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error_code": "PLANNER_RUN_NOT_FOUND", "id": run_id})
    return _serialize(record, include_result=True, include_snapshot=True)


@router.get("/{run_id}/progress")
async def get_progress(run_id: str, known_plan_version: int = 0, db: AsyncSession = Depends(get_db_session)):
    r = PlannerRunRecord
    # A single snapshot of status and payload; avoid loading the immutable input
    # or moving a large unchanged incumbent across the database connection.
    row = (await db.execute(select(
        r.id.label("run_id"), r.scenario_id, r.job_status, r.status, r.started_at,
        r.error_message, r.progress_version, r.plan_version, r.progress_json.label("metrics"),
        case((r.plan_version != known_plan_version, r.live_plan_json)).label("candidate"),
    ).where(r.id == run_id))).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "PLANNER_RUN_NOT_FOUND", "id": run_id})
    return dict(row)


@router.post("", status_code=201)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _prepare_record(payload, db)
    scenario = copy.deepcopy(record.request_json["effective_scenario_snapshot"])
    run_id = record.id
    snapshot_hash = record.scenario_hash
    base_scenario_hash = record.request_json["base_scenario_hash"]
    objectives = record.request_json["objectives"]

    engines = (["LEGACY", "ASTAR", "GA"] if payload.engine == "ALL" else
               ["LEGACY", "ASTAR", "GA", "JOINT_CP_SAT"] if payload.engine == "ALL_WITH_CP_SAT" else [payload.engine])
    try:
        results = await asyncio.gather(
            *[
                asyncio.to_thread(
                    run_engine,
                    copy.deepcopy(scenario),
                    engine=engine,
                    run_id=run_id,
                    seed=payload.seed,
                    budget_override=payload.budget,
                    objectives=objectives,
                )
                for engine in engines
            ],
            return_exceptions=True,
        )
        normalized: dict[str, Any] = {}
        for engine, result in zip(engines, results, strict=True):
            if isinstance(result, BaseException):
                normalized[engine] = {"algorithm": engine, "status": "ERROR", "error": str(result), "scenario_hash": snapshot_hash}
            else:
                normalized[engine] = result
        hashes = {item.get("scenario_hash") for item in normalized.values()}
        if hashes != {snapshot_hash}:
            raise RuntimeError("Engine input snapshot hash mismatch")
        successful = [item for item in normalized.values() if item.get("paths")]
        record.status = "OK" if len(successful) == len(engines) else "TIMEOUT_PARTIAL" if successful else "ERROR"
        if payload.engine == "JOINT_CP_SAT":
            record.status = normalized["JOINT_CP_SAT"].get("status", "ERROR")
        record.result_json = {
            "run_id": run_id,
            "scenario_id": payload.scenario_id,
            "base_scenario_hash": base_scenario_hash,
            "scenario_hash": snapshot_hash,
            "engines_share_mutable_state": False,
            "results": normalized,
        }
    except (PlannerScenarioError, PlannerEngineUnavailable) as exc:
        record.status = "ERROR"
        record.result_json = {"run_id": run_id, "scenario_hash": snapshot_hash, "error": str(exc)}
    finally:
        record.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return _serialize(record, include_result=True, include_snapshot=True)


def _serialize(record: PlannerRunRecord, *, include_result: bool, include_snapshot: bool) -> dict[str, Any]:
    request = copy.deepcopy(record.request_json or {})
    if not include_snapshot:
        request.pop("effective_scenario_snapshot", None)
    payload = {
        "id": record.id,
        "scenario_id": record.scenario_id,
        "scenario_hash": record.scenario_hash,
        "engine": record.engine,
        "status": record.status,
        "request": request,
        "created_at": record.created_at,
        "finished_at": record.finished_at,
        "run_id": record.id,
        "job_status": record.job_status,
        "started_at": record.started_at,
        "error_message": record.error_message,
    }
    if include_result:
        payload["result"] = record.result_json
    return payload


def _state_error(code: str, message: str, state_ids: list[str], state_by_id: dict[str, dict[str, Any]]) -> HTTPException:
    return HTTPException(status_code=422, detail={
        "error_code": code,
        "error_message": message,
        "states": [
            {"id": state_id, "name": state_by_id.get(state_id, {}).get("name") or state_id}
            for state_id in state_ids
        ],
    })


def _normalize_objectives(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items or DEFAULT_OBJECTIVES):
        objective_type = str(item.get("type") or "").strip()
        if objective_type not in SUPPORTED_OBJECTIVES:
            raise HTTPException(status_code=422, detail={
                "error_code": "PLANNER_OBJECTIVE_UNSUPPORTED",
                "error_message": f"Unsupported objective: {objective_type}",
                "objective_index": index,
            })
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail={
                "error_code": "PLANNER_OBJECTIVE_WEIGHT_INVALID",
                "error_message": f"Invalid objective weight at index {index}",
            }) from exc
        if weight <= 0:
            raise HTTPException(status_code=422, detail={
                "error_code": "PLANNER_OBJECTIVE_WEIGHT_INVALID",
                "error_message": "Objective weight must be greater than zero",
                "objective_index": index,
            })
        normalized.append({"type": objective_type, "weight": weight})
    return normalized or [dict(item) for item in DEFAULT_OBJECTIVES]


async def _prepare_record(payload: RunCreate, db: AsyncSession, *, lock_snapshot: bool = False):
    query = select(PlannerScenarioRecord).where(PlannerScenarioRecord.id == payload.scenario_id)
    if lock_snapshot:
        query = query.with_for_update()
    scenario_record = (await db.execute(query)).scalar_one_or_none()
    if scenario_record is None:
        raise HTTPException(status_code=404, detail={"error_code": "SCENARIO_NOT_FOUND", "id": payload.scenario_id})
    if scenario_record.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail={
            "error_code": "SCENARIO_REVISION_CONFLICT",
            "expected": payload.expected_revision,
            "actual": scenario_record.revision,
        })
    base_scenario = copy.deepcopy(scenario_record.scenario_json)
    base_scenario["revision"] = scenario_record.revision
    state_by_id = {item.get("id"): item for item in base_scenario.get("states", []) if item.get("id")}
    current_state_ids = sorted(set(payload.current_state_ids))
    target_state_ids = sorted(set(payload.target_state_ids))
    if not current_state_ids:
        raise HTTPException(status_code=422, detail={"error_code": "CURRENT_STATE_REQUIRED", "error_message": "请至少选择一个当前状态"})
    if not target_state_ids:
        raise HTTPException(status_code=422, detail={"error_code": "TARGET_STATE_REQUIRED", "error_message": "请至少选择一个目标状态"})
    unknown_current = [value for value in current_state_ids if value not in state_by_id]
    if unknown_current:
        raise _state_error("UNKNOWN_CURRENT_STATE", "当前状态不存在", unknown_current, state_by_id)
    unknown_target = [value for value in target_state_ids if value not in state_by_id]
    if unknown_target:
        raise _state_error("UNKNOWN_TARGET_STATE", "目标状态不存在", unknown_target, state_by_id)
    forbidden_target = sorted(set(target_state_ids) & set(base_scenario.get("forbidden_state_ids", [])))
    if forbidden_target:
        raise _state_error("TARGET_STATE_FORBIDDEN", "禁止状态不能作为目标状态", forbidden_target, state_by_id)

    scenario = copy.deepcopy(base_scenario)
    scenario["initial_state_ids"] = current_state_ids
    scenario["goal_state_ids"] = target_state_ids
    scenario["target_activity_ids"] = []
    scenario["target_activity_package_ids"] = []
    # Per-run overrides never inherit stale derived values from project JSON.
    scenario.pop('run_time_windows', None)
    try:
        run_windows = freeze_run_windows(scenario, payload.activity_time_windows, payload.display_start_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_RUN_TIME_WINDOWS", "error_message": str(exc)}) from exc
    if run_windows:
        scenario['run_time_windows'] = run_windows
    objectives = _normalize_objectives(payload.objectives)
    scenario["planner_run_objectives"] = objectives
    issues = validate_scenario(scenario)
    if issues:
        raise HTTPException(status_code=422, detail={
            "error_code": "SCENARIO_INVALID",
            "error_message": "本次当前状态和目标状态未通过求解预检",
            "issues": issues,
        })
    execution_bound = None
    if getattr(payload, "execution_bound_mode", "scenario") == "auto":
        from app.services.planner_execution_bounds import automatic_execution_bound
        execution_bound = automatic_execution_bound(scenario)
        scenario["max_steps"] = execution_bound["value"]
    from app.services.planner_calendars import night_rule_enabled
    if scenario.get('work_calendar_id') or night_rule_enabled(scenario):
        from app.services.planner_calendars import calendar_intervals, lift_day_windows
        if payload.display_start_at is None:
            raise HTTPException(status_code=422, detail={'error_code': 'CALENDAR_START_REQUIRED', 'error_message': '工作日历需要计划开始时间'})
        scenario['calendar_context'] = {'start_at': payload.display_start_at.isoformat(), 'timezone': payload.display_timezone}
        try:
            scenario['working_intervals'] = calendar_intervals(scenario)
            scenario['lift_day_windows'] = lift_day_windows(scenario,scenario['working_intervals'])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status_code=422, detail={'error_code': 'INVALID_CALENDAR_RUN', 'error_message': str(exc)}) from exc
    else:
        scenario.pop('calendar_context', None)
        scenario.pop('working_intervals', None)
        scenario.pop('lift_day_windows', None)
    base_scenario_hash = scenario_hash(base_scenario)
    snapshot_hash = scenario_hash(scenario)
    run_id = f"planner-run:{uuid4()}"
    request_json = {
        **payload.model_dump(mode="json"),
        "current_state_ids": current_state_ids,
        "target_state_ids": target_state_ids,
        "objectives": objectives,
        "base_scenario_hash": base_scenario_hash,
        "scenario_hash": snapshot_hash,
        "effective_scenario_snapshot": copy.deepcopy(scenario),
    }
    if execution_bound is not None:
        request_json["execution_bound"] = execution_bound
    if getattr(payload, "budget_mode", "manual") == "auto":
        from app.services.planner_execution_bounds import automatic_solver_budget
        allocation = automatic_solver_budget(scenario)
        request_json["budget_allocation"] = allocation
        request_json["effective_budget"] = {"time_limit_seconds": allocation["time_limit_seconds"]}
    record = PlannerRunRecord(
        id=run_id,
        scenario_id=payload.scenario_id,
        scenario_hash=snapshot_hash,
        engine=payload.engine,
        status="running",
        request_json=request_json,
    )
    db.add(record)
    await db.flush()
    return record



class AsyncRunCreate(RunCreate):
    # Existing API callers retain their explicit scenario boundary by default.
    # The React workbench opts into a server-calculated immutable run boundary.
    execution_bound_mode: Literal["scenario", "auto"] = "scenario"
    budget_mode: Literal["manual", "auto"] = "manual"
    budget: dict[str, Any] = Field(default_factory=lambda: {"time_limit_seconds": 60})
    engine: Literal["JOINT_CP_SAT"] = "JOINT_CP_SAT"
    seed: int = 11
    client_request_id: str = Field(min_length=1, max_length=64)
    display_start_at: datetime
    display_timezone: str = "Asia/Shanghai"


@router.post("/async", status_code=202)
async def enqueue_run(payload: AsyncRunCreate, db: AsyncSession = Depends(get_db_session)):
    from sqlalchemy.exc import IntegrityError
    from app.services.planner_jobs import check_async_request

    async def existing():
        record = (await db.execute(select(PlannerRunRecord).where(
            PlannerRunRecord.client_request_id == payload.client_request_id))).scalar_one_or_none()
        if record:
            defaults = {"execution_bound_mode": "scenario", "budget_mode": "manual", "activity_time_windows": []}
            original = {k: record.request_json.get(k, defaults.get(k)) for k in payload.model_dump(mode="json")}
            if original != payload.model_dump(mode="json"):
                raise HTTPException(status_code=409, detail={"error_code": "REQUEST_ID_CONFLICT"})
        return record

    prior = await existing()
    if prior:
        return _serialize(prior, include_result=True, include_snapshot=True)
    try:
        check_async_request(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_RUN_OPTIONS", "error_message": str(exc)})
    try:
        async with db.begin_nested():
            record = await _prepare_record(payload, db, lock_snapshot=True)
            from app.services.planner_jobs import check_joint_capabilities
            try:
                check_joint_capabilities(record.request_json["effective_scenario_snapshot"])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={"error_code": "UNSUPPORTED", "error_message": str(exc)})
            record.request_json = {**record.request_json, **payload.model_dump(mode="json")}
            record.client_request_id = payload.client_request_id
            record.job_status = "QUEUED"
            record.status = "QUEUED"
            await db.flush()
    except IntegrityError:
        prior = await existing()
        if prior is None:
            raise
        return _serialize(prior, include_result=True, include_snapshot=True)
    await db.commit()  # A 202 response always refers to a durable queued snapshot.
    return _serialize(record, include_result=True, include_snapshot=True)

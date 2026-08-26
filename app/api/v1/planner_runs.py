"""Run legacy, A*, and GA against one immutable expanded scenario snapshot."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlannerRunRecord, PlannerScenarioRecord
from app.db.session import get_db_session
from app.services.planner_engine_bridge import PlannerEngineUnavailable, planner_available, planner_project_path, run_engine
from app.services.planner_scenarios import PlannerScenarioError, scenario_hash, validate_scenario


router = APIRouter(prefix="/planner-runs", tags=["planner-runs"])


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    expected_revision: int
    current_state_ids: list[str] = Field(default_factory=list)
    target_state_ids: list[str] = Field(default_factory=list)
    engine: Literal["LEGACY", "ASTAR", "GA", "ALL"] = "ALL"
    seed: int = 42
    budget: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
async def capabilities():
    return {
        "planner_available": planner_available(),
        "planner_project_path": str(planner_project_path()),
        "engines": ["LEGACY", "ASTAR", "GA", "ALL"],
        "resource_model": "aggregate_capacity",
        "resource_instances_supported": False,
        "input_schema": "planner-shared-scenario/v1",
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


@router.post("", status_code=201)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db_session)):
    scenario_record = await db.get(PlannerScenarioRecord, payload.scenario_id)
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
    issues = validate_scenario(scenario)
    if issues:
        raise HTTPException(status_code=422, detail={
            "error_code": "SCENARIO_INVALID",
            "error_message": "本次当前状态和目标状态未通过求解预检",
            "issues": issues,
        })
    base_scenario_hash = scenario_hash(base_scenario)
    snapshot_hash = scenario_hash(scenario)
    run_id = f"planner-run:{uuid4()}"
    request_json = {
        **payload.model_dump(),
        "current_state_ids": current_state_ids,
        "target_state_ids": target_state_ids,
        "base_scenario_hash": base_scenario_hash,
        "scenario_hash": snapshot_hash,
        "effective_scenario_snapshot": copy.deepcopy(scenario),
    }
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

    engines = ["LEGACY", "ASTAR", "GA"] if payload.engine == "ALL" else [payload.engine]
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

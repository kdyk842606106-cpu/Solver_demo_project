"""Legacy layered-data migration preview and confirmed execution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MachineType, PlannerScenarioRecord
from app.db.session import get_db_session
from app.services.planner_legacy_migration import build_legacy_migration
from app.services.planner_scenarios import scenario_hash


router = APIRouter(prefix="/planner-migrations", tags=["planner-migrations"])


class MigrationExecute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    machine_type_id: int
    scenario_name: str = Field(min_length=1, max_length=128)
    backup_acknowledged: bool
    confirm: bool


@router.get("/legacy/preview")
async def preview_legacy(machine_type_id: int, scenario_name: str = "旧数据迁移场景", db: AsyncSession = Depends(get_db_session)):
    if await db.get(MachineType, machine_type_id) is None:
        raise HTTPException(status_code=404, detail={"error_code": "MACHINE_TYPE_NOT_FOUND"})
    scenario, report = await build_legacy_migration(db, machine_type_id, scenario_name=scenario_name)
    return {"report": report, "scenario_preview": scenario, "scenario_hash": scenario_hash(scenario) if report["executable"] else None}


@router.post("/legacy", status_code=201)
async def execute_legacy(payload: MigrationExecute, db: AsyncSession = Depends(get_db_session)):
    if not payload.confirm or not payload.backup_acknowledged:
        raise HTTPException(status_code=422, detail={"error_code": "MIGRATION_CONFIRMATION_REQUIRED", "error_message": "执行迁移前必须确认预览并确认已有可恢复备份"})
    if await db.get(MachineType, payload.machine_type_id) is None:
        raise HTTPException(status_code=404, detail={"error_code": "MACHINE_TYPE_NOT_FOUND"})
    scenario, report = await build_legacy_migration(db, payload.machine_type_id, scenario_name=payload.scenario_name)
    if not report["executable"]:
        raise HTTPException(status_code=422, detail={"error_code": "MIGRATION_BLOCKED", "report": report})
    record = PlannerScenarioRecord(id=scenario["id"], display_code=scenario["display_code"], name=scenario["name"], scenario_json=scenario, next_activity_number=len(scenario["activities"]) + 1, next_package_number=len(scenario["activity_packages"]) + 1)
    db.add(record)
    await db.flush()
    return {"scenario_id": record.id, "scenario_hash": scenario_hash(scenario), "report": report, "legacy_tables_mutated": False}

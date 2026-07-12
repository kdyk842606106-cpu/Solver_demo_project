"""Scenario import endpoints."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scenario_import import (
    build_scenario_template,
    import_scenario_workbook,
    parse_scenario_workbook,
    validate_scenario_workbook,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/scenario")
async def import_scenario(
    file: UploadFile = File(...),
    mode: str = Form(default="scenario_upsert"),
    dry_run: bool = Form(default=True),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate or import a business scenario workbook."""
    if mode != "scenario_upsert":
        raise HTTPException(status_code=422, detail="mode must be scenario_upsert")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="file must be a .xlsx workbook")

    content = await file.read()
    parsed = parse_scenario_workbook(content)
    validation = await validate_scenario_workbook(parsed, db)
    summary = dict(validation["summary"])
    summary["dry_run"] = dry_run

    if validation["errors"]:
        return {
            "status": "failed",
            "summary": summary,
            "preview": validation["preview"],
            "solve_cases": validation["solve_cases"],
            "post_import_health_checks": [],
            "errors": validation["errors"],
        }

    if dry_run:
        return {
            "status": "validated",
            "summary": summary,
            "preview": validation["preview"],
            "solve_cases": validation["solve_cases"],
            "post_import_health_checks": [],
            "errors": [],
        }

    imported = await import_scenario_workbook(parsed, db)
    return {
        "status": "imported",
        "summary": summary,
        "preview": validation["preview"],
        "solve_cases": imported["solve_cases"],
        "maintenance_intent_templates": imported.get("maintenance_intent_templates", []),
        "post_import_health_checks": imported.get("post_import_health_checks", []),
        "errors": [],
    }


@router.get("/scenario-template")
async def download_scenario_template():
    """Download the scenario import workbook template."""
    content = build_scenario_template()
    headers = {"Content-Disposition": 'attachment; filename="scenario-import-template.xlsx"'}
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

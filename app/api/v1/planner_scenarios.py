"""Planner shared-scenario CRUD, package mirror, graph, import and validation API."""

from __future__ import annotations

import copy
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlannerScenarioRecord
from app.db.session import get_db_session
from app.services.planner_scenarios import (
    PlannerScenarioError,
    add_membership,
    clone_activity,
    create_activity,
    create_package,
    delete_activity,
    delete_package,
    expand_packages,
    graph_projection,
    new_scenario,
    normalize_import,
    rebuild_mirror,
    remove_membership,
    scenario_hash,
    technical_id,
    update_activity,
    update_event,
    update_package,
    validate_scenario,
)
from app.services.planner_excel import export_workbook, import_workbook, template_workbook


router = APIRouter(prefix="/planner-scenarios", tags=["planner-scenarios"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)


class ScenarioUpdate(StrictModel):
    expected_revision: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    execution_mode: Literal["serial", "parallel"] | None = None
    start_time: int | None = Field(default=None, ge=0)
    max_steps: int | None = Field(default=None, gt=0)
    default_budget: dict[str, Any] | None = None
    initial_state_ids: list[str] | None = None
    goal_state_ids: list[str] | None = None
    forbidden_state_ids: list[str] | None = None
    target_activity_ids: list[str] | None = None
    target_activity_package_ids: list[str] | None = None
    activity_package_scope_ids: list[str] | None = None
    provenance: dict[str, Any] | None = None


class ActivityCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    duration: int = Field(default=1, gt=0)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    output_state_name: str | None = Field(default=None, min_length=1, max_length=128)
    additional_output_state_ids: list[str] = Field(default_factory=list)
    resource_reqs: dict[str, int] = Field(default_factory=dict)
    event_reqs: list[str] = Field(default_factory=list)
    max_instances: int | None = Field(default=None, gt=0)
    is_milestone: bool = False
    is_active: bool = True
    is_target: bool = False


class ActivityUpdate(StrictModel):
    expected_revision: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    duration: int | None = Field(default=None, gt=0)
    preconditions: list[dict[str, Any]] | None = None
    output_state_name: str | None = Field(default=None, min_length=1, max_length=128)
    additional_output_state_ids: list[str] | None = None
    resource_reqs: dict[str, int] | None = None
    event_reqs: list[str] | None = None
    max_instances: int | None = Field(default=None, gt=0)
    is_milestone: bool | None = None
    is_active: bool | None = None
    is_target: bool | None = None


class PackageCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None
    sort_order: int = 0
    is_active: bool = True
    layout: dict[str, Any] = Field(default_factory=dict)


class PackageUpdate(StrictModel):
    expected_revision: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    layout: dict[str, Any] | None = None


class MembershipCreate(StrictModel):
    activity_id: str
    sort_order: int = 0


class SeedStateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    initial: bool = False
    goal: bool = False
    forbidden: bool = False


class ResourceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    capacity: int = Field(gt=0)
    is_active: bool = True


class EventCreate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    time: int = Field(ge=0)
    add_state_ids: list[str] = Field(default_factory=list)
    remove_state_ids: list[str] = Field(default_factory=list)


class EventUpdate(StrictModel):
    expected_revision: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    time: int | None = Field(default=None, ge=0)
    add_state_ids: list[str] | None = None
    remove_state_ids: list[str] | None = None


class ImportRequest(StrictModel):
    scenario: dict[str, Any]
    preserve_ids: bool = False


class LayoutItem(StrictModel):
    id: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None


class LayoutUpdate(StrictModel):
    expected_revision: int | None = None
    activity_refs: list[LayoutItem] = Field(default_factory=list)
    package_containers: list[LayoutItem] = Field(default_factory=list)


class DraftOperation(StrictModel):
    operation: Literal[
        "create_package", "update_package", "delete_package", "create_activity",
        "update_activity", "delete_activity", "add_membership", "remove_membership",
        "create_seed_state", "create_resource", "create_event", "update_event", "update_scenario", "update_layout",
    ]
    client_ref: str | None = None
    object_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DraftCommit(StrictModel):
    expected_revision: int
    operations: list[DraftOperation] = Field(min_length=1)


@router.get("")
async def list_scenarios(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(PlannerScenarioRecord).order_by(PlannerScenarioRecord.created_at))
    return [_summary(item) for item in result.scalars().all()]


@router.post("", status_code=201)
async def create_scenario(payload: ScenarioCreate, db: AsyncSession = Depends(get_db_session)):
    scenario = new_scenario(payload.name)
    record = PlannerScenarioRecord(
        id=scenario["id"], display_code=scenario["display_code"], name=scenario["name"], scenario_json=scenario
    )
    db.add(record)
    await db.flush()
    return _serialize(record)


@router.get("/excel-template")
async def download_excel_template():
    return Response(
        content=template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="planner-scenario-template.xlsx"'},
    )


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    return _serialize(await _record(db, scenario_id))


@router.post("/{scenario_id}/draft-commit")
async def commit_draft(scenario_id: str, payload: DraftCommit, db: AsyncSession = Depends(get_db_session)):
    """Apply a page editing session atomically to one scenario snapshot."""
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    refs: dict[str, str] = {}
    activity_number = record.next_activity_number
    package_number = record.next_package_number

    def resolved(value):
        if isinstance(value, str) and value.startswith("draft:"):
            if value not in refs:
                raise HTTPException(status_code=422, detail={"error_code": "DRAFT_REF_UNRESOLVED", "ref": value})
            return refs[value]
        if isinstance(value, list):
            return [resolved(item) for item in value]
        if isinstance(value, dict):
            return {key: resolved(item) for key, item in value.items()}
        return value

    for item in payload.operations:
        data = resolved(copy.deepcopy(item.payload))
        object_id = resolved(item.object_id) if item.object_id else None
        if item.operation in {"create_activity", "update_activity", "update_scenario"}:
            _reject_deprecated_targets(data)
        if item.operation == "create_package":
            created = _domain(create_package, scenario, data, display_number=package_number)
            package_number += 1
        elif item.operation == "create_activity":
            created = _domain(create_activity, scenario, data, display_number=activity_number)
            activity_number += 1
        elif item.operation == "add_membership":
            created = _domain(add_membership, scenario, data["package_id"], data["activity_id"], sort_order=int(data.get("sort_order", 0)))
        elif item.operation == "update_package":
            created = _domain(update_package, scenario, object_id, data)
        elif item.operation == "delete_package":
            _domain(delete_package, scenario, object_id)
            created = None
        elif item.operation == "update_activity":
            created = _domain(update_activity, scenario, object_id, data)
        elif item.operation == "delete_activity":
            _domain(delete_activity, scenario, object_id)
            created = None
        elif item.operation == "remove_membership":
            _domain(remove_membership, scenario, object_id)
            created = None
        elif item.operation == "create_seed_state":
            created = {"id": technical_id("state") + ":seed", "name": data["name"], "state_kind": "seed", "managed": True}
            scenario.setdefault("states", []).append(created)
            for key in ("initial", "goal", "forbidden"):
                if data.get(key):
                    scenario.setdefault({"initial": "initial_state_ids", "goal": "goal_state_ids", "forbidden": "forbidden_state_ids"}[key], []).append(created["id"])
        elif item.operation == "create_resource":
            created = {"id": technical_id("resource"), **data}
            scenario.setdefault("resources", []).append(created)
        elif item.operation == "create_event":
            created = {"id": technical_id("event"), **data}
            scenario.setdefault("external_events", []).append(created)
        elif item.operation == "update_event":
            created = _domain(update_event, scenario, object_id, data)
        elif item.operation == "update_scenario":
            scenario.update(data)
            created = scenario
        elif item.operation == "update_layout":
            memberships = {value["id"]: value for value in scenario.get("activity_package_memberships", [])}
            packages = {value["id"]: value for value in scenario.get("activity_packages", [])}
            for layout in data.get("activity_refs", []):
                membership = memberships.get(layout.get("id"))
                if membership is None:
                    raise HTTPException(status_code=422, detail={"error_code": "GRAPH_REF_NOT_FOUND", "id": layout.get("id")})
                membership["layout"] = {key: float(layout[key]) for key in ("x", "y") if key in layout}
            for layout in data.get("package_containers", []):
                package = packages.get(layout.get("id"))
                if package is None:
                    raise HTTPException(status_code=422, detail={"error_code": "PACKAGE_NOT_FOUND", "id": layout.get("id")})
                package["layout"] = {key: float(layout[key]) for key in ("x", "y", "width", "height") if key in layout}
            created = scenario
        else:  # pragma: no cover - Literal guards this boundary
            raise HTTPException(status_code=422, detail={"error_code": "DRAFT_OPERATION_UNSUPPORTED"})
        if item.client_ref:
            if not item.client_ref.startswith("draft:"):
                raise HTTPException(status_code=422, detail={"error_code": "DRAFT_REF_INVALID", "ref": item.client_ref})
            if created is None or not created.get("id"):
                raise HTTPException(status_code=422, detail={"error_code": "DRAFT_REF_WITHOUT_OBJECT", "ref": item.client_ref})
            refs[item.client_ref] = created["id"]

    rebuild_mirror(scenario)
    issues = validate_scenario(copy.deepcopy(scenario))
    if issues:
        raise HTTPException(status_code=422, detail={"error_code": "DRAFT_VALIDATION_FAILED", "issues": issues})
    record.next_activity_number = activity_number
    record.next_package_number = package_number
    _save(record, scenario)
    return {"revision": record.revision, "created_refs": refs, "scenario": _scenario(record), "graph": graph_projection(scenario)}


@router.patch("/{scenario_id}")
async def patch_scenario(scenario_id: str, payload: ScenarioUpdate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    values = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    _reject_deprecated_targets(values)
    scenario.update(copy.deepcopy(values))
    if "name" in values:
        record.name = values["name"]
    rebuild_mirror(scenario)
    _save(record, scenario)
    return _serialize(record)


@router.delete("/{scenario_id}", status_code=204)
async def remove_scenario(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    await db.delete(record)
    return Response(status_code=204)


@router.post("/{scenario_id}/activities", status_code=201)
async def post_activity(scenario_id: str, payload: ActivityCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    values = payload.model_dump()
    _reject_deprecated_targets(values)
    activity = _domain(create_activity, scenario, values, display_number=record.next_activity_number)
    record.next_activity_number += 1
    _save(record, scenario)
    return {"revision": record.revision, "activity": activity, "scenario_hash": scenario_hash(scenario)}


@router.patch("/{scenario_id}/activities/{activity_id}")
async def patch_activity(scenario_id: str, activity_id: str, payload: ActivityUpdate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    values = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    _reject_deprecated_targets(values)
    activity = _domain(update_activity, scenario, activity_id, values)
    _save(record, scenario)
    return {"revision": record.revision, "activity": activity, "scenario_hash": scenario_hash(scenario)}


@router.post("/{scenario_id}/activities/{activity_id}/clone", status_code=201)
async def post_activity_clone(scenario_id: str, activity_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    activity = _domain(clone_activity, scenario, activity_id, display_number=record.next_activity_number)
    record.next_activity_number += 1
    _save(record, scenario)
    return {"revision": record.revision, "activity": activity}


@router.delete("/{scenario_id}/activities/{activity_id}", status_code=204)
async def remove_activity(scenario_id: str, activity_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    _domain(delete_activity, scenario, activity_id)
    _save(record, scenario)
    return Response(status_code=204)


@router.post("/{scenario_id}/activity-packages", status_code=201)
async def post_package(scenario_id: str, payload: PackageCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    package = _domain(create_package, scenario, payload.model_dump(), display_number=record.next_package_number)
    record.next_package_number += 1
    _save(record, scenario)
    return {"revision": record.revision, "activity_package": package, "state_package_id": package["mirrored_state_package_id"]}


@router.patch("/{scenario_id}/activity-packages/{package_id}")
async def patch_package(scenario_id: str, package_id: str, payload: PackageUpdate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    package = _domain(update_package, scenario, package_id, payload.model_dump(exclude_unset=True, exclude={"expected_revision"}))
    _save(record, scenario)
    return {"revision": record.revision, "activity_package": package}


@router.delete("/{scenario_id}/activity-packages/{package_id}", status_code=204)
async def remove_package(scenario_id: str, package_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    _domain(delete_package, scenario, package_id)
    _save(record, scenario)
    return Response(status_code=204)


@router.post("/{scenario_id}/activity-packages/{package_id}/members", status_code=201)
async def post_membership(scenario_id: str, package_id: str, payload: MembershipCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    membership = _domain(add_membership, scenario, package_id, payload.activity_id, sort_order=payload.sort_order)
    _save(record, scenario)
    state_membership = next(item for item in scenario["state_package_memberships"] if item["source_membership_id"] == membership["id"])
    return {"revision": record.revision, "activity_membership": membership, "state_membership": state_membership}


@router.delete("/{scenario_id}/activity-package-members/{membership_id}", status_code=204)
async def remove_package_member(scenario_id: str, membership_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    _domain(remove_membership, scenario, membership_id)
    _save(record, scenario)
    return Response(status_code=204)


@router.post("/{scenario_id}/seed-states", status_code=201)
async def post_seed_state(scenario_id: str, payload: SeedStateCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    state = {"id": technical_id("state") + ":seed", "name": payload.name, "state_kind": "seed", "managed": True}
    scenario.setdefault("states", []).append(state)
    for key, enabled in (("initial_state_ids", payload.initial), ("goal_state_ids", payload.goal), ("forbidden_state_ids", payload.forbidden)):
        if enabled:
            scenario.setdefault(key, []).append(state["id"])
    rebuild_mirror(scenario)
    _save(record, scenario)
    return {"revision": record.revision, "state": state}


@router.post("/{scenario_id}/resources", status_code=201)
async def post_resource(scenario_id: str, payload: ResourceCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    resource = {"id": technical_id("resource"), **payload.model_dump()}
    scenario.setdefault("resources", []).append(resource)
    _save(record, scenario)
    return {"revision": record.revision, "resource": resource}


@router.post("/{scenario_id}/external-events", status_code=201)
async def post_event(scenario_id: str, payload: EventCreate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    scenario = copy.deepcopy(record.scenario_json)
    event = {"id": technical_id("event"), **payload.model_dump()}
    scenario.setdefault("external_events", []).append(event)
    _save(record, scenario)
    return {"revision": record.revision, "external_event": event}


@router.patch("/{scenario_id}/external-events/{event_id}")
async def patch_event(
    scenario_id: str,
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    data = payload.model_dump(exclude={"expected_revision"}, exclude_none=True)
    event = _domain(update_event, scenario, event_id, data)
    _save(record, scenario)
    return {"revision": record.revision, "external_event": event}


@router.get("/{scenario_id}/graph")
async def get_graph(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id)
    return graph_projection(_scenario(record))


@router.patch("/{scenario_id}/graph/layout")
async def patch_graph_layout(scenario_id: str, payload: LayoutUpdate, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id, for_update=True)
    _check_revision(record, payload.expected_revision)
    scenario = copy.deepcopy(record.scenario_json)
    refs = {item["id"]: item for item in scenario.get("activity_package_memberships", [])}
    packages = {item["id"]: item for item in scenario.get("activity_packages", [])}
    for item in payload.activity_refs:
        if item.id not in refs:
            raise HTTPException(status_code=404, detail={"error_code": "GRAPH_REF_NOT_FOUND", "id": item.id})
        refs[item.id]["layout"] = item.model_dump(exclude={"id"}, exclude_none=True)
    for item in payload.package_containers:
        if item.id not in packages:
            raise HTTPException(status_code=404, detail={"error_code": "PACKAGE_NOT_FOUND", "id": item.id})
        packages[item.id]["layout"] = item.model_dump(exclude={"id"}, exclude_none=True)
    _save(record, scenario)
    return {"revision": record.revision, "graph": graph_projection(scenario)}


@router.post("/{scenario_id}/validate")
async def validate(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id)
    scenario = _scenario(record)
    issues = validate_scenario(scenario)
    return {"valid": not issues, "issues": issues, "scenario_hash": scenario_hash(scenario), "expanded_scenario": expand_packages(scenario) if not issues else None}


@router.get("/{scenario_id}/export")
async def export_scenario(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id)
    scenario = _scenario(record)
    return {"scenario": scenario, "scenario_hash": scenario_hash(scenario)}


@router.get("/{scenario_id}/export.xlsx")
async def export_scenario_excel(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    record = await _record(db, scenario_id)
    return Response(
        content=export_workbook(_scenario(record)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{record.display_code}.xlsx"'},
    )


@router.post("/import", status_code=201)
async def import_scenario(payload: ImportRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        scenario = normalize_import(payload.scenario, preserve_ids=payload.preserve_ids)
    except PlannerScenarioError as exc:
        raise _http_domain_error(exc) from exc
    if await db.get(PlannerScenarioRecord, scenario["id"]) is not None:
        raise HTTPException(status_code=409, detail={"error_code": "SCENARIO_ID_CONFLICT", "id": scenario["id"]})
    issues = validate_scenario(copy.deepcopy(scenario))
    if issues:
        raise HTTPException(status_code=422, detail={"error_code": "IMPORT_VALIDATION_FAILED", "issues": issues})
    activity_numbers = [int(item["display_code"].split("-")[-1]) for item in scenario.get("activities", []) if item.get("display_code", "").startswith("ACT-")]
    package_numbers = [int(item["display_code"].split("-")[-1]) for item in scenario.get("activity_packages", []) if item.get("display_code", "").startswith("AP-")]
    record = PlannerScenarioRecord(
        id=scenario["id"], display_code=scenario["display_code"], name=scenario["name"],
        scenario_json=scenario, next_activity_number=max(activity_numbers, default=0) + 1,
        next_package_number=max(package_numbers, default=0) + 1,
    )
    db.add(record)
    await db.flush()
    return _serialize(record)


@router.post("/import.xlsx", status_code=201)
async def import_scenario_excel(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session)):
    try:
        scenario = import_workbook(await file.read())
    except PlannerScenarioError as exc:
        raise _http_domain_error(exc) from exc
    issues = validate_scenario(copy.deepcopy(scenario))
    if issues:
        raise HTTPException(status_code=422, detail={"error_code": "IMPORT_VALIDATION_FAILED", "issues": issues})
    record = PlannerScenarioRecord(
        id=scenario["id"], display_code=scenario["display_code"], name=scenario["name"],
        scenario_json=scenario, next_activity_number=len(scenario.get("activities", [])) + 1,
        next_package_number=len(scenario.get("activity_packages", [])) + 1,
    )
    db.add(record)
    await db.flush()
    return _serialize(record)


async def _record(db: AsyncSession, scenario_id: str, *, for_update: bool = False) -> PlannerScenarioRecord:
    statement = select(PlannerScenarioRecord).where(PlannerScenarioRecord.id == scenario_id)
    if for_update:
        statement = statement.with_for_update()
    record = (await db.execute(statement)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail={"error_code": "SCENARIO_NOT_FOUND", "id": scenario_id})
    return record


def _check_revision(record: PlannerScenarioRecord, expected: int | None) -> None:
    if expected is not None and expected != record.revision:
        raise HTTPException(status_code=409, detail={"error_code": "SCENARIO_REVISION_CONFLICT", "expected": expected, "actual": record.revision})


def _save(record: PlannerScenarioRecord, scenario: dict[str, Any]) -> None:
    record.revision += 1
    scenario["revision"] = record.revision
    record.scenario_json = scenario
    record.name = scenario["name"]


def _scenario(record: PlannerScenarioRecord) -> dict[str, Any]:
    scenario = copy.deepcopy(record.scenario_json)
    scenario["revision"] = record.revision
    return scenario


def _serialize(record: PlannerScenarioRecord) -> dict[str, Any]:
    scenario = _scenario(record)
    return {"id": record.id, "display_code": record.display_code, "name": record.name, "revision": record.revision, "scenario_hash": scenario_hash(scenario), "scenario": scenario}


def _summary(record: PlannerScenarioRecord) -> dict[str, Any]:
    scenario = record.scenario_json or {}
    return {"id": record.id, "display_code": record.display_code, "name": record.name, "revision": record.revision, "activity_count": len(scenario.get("activities", [])), "package_count": len(scenario.get("activity_packages", []))}


def _domain(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except PlannerScenarioError as exc:
        raise _http_domain_error(exc) from exc


def _reject_deprecated_targets(values: dict[str, Any]) -> None:
    if values.get("target_activity_ids") or values.get("target_activity_package_ids") or values.get("is_target") is True:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "TARGET_ACTIVITY_DEPRECATED",
                "error_message": "Run goals must be selected as target states on the solve page",
            },
        )


def _http_domain_error(exc: PlannerScenarioError) -> HTTPException:
    status = 404 if exc.code.endswith("NOT_FOUND") else 409 if exc.code in {"BODY_IN_USE", "PACKAGE_HAS_CHILDREN", "PACKAGE_MEMBER_DUPLICATE"} else 422
    return HTTPException(status_code=status, detail={"error_code": exc.code, "error_message": str(exc), "details": exc.details})

import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import PlannerRunRecord
from app.services.planner_jobs import claim_job, finish_job, heartbeat
from app.services.planner_scenarios import (
    new_scenario,
    create_activity,
    scenario_hash,
    normalize_import,
)
from app.services.planner_excel import export_workbook, import_workbook


async def make_scenario(client):
    created = (
        await client.post("/api/v1/planner-scenarios", json={"name": "真实工作区"})
    ).json()
    assert created["scenario"]["execution_mode"] == "parallel"
    response = await client.post(
        f"/api/v1/planner-scenarios/{created['id']}/draft-commit",
        json={
            "expected_revision": created["revision"],
            "operations": [
                {
                    "operation": "create_seed_state",
                    "client_ref": "draft:s",
                    "payload": {"name": "就绪"},
                },
                {
                    "operation": "create_resource",
                    "client_ref": "draft:r",
                    "payload": {"name": "人员", "capacity": 2, "kind": "crew"},
                },
                {
                    "operation": "create_activity",
                    "client_ref": "draft:a",
                    "payload": {
                        "name": "装配",
                        "duration": 3,
                        "preconditions": [
                            {"state_id": "draft:s", "relation_role": "required"}
                        ],
                        "resource_reqs": {"draft:r": 1},
                        "metadata": {
                            "description": "保留说明",
                            "precision_fragile": True,
                        },
                    },
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["scenario"]


@pytest.mark.asyncio
async def test_turnover_material_crud_and_roundtrip(client):
    s = await make_scenario(client)
    response = await client.post(f"/api/v1/planner-scenarios/{s['id']}/resources",
                                 json={'name': '周转物料', 'kind': 'material', 'capacity': 4})
    assert response.status_code in (200, 201), response.text
    saved = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()['scenario']
    material = next(r for r in saved['resources'] if r['kind'] == 'material')
    updated = await client.patch(f"/api/v1/planner-scenarios/{s['id']}/resources/{material['id']}",
                                json={'kind': 'material', 'capacity': 3, 'expected_revision': saved['revision']})
    assert updated.status_code == 200, updated.text
    saved = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()['scenario']
    for restored in [normalize_import(saved, preserve_ids=False), import_workbook(export_workbook(saved))]:
        assert any(r['kind'] == 'material' and r['capacity'] == 3 for r in restored['resources'])


@pytest.mark.asyncio
async def test_calendar_draft_snapshot_roundtrip_and_references(client):
    s=await make_scenario(client)
    calendar={'id':'calendar:test','name':'工作日','weekdays':[0,1,2,3,4],
              'periods':[{'start':'08:00','end':'12:00'},{'start':'13:00','end':'17:00'}],
              'exceptions':[{'date':'2026-11-09','periods':[]}]}
    r=await client.post(f"/api/v1/planner-scenarios/{s['id']}/draft-commit",json={
        'expected_revision':s['revision'],'operations':[{'operation':'update_scenario',
        'payload':{'work_calendars':[calendar],'work_calendar_id':calendar['id']}}]})
    assert r.status_code==200,r.text
    s=r.json()['scenario']
    payload={**run_request(s),'budget_mode':'auto','execution_bound_mode':'auto'}
    r=await client.post('/api/v1/planner-runs/async',json=payload)
    assert r.status_code==202,r.text
    run=r.json(); frozen=run['request']['effective_scenario_snapshot']
    assert frozen['calendar_context']['timezone']=='Asia/Shanghai'
    assert frozen['working_intervals'] and frozen['work_calendars']==[calendar]
    assert (await client.post('/api/v1/planner-runs/async',json=payload)).json()['id']==run['id']
    bad=await client.patch(f"/api/v1/planner-scenarios/{s['id']}",json={'expected_revision':s['revision'],'work_calendars':[]})
    assert bad.status_code==422
    for restored in [normalize_import(s,preserve_ids=False), import_workbook(export_workbook(s))]:
        assert restored['work_calendar_id']!=calendar['id']
        assert restored['work_calendars'][0]['id']==restored['work_calendar_id']
        assert restored['work_calendars'][0]['exceptions']==calendar['exceptions']
    changed={**calendar,'name':'已更名','weekdays':[6]}
    r=await client.patch(f"/api/v1/planner-scenarios/{s['id']}",json={'expected_revision':s['revision'],'work_calendars':[changed]})
    assert r.status_code==200,r.text
    old=(await client.get(f"/api/v1/planner-runs/{run['id']}")).json()
    assert old['request']['effective_scenario_snapshot']==frozen


@pytest.mark.asyncio
async def test_night_lift_rule_snapshot_and_roundtrip(client):
    s=await make_scenario(client)
    rule={'enabled':True,'night_start':'20:00','night_end':'08:00'}
    response=await client.post(f"/api/v1/planner-scenarios/{s['id']}/draft-commit",json={
        'expected_revision':s['revision'],'operations':[
            {'operation':'create_resource','client_ref':'draft:crane','payload':{'name':'行吊','kind':'crane','capacity':1}},
            {'operation':'update_activity','object_id':s['activities'][0]['id'],'payload':{'duration':120,'resource_reqs':{'draft:crane':1},'metadata':{'precision_fragile':True}}},
            {'operation':'update_scenario','payload':{'night_lift_rule':rule}},
        ]})
    assert response.status_code==200,response.text
    s=response.json()['scenario']
    payload={**run_request(s),'display_start_at':'2026-11-04T19:00:00+08:00','execution_bound_mode':'auto'}
    response=await client.post('/api/v1/planner-runs/async',json=payload)
    assert response.status_code==202,response.text
    run=response.json();snapshot=run['request']['effective_scenario_snapshot']
    assert snapshot['night_lift_rule']==rule
    assert s['activities'][0]['id'] in snapshot['lift_day_windows']
    for restored in [normalize_import(s,preserve_ids=False),import_workbook(export_workbook(s))]:
        assert restored['night_lift_rule']==rule
        assert restored['resources'][0]['kind'] in ('crew','crane')
    change=await client.patch(f"/api/v1/planner-scenarios/{s['id']}",json={'expected_revision':s['revision'],
        'night_lift_rule':{**rule,'enabled':False}})
    assert change.status_code==200,change.text
    assert (await client.get(f"/api/v1/planner-runs/{run['id']}")).json()['request']['effective_scenario_snapshot']==snapshot


def run_request(s):
    return {
        "scenario_id": s["id"],
        "expected_revision": s["revision"],
        "current_state_ids": [s["states"][0]["id"]],
        "target_state_ids": [s["activities"][0]["output_state_id"]],
        "client_request_id": str(uuid4()),
        "display_start_at": "2026-11-04T08:00:00+08:00",
        "display_timezone": "Asia/Shanghai",
        "budget": {"time_limit_seconds": 2},
    }


@pytest.mark.asyncio
async def test_exclusive_rules_atomic_draft_snapshot_and_roundtrip(client):
    from app.services.planner_rules import exclusive_activity_ids
    s = await make_scenario(client)
    rules = {'crane': True, 'commissioning': True}
    response = await client.post(f"/api/v1/planner-scenarios/{s['id']}/draft-commit", json={
        'expected_revision': s['revision'], 'operations': [
            {'operation': 'update_activity', 'object_id': s['activities'][0]['id'], 'payload': {'metadata': {'activity_type': '功能调测'}}},
            {'operation': 'update_scenario', 'payload': {'exclusive_rules': rules}},
        ]})
    assert response.status_code == 200, response.text
    s = response.json()['scenario']
    run = await client.post('/api/v1/planner-runs/async', json=run_request(s))
    assert run.status_code == 202, run.text
    frozen = run.json()['request']['effective_scenario_snapshot']
    assert frozen['exclusive_rules'] == rules
    for restored in [normalize_import(s, preserve_ids=False), import_workbook(export_workbook(s))]:
        assert restored['exclusive_rules'] == rules
        assert len(exclusive_activity_ids(restored)) == 1
    bad = await client.post(f"/api/v1/planner-scenarios/{s['id']}/draft-commit", json={
        'expected_revision': s['revision'], 'operations': [
            {'operation': 'update_scenario', 'payload': {'name': 'Should roll back'}},
            {'operation': 'update_scenario', 'payload': {'exclusive_rules': {'crane': 'true', 'commissioning': False}}},
        ]})
    assert bad.status_code == 422, bad.text
    saved = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()['scenario']
    assert saved['name'] == s['name'] and saved['revision'] == s['revision']
    response = await client.patch(f"/api/v1/planner-scenarios/{s['id']}", json={
        'expected_revision': s['revision'], 'exclusive_rules': {'crane': False, 'commissioning': False}})
    assert response.status_code == 200, response.text
    history = (await client.get(f"/api/v1/planner-runs/{run.json()['id']}")).json()
    assert history['request']['effective_scenario_snapshot'] == frozen
    caps = (await client.get('/api/v1/planner-runs/capabilities')).json()['joint_cp_sat']
    assert caps['crane_exclusivity_supported'] and caps['commissioning_exclusivity_supported']


@pytest.mark.asyncio
async def test_automatic_bound_is_frozen_per_run_and_opt_in(client):
    s = await make_scenario(client)
    changed = await client.patch(f"/api/v1/planner-scenarios/{s['id']}", json={"expected_revision": s["revision"], "max_steps": 1})
    assert changed.status_code == 200, changed.text
    s = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()["scenario"]
    payload = {**run_request(s), "execution_bound_mode": "auto", "budget_mode": "auto"}
    response = await client.post("/api/v1/planner-runs/async", json=payload)
    assert response.status_code == 202, response.text
    run = response.json()
    assert run['request']['budget'] == {'time_limit_seconds': 2}
    assert run['request']['effective_budget'] == {'time_limit_seconds': 60}
    assert run['request']['budget_allocation']['policy'] == 'activity_tiers_v1'
    bound = run["request"]["execution_bound"]
    assert bound["mode"] == "auto" and bound["heuristic"] is True
    assert run["request"]["effective_scenario_snapshot"]["max_steps"] == bound["value"] >= 20
    saved = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()["scenario"]
    assert saved["max_steps"] == 1 and saved["revision"] == s["revision"]
    assert (await client.post("/api/v1/planner-runs/async", json=payload)).json()["id"] == run["id"]
    manual = await client.post("/api/v1/planner-runs/async", json=run_request(s))
    assert manual.status_code == 202, manual.text
    assert manual.json()["request"]["effective_scenario_snapshot"]["max_steps"] == 1
    assert "execution_bound" not in manual.json()["request"]
    assert 'effective_budget' not in manual.json()['request']
    assert manual.json()['request']['budget'] == {'time_limit_seconds': 2}
    conflict = await client.post('/api/v1/planner-runs/async', json={**payload, 'budget_mode': 'manual'})
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_resource_draft_atomicity_revision_and_roundtrip(client):
    s = await make_scenario(client)
    a, r = s["activities"][0], s["resources"][0]
    assert a["resource_reqs"] == {r["id"]: 1}
    for op in [
        {"operation": "delete_resource", "object_id": r["id"], "payload": {}},
        {
            "operation": "update_resource",
            "object_id": r["id"],
            "payload": {"is_active": False},
        },
    ]:
        response = await client.post(
            f"/api/v1/planner-scenarios/{s['id']}/draft-commit",
            json={
                "expected_revision": s["revision"],
                "operations": [
                    {
                        "operation": "update_activity",
                        "object_id": a["id"],
                        "payload": {"name": "不应保存"},
                    },
                    op,
                ],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["error_message"]["error_code"] == "RESOURCE_IN_USE"
    saved = (await client.get(f"/api/v1/planner-scenarios/{s['id']}")).json()[
        "scenario"
    ]
    assert (
        saved["activities"][0]["name"] == "装配" and saved["revision"] == s["revision"]
    )
    imported = normalize_import(s, preserve_ids=False)
    assert imported["activities"][0]["metadata"] == a["metadata"]
    assert imported["resources"][0]["kind"] == "crew"
    assert list(imported["activities"][0]["resource_reqs"]) == [
        imported["resources"][0]["id"]
    ]
    excel = import_workbook(export_workbook(s))
    assert excel["activities"][0]["metadata"] == a["metadata"]
    assert excel["resources"][0]["kind"] == "crew"
    response = await client.patch(
        f"/api/v1/planner-scenarios/{s['id']}/resources/{r['id']}",
        json={"expected_revision": s["revision"] - 1, "capacity": 3},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_async_idempotency_snapshot_and_version(client):
    s = await make_scenario(client)
    payload = run_request(s)
    response = await client.post("/api/v1/planner-runs/async", json=payload)
    assert response.status_code == 202, response.text
    run = response.json()
    assert run["job_status"] == "QUEUED" and run["result"] is None
    retry = await client.post("/api/v1/planner-runs/async", json=payload)
    assert retry.json()["id"] == run["id"]
    conflict = await client.post(
        "/api/v1/planner-runs/async", json={**payload, "seed": 12}
    )
    assert conflict.status_code == 409
    update = await client.patch(
        f"/api/v1/planner-scenarios/{s['id']}/activities/{s['activities'][0]['id']}",
        json={"expected_revision": s["revision"], "name": "后续更名"},
    )
    assert update.status_code == 200
    saved = (await client.get(f"/api/v1/planner-runs/{run['id']}")).json()
    assert (
        saved["request"]["effective_scenario_snapshot"]["activities"][0]["name"]
        == "装配"
    )
    stale = await client.post(
        "/api/v1/planner-runs/async",
        json={**payload, "client_request_id": str(uuid4())},
    )
    assert stale.status_code == 409
    assert (
        await client.delete(f"/api/v1/planner-scenarios/{s['id']}")
    ).status_code == 409


@pytest.mark.asyncio
async def test_async_rejects_unsupported_and_invalid_budget(client, db_session):
    from app.db.models import PlannerScenarioRecord

    s = await make_scenario(client)
    for seconds in [-1, 3601, "60", True]:
        response = await client.post(
            "/api/v1/planner-runs/async",
            json={**run_request(s), "budget": {"time_limit_seconds": seconds}},
        )
        assert response.status_code == 422
    record = await db_session.get(PlannerScenarioRecord, s["id"])
    record.scenario_json = {**record.scenario_json, "calendar": {"id": "not-supported"}}
    await db_session.commit()
    response = await client.post("/api/v1/planner-runs/async", json=run_request(s))
    assert response.status_code == 422, response.text
    assert response.json()["error_message"]["error_code"] == "UNSUPPORTED"
    assert (await client.get("/api/v1/planner-runs")).json() == []


def test_queue_claim_expiry_and_fenced_completion(tmp_path):
    from app.services.planner_jobs import save_progress
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    PlannerRunRecord.__table__.create(engine)
    request = {"base_scenario_hash": "h"}
    with Session(engine) as db:
        db.add_all(
            [
                PlannerRunRecord(
                    id=f"r{i}",
                    scenario_id="s",
                    scenario_hash="h",
                    engine="JOINT_CP_SAT",
                    status="QUEUED",
                    job_status="QUEUED",
                    request_json=request,
                )
                for i in range(2)
            ]
        )
        db.commit()
        first = claim_job(db)
        db.commit()
        assert first and claim_job(db) is None
        assert heartbeat(db, first)
        sample = {"branches": 7}
        plan = {"validator_status": "VALID", "executions": []}
        assert save_progress(db, first, 2, sample, 2, plan)
        assert not save_progress(db, first, 1, {}, 1, {})
        assert not save_progress(db, dict(first, token="old"), 3, {}, 3, {})
        assert save_progress(db, first, 3, {"branches": 9}, 2, None)
        db.commit()
        record = db.get(PlannerRunRecord, first["id"])
        record.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        second = claim_job(db)
        db.commit()
        assert second and second["id"] != first["id"]
        assert not finish_job(db, first, {"status": "OPTIMAL", "scenario_hash": "h"})
        assert not save_progress(db, first, 5, {}, 5, {})
        interrupted = db.get(PlannerRunRecord, first["id"])
        assert interrupted.live_plan_json == plan and interrupted.plan_version == 2
        assert not heartbeat(db, first)
        assert finish_job(db, second, {"status": "TIMEOUT_EMPTY", "scenario_hash": "h"})
        db.commit()
        db.expire_all()
        assert db.get(PlannerRunRecord, first["id"]).job_status == "FAILED"
        final = db.get(PlannerRunRecord, second["id"])
        assert final.job_status == "FINISHED" and final.status == "TIMEOUT_EMPTY"
    engine.dispose()


@pytest.mark.asyncio
async def test_inactive_resource_cannot_be_used_by_active_activity(client):
    p = (await client.post('/api/v1/planner-scenarios', json={'name': '停用资源'})).json()
    response = await client.post(f"/api/v1/planner-scenarios/{p['id']}/draft-commit", json={
        'expected_revision': p['revision'], 'operations': [
            {'operation': 'create_resource', 'client_ref': 'draft:r', 'payload': {'name': '停用人员', 'capacity': 1, 'is_active': False}},
            {'operation': 'create_activity', 'payload': {'name': '任务', 'duration': 1, 'resource_reqs': {'draft:r': 1}}},
        ]})
    assert response.status_code == 422
    issues = response.json()['error_message']['issues']
    assert any(issue['code'] == 'RESOURCE_INACTIVE' for issue in issues)
    saved = (await client.get(f"/api/v1/planner-scenarios/{p['id']}")).json()['scenario']
    assert not saved['resources'] and not saved['activities']

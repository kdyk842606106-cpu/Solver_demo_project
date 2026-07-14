import pytest
from app.core.scheduler.calendar import definition_checksum
from app.db.models import Machine, OpRule, WorkCalendar, WorkCalendarRevision
from sqlalchemy import select


@pytest.mark.asyncio
async def test_work_calendar_revision_preview_and_machine_policy(client):
    machine_type = (await client.post("/api/v1/machine-types", json={
        "code": "CAL_TYPE",
        "name": "Calendar Type",
    })).json()
    dimension = (await client.post(
        f"/api/v1/machine-types/{machine_type['id']}/feature-defs",
        json={
            "machine_type_id": machine_type["id"],
            "feature_key": "mechanical_dim",
            "feature_name": "Mechanical",
            "value_type": "enum",
            "allowed_values": ["off", "on"],
            "is_dimension_template": True,
        },
    )).json()
    machine = (await client.post("/api/v1/machines", json={
        "machine_type_id": machine_type["id"],
        "code": "CAL-M-001",
        "name": "Calendar Machine",
    })).json()
    calendar_response = await client.post("/api/v1/work-calendars", json={
        "code": "DAY_SHIFT",
        "name": "Day shift",
        "timezone": "Asia/Shanghai",
        "weekly_windows": [
            {"weekday": 1, "start_time": "08:00", "end_time": "12:00", "spans_next_day": False, "shift_code": "DAY_SHIFT", "shift_name": "白班"},
            {"weekday": 1, "start_time": "13:00", "end_time": "17:00", "spans_next_day": False},
        ],
        "date_exceptions": [],
    })
    assert calendar_response.status_code == 201, calendar_response.text
    calendar = calendar_response.json()
    assert calendar["current_revision"]["revision_no"] == 1

    preview = await client.post(
        f"/api/v1/work-calendars/{calendar['id']}/preview",
        json={
            "start_at": "2026-07-13T08:00:00+08:00",
            "end_at": "2026-07-13T18:00:00+08:00",
        },
    )
    assert preview.status_code == 200
    assert len(preview.json()["intervals"]) == 2
    assert preview.json()["intervals"][0]["shift_name"] == "白班"

    default_response = await client.post(f"/api/v1/work-calendars/{calendar['id']}/set-default")
    assert default_response.status_code == 200
    assert default_response.json()["is_system_default"] is True
    inherited_policy = await client.put(f"/api/v1/machines/{machine['id']}/calendar-policy", json={
        "default_work_calendar_id": None,
        "dimension_bindings": [],
    })
    assert inherited_policy.status_code == 200, inherited_policy.text
    assert inherited_policy.json()["inherits_system_default"] is True
    assert inherited_policy.json()["effective_default_work_calendar_id"] == calendar["id"]

    alternate = (await client.post("/api/v1/work-calendars", json={
        "code": "ALTERNATE_SHIFT",
        "name": "Alternate shift",
        "timezone": "Asia/Shanghai",
        "weekly_windows": [
            {"weekday": 1, "start_time": "09:00", "end_time": "18:00", "spans_next_day": False},
        ],
        "date_exceptions": [],
    })).json()
    switched = await client.post(f"/api/v1/work-calendars/{alternate['id']}/set-default")
    assert switched.status_code == 200, switched.text
    assert switched.json()["is_system_default"] is True
    calendars = (await client.get("/api/v1/work-calendars")).json()
    assert [item["code"] for item in calendars if item["is_system_default"]] == ["ALTERNATE_SHIFT"]
    await client.post(f"/api/v1/work-calendars/{calendar['id']}/set-default")

    policy = await client.put(f"/api/v1/machines/{machine['id']}/calendar-policy", json={
        "default_work_calendar_id": calendar["id"],
        "dimension_bindings": [{
            "state_dimension_template_id": dimension["id"],
            "work_calendar_id": calendar["id"],
        }],
    })
    assert policy.status_code == 200, policy.text
    assert policy.json()["default_work_calendar_id"] == calendar["id"]
    assert policy.json()["dimension_bindings"][0]["state_dimension_template_key"] == "mechanical_dim"

    updated = await client.put(f"/api/v1/work-calendars/{calendar['id']}", json={
        "name": "Day shift v2",
        "timezone": "Asia/Shanghai",
        "is_active": True,
        "weekly_windows": [
            {"weekday": 1, "start_time": "08:00", "end_time": "18:00", "spans_next_day": False},
        ],
        "date_exceptions": [],
    })
    assert updated.status_code == 200
    assert updated.json()["current_revision"]["revision_no"] == 2
    revisions = await client.get(f"/api/v1/work-calendars/{calendar['id']}/revisions")
    assert [item["revision_no"] for item in revisions.json()] == [2, 1]

    deactivate = await client.delete(f"/api/v1/work-calendars/{calendar['id']}")
    assert deactivate.status_code == 409


@pytest.mark.asyncio
async def test_system_default_dual_shift_is_inherited_and_labels_segments(client, integration_session):
    weekly = []
    for day in range(1, 8):
        weekly.extend([
            {"weekday": day, "start_time": "08:00", "end_time": "20:00", "spans_next_day": False, "shift_code": "DAY_SHIFT", "shift_name": "白班"},
            {"weekday": day, "start_time": "20:00", "end_time": "08:00", "spans_next_day": True, "shift_code": "NIGHT_SHIFT", "shift_name": "夜班"},
        ])
    calendar = WorkCalendar(
        code="DEFAULT_DUAL_SHIFT",
        name="默认白夜双班日历",
        is_system_default=True,
    )
    integration_session.add(calendar)
    await integration_session.flush()
    revision = WorkCalendarRevision(
        work_calendar_id=calendar.id,
        revision_no=1,
        timezone="Asia/Shanghai",
        weekly_windows=weekly,
        date_exceptions=[],
        checksum=definition_checksum("Asia/Shanghai", weekly, []),
    )
    integration_session.add(revision)
    await integration_session.flush()
    calendar.current_revision_id = revision.id
    machine = await integration_session.get(Machine, 1)
    machine.default_work_calendar_id = None
    rules = (await integration_session.execute(select(OpRule))).scalars().all()
    for rule in rules:
        rule.duration_min = 240
    await integration_session.commit()

    response = await client.post("/api/v1/solve", json={
        "machine_id": 1,
        "current_state_id": 1,
        "target_state_id": 2,
        "calendar_context": {
            "enabled": True,
            "schedule_start_at": "2026-07-13T18:00:00+08:00",
            "display_timezone": "Asia/Shanghai",
            "revision_policy": "latest",
        },
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["calendar_summary"]["inherits_system_default"] is True
    warnings = payload["diagnostics"]["schedule"]["calendar"]["warnings"]
    assert any(item["code"] == "CALENDAR_SYSTEM_DEFAULT_FALLBACK" for item in warnings)
    first_task = payload["schedule"]["tasks"][0]
    assert first_task["calendar_pause_min"] == 0
    assert [item.get("shift_code") for item in first_task["segments"][:2]] == ["DAY_SHIFT", "NIGHT_SHIFT"]


@pytest.mark.asyncio
async def test_snapshot_solve_uses_contiguous_window_and_persists_calendar_snapshot(client, integration_session):
    weekly = [
        {"weekday": day, "start_time": "08:00", "end_time": "12:00", "spans_next_day": False}
        for day in range(1, 6)
    ] + [
        {"weekday": day, "start_time": "13:00", "end_time": "17:00", "spans_next_day": False}
        for day in range(1, 6)
    ]
    calendar = WorkCalendar(code="SOLVE_DAY", name="Solve day")
    integration_session.add(calendar)
    await integration_session.flush()
    revision = WorkCalendarRevision(
        work_calendar_id=calendar.id,
        revision_no=1,
        timezone="Asia/Shanghai",
        weekly_windows=weekly,
        date_exceptions=[],
        checksum=definition_checksum("Asia/Shanghai", weekly, []),
    )
    integration_session.add(revision)
    await integration_session.flush()
    calendar.current_revision_id = revision.id
    machine = await integration_session.get(Machine, 1)
    machine.default_work_calendar_id = calendar.id
    await integration_session.commit()

    response = await client.post("/api/v1/solve", json={
        "machine_id": 1,
        "current_state_id": 1,
        "target_state_id": 2,
        "calendar_context": {
            "enabled": True,
            "schedule_start_at": "2026-07-13T11:50:00+08:00",
            "display_timezone": "Asia/Shanghai",
            "revision_policy": "latest",
        },
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "done", payload
    assert payload["calendar_summary"]["enabled"] is True
    assert all(task["elapsed_min"] == task["duration_min"] for task in payload["schedule"]["tasks"])
    assert all(task["calendar_pause_min"] == 0 for task in payload["schedule"]["tasks"])
    assert all(len(task["segments"]) == 1 for task in payload["schedule"]["tasks"])
    assert any(item["kind"] == "calendar_wait" for item in payload["critical_path_segments"])
    for task in payload["schedule"]["tasks"]:
        assert sum(segment["duration_min"] for segment in task["segments"]) == task["duration_min"]
        assert task["start_at"] and task["end_at"]

from datetime import datetime, timezone
from types import SimpleNamespace

from ortools.sat.python import cp_model
import pytest

from app.core.scheduler.calendar import (
    CalendarError,
    consume_contiguous_work,
    expand_definition,
    expand_definition_with_metadata,
    intersect_intervals,
    to_minute_offsets,
    validate_definition,
)
from app.core.scheduler.loader import RagData, StepData
from app.core.scheduler.model import build_model


MECHANICAL = {
    "timezone": "Asia/Shanghai",
    "weekly_windows": [
        {"weekday": day, "start_time": "08:00", "end_time": "12:00", "spans_next_day": False}
        for day in range(1, 6)
    ] + [
        {"weekday": day, "start_time": "13:00", "end_time": "17:00", "spans_next_day": False}
        for day in range(1, 6)
    ],
    "date_exceptions": [],
}


def test_calendar_expands_lunch_break_and_closed_exception():
    definition = {
        **MECHANICAL,
        "date_exceptions": [{"date": "2026-07-14", "mode": "closed", "windows": []}],
    }
    validate_definition(
        definition["timezone"], definition["weekly_windows"], definition["date_exceptions"]
    )
    anchor = datetime.fromisoformat("2026-07-13T08:00:00+08:00")
    intervals = expand_definition(
        definition,
        anchor,
        datetime.fromisoformat("2026-07-15T18:00:00+08:00"),
    )
    assert to_minute_offsets(intervals, anchor) == [
        (0, 240),
        (300, 540),
        (2880, 3120),
        (3180, 3420),
    ]


def test_multiple_calendars_use_intersection():
    anchor = datetime.fromisoformat("2026-07-13T08:00:00+08:00")
    end = datetime.fromisoformat("2026-07-13T22:00:00+08:00")
    functional = {
        "timezone": "Asia/Shanghai",
        "weekly_windows": [
            {"weekday": 1, "start_time": "09:00", "end_time": "21:00", "spans_next_day": False}
        ],
        "date_exceptions": [],
    }
    common = intersect_intervals([
        expand_definition(MECHANICAL, anchor, end),
        expand_definition(functional, anchor, end),
    ])
    assert to_minute_offsets(common, anchor) == [(60, 240), (300, 540)]


def test_scheduler_rejects_resume_after_calendar_gap():
    rag = RagData(
        candidate_plan_id=1,
        steps=[StepData(1, 1, "MECH", "Mechanical work", 360)],
        edges=[],
    )
    context = SimpleNamespace(
        horizon=540,
        windows_by_step={1: [(120, 240), (300, 540)]},
    )
    schedule_model = build_model(rag, [], calendar_context=context)
    solver = cp_model.CpSolver()
    status = solver.solve(schedule_model.model)
    assert status == cp_model.INFEASIBLE


def test_contiguous_lookup_merges_adjacent_shifts_but_not_one_minute_gap():
    assert consume_contiguous_work([(0, 120), (120, 240), (240, 360)], 0, 300) == 300
    assert consume_contiguous_work([(0, 120), (121, 360)], 0, 300) is None


def test_scheduler_can_span_adjacent_allowed_shifts_without_pause():
    rag = RagData(
        candidate_plan_id=1,
        steps=[StepData(1, 1, "ADJACENT", "Adjacent shifts", 300)],
        edges=[],
    )
    context = SimpleNamespace(horizon=360, windows_by_step={1: [(0, 120), (120, 240), (240, 360)]})
    schedule_model = build_model(rag, [], calendar_context=context)
    solver = cp_model.CpSolver()
    assert solver.solve(schedule_model.model) == cp_model.OPTIMAL
    task = schedule_model.task_vars[1]
    assert solver.value(task.end) - solver.value(task.start) == 300


def test_named_day_and_night_shifts_keep_the_handover_boundary():
    definition = {
        "timezone": "Asia/Shanghai",
        "weekly_windows": [
            {
                "weekday": day,
                "start_time": "08:00",
                "end_time": "20:00",
                "spans_next_day": False,
                "shift_code": "DAY_SHIFT",
                "shift_name": "白班",
            }
            for day in range(1, 8)
        ] + [
            {
                "weekday": day,
                "start_time": "20:00",
                "end_time": "08:00",
                "spans_next_day": True,
                "shift_code": "NIGHT_SHIFT",
                "shift_name": "夜班",
            }
            for day in range(1, 8)
        ],
        "date_exceptions": [],
    }
    validate_definition(definition["timezone"], definition["weekly_windows"], [])
    anchor = datetime.fromisoformat("2026-07-13T18:00:00+08:00")
    intervals = expand_definition_with_metadata(
        definition,
        anchor,
        datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
    )
    assert [(item.start.hour, item.end.hour, item.metadata().get("shift_code")) for item in intervals[:2]] == [
        (10, 12, "DAY_SHIFT"),
        (12, 0, "NIGHT_SHIFT"),
    ]

    rag = RagData(
        candidate_plan_id=1,
        steps=[StepData(1, 1, "DUAL", "Dual shift work", 240)],
        edges=[],
    )
    context = SimpleNamespace(horizon=720, windows_by_step={1: [(0, 120), (120, 720)]})
    schedule_model = build_model(rag, [], calendar_context=context)
    solver = cp_model.CpSolver()
    assert solver.solve(schedule_model.model) == cp_model.OPTIMAL
    used = [item for item in schedule_model.task_vars[1].segments if solver.value(item.present)]
    assert [(solver.value(item.start), solver.value(item.end)) for item in used] == [(0, 120), (120, 240)]


def test_weekly_validation_detects_overlap_across_midnight():
    windows = [
        {"weekday": 1, "start_time": "20:00", "end_time": "09:00", "spans_next_day": True},
        {"weekday": 2, "start_time": "08:00", "end_time": "12:00", "spans_next_day": False},
    ]
    with pytest.raises(CalendarError):
        validate_definition("Asia/Shanghai", windows, [])

"""Pure work-calendar validation, expansion, and interval operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CalendarError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class CalendarInterval:
    """Absolute work interval carrying immutable shift attribution."""

    start: datetime
    end: datetime
    shifts: tuple[tuple[str | None, str | None], ...] = ()

    def metadata(self) -> dict[str, Any]:
        items = [
            {"shift_code": code, "shift_name": name}
            for code, name in self.shifts
            if code or name
        ]
        if len(items) == 1:
            return items[0]
        if items:
            return {"shifts": items}
        return {}


def _parse_time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise CalendarError("INVALID_CALENDAR_WINDOW", f"Invalid time: {value}") from exc
    if parsed.second or parsed.microsecond:
        raise CalendarError("INVALID_CALENDAR_WINDOW", "Calendar times must use minute precision")
    return parsed


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise CalendarError("INVALID_CALENDAR_TIMEZONE", f"Unknown timezone: {name}") from exc


def _window_minutes(window: dict[str, Any]) -> tuple[int, int]:
    start = _parse_time(str(window.get("start_time", "")))
    end = _parse_time(str(window.get("end_time", "")))
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if bool(window.get("spans_next_day")):
        end_min += 1440
    if end_min <= start_min:
        raise CalendarError("INVALID_CALENDAR_WINDOW", "Calendar window end must be after start")
    return start_min, end_min


def _validate_no_overlap(windows: Iterable[dict[str, Any]], *, keyed_by_weekday: bool) -> None:
    groups: dict[int, list[tuple[int, int]]] = {}
    for window in windows:
        weekday = int(window.get("weekday") or 1) if keyed_by_weekday else 1
        if keyed_by_weekday and not 1 <= weekday <= 7:
            raise CalendarError("INVALID_CALENDAR_WINDOW", "weekday must be between 1 and 7")
        groups.setdefault(weekday, []).append(_window_minutes(window))
    for items in groups.values():
        items.sort()
        for previous, current in zip(items, items[1:]):
            if current[0] < previous[1]:
                raise CalendarError("INVALID_CALENDAR_WINDOW", "Calendar windows cannot overlap")


def _validate_weekly_no_overlap(windows: list[dict[str, Any]]) -> None:
    week_minutes = 7 * 1440
    intervals: list[tuple[int, int]] = []
    for window in windows:
        weekday = int(window.get("weekday") or 0)
        if not 1 <= weekday <= 7:
            raise CalendarError("INVALID_CALENDAR_WINDOW", "weekday must be between 1 and 7")
        start, end = _window_minutes(window)
        offset = (weekday - 1) * 1440
        intervals.append((offset + start, offset + end))
    expanded = sorted([*intervals, *((start + week_minutes, end + week_minutes) for start, end in intervals)])
    for previous, current in zip(expanded, expanded[1:]):
        if current[0] < previous[1]:
            raise CalendarError("INVALID_CALENDAR_WINDOW", "Calendar windows cannot overlap")


def validate_definition(
    timezone_name: str,
    weekly_windows: list[dict[str, Any]],
    date_exceptions: list[dict[str, Any]],
) -> None:
    get_zone(timezone_name)
    _validate_weekly_no_overlap(weekly_windows)
    seen_dates: set[str] = set()
    for exception in date_exceptions:
        date_text = str(exception.get("date", ""))
        try:
            date.fromisoformat(date_text)
        except ValueError as exc:
            raise CalendarError("INVALID_CALENDAR_EXCEPTION", f"Invalid exception date: {date_text}") from exc
        if date_text in seen_dates:
            raise CalendarError("INVALID_CALENDAR_EXCEPTION", f"Duplicate exception date: {date_text}")
        seen_dates.add(date_text)
        mode = exception.get("mode")
        if mode not in {"closed", "replace", "add"}:
            raise CalendarError("INVALID_CALENDAR_EXCEPTION", f"Invalid exception mode: {mode}")
        windows = exception.get("windows") or []
        if mode == "closed" and windows:
            raise CalendarError("INVALID_CALENDAR_EXCEPTION", "closed exception cannot contain windows")
        _validate_no_overlap(windows, keyed_by_weekday=False)


def definition_checksum(
    timezone_name: str,
    weekly_windows: list[dict[str, Any]],
    date_exceptions: list[dict[str, Any]],
) -> str:
    payload = {
        "timezone": timezone_name,
        "weekly_windows": weekly_windows,
        "date_exceptions": date_exceptions,
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _shift_identity(window: dict[str, Any]) -> tuple[tuple[str | None, str | None], ...]:
    code = window.get("shift_code")
    name = window.get("shift_name")
    return ((str(code) if code else None, str(name) if name else None),) if code or name else ()


def merge_calendar_intervals(intervals: Iterable[CalendarInterval]) -> list[CalendarInterval]:
    """Merge overlap, and merge adjacency only when shift attribution matches."""
    ordered = sorted((item for item in intervals if item.end > item.start), key=lambda item: (item.start, item.end))
    merged: list[CalendarInterval] = []
    for item in ordered:
        if not merged or item.start > merged[-1].end:
            merged.append(item)
            continue
        previous = merged[-1]
        if item.start == previous.end and item.shifts != previous.shifts:
            merged.append(item)
            continue
        shifts = tuple(dict.fromkeys([*previous.shifts, *item.shifts]))
        merged[-1] = CalendarInterval(previous.start, max(previous.end, item.end), shifts)
    return merged


def expand_definition_with_metadata(
    definition: dict[str, Any],
    range_start: datetime,
    range_end: datetime,
) -> list[CalendarInterval]:
    """Expand one revision while preserving named shift boundaries."""
    if range_start.tzinfo is None or range_end.tzinfo is None:
        raise CalendarError("CALENDAR_START_REQUIRED", "Calendar range must be timezone-aware")
    zone = get_zone(str(definition["timezone"]))
    weekly = definition.get("weekly_windows") or []
    exceptions = {item["date"]: item for item in definition.get("date_exceptions") or []}
    local_start = range_start.astimezone(zone).date() - timedelta(days=1)
    local_end = range_end.astimezone(zone).date() + timedelta(days=1)
    result: list[CalendarInterval] = []
    current = local_start
    while current <= local_end:
        base = [item for item in weekly if int(item.get("weekday") or 0) == current.isoweekday()]
        exception = exceptions.get(current.isoformat())
        if exception:
            mode = exception["mode"]
            if mode == "closed":
                selected: list[dict[str, Any]] = []
            elif mode == "replace":
                selected = exception.get("windows") or []
            else:
                selected = [*base, *(exception.get("windows") or [])]
        else:
            selected = base
        local_midnight = datetime.combine(current, time.min, tzinfo=zone)
        for window in selected:
            start_min, end_min = _window_minutes(window)
            start = (local_midnight + timedelta(minutes=start_min)).astimezone(timezone.utc)
            end = (local_midnight + timedelta(minutes=end_min)).astimezone(timezone.utc)
            result.append(CalendarInterval(start, end, _shift_identity(window)))
        current += timedelta(days=1)
    clipped = [
        CalendarInterval(
            max(item.start, range_start.astimezone(timezone.utc)),
            min(item.end, range_end.astimezone(timezone.utc)),
            item.shifts,
        )
        for item in result
    ]
    return merge_calendar_intervals(clipped)


def expand_definition(
    definition: dict[str, Any],
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Expand one revision into UTC half-open intervals."""
    tagged = expand_definition_with_metadata(definition, range_start, range_end)
    return merge_intervals((item.start, item.end) for item in tagged)


def intersect_calendar_intervals(groups: list[list[CalendarInterval]]) -> list[CalendarInterval]:
    if not groups:
        return []
    current = merge_calendar_intervals(groups[0])
    for other in groups[1:]:
        right = merge_calendar_intervals(other)
        combined: list[CalendarInterval] = []
        left_index = right_index = 0
        while left_index < len(current) and right_index < len(right):
            left = current[left_index]
            right_item = right[right_index]
            start = max(left.start, right_item.start)
            end = min(left.end, right_item.end)
            if end > start:
                shifts = tuple(dict.fromkeys([*left.shifts, *right_item.shifts]))
                combined.append(CalendarInterval(start, end, shifts))
            if left.end <= right_item.end:
                left_index += 1
            else:
                right_index += 1
        current = merge_calendar_intervals(combined)
    return current


def intersect_intervals(
    groups: list[list[tuple[datetime, datetime]]],
) -> list[tuple[datetime, datetime]]:
    if not groups:
        return []
    current = merge_intervals(groups[0])
    for other in groups[1:]:
        right = merge_intervals(other)
        merged: list[tuple[datetime, datetime]] = []
        left_index = right_index = 0
        while left_index < len(current) and right_index < len(right):
            start = max(current[left_index][0], right[right_index][0])
            end = min(current[left_index][1], right[right_index][1])
            if end > start:
                merged.append((start, end))
            if current[left_index][1] <= right[right_index][1]:
                left_index += 1
            else:
                right_index += 1
        current = merged
        if not current:
            break
    return current


def to_minute_offsets(
    intervals: list[tuple[datetime, datetime]],
    anchor: datetime,
) -> list[tuple[int, int]]:
    anchor_utc = anchor.astimezone(timezone.utc)
    offsets = []
    for start, end in intervals:
        start_min = max(0, int((start - anchor_utc).total_seconds() // 60))
        end_min = int((end - anchor_utc).total_seconds() // 60)
        if end_min > start_min:
            offsets.append((start_min, end_min))
    return offsets


def consume_work(
    windows: list[tuple[int, int]],
    not_before_min: int,
    duration_min: int,
) -> int | None:
    remaining = duration_min
    for start, end in windows:
        cursor = max(start, not_before_min)
        if cursor >= end:
            continue
        available = end - cursor
        if available >= remaining:
            return cursor + remaining
        remaining -= available
        not_before_min = end
    return None


def consume_contiguous_work(
    windows: list[tuple[int, int]],
    not_before_min: int,
    duration_min: int,
) -> int | None:
    """Return completion time when work fits without skipping an intermediate window."""
    blocks: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if blocks and start == blocks[-1][1]:
            blocks[-1] = (blocks[-1][0], end)
        else:
            blocks.append((start, end))
    for start, end in blocks:
        cursor = max(start, not_before_min)
        if end - cursor >= duration_min:
            return cursor + duration_min
    return None


def longest_contiguous_work_window(windows: list[tuple[int, int]]) -> int:
    blocks: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if blocks and start == blocks[-1][1]:
            blocks[-1] = (blocks[-1][0], end)
        else:
            blocks.append((start, end))
    return max((end - start for start, end in blocks), default=0)

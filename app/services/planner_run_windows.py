"""Absolute, first-occurrence windows frozen per run, separate from project rules."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ActivityTimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: str
    earliest_start_at: datetime | None = None
    latest_finish_at: datetime | None = None

    @field_validator('earliest_start_at', 'latest_finish_at', mode='before')
    @classmethod
    def timestamp_type(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError('时间窗必须使用带时区的日期时间')
        return value

    @field_validator('earliest_start_at', 'latest_finish_at')
    @classmethod
    def timestamp(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('时间窗日期必须包含时区偏移')
            if value.second or value.microsecond or value.utcoffset().total_seconds() % 60:
                raise ValueError('时间窗必须精确到整分钟')
            value = value.astimezone(timezone.utc)
        return value

    @model_validator(mode='after')
    def ordered(self):
        if self.earliest_start_at and self.latest_finish_at and self.latest_finish_at < self.earliest_start_at:
            raise ValueError('最晚完成时间不得早于最早开始时间')
        return self


def freeze_run_windows(scenario, windows, start):
    from app.services.planner_scenarios import expand_packages
    active = {a['id'] for a in expand_packages(scenario)['activities']}
    seen, frozen = set(), []
    for window in windows:
        aid = window.activity_id
        if aid not in active:
            raise ValueError(f'时间窗绑定活动不存在、已停用或不在本次范围内：{aid}')
        if aid in seen:
            raise ValueError(f'同一活动只能配置一个本次时间窗：{aid}')
        seen.add(aid)
        if window.earliest_start_at is None and window.latest_finish_at is None:
            continue
        if start is None or start.tzinfo is None or start.utcoffset() is None or start.second or start.microsecond:
            raise ValueError('使用本次时间窗需要带时区且精确到整分钟的计划开始时间')
        def offset(value):
            if value is None:
                return None
            seconds = (value - start.astimezone(timezone.utc)).total_seconds()
            if seconds % 60:
                raise ValueError('计划开始时间与时间窗必须使用整分钟')
            return scenario.get('start_time', 0) + int(seconds // 60)
        frozen.append({'id': 'run-window:' + aid, 'activity_id': aid,
                       'earliest_start': offset(window.earliest_start_at),
                       'latest_finish': offset(window.latest_finish_at)})
    return sorted(frozen, key=lambda w: w['activity_id'])


def frozen_run_windows(scenario):
    windows = scenario.get('run_time_windows', [])
    if not isinstance(windows, list):
        raise ValueError('本次活动时间窗必须为列表')
    active = {a['id'] for a in scenario.get('activities', [])}
    seen, ids = set(), set()
    for w in windows:
        if not isinstance(w, dict) or not isinstance(w.get('id'), str) or not w['id']:
            raise ValueError('本次时间窗缺少编号')
        aid = w.get('activity_id')
        if not isinstance(aid, str) or aid not in active or aid in seen or w['id'] in ids:
            raise ValueError('本次时间窗活动无效或重复绑定')
        seen.add(aid); ids.add(w['id'])
        lo, hi = w.get('earliest_start'), w.get('latest_finish')
        if any(v is not None and type(v) is not int for v in (lo, hi)):
            raise ValueError('本次时间窗边界必须为整数分钟或空')
        if lo is not None and hi is not None and hi < lo:
            raise ValueError('最晚完成时间不得早于最早开始时间')
    return windows

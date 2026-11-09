import copy
from datetime import datetime

import pytest
from pydantic import ValidationError

from tests.unit.test_joint_cpsat import core, payload, setup_db, solve
from app.services.planner_run_windows import ActivityTimeWindow, freeze_run_windows


@pytest.mark.parametrize('lo,hi,status,span', [(None,None,'OPTIMAL',3),(5,None,'OPTIMAL',8),
    (None,3,'OPTIMAL',3),(5,8,'OPTIMAL',8),(None,2,'INFEASIBLE',None),(5,7,'INFEASIBLE',None)])
def test_optional_bounds(core,payload,lo,hi,status,span):
    payload['run_time_windows']=[{'id':'rw','activity_id':'a','earliest_start':lo,'latest_finish':hi}]
    saved=copy.deepcopy(payload)
    r=solve(core,payload)
    assert r.status==status,r
    if span is not None:
        assert r.paths[0].metrics.makespan==span and r.paths[0].validator_status=='VALID'
    assert payload==saved


def test_project_and_run_windows_both_apply(core,payload):
    payload['time_windows']=[{'id':'old','activity_id':'a','earliest_start':10,'latest_finish':20}]
    payload['run_time_windows']=[{'id':'new','activity_id':'a','earliest_start':12,'latest_finish':15}]
    r=solve(core,payload)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==15
    payload['run_time_windows'][0]['latest_finish']=12
    assert solve(core,payload).status=='INFEASIBLE'


def test_past_bound_optional_activity_and_zero_step(core,payload):
    payload['start_time']=20
    payload['run_time_windows']=[{'id':'rw','activity_id':'a','earliest_start':None,'latest_finish':19}]
    assert solve(core,payload).status=='INFEASIBLE'
    payload['goal_state_ids']=['done:b']
    r=solve(core,payload)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==2
    payload['goal_state_ids']=['ready']
    assert solve(core,payload).paths[0].metrics.makespan==0


def test_first_only_with_late_materials_and_three_power_ons(core,monkeypatch):
    from tests.unit.test_material_power_cycles import material_power_case
    from tests.unit.test_joint_pruning import assert_matches_unpruned
    p=material_power_case()
    p['run_time_windows']=[{'id':'rw','activity_id':'power_on','earliest_start':10,'latest_finish':15}]
    r=solve(core,p,seconds=10)
    assert r.status=='OPTIMAL',r
    rows=[e for e in r.paths[0].executions if e.activity_id=='power_on']
    assert len(rows)==3 and (rows[0].start_time,rows[0].end_time)==(10,15)
    assert all(e.start_time>15 for e in rows[1:])
    assert r.paths[0].validator_status=='VALID' and r.paths[0].metrics.makespan==285
    assert_matches_unpruned(core,p,monkeypatch,r)


@pytest.mark.parametrize('closing,status',[(150,'INFEASIBLE'),(180,'OPTIMAL')])
def test_first_completion_includes_calendar_pause(core,closing,status):
    from tests.unit.test_work_calendars import scenario
    p=scenario(120)
    p['run_time_windows']=[{'id':'rw','activity_id':'a','latest_finish':closing}]
    r=solve(core,p)
    assert r.status==status,r
    if status=='OPTIMAL':
        assert r.paths[0].metrics.makespan==180 and r.paths[0].validator_status=='VALID'


def test_far_future_opening_expands_calendar(core):
    from tests.unit.test_work_calendars import scenario
    p=scenario(60,anchor='2026-11-02T08:00:00+08:00')
    p['run_time_windows']=[{'id':'rw','activity_id':'a','earliest_start':14*1440,'latest_finish':14*1440+60}]
    r=solve(core,p)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==14*1440+60


@pytest.mark.parametrize('closing,status',[(800,'INFEASIBLE'),(900,'OPTIMAL')])
def test_run_window_and_night_restriction(core,closing,status):
    from tests.unit.test_night_lifts import fixture
    p=fixture()
    p['run_time_windows']=[{'id':'rw','activity_id':'a','latest_finish':closing}]
    assert solve(core,p).status==status


def test_replay_rejects_bad_first_but_allows_later_execution(core,payload):
    payload['run_time_windows']=[{'id':'rw','activity_id':'a','earliest_start':5,'latest_finish':8}]
    core._check_windows(payload,[{'activity_id':'a','start':10,'end':13}, {'activity_id':'a','start':5,'end':8}])
    with pytest.raises(ValueError,match='First execution'):
        core._check_windows(payload,[{'activity_id':'a','start':4,'end':7}])


def test_absolute_conversion_and_nonzero_origin():
    p={'activities':[{'id':'a'}],'start_time':20}
    w=ActivityTimeWindow(activity_id='a',earliest_start_at='2026-11-06T09:00:00+08:00',latest_finish_at=None)
    start=datetime.fromisoformat('2026-11-05T17:00:00-08:00')
    assert freeze_run_windows(p,[w],start)[0]['earliest_start']==20
    later=datetime.fromisoformat('2026-11-06T02:00:00+00:00')
    assert freeze_run_windows(p,[w],later)[0]['earliest_start']==-40
    assert freeze_run_windows(p,[ActivityTimeWindow(activity_id='a')],None)==[]


@pytest.mark.parametrize('stamp',['2026-11-05T08:00:00','2026-11-05T08:00:01+08:00',123])
def test_absolute_dates_require_offset_and_minutes(stamp):
    with pytest.raises(ValidationError):
        ActivityTimeWindow(activity_id='a',earliest_start_at=stamp)

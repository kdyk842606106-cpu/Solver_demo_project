import copy
import pytest
from tests.unit.test_work_calendars import scenario, solve


def fixture(duration=120, anchor='2026-11-02T19:00:00+08:00', calendar=False):
    s=scenario(duration,anchor)
    if not calendar:
        s.pop('work_calendar_id');s.pop('work_calendars')
    s['night_lift_rule']={'enabled':True,'night_start':'20:00','night_end':'08:00'}
    s['resources']=[{'id':'crane','kind':'crane','capacity':1}]
    s['activities'][0].update(resource_reqs={'crane':1},metadata={'precision_fragile':True})
    return s


@pytest.mark.parametrize('mode',['serial','parallel'])
@pytest.mark.parametrize('duration,anchor,expected',[
    (120,'2026-11-02T19:00:00+08:00',900),
    (60,'2026-11-02T19:00:00+08:00',60),
    (60,'2026-11-02T20:00:00+08:00',780),
    (30,'2026-11-02T07:00:00+08:00',90),
])
def test_whole_execution_must_fit_daylight(mode,duration,anchor,expected):
    s=fixture(duration,anchor);s['execution_mode']=mode
    r=solve(s)
    assert r.status=='OPTIMAL',r
    assert r.paths[0].validator_status=='VALID'
    assert r.paths[0].metrics.makespan==r.stats['lower_bound']==expected


@pytest.mark.parametrize('change',['ordinary','no_crane','disabled'])
def test_requires_both_crane_and_fragile(change):
    s=fixture()
    if change=='ordinary':s['activities'][0]['metadata']['precision_fragile']=False
    elif change=='no_crane':s['activities'][0]['resource_reqs']={}
    else:s['night_lift_rule']['enabled']=False
    assert solve(s).paths[0].metrics.makespan==120


def test_long_activity_is_not_silently_split_over_night():
    assert solve(fixture(721)).status=='INFEASIBLE'
    s=fixture(540,calendar=True)
    assert solve(s).status=='INFEASIBLE'
    s['goal_state_ids']=['ready']
    assert solve(s).paths[0].metrics.makespan==0


def test_lunch_pause_permitted_but_overnight_pause_forbidden():
    s=fixture(420,'2026-11-02T11:00:00+08:00',calendar=True)
    r=solve(s)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==1740
    s['night_lift_rule']['enabled']=False
    assert solve(s).paths[0].metrics.makespan==1380


def test_normal_lift_can_use_night_with_shared_capacity():
    s=fixture()
    b=copy.deepcopy(s['activities'][0]);b.update(id='b',output_state_id='done:b',metadata={'precision_fragile':False})
    s['activities'].append(b);s['goal_state_ids'].append('done:b')
    r=solve(s)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==900
    assert next(e for e in r.paths[0].executions if e.activity_id=='b').start_time==0


def test_engine_bridge_replays_daylight_wait_without_time_windows():
    from app.services.planner_engine_bridge import run_engine
    from app.services.planner_scenarios import new_scenario,create_activity,rebuild_mirror
    s=new_scenario('Daylight replay')
    s.update({k:copy.deepcopy(v) for k,v in fixture().items() if k in ('night_lift_rule','resources','calendar_context','max_steps')})
    for index in range(2):
        a=create_activity(s,{'name':f'lift {index}','duration':120,'max_instances':1,
            'metadata':{'precision_fragile':index==0},'resource_reqs':{'crane':1}},display_number=index+1)
        s['goal_state_ids'].append(a['output_state_id'])
    rebuild_mirror(s)
    r=run_engine(s,engine='JOINT_CP_SAT',run_id='night-gap',seed=11)
    assert r['status']=='OPTIMAL',r
    assert r['stats']['validator_rejected']==0
    assert r['paths'][0]['validator_status']=='VALID'
    assert r['paths'][0]['metrics']['makespan']==900


def test_deadline_rejects_and_validator_rejects_crossing_night():
    s=fixture();s['time_windows']=[{'id':'w','activity_id':'a','earliest_start':0,'latest_finish':120}]
    assert solve(s).status=='INFEASIBLE'
    s.pop('time_windows')
    from app.core.joint_cpsat import build_model,replay_candidate
    _,parsed,_,_=build_model(s)
    with pytest.raises(ValueError,match='night'):
        replay_candidate(s,parsed,[{'activity_id':'a','ordinal':1,'start':0,'end':120}],run_id='bad',seed=11)
    from planner_experiment.models import Action
    from planner_experiment.simulator import PathSimulator
    sim=PathSimulator(parsed)
    with pytest.raises(ValueError):sim.transition(sim.initial_state(),Action('START',activity_id='a'))


def test_future_exception_is_not_lost_to_short_horizon():
    s=fixture(calendar=True)
    s['work_calendars'][0].update(weekdays=list(range(7)),periods=[{'start':'00:00','end':'08:00'},{'start':'20:00','end':'24:00'}],
        exceptions=[{'date':'2026-11-16','periods':[{'start':'08:00','end':'20:00'}]}])
    r=solve(s)
    assert r.status=='OPTIMAL',r
    assert r.paths[0].metrics.makespan==19620

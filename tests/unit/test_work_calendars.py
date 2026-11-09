import copy
import pytest
from app.services.planner_engine_bridge import _planner_modules
from app.services.planner_calendars import calendar_intervals, validate_calendars


def scenario(duration=120, anchor='2026-11-02T11:00:00+08:00'):
    return {'schema_version':2,'id':'calendar-test','execution_mode':'parallel','start_time':0,
        'max_steps':2,'initial_state_ids':['ready'],'goal_state_ids':['done:a'],
        'activities':[{'id':'a','name':'a','duration':duration,'output_state_id':'done:a',
                       'preconditions':[{'state_id':'ready','relation_role':'required'}],'max_instances':1}],
        'work_calendar_id':'c','work_calendars':[{'id':'c','name':'标准班次','weekdays':[0,1,2,3,4],
            'periods':[{'start':'08:00','end':'12:00'},{'start':'13:00','end':'17:00'}],'exceptions':[]}],
        'calendar_context':{'start_at':anchor,'timezone':'Asia/Shanghai'}}


def solve(s):
    modules=_planner_modules()
    from app.core.joint_cpsat import solve_joint
    return solve_joint(s,run_id='cal',seed=11,budget=modules['Budget'](5,20000,20))


@pytest.mark.parametrize('mode',['serial','parallel'])
@pytest.mark.parametrize('duration,anchor,expected',[
    (120,'2026-11-02T11:00:00+08:00',180),
    (60,'2026-11-02T12:00:00+08:00',120),
    (180,'2026-11-06T16:00:00+08:00',3960),
    (60,'2026-11-07T08:00:00+08:00',2940),
])
def test_pause_resume_and_closed_start(mode,duration,anchor,expected):
    s=scenario(duration,anchor);s['execution_mode']=mode
    original=copy.deepcopy(s)
    r=solve(s)
    assert r.status=='OPTIMAL',r
    assert r.paths[0].validator_status=='VALID'
    assert r.paths[0].metrics.makespan==expected
    assert s==original


def test_exception_holiday_makeup_and_capacity():
    s=scenario(180,'2026-11-06T16:00:00+08:00')
    s['work_calendars'][0]['exceptions']=[{'date':'2026-11-07','periods':[{'start':'09:00','end':'12:00'}]}]
    assert solve(s).paths[0].metrics.makespan==1140  # Saturday 11:00
    s['work_calendars'][0]['exceptions']=[{'date':'2026-11-09','periods':[]}]
    assert solve(s).paths[0].metrics.makespan==5400  # Tuesday 10:00
    s=scenario(300,'2026-11-02T08:00:00+08:00')
    s['resources']=[{'id':'r','capacity':1}]
    s['activities'][0]['resource_reqs']={'r':1}
    b=copy.deepcopy(s['activities'][0]);b.update(id='b',output_state_id='done:b')
    s['activities'].append(b);s['goal_state_ids'].append('done:b')
    r=solve(s)
    assert r.status=='OPTIMAL' and r.paths[0].metrics.makespan==1560
    assert r.paths[0].validator_status=='VALID'


def test_calendar_window_and_zero_step():
    s=scenario(60,'2026-11-02T08:00:00+08:00')
    s['time_windows']=[{'id':'w','activity_id':'a','earliest_start':240,'latest_finish':300}]
    assert solve(s).status=='INFEASIBLE'
    s['time_windows'][0]['latest_finish']=360
    assert solve(s).paths[0].metrics.makespan==360
    s['goal_state_ids']=['ready']
    assert solve(s).paths[0].metrics.makespan==0


def test_replay_rejects_calendar_duration_tampering():
    s=scenario();_planner_modules()
    from app.core.joint_cpsat import build_model,replay_candidate
    _,parsed,_,_=build_model(s)
    with pytest.raises(ValueError,match='Calendar'):
        replay_candidate(s,parsed,[{'activity_id':'a','ordinal':1,'start':0,'end':120}],run_id='bad',seed=11)


def test_invalid_calendar_and_dst_boundaries():
    s=scenario();s['work_calendars'][0]['periods'].append({'start':'11:00','end':'14:00'})
    with pytest.raises(ValueError,match='重叠'):validate_calendars(s)
    s=scenario();s['work_calendar_id']='missing'
    with pytest.raises(ValueError,match='不存在'):validate_calendars(s)
    s=scenario(60,'2026-03-08T00:00:00-05:00');s['calendar_context']['timezone']='America/New_York'
    s['work_calendars'][0].update(weekdays=[6],periods=[{'start':'02:00','end':'04:00'}])
    with pytest.raises(ValueError,match='夏令时'):calendar_intervals(s)


def test_calendar_recovery_and_replay_with_nonzero_origin():
    s=scenario(60,'2026-11-06T16:00:00+08:00')
    s['start_time']=100
    s['max_steps']=3
    s['initial_state_ids']=['off','clean']
    s['goal_state_ids']=['on','done:use','clean']
    s['activities']=[
        {'id':'on','name':'on','duration':60,'max_instances':2,'output_state_id':'on',
         'additional_output_state_ids':['clean'], 'preconditions':[{'state_id':'off','relation_role':'transition'}]},
        {'id':'use','name':'use','duration':60,'max_instances':1,'output_state_id':'done:use',
         'additional_output_state_ids':['off'], 'delete_effect_state_ids':['clean'],
         'preconditions':[{'state_id':'on','relation_role':'transition'}]},
    ]
    r=solve(s)
    assert r.status=='OPTIMAL',r
    assert r.paths[0].metrics.makespan==3960
    assert r.paths[0].validator_status=='VALID'
    assert [e.activity_id for e in r.paths[0].executions].count('on')==2


def test_fixed_intervals_match_when_inactive_windows_are_excluded():
    s=scenario()
    s['activities'].append({'id':'inactive','name':'inactive','duration':5000,'output_state_id':'unused','is_active':False})
    s['time_windows']=[{'id':'unused','activity_id':'inactive','earliest_start':100000,'latest_finish':110000}]
    from app.services.planner_scenarios import expand_packages
    s['working_intervals']=calendar_intervals(s)
    expanded=expand_packages(s)
    assert calendar_intervals(expanded)==s['working_intervals']
    assert solve(expanded).status=='OPTIMAL'

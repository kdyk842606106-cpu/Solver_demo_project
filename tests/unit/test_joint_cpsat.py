import copy
import time

import pytest

from app.services.planner_engine_bridge import _planner_modules, planner_available


@pytest.fixture(autouse=True)
def setup_db():
    if not planner_available():
        pytest.skip("external Planner runtime unavailable")
    _planner_modules()


@pytest.fixture
def core():
    from app.core import joint_cpsat
    return joint_cpsat


def activity(aid, duration, *, required=(), transition=(), outputs=(), delete=(), limit=1, resources=None):
    return {"id":aid,"name":aid,"duration":duration,"output_state_id":"done:"+aid,
            "additional_output_state_ids":list(outputs),"delete_effect_state_ids":list(delete),
            "preconditions":[{"state_id":s,"relation_role":"required"} for s in required]+
                            [{"state_id":s,"relation_role":"transition"} for s in transition],
            "max_instances":limit,"resource_reqs":resources or {},"event_reqs":[]}


@pytest.fixture
def payload():
    return {"schema_version":2,"id":"joint-test","execution_mode":"parallel","start_time":0,
            "initial_state_ids":["ready"],"goal_state_ids":["done:a","done:b"],"forbidden_state_ids":[],
            "activities":[activity("a",3,required=["ready"]),activity("b",2,required=["ready"])],
            "resources":[],"external_events":[],"max_steps":8}


def solve(core,payload,seconds=3,seed=23,observer=None,progress=None):
    from planner_experiment.models import Budget
    return core.solve_joint(payload,run_id="joint-unit",seed=seed,budget=Budget(seconds,1,3),
                            candidate_observer=observer,progress_observer=progress)


@pytest.mark.parametrize("mode,optimum",[("parallel",3),("serial",5)])
def test_joint_selects_and_schedules_in_both_modes(core,payload,mode,optimum):
    payload['execution_mode']=mode
    payload['activities'].append(activity('irrelevant',50,required=['never']))
    saved=copy.deepcopy(payload);seen=[]
    result=solve(core,payload,observer=seen.append)
    assert result.status=='OPTIMAL',result
    assert result.paths[0].metrics.makespan==optimum
    assert result.paths[0].validator_status=='VALID'
    assert result.seed==23 and result.paths[0].seed==23
    assert result.stats['lower_bound']==optimum and seen
    assert payload==saved
    assert all(e.activity_id!='irrelevant' for e in result.paths[0].executions)


def test_resource_bottleneck(core,payload):
    payload['resources']=[{'id':'r','capacity':1}]
    for a in payload['activities']:a['resource_reqs']={'r':1}
    result=solve(core,payload)
    assert result.status=='OPTIMAL' and result.paths[0].metrics.makespan==5


def test_equal_makespan_prefers_fewer_executions(core, payload):
    payload["goal_state_ids"] = ["done:critical", "ready_for_test"]
    payload["activities"] = [
        activity("critical", 10, required=["ready"]),
        activity("prep", 1, required=["ready"], limit=4),
        activity("via_prep", 1, required=["done:prep"], outputs=["ready_for_test"]),
        activity("direct", 6, required=["ready"], outputs=["ready_for_test"], limit=3),
    ]
    events = []
    result = solve(core, payload, progress=lambda m, p: events.append((m,p)))
    path = result.paths[0]
    assert result.status == "OPTIMAL" and path.validator_status == "VALID"
    assert path.metrics.makespan == result.stats["lower_bound"] == 10
    assert sorted(e.activity_id for e in path.executions) == ["critical", "direct"]
    assert result.stats["execution_count_proven_optimal"]
    plans = [p for _, p in events if p is not None]
    assert all(p.validator_status == "VALID" for p in plans)
    scores = [(p.metrics.makespan, len(p.executions)) for p in plans]
    assert scores == sorted(set(scores), reverse=True) and scores[-1] == (10, 2)
    assert any(m["phase"] == "EXECUTION_COUNT" for m,_ in events)
    for key in ("branches", "conflicts"):
        totals = [m[key] for m,_ in events if key in m]
        assert totals == sorted(totals) and totals[-1] == result.stats[key]


def test_shorter_makespan_wins_even_if_it_needs_more_executions(core, payload):
    payload["goal_state_ids"] = ["done"]
    payload["activities"] = [
        activity("direct", 4, required=["ready"], outputs=["done"]),
        activity("prep", 1, required=["ready"]),
        activity("fast", 2, required=["done:prep"], outputs=["done"]),
    ]
    result = solve(core, payload)
    path = result.paths[0]
    assert result.status == "OPTIMAL" and path.metrics.makespan == 3
    assert [e.activity_id for e in path.executions] == ["prep", "fast"]


@pytest.mark.parametrize('mode',['serial','parallel'])
def test_window_release_and_replay(core,payload,mode):
    payload['execution_mode']=mode
    payload['time_windows']=[{'id':'w','activity_id':'b','earliest_start':10,'latest_finish':12}]
    result=solve(core,payload)
    assert result.status=='OPTIMAL',result
    b=next(e for e in result.paths[0].executions if e.activity_id=='b')
    assert (b.start_time,b.end_time)==(10,12)


def test_deadline_infeasibility_is_proven(core,payload):
    payload['activities'][1]['preconditions'].append({'state_id':'done:a','relation_role':'required'})
    payload['time_windows']=[{'id':'w','activity_id':'b','earliest_start':0,'latest_finish':4}]
    result=solve(core,payload)
    assert result.status=='INFEASIBLE'
    assert result.stats['proven_infeasible'] and not result.paths


def test_recovery_and_negative_goal(core,payload):
    payload.update(initial_state_ids=['off','dirty:cal','dirty:test'],
                   goal_state_ids=['done:repair','valid:cal','valid:test','on'],forbidden_state_ids=['off'],max_steps=12)
    payload['activities']=[
        activity('on',1,transition=['off'],outputs=['on'],limit=2),
        activity('cal',2,required=['on'],transition=['dirty:cal'],outputs=['valid:cal'],limit=2),
        activity('test',3,required=['on','valid:cal'],transition=['dirty:test'],outputs=['valid:test'],limit=2),
        activity('work',1,required=['on','valid:test']),
        activity('off',1,transition=['on'],outputs=['off']),
        activity('repair',1,required=['off','done:work'],outputs=['dirty:cal','dirty:test'],delete=['valid:cal','valid:test']),
    ]
    result=solve(core,payload,seconds=5)
    assert result.status=='OPTIMAL',result
    assert result.paths[0].metrics.makespan==15
    from collections import Counter
    counts=Counter(e.activity_id for e in result.paths[0].executions)
    assert counts['cal']==counts['test']==counts['on']==2
    assert counts['repair']==counts['off']==1


def test_unset_activity_limit_allows_automatic_recovery(core,payload):
    payload.update(initial_state_ids=['spent'], goal_state_ids=['token','done:use'], max_steps=3)
    payload['activities']=[
        activity('restore',1,transition=['spent'],outputs=['token'],limit=None),
        activity('use',1,transition=['token'],outputs=['spent']),
    ]
    result=solve(core,payload)
    assert result.status=='OPTIMAL',result
    candidate=result.paths[0]
    assert candidate.validator_status=='VALID'
    assert candidate.metrics.makespan==3
    assert [e.activity_id for e in candidate.executions].count('restore')==2
    assert len(candidate.executions)==3


def test_unsupported_events_are_not_silently_dropped(core,payload):
    payload['external_events']=[{'id':'e','time':5,'add_state_ids':['new'],'remove_state_ids':[]}]
    result=solve(core,payload)
    assert result.status=='UNSUPPORTED' and not result.stats['proven_infeasible']


def test_zero_budget_is_unknown_timeout_not_infeasible(core,payload):
    result=solve(core,payload,seconds=0)
    assert result.status=='TIMEOUT_EMPTY' and not result.paths
    assert not result.stats['proven_infeasible']


def test_late_valid_candidate_excluded(core,payload,monkeypatch):
    original=core.replay_candidate
    def slow(*args,**kwargs):
        result=original(*args,**kwargs)
        time.sleep(.15)
        return result
    monkeypatch.setattr(core,'replay_candidate',slow)
    result=solve(core,payload,seconds=.1)
    assert result.status=='TIMEOUT_EMPTY' and not result.paths
    assert result.stats['late_candidate_count']==1


def test_normalization_separates_shift_and_tail(core,payload):
    payload['goal_state_ids']=['done:a']
    _,scenario,_,_=core.build_model(payload)
    rows=[{'activity_id':'a','ordinal':1,'start':10,'end':13},
          {'activity_id':'b','ordinal':1,'start':20,'end':22}]
    candidate,details=core.replay_candidate(payload,scenario,rows,run_id='n',seed=11)
    assert candidate.metrics.makespan==3
    assert details['raw_schedule_makespan']==22
    assert details['shifted_schedule_makespan']==5
    assert details['left_shift_saved_time']==17 and details['terminal_tail_saved_time']==2
    assert len(details['omitted_tail_occurrences'])==1
    assert candidate.raw_makespan==22 and candidate.normalization_saved_time==19


def test_initial_goal_and_nonzero_start(core,payload):
    payload.update(start_time=20,goal_state_ids=['ready'])
    result=solve(core,payload)
    assert result.status=='OPTIMAL' and result.paths[0].metrics.makespan==0
    assert result.stats['lower_bound']==0


def test_optional_window_does_not_force_execution(core,payload):
    payload['goal_state_ids']=['done:a']
    payload['activities'][1]['preconditions']=[{'state_id':'missing','relation_role':'required'}]
    payload['time_windows']=[{'id':'w','activity_id':'b','earliest_start':0,'latest_finish':2}]
    result=solve(core,payload)
    assert result.status=='OPTIMAL' and result.paths[0].metrics.makespan==3


def test_persistent_facts_prune_before_variable_creation_without_mutating_input(core, payload):
    payload['activities'][0]['max_instances'] = None
    payload['activities'][1]['max_instances'] = 3
    saved = copy.deepcopy(payload)
    _, parsed, slots, stats = core.build_model(payload)
    assert len(slots) == stats['optional_occurrence_slots'] == 2
    pruning = stats['occurrence_pruning']
    assert pruning['eligible'] and pruning['applied']
    assert pruning['input_slots'] == 11 and pruning['removed_slots'] == 9
    assert pruning['activity_limits'] == {
        'a': {'input_limit': 8, 'effective_limit': 1},
        'b': {'input_limit': 3, 'effective_limit': 1},
    }
    assert parsed.activity_by_id['a'].max_instances is None
    assert parsed.activity_by_id['b'].max_instances == 3
    assert payload == saved


@pytest.mark.parametrize('mode', ['serial', 'parallel'])
@pytest.mark.parametrize('goal_kind', ['normal', 'initial', 'forbidden', 'unreachable'])
def test_pruning_preserves_optimum_against_unpruned_model(core, payload, monkeypatch, mode, goal_kind):
    payload['execution_mode'] = mode
    payload['max_steps'] = 4
    for a in payload['activities']:
        a['max_instances'] = None
        a['resource_reqs'] = {'crew': 1}
    payload['resources'] = [{'id': 'crew', 'capacity': 1}]
    payload['activities'][1]['preconditions'].append({'state_id': 'done:a', 'relation_role': 'required'})
    payload['time_windows'] = [{'id': 'late', 'activity_id': 'b', 'earliest_start': 7, 'latest_finish': 12}]
    if goal_kind == 'initial':
        payload['goal_state_ids'] = ['ready']
    elif goal_kind == 'forbidden':
        payload['forbidden_state_ids'] = ['done:a']
    elif goal_kind == 'unreachable':
        payload['activities'][0]['preconditions'] = [{'state_id': 'done:b', 'relation_role': 'required'}]
    reduced = solve(core, payload)
    original_policy = core._occurrence_limits

    def unpruned(scenario, **kwargs):
        _, stats = original_policy(scenario)
        return {a.id: min(scenario.max_steps, a.max_instances or scenario.max_steps)
                for a in scenario.activities}, stats

    monkeypatch.setattr(core, '_occurrence_limits', unpruned)
    baseline = solve(core, payload)
    assert reduced.status == baseline.status
    assert reduced.status in ('OPTIMAL', 'INFEASIBLE')
    assert [(p.metrics.makespan, len(p.executions), p.validator_status) for p in reduced.paths] == [
        (p.metrics.makespan, len(p.executions), p.validator_status) for p in baseline.paths]


@pytest.mark.parametrize('removal', ['transition', 'delete'])
@pytest.mark.parametrize('restore_limit', [None, 1])
def test_any_removal_preserves_additive_restoration_instances(core, payload, removal, restore_limit):
    payload.update(initial_state_ids=['ready'], goal_state_ids=['token', 'done:use'], max_steps=3)
    payload['activities'] = [
        activity('restore', 1, required=['ready'], outputs=['token'], limit=restore_limit),
        activity('use', 1, transition=['token']) if removal == 'transition' else
        activity('use', 1, required=['done:restore'], delete=['token']),
    ]
    result = solve(core, payload)
    pruning = result.stats['model']['occurrence_pruning']
    assert not pruning['eligible'] and not pruning['applied']
    assert pruning['skip_reason'] == 'no_safe_single_occurrence_proof'
    assert pruning['retained_activities']['restore']['reason'] == 'output_can_be_removed'
    assert pruning['removed_slots'] == 0
    if restore_limit == 1:
        assert result.status == 'INFEASIBLE'
    else:
        assert result.status == 'OPTIMAL'
        assert result.paths[0].validator_status == 'VALID'
        assert result.paths[0].metrics.makespan == 3
        assert [e.activity_id for e in result.paths[0].executions].count('restore') == 2


def test_legacy_implicit_overwrite_disables_pruning(core):
    payload = {'schema_version': 1, 'id': 'legacy-pruning', 'execution_mode': 'parallel', 'max_steps': 4,
               'initial_facts': {'power': 'off'}, 'goal': {'required': {'power': 'on'}},
               'activities': [{'id': 'on', 'duration': 1, 'effects': {'power': 'on'}}]}
    _, _, slots, stats = core.build_model(payload)
    assert len(slots) == 4
    assert stats['occurrence_pruning']['retained_activities']['on']['reason'] == 'state_removal_or_transition'


def test_pruning_keeps_frozen_calendar_and_night_windows(core):
    from tests.unit.test_night_lifts import fixture
    from app.services.planner_calendars import calendar_intervals, lift_day_windows
    payload = fixture(calendar=True)
    payload['activities'][0]['max_instances'] = None
    payload['working_intervals'] = calendar_intervals(payload)
    payload['lift_day_windows'] = lift_day_windows(payload, payload['working_intervals'])
    saved = copy.deepcopy(payload)
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].validator_status == 'VALID'
    assert result.stats['model']['optional_occurrence_slots'] == 1
    assert result.stats['model']['occurrence_pruning']['applied']
    assert payload == saved


@pytest.mark.parametrize('mode', ['parallel', 'serial'])
@pytest.mark.parametrize('removal', ['transition', 'delete'])
@pytest.mark.parametrize('calendar', [False, True])
def test_mixed_scene_prunes_proven_repeats_but_preserves_recovery(core, payload, monkeypatch, mode, removal, calendar):
    payload.update(execution_mode=mode, initial_state_ids=['ready', 'permit'],
                   goal_state_ids=['token', 'done:finalize', 'done:audit'],
                   forbidden_state_ids=['permit'], max_steps=8)
    payload['activities'] = [
        activity('prepare', 1, required=['ready'], limit=None),
        activity('restore', 1, required=['done:prepare'], outputs=['token'], limit=None),
        activity('use', 1, transition=['token']) if removal == 'transition' else
        activity('use', 1, required=['done:restore'], delete=['token']),
        activity('finalize', 1, required=['token', 'done:use'], limit=None),
        activity('audit', 1, transition=['permit'], limit=None),
    ]
    payload['resources'] = [{'id': 'crew', 'capacity': 1}]
    for a in payload['activities']:
        a['resource_reqs'] = {'crew': 1}
    if calendar:
        from tests.unit.test_work_calendars import scenario
        reference = scenario(anchor='2026-11-02T11:58:00+08:00')
        for key in ('work_calendar_id', 'work_calendars', 'calendar_context'):
            payload[key] = reference[key]
    saved = copy.deepcopy(payload)
    reduced = solve(core, payload, seconds=5)
    assert reduced.status == 'OPTIMAL', reduced
    p = reduced.paths[0]
    assert p.validator_status == 'VALID' and len(p.executions) == 6
    assert p.metrics.makespan == (66 if calendar else 6)
    assert [e.activity_id for e in p.executions].count('restore') == 2
    pruning = reduced.stats['model']['occurrence_pruning']
    assert pruning['input_slots'] == 33 and pruning['effective_slots'] == 12
    assert set(pruning['activity_limits']) == {'prepare', 'finalize', 'audit'}
    assert pruning['activity_proofs']['audit'] == {'reason': 'nonrenewable_transition', 'state_ids': ['permit']}
    assert pruning['activity_proofs']['finalize']['reason'] == 'persistent_outputs'
    assert pruning['retained_activities']['restore'] == {'reason': 'output_can_be_removed', 'state_ids': ['token']}
    assert payload == saved
    original_policy = core._occurrence_limits

    def unpruned(scenario, **kwargs):
        _, stats = original_policy(scenario)
        return {a.id: min(scenario.max_steps, a.max_instances or scenario.max_steps)
                for a in scenario.activities}, stats

    monkeypatch.setattr(core, '_occurrence_limits', unpruned)
    baseline = solve(core, payload, seconds=5)
    assert baseline.status == 'OPTIMAL', baseline
    b = baseline.paths[0]
    assert b.validator_status == 'VALID'
    assert (p.metrics.makespan, len(p.executions)) == (b.metrics.makespan, len(b.executions))


def test_renewable_transition_is_not_treated_as_single_use(core, payload):
    payload.update(initial_state_ids=['permit'], goal_state_ids=['done:consume'], max_steps=4)
    payload['activities'] = [activity('consume', 1, transition=['permit'], limit=None),
                             activity('reissue', 1, outputs=['permit'], limit=None),
                             activity('durable', 1, limit=None)]
    _, _, slots, stats = core.build_model(payload)
    pruning = stats['occurrence_pruning']
    assert len(slots) == 8
    assert set(pruning['activity_limits']) == {'durable'}
    assert set(pruning['retained_activities']) == {'consume', 'reissue'}


def test_persistent_output_alone_does_not_prove_destructive_activity_redundant(core, payload):
    payload.update(initial_state_ids=['dirty'], goal_state_ids=['done:work'],
                   forbidden_state_ids=['dirty'], max_steps=3)
    payload['activities'] = [activity('clean', 1, delete=['dirty'], limit=None),
                             activity('work', 1, required=['done:clean'], outputs=['dirty'])]
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].validator_status == 'VALID'
    assert [e.activity_id for e in result.paths[0].executions].count('clean') == 2
    assert result.stats['model']['occurrence_pruning']['retained_activities']['clean']['reason'] == 'state_removal_or_transition'


def test_legacy_overwrite_protects_other_activities_outputs(core):
    payload = {'schema_version': 1, 'id': 'legacy-mixed-pruning', 'execution_mode': 'parallel', 'max_steps': 4,
               'initial_facts': {'power': 'off'}, 'goal': {'required': {'power': 'on'}},
               'activities': [{'id': 'on', 'duration': 1, 'preconditions': {'power': 'off'}, 'effects': {'power': 'on'}},
                              {'id': 'native', 'duration': 1, 'preconditions': [], 'is_milestone': True,
                               'output_state_id': 'fact:power=off'},
                              {'id': 'durable', 'duration': 1, 'effects': {'receipt': 'issued'}}]}
    _, _, slots, stats = core.build_model(payload)
    pruning = stats['occurrence_pruning']
    assert len(slots) == 8 and set(pruning['activity_limits']) == {'durable'}
    assert pruning['retained_activities']['native']['reason'] == 'output_can_be_removed'

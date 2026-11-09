import copy

import pytest

from app.services.planner_engine_bridge import _planner_modules, run_engine
from app.services.planner_scenarios import new_scenario, create_activity, rebuild_mirror, normalize_import
from app.services.planner_rules import exclusive_activity_ids, validate_exclusive_rules
from app.services.planner_excel import export_workbook, import_workbook


def fixture(crane=False, commissioning=False):
    s = new_scenario('独占验收')
    s.update(execution_mode='parallel', max_steps=4,
             exclusive_rules={'crane': crane, 'commissioning': commissioning})
    s['resources'] = [{'id': 'crane', 'name': '行吊', 'kind': 'crane', 'capacity': 2}]
    for i in range(4):
        a = create_activity(s, {'name': f'任务{i}', 'duration': 10, 'max_instances': 1,
            'resource_reqs': {'crane': 1} if i == 0 else {},
            'metadata': {'activity_type': '功能调测' if i == 1 else '机械集成'}}, display_number=i+1)
        s['goal_state_ids'].append(a['output_state_id'])
    rebuild_mirror(s)
    return s


def solve(s):
    return run_engine(s, engine='JOINT_CP_SAT', run_id='exclusive-test', seed=11,
                      budget_override={'time_limit_seconds': 5})


@pytest.mark.parametrize('crane,commissioning,expected', [(False, False, 10), (True, False, 20), (False, True, 20), (True, True, 30)])
def test_global_exclusivity_keeps_ordinary_concurrency(crane, commissioning, expected):
    s = fixture(crane, commissioning)
    r = solve(s)
    assert r['status'] == 'OPTIMAL', r
    p = r['paths'][0]
    assert p['validator_status'] == 'VALID'
    assert p['metrics']['makespan'] == r['lower_bound'] == expected
    exclusive = exclusive_activity_ids(s)
    rows = p['executions']
    for a in rows:
        for b in rows:
            if a is not b and a['activity_id'] in exclusive:
                assert a['end_time'] <= b['start_time'] or b['end_time'] <= a['start_time']
    # Two ordinary jobs must still overlap in the proven optimum.
    ordinary = [e for e in rows if e['activity_id'] in {a['id'] for a in s['activities'][2:]}]
    assert ordinary[0]['start_time'] == ordinary[1]['start_time']


@pytest.mark.parametrize('exclusive_first', [True, False])
@pytest.mark.parametrize('kind', ['crane', 'commissioning'])
def test_independent_simulator_rejects_overlap_in_both_start_orders(exclusive_first, kind):
    _planner_modules()
    from app.core.joint_cpsat import prepare_payload
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.simulator import PathSimulator
    from planner_experiment.models import Action
    s = fixture(**{kind: True})
    # Stable ID order prevents the canonical same-time ordering from masking
    # the actual exclusivity rejection under test.
    first = 0 if kind == 'crane' else 1
    s['activities'][first]['id'] = 'a' if exclusive_first else 'b'
    s['activities'][2]['id'] = 'b' if exclusive_first else 'a'
    sim = PathSimulator(scenario_from_dict(prepare_payload(s)))
    state = sim.transition(sim.initial_state(), Action('START', activity_id='a'))
    assert Action('START', activity_id='b') not in sim.enabled_actions(state)
    with pytest.raises(ValueError):
        sim.transition(state, Action('START', activity_id='b'))


def test_rules_use_structured_fields_and_both_rules_do_not_double_count():
    s = fixture(True, True)
    s['activities'][0]['metadata']['activity_type'] = '功能调测'
    s['activities'][1]['metadata'] = {}
    s['activities'][1]['name'] = '行吊调测（名称不推断约束）'
    s['activities'][1]['resource_reqs'] = {'crane': 0}
    assert exclusive_activity_ids(s) == {s['activities'][0]['id']}
    s['activities'][1]['resource_reqs'] = {}  # Stored resource requirements must be positive.
    assert solve(s)['paths'][0]['metrics']['makespan'] == 20


def test_optional_exclusive_activity_does_not_block_other_jobs():
    s = fixture(True, True)
    s['goal_state_ids'] = [a['output_state_id'] for a in s['activities'][2:]]
    r = solve(s)
    assert r['status'] == 'OPTIMAL' and r['paths'][0]['metrics']['makespan'] == 10
    assert len(r['paths'][0]['executions']) == 2


def test_daylight_wait_does_not_hold_exclusivity_and_lunch_pause_is_respected():
    s = fixture(True, False)
    s['activities'][0]['duration'] = 120
    s['activities'][0]['metadata']['precision_fragile'] = True
    s['night_lift_rule'] = {'enabled': True, 'night_start': '20:00', 'night_end': '08:00'}
    s['calendar_context'] = {'start_at': '2026-11-04T19:00:00+08:00', 'timezone': 'Asia/Shanghai'}
    r = solve(s)
    assert r['status'] == 'OPTIMAL' and r['paths'][0]['metrics']['makespan'] == 900
    rows = r['paths'][0]['executions']
    assert all(e['start_time'] == 0 for e in rows if e['activity_id'] != s['activities'][0]['id'])
    s['calendar_context']['start_at'] = '2026-11-04T11:00:00+08:00'
    s['work_calendar_id'] = 'c'
    s['work_calendars'] = [{'id': 'c', 'name': '午休', 'weekdays': list(range(7)),
        'periods': [{'start': '08:00', 'end': '12:00'}, {'start': '13:00', 'end': '17:00'}]}]
    r = solve(s)
    assert r['status'] == 'OPTIMAL' and r['paths'][0]['metrics']['makespan'] == 190
    assert r['paths'][0]['validator_status'] == 'VALID'


def test_impossible_windows_cannot_bypass_exclusivity():
    s = fixture(True)
    s['time_windows'] = [{'id': f'w{i}', 'activity_id': a['id'], 'earliest_start': 0, 'latest_finish': 10}
                         for i, a in enumerate(s['activities'])]
    assert solve(s)['status'] == 'INFEASIBLE'


def test_repeated_exclusive_activity_and_zero_step_goal():
    s = fixture(True)
    a, b = s['activities'][:2]
    a['max_instances'] = 2
    b['preconditions'] = [{'state_id': a['output_state_id'], 'relation_role': 'transition'}]
    s['goal_state_ids'] = [a['output_state_id'], b['output_state_id']]
    rebuild_mirror(s)
    r = solve(s)
    assert r['status'] == 'OPTIMAL' and r['paths'][0]['metrics']['makespan'] == 30
    assert sum(e['activity_id'] == a['id'] for e in r['paths'][0]['executions']) == 2
    s['initial_state_ids'] = s['goal_state_ids'][:]
    assert solve(s)['paths'][0]['metrics']['makespan'] == 0


@pytest.mark.parametrize('bad', [True, [], {'crane': True}, {'crane': 1, 'commissioning': False},
                               {'crane': False, 'commissioning': 'false'}, {'crane': False, 'commissioning': False, 'extra': True}])
def test_invalid_rules_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_exclusive_rules({'exclusive_rules': bad})


def test_roundtrip_and_legacy_rejection():
    s = fixture(True, True)
    for restored in [normalize_import(s, preserve_ids=False), import_workbook(export_workbook(s))]:
        assert restored['exclusive_rules'] == s['exclusive_rules']
        assert len(exclusive_activity_ids(restored)) == 2
        assert solve(restored)['paths'][0]['metrics']['makespan'] == 30
    for engine in ['ASTAR', 'GA', 'LEGACY']:
        with pytest.raises(ValueError, match='独占'):
            run_engine(s, engine=engine, run_id='unsupported', seed=11)


def test_no_mutation_or_implicit_derived_flag():
    _planner_modules()
    from app.core.joint_cpsat import prepare_payload
    from planner_experiment.scenario import scenario_from_dict, scenario_to_dict
    s = fixture()
    s['activities'][0]['exclusive_execution'] = True
    saved = copy.deepcopy(s)
    prepared = prepare_payload(s)
    assert s == saved
    assert not any(a.get('exclusive_execution') for a in prepared['activities'])
    encoded = scenario_to_dict(scenario_from_dict(prepared))
    assert all('exclusive_execution' not in a for a in encoded['activities'])

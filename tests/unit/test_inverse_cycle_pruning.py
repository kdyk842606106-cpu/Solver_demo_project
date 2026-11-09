"""Private inverse-cycle deletion: proofs, counterexamples and time semantics."""
import copy
from collections import Counter

import pytest

from tests.unit.test_joint_cpsat import activity, core, setup_db, solve
from tests.unit.test_joint_pruning import assert_matches_unpruned


def pair_case():
    forward = activity('a', 2, transition=['s0'], limit=3, resources={'crew': 1})
    reset = activity('b', 1, transition=['s1'], limit=3, resources={'crew': 1})
    forward['output_state_id'], reset['output_state_id'] = 's1', 's0'
    finish = activity('finish', 3, required=['s1'], limit=3, resources={'crew': 1})
    return {'schema_version': 2, 'id': 'private-cycle', 'execution_mode': 'parallel',
            'max_steps': 9, 'initial_state_ids': ['s0'], 'goal_state_ids': ['done:finish'],
            'activities': [forward, reset, finish], 'resources': [{'id': 'crew', 'capacity': 1}]}


def limits(core, payload):
    from planner_experiment.scenario import scenario_from_dict
    return core._occurrence_limits(scenario_from_dict(core.prepare_payload(payload)))


def test_private_cycle_needs_no_business_labels(core, monkeypatch):
    payload = pair_case()
    before = copy.deepcopy(payload)
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == 5
    assert [e.activity_id for e in result.paths[0].executions] == ['a', 'finish']
    caps, stats = limits(core, payload)
    assert caps == {'a': 1, 'b': 0, 'finish': 1}
    assert stats['activity_proofs']['b']['reason'] == 'unnecessary_inverse_reset'
    assert stats['scope_analysis']['inverse_cycle_proofs'][0]['certificate_verified']
    assert payload == before
    assert_matches_unpruned(core, payload, monkeypatch, result)


@pytest.mark.parametrize('change', ['repair_reader', 'extra_output', 'extra_delete',
                                  'external_writer', 'initially_installed', 'both_initial',
                                  'final_uninstalled', 'forbid_installed'])
def test_counterexamples_do_not_apply_private_cycle_proof(core, monkeypatch, change):
    payload = pair_case()
    if change == 'repair_reader':
        extra = activity('inspect', 1, required=['s1'])
        repair = activity('repair', 1, required=['s0', 'done:inspect'])
        payload['activities'].extend([extra, repair])
        payload['goal_state_ids'].extend(['done:repair', 's1'])
    elif change == 'extra_output':
        payload['activities'][1]['additional_output_state_ids'] = ['repaired']
        payload['goal_state_ids'].extend(['repaired', 's1'])
    elif change == 'extra_delete':
        payload['initial_state_ids'].append('dirty')
        payload['activities'][1]['delete_effect_state_ids'] = ['dirty']
        payload['forbidden_state_ids'] = ['dirty']
        payload['goal_state_ids'].append('s1')
    elif change == 'external_writer':
        payload['activities'].append(activity('damage', 1, transition=['s1'], outputs=['s0']))
        payload['goal_state_ids'].extend(['done:damage', 's1'])
    elif change == 'initially_installed':
        payload['initial_state_ids'] = ['s1']
        payload['goal_state_ids'].append('s0')
    elif change == 'both_initial':
        payload['initial_state_ids'].append('s1')
        payload['goal_state_ids'].append('s0')
    elif change == 'final_uninstalled':
        payload['goal_state_ids'].append('s0')
    else:
        payload['forbidden_state_ids'] = ['s1']
    caps, stats = limits(core, payload)
    assert not stats['scope_analysis']['inverse_cycle_proofs']
    assert caps['b'] == 3
    result = solve(core, payload)
    assert result.status == 'OPTIMAL', result
    assert_matches_unpruned(core, payload, monkeypatch, result)
    if change in ('repair_reader', 'extra_output', 'extra_delete'):
        counts = Counter(e.activity_id for e in result.paths[0].executions)
        assert counts['a'] >= 2 and counts['b'] >= 1


def test_state_events_fall_back(core):
    from planner_experiment.scenario import scenario_from_dict
    payload = pair_case()
    payload['external_events'] = [{'id': 'damage', 'time': 10, 'remove_state_ids': ['s1']}]
    caps, stats = core._occurrence_limits(scenario_from_dict(payload))
    assert all(value == 3 for value in caps.values())
    assert stats['scope_analysis']['status'] == 'unsupported_state_events'


def test_mixed_scope_prunes_only_optional_pair(core, monkeypatch):
    payload = pair_case()
    second = copy.deepcopy(pair_case())
    for a in second['activities']:
        a['id'] = 'second:' + a['id']
        a['output_state_id'] = 'second:' + a['output_state_id']
        for precondition in a['preconditions']:
            precondition['state_id'] = 'second:' + precondition['state_id']
    # The second inverse produces a repair certificate, so restoration must survive.
    second['activities'][1]['additional_output_state_ids'] = ['repair_certificate']
    repair = activity('repair', 1, required=['second:s0', 'repair_certificate'])
    payload['activities'].extend([*second['activities'], repair])
    payload['initial_state_ids'].append('second:s0')
    payload['goal_state_ids'].extend(['second:done:finish', 'done:repair', 'second:s1'])
    payload['max_steps'] = 12
    caps, stats = limits(core, payload)
    assert caps['a'] == 1 and caps['b'] == 0
    assert caps['second:a'] == caps['second:b'] == 3
    assert len(stats['scope_analysis']['inverse_cycle_proofs']) == 1
    result = solve(core, payload)
    assert result.status == 'OPTIMAL'
    counts = Counter(e.activity_id for e in result.paths[0].executions)
    assert counts['a'] == 1 and counts['b'] == 0
    assert counts['second:a'] == 2 and counts['second:b'] == 1
    assert_matches_unpruned(core, payload, monkeypatch, result)


@pytest.mark.parametrize('fault', ['reject', 'timeout', 'forged'])
def test_failed_certificate_never_changes_scope(core, monkeypatch, fault):
    from app.core import joint_pruning
    if fault == 'reject':
        monkeypatch.setattr(joint_pruning, '_verify_inverse_cycle', lambda *args: False)
    elif fault == 'timeout':
        def timeout(*args):
            raise joint_pruning._AnalysisTimeout()
        monkeypatch.setattr(joint_pruning, '_verify_inverse_cycle', timeout)
    else:
        monkeypatch.setattr(joint_pruning, '_inverse_cycle_candidates', lambda *args: [{
            'forward_activity_id': 'a', 'reset_activity_id': 'finish',
            'initial_state_id': 's0', 'persistent_state_id': 's1'}])
    caps, stats = limits(core, pair_case())
    assert caps['a'] == caps['b'] == 3
    assert not stats['scope_analysis']['inverse_cycle_proofs']
    assert stats['scope_analysis']['status'] == ('time_slice_exhausted' if fault == 'timeout' else 'certificate_rejected')


@pytest.mark.parametrize('window', ['first', 'project', 'material', 'calendar', 'exclusive', 'night'])
def test_deletion_preserves_time_and_resource_constraints(core, monkeypatch, window):
    payload = pair_case()
    expected = 5
    if window == 'first':
        payload['run_time_windows'] = [{'id': 'w', 'activity_id': 'a', 'earliest_start': 5, 'latest_finish': 7}]
        expected = 10
    elif window == 'project':
        payload['time_windows'] = [{'id': 'w', 'activity_id': 'a', 'earliest_start': 5, 'latest_finish': 7}]
        expected = 10
    elif window == 'material':
        payload['external_events'] = [{'id': 'arrival', 'time': 5}]
        payload['activities'][0]['event_reqs'] = ['arrival']
        expected = 10
    elif window == 'calendar':
        from tests.unit.test_work_calendars import scenario
        reference = scenario(anchor='2026-11-02T11:59:00+08:00')
        for key in ('work_calendar_id', 'work_calendars', 'calendar_context'):
            payload[key] = reference[key]
        expected = 65
    elif window == 'exclusive':
        payload['resources'].append({'id': 'crane', 'capacity': 1, 'kind': 'crane'})
        payload['activities'][0]['resource_reqs']['crane'] = 1
        payload['exclusive_rules'] = {'crane': True, 'commissioning': False}
    else:
        payload['resources'].append({'id': 'crane', 'capacity': 1, 'kind': 'crane'})
        payload['activities'][0].update(resource_reqs={'crane': 1}, metadata={'precision_fragile': True})
        payload['calendar_context'] = {'start_at': '2026-11-02T19:59:00+08:00', 'timezone': 'Asia/Shanghai'}
        payload['night_lift_rule'] = {'enabled': True, 'night_start': '20:00', 'night_end': '08:00'}
        expected = 726  # 721 elapsed minutes until 08:00, then 2 + 3 minutes.
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == expected, result
    assert limits(core, payload)[0]['b'] == 0
    assert_matches_unpruned(core, payload, monkeypatch, result)


def test_pruning_never_relaxes_first_window(core, monkeypatch):
    payload = pair_case()
    payload['run_time_windows'] = [{'id': 'w', 'activity_id': 'a', 'latest_finish': 1}]
    result = solve(core, payload)
    assert result.status == 'INFEASIBLE'
    with monkeypatch.context() as patch:
        patch.setattr(core, '_occurrence_limits', lambda scenario, **kwargs:
                      ({a.id: 3 for a in scenario.activities}, {'policy': 'unpruned_test'}))
        assert solve(core, payload).status == 'INFEASIBLE'


@pytest.mark.parametrize('initial', [('s0',), ('s1',), ('s0', 's1'), ()])
@pytest.mark.parametrize('goals,forbidden', [(['done:finish'], []), (['done:finish', 's0'], []),
                                          (['done:finish', 's1'], []), (['done:finish'], ['s1'])])
def test_small_state_exhaustion_preserves_optimum(core, initial, goals, forbidden):
    from planner_experiment.scenario import scenario_from_dict
    payload = pair_case()
    payload.update(initial_state_ids=list(initial), goal_state_ids=goals, forbidden_state_ids=forbidden,
                   execution_mode='serial', max_steps=6)
    parsed = scenario_from_dict(payload)
    capped, _ = core._occurrence_limits(parsed)

    def enumerate_best(caps):
        stack = [(set(initial), (), 0)]
        best = None
        while stack:
            state, path, elapsed = stack.pop()
            if set(goals) <= state and not set(forbidden) & state:
                score = (elapsed, len(path))
                best = score if best is None else min(best, score)
            if len(path) >= 6:
                continue
            for a in parsed.activities:
                if path.count(a.id) < caps[a.id] and set(a.precondition_state_ids) <= state:
                    stack.append(((state-set(a.removed_state_ids)) | set(a.output_state_ids),
                                  (*path, a.id), elapsed+a.duration))
        return best

    expected = enumerate_best({a.id: 3 for a in parsed.activities})
    assert enumerate_best(capped) == expected
    result = solve(core, payload)
    if expected is None:
        assert result.status == 'INFEASIBLE'
    else:
        assert result.status == 'OPTIMAL'
        assert (result.paths[0].metrics.makespan, len(result.paths[0].executions)) == expected

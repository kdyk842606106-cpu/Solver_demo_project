import copy
import random
import time

import pytest

from tests.unit.test_joint_cpsat import activity, core, setup_db, solve


def assembly(initial_installed, repair_goal):
    activities = [activity('install', 1, required=['ready'], limit=3),
                  activity('dismantle', 1, transition=['installed'], delete=['tested'], limit=3),
                  activity('repair', 1, required=['dismantled'], limit=3),
                  activity('test', 1, required=['installed'], limit=3)]
    for a, output in zip(activities, ['installed', 'dismantled', 'repaired', 'tested']):
        a['output_state_id'] = output
        a['resource_reqs'] = {'crew': 1}
    return {'schema_version': 2, 'id': 'dynamic-assembly', 'execution_mode': 'parallel', 'max_steps': 6,
            'initial_state_ids': ['ready', *(['installed'] if initial_installed else [])],
            'goal_state_ids': ['tested', *(['repaired', 'installed'] if repair_goal else [])],
            'activities': activities, 'resources': [{'id': 'crew', 'capacity': 1}]}


def assert_matches_unpruned(core, payload, monkeypatch, result):
    def unpruned(scenario, **kwargs):
        return {a.id: min(scenario.max_steps, a.max_instances or scenario.max_steps)
                for a in scenario.activities}, {'policy': 'test_unpruned'}
    with monkeypatch.context() as patch:
        patch.setattr(core, '_occurrence_limits', unpruned)
        baseline = solve(core, payload, seconds=5)
    assert result.status == baseline.status
    assert result.status in ('OPTIMAL', 'INFEASIBLE')
    assert [(p.metrics.makespan, len(p.executions), p.validator_status) for p in result.paths] == [
        (p.metrics.makespan, len(p.executions), p.validator_status) for p in baseline.paths]


@pytest.mark.parametrize('initial_installed,repair_goal,install_count,makespan', [
    (True, False, 0, 1), (False, False, 1, 2), (True, True, 1, 4), (False, True, 2, 5),
])
def test_same_library_changes_scope_with_current_and_target(core, monkeypatch, initial_installed,
                                                           repair_goal, install_count, makespan):
    payload = assembly(initial_installed, repair_goal)
    saved = copy.deepcopy(payload)
    result = solve(core, payload)
    assert result.status == 'OPTIMAL', result
    path = result.paths[0]
    assert path.validator_status == 'VALID' and path.metrics.makespan == makespan
    assert sum(e.activity_id == 'install' for e in path.executions) == install_count
    pruning = result.stats['model']['occurrence_pruning']
    assert all(r['certificate_verified'] for r in pruning['scope_analysis']['rounds'])
    if not repair_goal:
        excluded = pruning['scope_analysis']['excluded_activities']
        assert {'dismantle', 'repair'} <= excluded.keys()
        assert pruning['activity_limits']['install']['effective_limit'] == (0 if initial_installed else 1)
        if initial_installed:
            assert excluded['install']['round'] > excluded['dismantle']['round']
    else:
        assert 'install' not in pruning['activity_limits']
    assert payload == saved
    assert_matches_unpruned(core, payload, monkeypatch, result)


def test_already_satisfied_targets_create_no_instances(core, monkeypatch):
    payload = assembly(True, False)
    payload['initial_state_ids'].append('tested')
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == 0
    assert result.stats['model']['optional_occurrence_slots'] == 0
    assert_matches_unpruned(core, payload, monkeypatch, result)


def test_unreachable_destroyer_does_not_force_repeat_slots(core, monkeypatch):
    payload = assembly(False, False)
    payload['activities'][1]['preconditions'].append({'state_id': 'repaired', 'relation_role': 'required'})
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == 2
    excluded = result.stats['model']['occurrence_pruning']['scope_analysis']['excluded_activities']
    assert excluded['dismantle']['reason'] == excluded['repair']['reason'] == 'unreachable_preconditions'
    assert_matches_unpruned(core, payload, monkeypatch, result)


def test_negative_goal_cleanup_and_all_alternative_producers_survive(core, monkeypatch):
    payload = {'schema_version': 2, 'id': 'alternatives', 'execution_mode': 'parallel', 'max_steps': 4,
               'initial_state_ids': ['ready'], 'goal_state_ids': ['done'], 'forbidden_state_ids': ['dirty'],
               'activities': [activity('fast', 1, outputs=['done', 'dirty'], limit=3),
                              activity('slow', 5, outputs=['done'], limit=3),
                              activity('cleanup', 1, required=['done:fast'], delete=['dirty'], limit=3)]}
    result = solve(core, payload)
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == 2
    assert set(result.stats['model']['occurrence_pruning']['scope_analysis']['excluded_activities']) == set()
    assert_matches_unpruned(core, payload, monkeypatch, result)


@pytest.mark.parametrize('fault', ['reject', 'timeout'])
def test_deadline_or_rejected_certificate_keeps_last_safe_scope(core, monkeypatch, fault):
    from app.core import joint_pruning
    from planner_experiment.scenario import scenario_from_dict
    parsed = scenario_from_dict(assembly(True, False))
    active, stats = joint_pruning.analyze_run_scope(parsed, deadline=time.perf_counter() - 1)
    assert active == {'install', 'dismantle', 'repair', 'test'}
    assert stats['status'] == 'time_slice_exhausted' and not stats['excluded_activities']
    verify = joint_pruning._verify_round
    calls = []

    def reject_second(*args):
        calls.append(1)
        if len(calls) > 1 and fault == 'timeout':
            raise joint_pruning._AnalysisTimeout()
        return verify(*args) if len(calls) == 1 else False

    monkeypatch.setattr(joint_pruning, '_verify_round', reject_second)
    active, stats = joint_pruning.analyze_run_scope(parsed)
    assert stats['status'] == ('certificate_rejected' if fault == 'reject' else 'time_slice_exhausted')
    assert active == {'install', 'test'}
    assert set(stats['excluded_activities']) == {'dismantle', 'repair'}


def test_checker_rejects_missing_producer_in_backward_closure(core, monkeypatch):
    from app.core import joint_pruning
    from planner_experiment.scenario import scenario_from_dict
    parsed = scenario_from_dict(assembly(False, False))
    monkeypatch.setattr(joint_pruning, '_relevant', lambda *args: {'test'})
    active, stats = joint_pruning.analyze_run_scope(parsed)
    assert stats['status'] == 'certificate_rejected'
    assert active == {a.id for a in parsed.activities}
    assert stats['excluded_activities'] == {}


@pytest.mark.parametrize('seed', range(32))
def test_exhaustive_small_state_plans_preserve_serial_optimum(core, seed):
    """Independent bounded state enumeration, not a second copy of the slicer."""
    from planner_experiment.scenario import scenario_from_dict
    rng = random.Random(seed)
    facts = ['s0', 's1', 's2', 's3']
    activities = []
    for index, fact in enumerate(facts):
        others = [s for s in facts if s != fact]
        required = rng.sample(others, rng.randrange(3))
        transition = required[:1] if rng.choice([True, False]) else []
        deletes = [s for s in others if s not in required and rng.random() < .3]
        a = activity('a' + str(index), rng.randint(1, 3), required=[s for s in required if s not in transition],
                     transition=transition, delete=deletes, limit=None)
        a['output_state_id'] = fact
        activities.append(a)
    goals = set(rng.sample(facts, rng.randint(1, 2)))
    payload = {'schema_version': 2, 'id': 'exhaustive', 'execution_mode': 'serial', 'max_steps': 4,
               'initial_state_ids': [s for s in facts if rng.random() < .5], 'goal_state_ids': sorted(goals),
               'forbidden_state_ids': [s for s in facts if s not in goals and rng.random() < .4],
               'activities': activities}
    scenario = scenario_from_dict(payload)
    limits, _ = core._occurrence_limits(scenario)

    def best(allowed):
        result = None
        stack = [(set(scenario.initial_state_ids), (), 0)]
        while stack:
            state, sequence, elapsed = stack.pop()
            if goals <= state and not set(scenario.forbidden_state_ids) & state:
                score = (elapsed, len(sequence))
                result = score if result is None else min(result, score)
            if len(sequence) == scenario.max_steps:
                continue
            for a in scenario.activities:
                if sequence.count(a.id) < allowed[a.id] and set(a.precondition_state_ids) <= state:
                    stack.append(((state - set(a.removed_state_ids)) | set(a.output_state_ids),
                                  (*sequence, a.id), elapsed + a.duration))
        return result

    expected = best(limits)
    assert expected == best({a.id: scenario.max_steps for a in scenario.activities})
    # Also validate the causal encoding against independent state enumeration,
    # including initial facts, positive/negative goals and renewable cycles.
    result = solve(core, payload)
    if expected is None:
        assert result.status == 'INFEASIBLE', result
    else:
        assert result.status == 'OPTIMAL', result
        candidate = result.paths[0]
        assert candidate.validator_status == 'VALID'
        assert (candidate.metrics.makespan, len(candidate.executions)) == expected

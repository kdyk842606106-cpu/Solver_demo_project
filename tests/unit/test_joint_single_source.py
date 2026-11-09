"""Projection equivalence, including absent consumers and real repeat recovery."""
import copy
from collections import Counter
import pytest
from tests.unit.test_joint_cpsat import activity, core, setup_db, solve


def case_payload(case):
    p = dict(schema_version=2, id='singleton-projection', execution_mode='parallel',
             max_steps=3, initial_state_ids=['ready'], goal_state_ids=['done:use'],
             forbidden_state_ids=[], resources=[], external_events=[])
    if case == 'initial_threat':
        p['activities'] = [activity('use', 1, required=['ready']),
                           activity('destroy', 1, delete=['ready'])]
        p['goal_state_ids'].append('done:destroy')
    elif case == 'producer_threat':
        p['activities'] = [activity('make', 1, outputs=['fact']),
            activity('use', 1, required=['fact']), activity('destroy', 1, delete=['fact'])]
        p['goal_state_ids'].append('done:destroy')
    elif case == 'absent_consumer':
        p['activities'] = [activity('make', 1, outputs=['fact']),
            activity('use', 1, required=['fact']), activity('alternative', 1, outputs=['done:use'])]
    elif case == 'initial_plus_producer':
        p['initial_state_ids'] = ['fact']
        p['activities'] = [activity('make', 1, outputs=['fact']),
            activity('use', 1, required=['fact']), activity('destroy', 1, delete=['fact'])]
    elif case == 'negative_goal':
        p['activities'] = [activity('use', 1, transition=['ready'])]
        p['forbidden_state_ids'] = ['ready']
    elif case == 'missing_optional':
        p['activities'] = [activity('bad', 1, required=['missing']), activity('use', 1)]
    else:
        raise AssertionError(case)
    return p


@pytest.mark.parametrize('encoding', ['none', 'early', 'appended'])
@pytest.mark.parametrize('case', ['initial_threat', 'producer_threat', 'absent_consumer',
                                 'initial_plus_producer', 'negative_goal', 'missing_optional'])
def test_all_timed_schedules_are_preserved(core, monkeypatch, case, encoding):
    p = case_payload(case)
    # Retain even redundant/irrelevant instances so the projection test covers
    # absence, optional producers and destructive paths independently of pruning.
    monkeypatch.setattr(core, '_occurrence_limits', lambda scene, **kw:
        ({a.id: a.max_instances for a in scene.activities}, {}))
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', encoding)
    sets = []
    for direct in (False, True):
        monkeypatch.setattr(core, '_SINGLE_SOURCE_DIRECT', direct)
        model, _, slots, _, finish = core._build_model_with_finish(p, deadline=None)
        model.clear_objective()
        found = set()
        class Collector(core.cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                found.add((self.value(finish), tuple((s.aid, s.ordinal, self.value(s.present),
                    self.value(s.start), self.value(s.end)) for s in slots)))
        solver = core.cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.max_time_in_seconds = 10
        assert solver.solve(model, Collector()) == core.cp_model.OPTIMAL
        sets.append(found)
    assert sets[0] == sets[1] and sets[0]


def recovery_case():
    return dict(schema_version=2, id='three-install-recovery', execution_mode='parallel', max_steps=5,
        initial_state_ids=['off'], goal_state_ids=['installed', 'done:remove2'], forbidden_state_ids=['off'],
        activities=[activity('install', 1, transition=['off'], outputs=['installed'], limit=3),
            activity('remove1', 1, transition=['installed'], outputs=['off']),
            activity('remove2', 1, required=['done:remove1'], transition=['installed'], outputs=['off'])])


@pytest.mark.parametrize('ranks', [False, True])
def test_third_install_and_second_removal_are_retained(core, monkeypatch, ranks):
    p = recovery_case(); saved = copy.deepcopy(p)
    monkeypatch.setattr(core, '_CAUSAL_RANKS', ranks)
    models = []
    for direct in (False, True):
        monkeypatch.setattr(core, '_SINGLE_SOURCE_DIRECT', direct)
        result = solve(core, p, seconds=10)
        assert result.status == 'OPTIMAL', result
        path = result.paths[0]
        assert path.validator_status == 'VALID' and path.metrics.makespan == 5
        assert Counter(e.activity_id for e in path.executions) == {'install': 3, 'remove1': 1, 'remove2': 1}
        assert [(e.activity_id, e.ordinal) for e in path.executions] == [
            ('install', 1), ('remove1', 1), ('install', 2), ('remove2', 1), ('install', 3)]
        models.append(result.stats['model'])
    assert p == saved
    for field in ('input_slots', 'effective_slots', 'activity_limits', 'activity_proofs', 'retained_activities'):
        assert models[0]['occurrence_pruning'][field] == models[1]['occurrence_pruning'][field]
    assert models[0]['support_choices'] == models[1]['support_choices']
    assert models[1]['single_source_direct']['eliminated_variables'] > 0
    assert models[1]['variables'] < models[0]['variables']


def test_insufficient_repeat_limit_stays_infeasible(core, monkeypatch):
    p = recovery_case(); p['activities'][0]['max_instances'] = 2
    for direct in (False, True):
        monkeypatch.setattr(core, '_SINGLE_SOURCE_DIRECT', direct)
        result = solve(core, p, seconds=10)
        assert result.status == 'INFEASIBLE' and not result.paths

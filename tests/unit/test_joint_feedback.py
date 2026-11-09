"""Model-witness safety and actual restart behavior for incumbent feedback."""
import copy
import time
from dataclasses import replace

import pytest

from app.services.planner_engine_bridge import _planner_modules


@pytest.fixture(autouse=True)
def setup_db():
    _planner_modules()


@pytest.fixture
def core():
    from app.core import joint_cpsat
    return joint_cpsat


def case(start=0):
    return dict(schema_version=2, id='feedback', execution_mode='parallel', start_time=start,
                initial_state_ids=['ready'], goal_state_ids=['done:a'], forbidden_state_ids=[],
                resources=[], external_events=[], max_steps=4,
                activities=[dict(id='a', name='a', duration=3, output_state_id='done:a',
                    max_instances=1, preconditions=[dict(state_id='ready', relation_role='required')],
                    resource_reqs={}, event_reqs=[])])


@pytest.mark.parametrize('start', [0, 20])
@pytest.mark.parametrize('initial_goal', [False, True])
def test_certified_cut_preserves_optimum_and_only_hints_assignment(core, start, initial_goal):
    payload = case(start)
    if initial_goal:
        payload['goal_state_ids'] = ['ready']
    saved = copy.deepcopy(payload)
    model, scene, slots, _, finish = core._build_model_with_finish(payload, deadline=None)
    candidate, _ = core.replay_candidate(payload, scene, [dict(activity_id='a', ordinal=1,
        start=start+5, end=start+8)], run_id='test', seed=11)
    original = str(model.proto)
    cert, values = core._certify_feedback(model, finish, slots, scene, candidate,
                                         deadline=time.perf_counter()+3, seed=11)
    assert str(model.proto) == original and payload == saved
    assert values is not None
    core._apply_feedback(model, finish, slots, cert, values, count_phase=False)
    solver = core.cp_model.CpSolver()
    assert solver.solve(model) == core.cp_model.OPTIMAL
    assert solver.value(finish) == start + (0 if initial_goal else 3)
    # All fixed assignments exist only in the clone; original gains one cap.
    assert len(model.proto.solution_hint.vars) == len(model.proto.variables)


def test_failed_witness_and_expired_budget_never_mutate_model(core):
    payload = case()
    model, scene, slots, _, finish = core._build_model_with_finish(payload, deadline=None)
    candidate, _ = core.replay_candidate(payload, scene,
        [dict(activity_id='a', ordinal=1, start=0, end=3)], run_id='test', seed=11)
    impossible = replace(candidate, executions=(replace(candidate.executions[0], end_time=2),))
    original = str(model.proto)
    cert, values = core._certify_feedback(model, finish, slots, scene, impossible,
                                         deadline=time.perf_counter()+3, seed=11)
    assert values is None and cert['status'] == 'INFEASIBLE'
    cert, values = core._certify_feedback(model, finish, slots, scene, candidate,
                                         deadline=time.perf_counter()-1, seed=11)
    assert values is None and cert['status'] == 'BUDGET_EXHAUSTED'
    assert str(model.proto) == original
    solver = core.cp_model.CpSolver()
    assert solver.solve(model) == core.cp_model.OPTIMAL and solver.value(finish) == 3


@pytest.mark.parametrize('kind', ['lunch', 'night', 'power_cycles', 'first_window', 'exclusive'])
def test_feedback_certificate_respects_calendar_restoration_windows_and_resources(core, kind):
    from planner_experiment.models import Budget
    from app.services.planner_scenarios import expand_packages
    if kind == 'lunch':
        from tests.unit.test_work_calendars import scenario
        payload = scenario(120)
    elif kind == 'night':
        from tests.unit.test_night_lifts import fixture
        payload = fixture()
    elif kind in ('power_cycles', 'first_window'):
        from tests.unit.test_material_power_cycles import material_power_case
        payload = material_power_case()
        if kind == 'first_window':
            payload['run_time_windows'] = [dict(id='first', activity_id='power_on', earliest_start=10, latest_finish=15)]
    else:
        from tests.unit.test_exclusive_rules import fixture
        payload = expand_packages(fixture(crane=True, commissioning=True))
    result = core.solve_joint(payload, run_id='certificate', seed=11, budget=Budget(10,1,3))
    assert result.status == 'OPTIMAL', result
    candidate = result.paths[0]
    model, scene, slots, _, finish = core._build_model_with_finish(payload, deadline=None)
    cert, values = core._certify_feedback(model, finish, slots, scene, candidate,
                                         deadline=time.perf_counter()+3, seed=11)
    assert values is not None, cert
    # Simulate the second phase too: caps must not eliminate the optimal
    # restoration cycles, including later executions beyond the first window.
    core._apply_feedback(model, finish, slots, cert, values, count_phase=True)
    model.minimize(sum(x.present for x in slots))
    solver = core.cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3
    assert solver.solve(model) == core.cp_model.OPTIMAL
    assert solver.objective_value == len(candidate.executions)


@pytest.mark.parametrize('reject', [False, 'unknown', 'exception', 'deadline'])
def test_restart_and_failed_certificate_fallback(core, monkeypatch, reject):
    from planner_experiment.models import Budget
    builder = core._build_model_with_finish
    original_solver = core.cp_model.CpSolver
    payload = case()
    payload['resources'] = [dict(id=r, capacity=1) for r in ['ab','bc','ca']]
    payload['activities'] = [dict(copy.deepcopy(payload['activities'][0]), id=aid, name=aid,
        output_state_id='done:'+aid, resource_reqs={r:1 for r in resources})
        for aid,resources in [('a',['ab','ca']),('b',['ab','bc']),('c',['bc','ca'])]]
    payload['goal_state_ids'] = ['done:a','done:b','done:c']

    def hinted(*args, **kwargs):
        model, scene, slots, stats, finish = builder(*args, **kwargs)
        # A real, deliberately delayed feasible incumbent. Presolve disabled
        # below so the callback sees it before the model proves the optimum.
        for i,slot in enumerate(slots):
            model.add_hint(slot.present, 1)
            model.add_hint(slot.start, 5+i*3)
            model.add_hint(slot.end, 8+i*3)
        model.add_hint(finish, 14)
        return model, scene, slots, stats, finish

    class NoPresolve(original_solver):
        def __init__(self):
            super().__init__()
            self.parameters.cp_model_presolve = False
            self.parameters.linearization_level = 0
    monkeypatch.setattr(core, '_build_model_with_finish', hinted)
    monkeypatch.setattr(core.cp_model, 'CpSolver', NoPresolve)
    if reject == 'unknown':
        monkeypatch.setattr(core, '_certify_feedback', lambda *a, **k: ({'status':'UNKNOWN'}, None))
    elif reject == 'exception':
        def broken(*args, **kwargs):
            raise RuntimeError('verification unavailable')
        monkeypatch.setattr(core, '_certify_feedback', broken)
    elif reject == 'deadline':
        def expired(*args, **kwargs):
            time.sleep(.15)
            return {'status':'BUDGET_EXHAUSTED'}, None
        monkeypatch.setattr(core, '_certify_feedback', expired)
    events = []
    result = core.solve_joint(payload, run_id='restart', seed=11, budget=Budget(.1 if reject=='deadline' else 3,1,3),
                             progress_observer=lambda m,p: events.append(m))
    if reject == 'deadline':
        assert result.status == 'TIMEOUT_PARTIAL'
        assert result.paths[0].validator_status == 'VALID' and result.paths[0].metrics.makespan == 9
        assert not result.stats['proven_optimal'] and not result.stats['proven_infeasible']
        assert result.stats['feedback_restarts'] == 0
        return
    assert result.status == 'OPTIMAL' and result.paths[0].metrics.makespan == 9
    assert result.paths[0].validator_status == 'VALID'
    assert result.stats['feedback_certificates']
    assert result.stats['feedback_restarts'] == (0 if reject else 1)
    assert result.stats['search_epochs'] >= 2
    for key in ('branches', 'conflicts'):
        counts = [m[key] for m in events if key in m]
        assert counts == sorted(counts) and counts[-1] == result.stats[key]


@pytest.mark.parametrize('arrival', ['shorter', 'fewer_executions', 'worse'])
def test_inflight_callback_feedback_uses_best_not_trigger_or_last(core, monkeypatch, arrival):
    """Deterministically deliver an already-in-flight callback after stop_search.

    Only the first native response is scripted. Candidates use the real replay;
    certification, cap/hint application and all later searches are real CP-SAT.
    """
    from planner_experiment.models import Budget
    from tests.unit.test_joint_cpsat import activity
    payload = case()
    payload['goal_state_ids'] = ['goal']
    if arrival == 'fewer_executions':
        payload['activities'] = [activity('setup', 2),
            activity('chain', 3, required=['done:setup'], outputs=['goal']),
            activity('direct', 5, outputs=['goal'])]
        schedules = [({'setup': (7, 9), 'chain': (9, 12)}, 12), ({'direct': (0, 5)}, 5)]
        expected = (5, 1)
    else:
        payload['activities'] = [activity('slow', 10, outputs=['goal']),
            activity('fast', 5, outputs=['goal']), activity('worse', 12, outputs=['goal'])]
        schedules = [({'slow': (5, 15)}, 15),
                     ({'fast': (0, 5)}, 5) if arrival == 'shorter' else ({'worse': (0, 12)}, 12)]
        expected = (5 if arrival == 'shorter' else 10, 1)
    saved = copy.deepcopy(payload)
    builder = core._build_model_with_finish
    captured = {}
    def build(*args, **kwargs):
        result = builder(*args, **kwargs)
        captured['slots'], captured['finish'] = result[2], result[4]
        return result
    native_callback = core.cp_model.CpSolverSolutionCallback
    class InflightCallback(native_callback):
        _script_values = None
        def value(self, expression):
            return self._script_values[expression.index] if self._script_values is not None else super().value(expression)
        @property
        def best_objective_bound(self):
            return 0 if self._script_values is not None else super().best_objective_bound
        def stop_search(self):
            if self._script_values is None:
                super().stop_search()
    native_solver = core.cp_model.CpSolver
    sent = False
    class InflightSolver(native_solver):
        _script = False
        def solve(self, model, callback=None, *args, **kwargs):
            nonlocal sent
            if not sent and self.parameters.num_search_workers == 8:
                sent = self._script = True
                for schedule, finish in schedules:
                    values = {captured['finish'].index: finish}
                    for slot in captured['slots']:
                        selected = slot.aid in schedule
                        start, end = schedule.get(slot.aid, (0, 0))
                        values.update({slot.present.index: int(selected), slot.start.index: start, slot.end.index: end})
                    callback._script_values = values
                    callback.on_solution_callback()
                callback._script_values = None
                return core.cp_model.FEASIBLE
            self._script = False
            return super().solve(model, callback, *args, **kwargs)
        @property
        def best_objective_bound(self):
            return 0 if self._script else super().best_objective_bound
        @property
        def num_branches(self):
            return 0 if self._script else super().num_branches
        @property
        def num_conflicts(self):
            return 0 if self._script else super().num_conflicts
        @property
        def wall_time(self):
            return 0 if self._script else super().wall_time
        def response_stats(self):
            return 'scripted in-flight callbacks' if self._script else super().response_stats()
        def stop_search(self):
            if not self._script:
                super().stop_search()
    monkeypatch.setattr(core, '_build_model_with_finish', build)
    monkeypatch.setattr(core.cp_model, 'CpSolverSolutionCallback', InflightCallback)
    monkeypatch.setattr(core.cp_model, 'CpSolver', InflightSolver)
    result = core.solve_joint(payload, run_id='inflight-feedback', seed=11, budget=Budget(5, 1, 3), worker_threads=8)
    assert result.status == 'OPTIMAL', result
    assert result.paths[0].validator_status == 'VALID' and result.paths[0].metrics.makespan == 5
    cert = result.stats['feedback_certificates'][0]
    assert cert['applied'] and (cert['makespan'], cert['execution_count']) == expected
    assert (cert['selection']['selected_makespan'], cert['selection']['selected_execution_count']) == expected
    assert cert['selection']['refreshed_from_trigger'] == (arrival != 'worse')
    assert payload == saved

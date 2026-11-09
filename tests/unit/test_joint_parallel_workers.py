"""CPU portfolios preserve validation/proofs and publish honest counters."""
import copy
import pytest
from tests.unit.test_joint_cpsat import core, setup_db, activity


def test_worker_count_auto_override_and_cpu_cap(core, monkeypatch):
    monkeypatch.setattr(core.os, 'cpu_count', lambda: 16)
    monkeypatch.delenv('PLANNER_JOINT_CP_SAT_WORKERS', raising=False)
    assert core.search_worker_count() == 8
    monkeypatch.setenv('PLANNER_JOINT_CP_SAT_WORKERS', '4')
    assert core.search_worker_count() == 4
    assert core.search_worker_count(1) == 1
    assert core.search_worker_count(32) == 16


@pytest.mark.parametrize('value', [0, -1, True, 1.5, '8'])
def test_invalid_explicit_workers_rejected(core, value):
    with pytest.raises(ValueError, match='positive integer'):
        core.search_worker_count(value)


def test_invalid_environment_rejected_and_single_cpu_supported(core, monkeypatch):
    monkeypatch.setenv('PLANNER_JOINT_CP_SAT_WORKERS', 'bad')
    with pytest.raises(ValueError, match='positive integer'):
        core.search_worker_count()
    monkeypatch.delenv('PLANNER_JOINT_CP_SAT_WORKERS', raising=False)
    monkeypatch.setattr(core.os, 'cpu_count', lambda: 1)
    assert core.search_worker_count() == 1


@pytest.mark.parametrize('workers', [1, 4, 8])
def test_workers_restore_state_and_preserve_first_window(core, monkeypatch, workers):
    from planner_experiment.models import Budget
    from tests.unit.test_material_power_cycles import material_power_case
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'none')
    monkeypatch.setattr(core, '_CAUSAL_RANKS', False)
    payload = material_power_case(2)
    payload['run_time_windows'] = [dict(id='first-on', activity_id='power_on', earliest_start=10, latest_finish=15)]
    saved = copy.deepcopy(payload)
    seen = []
    samples = []
    result = core.solve_joint(payload, run_id='parallel-workers', seed=37, budget=Budget(10, 1, 3),
        worker_threads=workers, candidate_observer=seen.append,
        progress_observer=lambda metrics, best: samples.append((metrics, best)))
    assert payload == saved
    assert result.status == 'OPTIMAL' and result.paths[0].validator_status == 'VALID'
    assert result.paths[0].metrics.makespan == 285
    assert result.stats['worker_threads'] == core.search_worker_count(workers)
    assert result.stats['makespan_proven_optimal'] and result.stats['execution_count_proven_optimal']
    assert not result.stats['validator_rejections'] and seen
    assert all(p.validator_status == 'VALID' for p in seen)
    runs = [e for e in result.paths[0].executions if e.activity_id == 'power_on']
    assert len(runs) == 3 and (runs[0].start_time, runs[0].end_time) == (10, 15)
    counters = [m['branches'] for m, _ in samples if 'branches' in m]
    assert counters == sorted(counters)
    if workers > 1:
        assert all(m.get('branches_per_second') is None for m, _ in samples)
        assert result.stats['search_counter_scope'] == 'solver_response_per_epoch'


def test_bridge_forwards_worker_selection(core, monkeypatch):
    from app.services.planner_engine_bridge import run_engine
    payload = dict(schema_version=2, id='parallel-bridge', execution_mode='parallel', max_steps=2,
        initial_state_ids=['ready'], goal_state_ids=['done:a'], forbidden_state_ids=[],
        states=[dict(id='ready', name='ready', state_kind='seed'),
                dict(id='done:a', name='done:a', state_kind='activity_output', source_activity_id='a')],
        activities=[activity('a', 1, required=['ready'])])
    before = copy.deepcopy(payload)
    result = run_engine(payload, engine='JOINT_CP_SAT', run_id='bridge-workers', seed=11,
        budget_override={'time_limit_seconds': 5}, run_options={'worker_threads': 4, 'trace_memory': False})
    assert payload == before and result['status'] == 'OPTIMAL'
    assert result['stats']['worker_threads'] == core.search_worker_count(4)
    assert result['paths'][0]['validator_status'] == 'VALID'


def test_capabilities_report_effective_workers(core, monkeypatch):
    from app.api.v1.planner_runs import capabilities
    monkeypatch.setenv('PLANNER_JOINT_CP_SAT_WORKERS', '4')
    # This route has no await/I/O. Drive it directly: Windows event-loop
    # construction otherwise requires a loopback socket even for a pure unit test.
    with pytest.raises(StopIteration) as completed:
        capabilities().send(None)
    result = completed.value.value
    assert result['joint_cp_sat']['worker_threads'] == core.search_worker_count(4)
    assert result['joint_cp_sat']['parallel_search_supported'] is True

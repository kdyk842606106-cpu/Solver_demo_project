"""Back up Test A, verify four initial facts locally, commit only its scope."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/test-a-all-scope-20261106'
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
RUN = 'planner-run:89f9614b-b5cf-4206-95b2-5f8d339a3b7f'

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def load(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))

def api(path, data=None):
    req = urllib.request.Request('http://127.0.0.1:8016/api/v1/' + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

def prepare():
    before = api('planner-scenarios/' + SID)
    save('before.json', before)
    save('history-before.json', api('planner-runs?scenario_id=' + SID))
    old = api('planner-runs/' + RUN)
    save('previous-run.json', old)
    s = copy.deepcopy(before['scenario'])
    s['activity_package_scope_ids'] = []
    save('preview.json', s)
    p = copy.deepcopy(s)
    request = old['request']
    p['initial_state_ids'] = request['current_state_ids']
    p['goal_state_ids'] = request['target_state_ids']
    p['calendar_context'] = request['effective_scenario_snapshot']['calendar_context']
    p['run_time_windows'] = []
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    p['max_steps'] = automatic_execution_bound(p)['value']
    save('input.json', p)
    save('budget.json', automatic_solver_budget(p))
    save('draft-commit.json', {'expected_revision': before['revision'], 'operations': [
        {'operation': 'update_scenario', 'payload': {'activity_package_scope_ids': []}}]})
    print(json.dumps({'revision': before['revision'], 'activities': len(p['activities']),
                      'initial_count': len(p['initial_state_ids']), 'budget': load('budget.json')}))

def solve():
    from app.services.planner_engine_bridge import run_engine
    p = load('input.json')
    budget = load('budget.json')
    start = time.perf_counter()
    with (OUT/'progress.jsonl').open('w', encoding='utf-8') as stream:
        def progress(metrics, best):
            row = dict(metrics, observed_seconds=time.perf_counter()-start, improved=best is not None)
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
            stream.flush()
        result = run_engine(p, engine='JOINT_CP_SAT', run_id='local:test-a:all-scope',
                            seed=11, budget_override={'time_limit_seconds': budget['time_limit_seconds']},
                            progress_observer=progress)
    save('result.json', result)
    summary = {k: result.get(k) for k in ('status', 'first_solution_seconds', 'elapsed_seconds', 'lower_bound', 'proven_optimal')}
    summary.update({k: result['stats'].get(k) for k in ('branches', 'conflicts', 'best_makespan', 'best_execution_count', 'model')})
    names = {a['id']: a['name'] for a in p['activities']}
    summary['schedule'] = []
    if result['paths']:
        best = result['paths'][0]
        assert best['validator_status'] == 'VALID'
        summary['validator'] = best['validator_status']
        summary['schedule'] = [{'name': names[e['activity_id']], 'ordinal': e['ordinal'],
                                'start': e['start_time'], 'end': e['end_time']} for e in best['executions']]
        assert any(e['name'] == '模块A维修' for e in summary['schedule'])
    save('summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'model'}, ensure_ascii=False))

def apply():
    before = load('before.json')
    current = api('planner-scenarios/' + SID)
    assert current == before, 'Project changed; rebase before committing'
    save('commit-response.json', api('planner-scenarios/' + SID + '/draft-commit', load('draft-commit.json')))
    verify()

def verify():
    before = load('before.json')
    after = api('planner-scenarios/' + SID)
    save('after.json', after)
    assert after['revision'] == before['revision'] + 1
    expected = load('preview.json')
    expected['revision'] = after['revision']
    assert after['scenario'] == expected, 'Unexpected scenario mutation'
    history_same = api('planner-runs?scenario_id=' + SID) == load('history-before.json')
    save('verification.json', {'revision': after['revision'], 'all_activities': not after['scenario']['activity_package_scope_ids'],
                              'history_unchanged': history_same})
    print(json.dumps(load('verification.json')))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'solve', 'apply', 'verify'])
    globals()[parser.parse_args().action]()

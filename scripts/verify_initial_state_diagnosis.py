"""Read-only Test A diagnosis/API verification and independent recovery solves."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT/'output/initial-state-diagnosis-20261106'
BASE = 'http://127.0.0.1:8017/api/v1'
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'


def api(path, body=None):
    req = urllib.request.Request(BASE+path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.load(res)


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = api('/planner-scenarios/'+SID)
    history = api('/planner-runs?scenario_id='+SID)
    save('project-before.json', before)
    s = before['scenario']
    acts = {a['name']: a for a in s['activities']}
    state = lambda name: acts[name]['output_state_id']
    fault = next(x['id'] for x in s['states'] if x['name'] == '模块A待维修')
    repair_initial = [state(n) for n in ['下电', '模块A拆卸', '模块C拆卸', '集成检测完成', '安全验收']] + [fault]
    repair_goals = [state('模块A维修'), state('扩展功能联调')]
    fixture = copy.deepcopy(s)
    fixture['calendar_context'] = {'start_at': '2026-11-06T08:00:00+08:00', 'timezone': 'Asia/Shanghai'}
    results = {}
    requests = {}
    def check(name, initial, goals):
        body = dict(expected_revision=before['revision'], current_state_ids=initial,
                    target_state_ids=goals, draft_scenario=fixture)
        requests[name] = copy.deepcopy(body)
        result = api('/planner-scenarios/'+SID+'/initial-state-check', body)
        results[name] = result
        return result
    missing = check('missing-fault', [x for x in repair_initial if x != fault], repair_goals)
    assert missing['status'] == 'STRUCTURALLY_BLOCKED'
    assert any(x['id'] == fault and x['confirmable'] for g in missing['groups'] for x in g['states'])
    repaired = check('repair-confirmed', repair_initial, repair_goals)
    assert repaired['status'] == 'STRUCTURALLY_REACHABLE'
    normal = [state('下电'), state('集成检测完成')]
    normal_goal = [state('模块联调')]
    cycle = check('cycle-no-start', normal, normal_goal)
    assert any(g['reason'] == 'dependency_cycle' for g in cycle['groups'])
    normal.append(state('模块C拆卸'))
    check('cycle-confirm-C', list(normal), normal_goal)
    normal.append(state('模块A拆卸'))
    assert check('cycle-confirm-A-C', normal, normal_goal)['status'] == 'STRUCTURALLY_REACHABLE'
    save('requests.json', requests); save('diagnoses.json', results)
    from app.services.planner_engine_bridge import _planner_modules, run_engine
    _planner_modules()
    solve_results = {}
    for name, initial, goals in [('normal', normal, normal_goal), ('recovery', repair_initial, repair_goals)]:
        payload = copy.deepcopy(fixture)
        payload['initial_state_ids'], payload['goal_state_ids'] = initial, goals
        original = copy.deepcopy(payload)
        result = run_engine(payload, engine='JOINT_CP_SAT', run_id='local:initial-check:'+name, seed=11,
                            budget_override={'time_limit_seconds': 60})
        assert payload == original
        assert result['paths'] and result['paths'][0]['validator_status'] == 'VALID'
        if name == 'recovery':
            executions = result['paths'][0]['executions']
            assert any(e['activity_id'] == acts['模块A维修']['id'] for e in executions)
            assert sum(e['activity_id'] == acts['上电']['id'] for e in executions) == 2
            assert fault not in result['paths'][0]['final_state_ids']
        save(name+'-input.json', payload); save(name+'-result.json', result)
        solve_results[name] = {k: result.get(k) for k in ['status', 'elapsed_seconds', 'first_solution_seconds']}
        solve_results[name].update(validator=result['paths'][0]['validator_status'], metrics=result['paths'][0]['metrics'])
        print(name, solve_results[name], flush=True)
    assert api('/planner-scenarios/'+SID) == before
    assert api('/planner-runs?scenario_id='+SID) == history
    summary = dict(scenario_id=SID, revision=before['revision'], diagnoses={k:v['status'] for k,v in results.items()},
                   solves=solve_results, project_unchanged=True, history_unchanged=True,
                   compiler_sha256=hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest())
    save('summary.json', summary)
    print('Read-only API and replay checks passed', flush=True)


if __name__ == '__main__':
    main()

"""Read-only live snapshot; local normal/recovery solve and replay evidence."""
import copy
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output' / ('test-a-v10-recovery-' + time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'

def api(path):
    with urllib.request.urlopen('http://127.0.0.1:8016/api/v1/' + path, timeout=30) as response:
        return json.load(response)

def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

from app.services.planner_engine_bridge import _planner_modules, run_engine
_planner_modules()
from app.services.planner_scenarios import expand_packages, validate_scenario
from app.services.planner_execution_bounds import automatic_execution_bound
from app.core.joint_cpsat import prepare_payload, replay_candidate, _occurrence_limits
from planner_experiment.scenario import scenario_from_dict
from planner_experiment.models import Action, to_primitive
from planner_experiment.simulator import PathSimulator

source = api('planner-scenarios/' + SID)
history = api('planner-runs?scenario_id=' + SID)
save('source.json', source)
save('history-before.json', history)
assert source['revision'] == 10, 'Recheck changed live revision before testing'
s = source['scenario']
acts = {a['name']: a for a in s['activities']}
names = {a['id']: a['name'] for a in s['activities']}
fault = next(x['id'] for x in s['states'] if x['name'] == '模块A待维修')
old = json.loads((ROOT / 'output/test-a-repair-page-diagnosis/page-input.json').read_text('utf-8'))
normal = copy.deepcopy(s)
normal['calendar_context'] = copy.deepcopy(old['calendar_context'])
normal['max_steps'] = automatic_execution_bound(normal)['value']
repair = copy.deepcopy(normal)
for field in ('initial_state_ids', 'goal_state_ids', 'forbidden_state_ids', 'activity_package_scope_ids'):
    repair[field] = copy.deepcopy(old[field])
repair['max_steps'] = automatic_execution_bound(repair)['value']
assert fault not in normal['initial_state_ids'] and fault in repair['initial_state_ids']
assert all(a['max_instances'] == 3 for a in s['activities'])
for payload in (normal, repair):
    assert not validate_scenario(copy.deepcopy(payload))
save('normal-input.json', normal)
save('repair-input.json', repair)
print('OUTPUT ' + str(OUT), flush=True)

expanded = expand_packages(copy.deepcopy(repair))
scene = scenario_from_dict(prepare_payload(expanded))
prior = json.loads((ROOT / 'output/incumbent-feedback-20261105/after-600s-best.json').read_text('utf-8'))
rows = [{'activity_id': e['activity_id'], 'ordinal': e['ordinal'], 'start': e['start_time'], 'end': e['end_time']} for e in prior['executions']]
candidate, details = replay_candidate(expanded, scene, rows, run_id='local:v10:reference', seed=11)
assert candidate.validator_status == 'VALID' and len(candidate.executions) == 11
save('reference-replay.json', to_primitive(candidate))
caps, proofs = _occurrence_limits(scene)
for n in ('下电', '模块C拆卸', '模块A拆卸', '模块A维修', '模块A安装', '模块C安装'):
    assert caps[acts[n]['id']] > 0, n
save('pruning.json', {'caps': {names[k]: v for k, v in caps.items()}, 'proofs': proofs})

# Replay actions with explicit safety checkpoints in the current domain model.
sim = PathSimulator(scene)
state = sim.initial_state()
checks = []
def enabled(name):
    return any(a.kind == 'START' and a.activity_id == acts[name]['id'] for a in sim.enabled_actions(state))
assert not enabled('模块A维修') and not enabled('模块A拆卸')
for action in candidate.actions:
    if action.kind == 'START' and action.activity_id == acts['模块C拆卸']['id']:
        assert not enabled('模块A拆卸')
        checks.append('cannot_remove_A_before_C')
    state = sim.transition(state, action)
    if action.kind == 'START' and action.activity_id == acts['模块A维修']['id']:
        assert not any(enabled(n) for n in ('模块A安装', '模块C安装', '上电'))
        checks.append('cannot_reinstall_or_power_on_during_repair')
assert sim.is_goal(state) and fault not in candidate.final_state_ids
negative = copy.deepcopy(repair)
negative['initial_state_ids'].remove(fault)
negative_issues = validate_scenario(negative)
assert any(i['code'] == 'GOAL_STRUCTURALLY_UNREACHABLE' for i in negative_issues)
save('safety-checks.json', {'passed': checks, 'missing_fault_issues': negative_issues,
     'reference_makespan': candidate.metrics.makespan, 'reference_details': details})
print('Reference and safety checks passed', flush=True)

summaries = {}
for label, payload, seconds in [('normal', normal, 60), ('repair', repair, 600)]:
    began = time.perf_counter()
    with (OUT / (label + '-progress.jsonl')).open('w', encoding='utf-8') as log:
        def progress(metrics, best):
            sample = dict(metrics, observed_seconds=time.perf_counter()-began, improved=best is not None)
            log.write(json.dumps(sample, ensure_ascii=False) + '\n')
            log.flush()
            if best is not None:
                print(label + ' ' + json.dumps(sample, ensure_ascii=False), flush=True)
        result = run_engine(payload, engine='JOINT_CP_SAT', run_id='local:v10:' + label, seed=11,
                            budget_override={'time_limit_seconds': seconds}, progress_observer=progress)
    save(label + '-result.json', result)
    stats = result['stats']
    summary = {k: result.get(k) for k in ('status', 'first_solution_seconds', 'elapsed_seconds', 'lower_bound', 'proven_optimal')}
    summary.update({k: stats.get(k) for k in ('branches', 'conflicts', 'model', 'best_makespan', 'best_execution_count', 'makespan_proven_optimal', 'execution_count_proven_optimal')})
    if result['paths']:
        path = result['paths'][0]
        domain = expand_packages(copy.deepcopy(payload))
        replayed, _ = replay_candidate(domain, scenario_from_dict(prepare_payload(domain)), [
            {'activity_id': e['activity_id'], 'ordinal': e['ordinal'], 'start': e['start_time'], 'end': e['end_time']}
            for e in path['executions']], run_id='local:v10:' + label + ':replay', seed=11)
        assert replayed.validator_status == 'VALID'
        summary['validator'] = replayed.validator_status
        summary['sequence'] = [{'name': names[e.activity_id], 'ordinal': e.ordinal, 'start': e.start_time, 'end': e.end_time} for e in replayed.executions]
        if label == 'normal':
            assert not any(e.activity_id == acts[n]['id'] for e in replayed.executions for n in ('下电', '模块C拆卸', '模块A拆卸', '模块A维修'))
        save(label + '-replay.json', to_primitive(replayed))
    summaries[label] = summary
    save('summary.json', summaries)
    print(label + ' RESULT ' + json.dumps(summary, ensure_ascii=False), flush=True)

assert api('planner-scenarios/' + SID) == source
assert api('planner-runs?scenario_id=' + SID) == history
save('isolation.json', {'project_unchanged': True, 'history_unchanged': True})
print('LIVE PROJECT AND HISTORY UNCHANGED', flush=True)

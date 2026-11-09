"""Read-only, longer-budget maintenance search with durable candidate evidence."""
import copy
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--budget', type=int, default=600)
parser.add_argument('--source', type=Path)
args = parser.parse_args()
OUT = ROOT / 'output' / ('test-a-repair-long-' + time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.services.planner_execution_bounds import automatic_execution_bound
from app.core.joint_cpsat import solve_joint, prepare_payload, replay_candidate
from planner_experiment.models import Budget, to_primitive
from planner_experiment.scenario import scenario_from_dict

url = 'http://127.0.0.1:8016/api/v1/planner-scenarios/scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
if args.source:
    envelope = json.loads(args.source.read_text(encoding='utf-8'))
else:
    with urllib.request.urlopen(url, timeout=30) as response:
        envelope = json.load(response)
save('source.json', envelope)
s = envelope['scenario']
assert len(s['activities']) == 14
assert all(a['max_instances'] == 3 for a in s['activities'])
payload = expand_packages(copy.deepcopy(s))
assert len(payload['activities']) == 11
payload['max_steps'] = automatic_execution_bound(s)['value']
payload['calendar_context'] = {'start_at': '2026-11-09T08:00:00+08:00', 'timezone': 'Asia/Shanghai'}
save('input.json', payload)
print(json.dumps({'output': str(OUT), 'revision': envelope['revision'], 'budget': args.budget,
                  'activities': len(payload['activities']), 'max_steps': payload['max_steps']}, ensure_ascii=False), flush=True)
started = time.perf_counter()
samples = []
def progress(metrics, candidate):
    sample = {'elapsed': time.perf_counter() - started, **metrics, 'improved': candidate is not None}
    samples.append(sample)
    save('progress.json', samples)
    if candidate is not None:
        save('best.json', to_primitive(candidate))
    print(json.dumps(sample, ensure_ascii=False), flush=True)

result = solve_joint(payload, run_id='local:repair-long-budget', seed=11,
                     budget=Budget(args.budget, 1, 3), progress_observer=progress)
save('result.json', to_primitive(result))
if result.paths:
    path = result.paths[0]
    scene = scenario_from_dict(prepare_payload(payload))
    checked, _ = replay_candidate(payload, scene, [
        {'activity_id': e.activity_id, 'ordinal': e.ordinal, 'start': e.start_time, 'end': e.end_time}
        for e in path.executions], run_id='local:repair-long-replay', seed=11)
    assert checked.validator_status == 'VALID'
    save('replay.json', to_primitive(checked))
summary = {'status': result.status, 'first_solution_seconds': result.first_solution_seconds,
           'elapsed_seconds': result.stats.get('elapsed_seconds'), 'branches': result.stats.get('branches'),
           'conflicts': result.stats.get('conflicts'), 'lower_bound': result.stats.get('lower_bound'),
           'best_makespan': result.stats.get('best_makespan'), 'candidate_count': result.stats.get('candidate_count'),
           'model': result.stats.get('model'), 'build_seconds': result.stats.get('build_seconds'),
           'error': result.error}
if result.paths:
    summary.update(executions=len(result.paths[0].executions), validator=result.paths[0].validator_status)
save('summary.json', summary)
print(json.dumps(summary, ensure_ascii=False), flush=True)

"""Compare the exact frozen UI run with a start-time-only control."""
import copy
import argparse
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import run_engine
parser = argparse.ArgumentParser()
parser.add_argument('--budget', type=int, default=60)
parser.add_argument('--mode', choices=['both', 'page-original', 'start-at-0800'], default='both')
args = parser.parse_args()

OUT = ROOT / 'output/test-a-repair-page-diagnosis'
record = json.loads((OUT/'planner-run_53c1a5d7-e959-4da6-b39e-9d0d43354554.json').read_text('utf-8-sig'))
for mode in (['page-original', 'start-at-0800'] if args.mode == 'both' else [args.mode]):
    stem = mode if args.budget == 60 else f'{mode}-{args.budget}s'
    started = time.perf_counter()
    samples = []
    s = copy.deepcopy(record['request']['effective_scenario_snapshot'])
    if mode == 'start-at-0800':
        s['calendar_context'] = {'start_at':'2026-11-09T08:00:00+08:00','timezone':'Asia/Shanghai'}
        s.pop('working_intervals', None)
        s.pop('lift_day_windows', None)
    def progress(m, p):
        samples.append({'elapsed':time.perf_counter()-started, **m, 'improved':p is not None})
        (OUT/(stem+'-progress.json')).write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf-8')
        if p is not None:
            from planner_experiment.models import to_primitive
            (OUT/(stem+'-best.json')).write_text(json.dumps(to_primitive(p),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'case':mode, 'candidate':m},ensure_ascii=False),flush=True)
    print('START '+mode, flush=True)
    result = run_engine(s, engine='JOINT_CP_SAT', run_id='local:diagnose:'+mode,
            seed=11, budget_override={'time_limit_seconds':args.budget}, progress_observer=progress)
    (OUT/(stem+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'case':mode,'status':result['status'],
        'first':result['first_solution_seconds'],'elapsed':result['elapsed_seconds'],
        'branches':result['stats'].get('branches'),'best':result['stats'].get('best_makespan')},ensure_ascii=False),flush=True)

"""Paired read-only benchmark on the exact 00:42 Test A run snapshot."""
import argparse
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('implementation', choices=['before','after'])
parser.add_argument('--seconds', type=int, default=600)
args = parser.parse_args()
OUT = ROOT/'output/incumbent-feedback-20261105'
OUT.mkdir(exist_ok=True)
from app.services.planner_engine_bridge import _planner_modules, run_engine
_planner_modules()
core_file = ROOT/'app/core/joint_cpsat.py' if args.implementation=='after' else OUT/'joint_cpsat_before.py'
if args.implementation == 'before':
    spec = importlib.util.spec_from_file_location('app.core.joint_cpsat', core_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
source = ROOT/'output/test-a-repair-page-diagnosis/page-input.json'
payload = json.loads(source.read_text('utf-8'))
stem = f'{args.implementation}-{args.seconds}s'
def save(suffix, value):
    (OUT/(stem+'-'+suffix+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
import ortools
save('environment', dict(core_sha256=hashlib.sha256(core_file.read_bytes()).hexdigest(),
    input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), python=platform.python_version(),
    ortools=ortools.__version__, budget=args.seconds, seed=11, threads=1))
started = time.perf_counter()
with (OUT/(stem+'-progress.jsonl')).open('w',encoding='utf-8') as log:
    def progress(metrics, candidate):
        sample = dict(elapsed=time.perf_counter()-started, **metrics, improved=candidate is not None)
        log.write(json.dumps(sample,ensure_ascii=False)+'\n')
        log.flush()
        if candidate is not None:
            from planner_experiment.models import to_primitive
            save('best',to_primitive(candidate))
            print(json.dumps(sample,ensure_ascii=False),flush=True)
    print('START '+stem,flush=True)
    result = run_engine(payload,engine='JOINT_CP_SAT',run_id='local:feedback:'+stem,seed=11,
                        budget_override={'time_limit_seconds':args.seconds},progress_observer=progress)
save('result',result)
stats=result['stats']
summary={k:result.get(k) for k in ['status','first_solution_seconds','elapsed_seconds','lower_bound','proven_optimal']}
summary.update({k:stats.get(k) for k in ['branches','conflicts','candidate_count','build_seconds','best_makespan',
    'best_execution_count','feedback_restarts','search_epochs','feedback_certificates',
    'makespan_proven_optimal','execution_count_proven_optimal']})
if result['paths']:
    summary['validator_status']=result['paths'][0]['validator_status']
save('summary',summary)
print(json.dumps(summary,ensure_ascii=False),flush=True)

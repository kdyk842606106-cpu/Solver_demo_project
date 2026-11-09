"""Independent diagnostic run; never writes project data or changes production settings."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import _planner_modules, run_engine
_planner_modules()
from app.core import joint_cpsat as core

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['baseline', 'mandatory'], required=True)
parser.add_argument('--label', default='')
parser.add_argument('--parameters', default='{}', help='Diagnostic-only solver parameter overrides')
parser.add_argument('--parameter', action='append', default=[], help='NAME=JSON_VALUE; diagnostic only')
args = parser.parse_args()
parameters = json.loads(args.parameters)
for parameter in args.parameter:
    name, value = parameter.split('=', 1)
    parameters[name] = json.loads(value)
out = ROOT / 'output/mandatory-late-diagnosis-20261106'
out.mkdir(parents=True, exist_ok=True)
tag = args.mode + ('-' + args.label if args.label else '')
payload = json.loads((ROOT / 'output/mandatory-normal-late-20261106/late-input.json').read_text(encoding='utf-8'))
if args.mode == 'baseline':
    core.identify_mandatory_activities = lambda *a, **k: (set(), {'proofs': {}})

original_solve = core.cp_model.CpSolver.solve
original_replay = core.replay_candidate
calls, replays, progress = [], [], []
started = time.perf_counter()
def solve(self, model, *a, **k):
    number = len(calls) + 1
    entry = {'call': number, 'start_seconds': time.perf_counter() - started,
             'variables': len(model.proto.variables), 'constraints': len(model.proto.constraints)}
    calls.append(entry)
    self.parameters.log_search_progress = True
    self.parameters.log_to_stdout = False
    for name, value in parameters.items():
        setattr(self.parameters, name, value)
    model.export_to_file(str(out / f'{tag}-call{number}.pbtxt'))
    with (out / f'{tag}-call{number}.log').open('w', encoding='utf-8') as stream:
        def log(message):
            stream.write(message + '\n')
            stream.flush()
        self.log_callback = log
        status = original_solve(self, model, *a, **k)
    entry.update(end_seconds=time.perf_counter()-started, response_stats=self.response_stats())
    if self.parameters.fill_tightened_domains_in_response:
        entry['tightened_domains'] = {v.name: list(v.domain) for v in self.response_proto.tightened_variables}
    return status
def replay(*a, **k):
    begin = time.perf_counter()
    try:
        return original_replay(*a, **k)
    finally:
        replays.append(time.perf_counter()-begin)
core.cp_model.CpSolver.solve = solve
core.replay_candidate = replay
def observe(metrics, best):
    progress.append(dict(metrics, observed_seconds=time.perf_counter()-started, improved=best is not None))
result = run_engine(payload, engine='JOINT_CP_SAT', run_id='local:diagnostic:'+tag, seed=11,
                    budget_override={'time_limit_seconds':60}, progress_observer=observe)
report = {'mode': args.mode, 'parameters': parameters, 'result': result, 'solver_calls': calls,
          'replay_seconds': replays, 'progress': progress}
(out / f'{tag}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'tag': tag, 'status': result['status'], 'first': result.get('first_solution_seconds'),
                  'elapsed': result['elapsed_seconds'], 'replay_total': sum(replays),
                  'calls': calls}, ensure_ascii=False))

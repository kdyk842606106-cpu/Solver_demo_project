"""Paired independent-process regression of the linear propagation implementation."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/linear-propagation-regression-20261106'
CASES = {
    'normal-a': ('output/mandatory-normal-late-20261106/normal-input.json', 60),
    'recovery-current': ('output/test-a-b-d-repair-effects-20261106/after-input.json', 60),
    'repair-0042': ('output/test-a-repair-page-diagnosis/page-input.json', 60),
    'disassembly-only': ('output/test-a-install-keeps-tests-20261106/disassembly-only-input.json', 60),
    'assembly-20': ('output/fixtures/assembly-commissioning-20/scenario.json', 60),
    'required-cycles-5': ('output/cycle-capacity-pruned-20261105/required-5-input.json', 60),
    'calendar-night-150': ('output/fixtures/night-calendar-150/result.json', 120),
}
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def single(case, implementation, seed, label, encoding=None, causal_ranks=None, worker_threads=None, native_log=False):
    sys.path.insert(0, str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules, run_engine
    _planner_modules()
    from app.core import joint_cpsat as core
    if encoding is not None:
        core._MANDATORY_ENCODING = encoding
    if causal_ranks is not None:
        core._CAUSAL_RANKS = causal_ranks
    import ortools
    source, seconds = CASES[case]
    saved = json.loads((ROOT / source).read_text(encoding='utf-8-sig'))
    payload = copy.deepcopy(saved['request']['effective_scenario_snapshot'] if case == 'calendar-night-150' else saved)
    before = copy.deepcopy(payload)
    tag = f'{case}-{implementation}-seed{seed}' + (f'-{label}' if label else '')
    if encoding is not None:
        tag = f'{encoding}-{tag}'
    if causal_ranks is not None:
        tag = f'ranks-{int(causal_ranks)}-{tag}'
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / f'{tag}-input.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    original = core.cp_model.CpSolver.solve
    calls = []
    started = time.perf_counter()
    cpu_started = time.process_time()
    def solve(self, model, *args, **kwargs):
        self.parameters.new_linear_propagation = implementation == 'new'
        # Hash before solving: no diagnostic objective, hint, ordering or constraint is added.
        entry = {'initial_model_sha256': hashlib.sha256(str(model.proto).encode()).hexdigest(),
                 'worker_threads': self.parameters.num_search_workers,
                 'start_seconds': time.perf_counter()-started}
        calls.append(entry)
        if native_log:
            self.parameters.log_search_progress = True
            self.parameters.log_to_stdout = False
            self.parameters.log_subsolver_statistics = True
            with (OUT / f'{tag}-call{len(calls)-1}.log').open('w', encoding='utf-8') as log:
                self.log_callback = lambda line: log.write(line+'\n')
                try:
                    status = original(self, model, *args, **kwargs)
                finally:
                    self.log_callback = None
        else:
            status = original(self, model, *args, **kwargs)
        entry.update(end_seconds=time.perf_counter()-started, response_stats=self.response_stats())
        return status
    core.cp_model.CpSolver.solve = solve
    with (OUT / f'{tag}-progress.jsonl').open('w', encoding='utf-8') as stream:
        def observe(metrics, best):
            stream.write(json.dumps(dict(metrics, observed_seconds=time.perf_counter()-started,
                                         improved=best is not None), ensure_ascii=False)+'\n')
            stream.flush()
        result = run_engine(payload, engine='JOINT_CP_SAT', run_id='local:linear:'+tag, seed=seed,
                            budget_override={'time_limit_seconds':seconds}, progress_observer=observe,
                            run_options=({'worker_threads': worker_threads, 'trace_memory': False}
                                         if worker_threads is not None else None))
    cpu_seconds = time.process_time() - cpu_started
    assert payload == before
    (OUT / f'{tag}-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'case': case, 'implementation': implementation, 'encoding': core._MANDATORY_ENCODING,
               'causal_ranks_enabled': core._CAUSAL_RANKS, 'source': source,
               'seed': seed, 'budget_seconds': seconds, 'ortools_version': ortools.__version__,
               'process_cpu_seconds': cpu_seconds,
               'input_sha256': digest(payload), 'solver_calls': calls,
               **{k: result.get(k) for k in ['status', 'first_solution_seconds', 'elapsed_seconds', 'lower_bound', 'proven_optimal']},
               **{k: result['stats'].get(k) for k in ['branches', 'conflicts', 'best_makespan', 'best_execution_count',
                                                     'worker_threads', 'build_seconds', 'validator_rejections',
                                                     'makespan_proven_optimal', 'execution_count_proven_optimal']},
               'model': result['stats'].get('model')}
    if result['paths']:
        best = result['paths'][0]
        assert best['validator_status'] == 'VALID'
        names = {a['id']:a['name'] for a in payload['activities']}
        summary.update(validator=best['validator_status'], schedule=[{
            'name': names[e['activity_id']], 'ordinal': e['ordinal'],
            'start': e['start_time'], 'end': e['end_time']} for e in best['executions']])
    (OUT / f'{tag}-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['model','solver_calls','schedule']}, ensure_ascii=False), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=list(CASES))
    parser.add_argument('--implementation', choices=['new','old'])
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--label', default='')
    args = parser.parse_args()
    if args.case:
        assert args.implementation
        single(args.case, args.implementation, args.seed, args.label)
    else:
        # Alternate order across cases; never overlap solvers or touch the live worker.
        for index, case in enumerate(CASES):
            for implementation in (('new','old') if index % 2 == 0 else ('old','new')):
                subprocess.run([sys.executable, '-X', 'utf8', __file__, '--case', case,
                                '--implementation', implementation, '--seed', str(args.seed)],
                               cwd=ROOT, check=True)

if __name__ == '__main__':
    main()

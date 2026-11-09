"""CPU portfolio comparison: same unstrengthened business model, fresh processes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/multicore-20261106'
CASES = ['normal-a', 'late-material', 'recovery-current']
SEEDS = [11, 23, 37, 53, 71]
WORKERS = [1, 4, 8]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES)
    p.add_argument('--seed', type=int, choices=SEEDS)
    p.add_argument('--workers', type=int, choices=WORKERS)
    p.add_argument('--repeat', action='store_true')
    args = p.parse_args()
    if args.case:
        import benchmark_linear_propagation as runner
        runner.OUT = OUT
        runner.CASES['late-material'] = ('output/mandatory-normal-late-20261106/late-input.json', 60)
        label = f'w{args.workers}' + ('-repeat' if args.repeat else '')
        runner.single(args.case, 'new', args.seed, label, encoding='none', causal_ranks=False,
                      worker_threads=args.workers, native_log=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for si, seed in enumerate(SEEDS):
        for ci, case in enumerate(CASES):
            offset = (si+ci) % len(WORKERS)
            for workers in WORKERS[offset:]+WORKERS[:offset]:
                tasks.append(dict(case=case, seed=seed, workers=workers, repeat=False))
    for case in CASES:
        for workers in (4, 8):
            tasks.append(dict(case=case, seed=53, workers=workers, repeat=True))
    (OUT/'matrix.json').write_text(json.dumps(tasks, indent=2), encoding='utf-8')
    code = ROOT/'app/core/joint_cpsat.py'
    sha = hashlib.sha256(code.read_bytes()).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps({
        'compiler_sha256': sha, 'available_logical_processors': os.cpu_count(), 'seeds': SEEDS,
        'workers': WORKERS, 'runs': len(tasks), 'budget_seconds': 60,
        'mandatory_encoding': 'none', 'causal_ranks': False, 'new_linear_propagation': True,
        'sequential_fresh_processes': True, 'database_writes': False, 'native_logs': True,
        'cpu_seconds': 'process_time includes CPU time across threads; excludes subprocess startup',
        'counter_scope': 'Parallel response branches represent the first subsolver, not the sum of all workers.'
    }, indent=2), encoding='utf-8')
    for index, task in enumerate(tasks, 1):
        assert hashlib.sha256(code.read_bytes()).hexdigest() == sha
        print(f'RUN {index}/{len(tasks)} {task}', flush=True)
        cmd = [sys.executable, '-X', 'utf8', __file__, '--case', task['case'], '--seed', str(task['seed']), '--workers', str(task['workers'])]
        if task['repeat']:
            cmd.append('--repeat')
        subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

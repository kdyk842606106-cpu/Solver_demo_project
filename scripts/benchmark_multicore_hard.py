"""Replay historical hard inputs with current identical models at 1/8 workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/multicore-hard-20261106'
CASES = {
    'repair-0042': ('output/test-a-repair-page-diagnosis/page-input.json', 600),
    'disassembly-only': ('output/test-a-install-keeps-tests-20261106/disassembly-only-input.json', 60),
    'optional-cycles-20': ('output/cycle-capacity-pruned-20261105/optional-20-input.json', 60),
    'required-cycles-15': ('output/cycle-capacity-pruned-20261105/required-15-input.json', 60),
    'required-cycles-20': ('output/cycle-capacity-pruned-20261105/required-20-input.json', 60),
    'calendar-night-150': ('output/fixtures/night-calendar-150/result.json', 120),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES)
    p.add_argument('--workers', type=int, choices=[1, 8])
    p.add_argument('--repeat', action='store_true')
    args = p.parse_args()
    if args.case:
        import benchmark_linear_propagation as runner
        runner.OUT = OUT
        runner.CASES.update(CASES)
        runner.single(args.case, 'new', 11, f'w{args.workers}' + ('-repeat' if args.repeat else ''),
                      encoding='none', causal_ranks=False, worker_threads=args.workers, native_log=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for i, case in enumerate(CASES):
        for workers in ([8, 1] if i % 2 == 0 else [1, 8]):
            tasks.append(dict(case=case, workers=workers, repeat=False))
    for case in ['repair-0042', 'disassembly-only', 'required-cycles-20']:
        tasks.append(dict(case=case, workers=8, repeat=True))
    code = ROOT / 'app/core/joint_cpsat.py'
    sha = hashlib.sha256(code.read_bytes()).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps(dict(
        compiler_sha256=sha, available_logical_processors=os.cpu_count(), seed=11,
        cases=CASES, tasks=tasks, mandatory_encoding='none', causal_ranks=False,
        new_linear_propagation=True, sequential_fresh_processes=True, database_writes=False,
        source_sha256={case: hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
                       for case, (source, _) in CASES.items()},
    ), ensure_ascii=False, indent=2), encoding='utf-8')
    for i, task in enumerate(tasks, 1):
        assert hashlib.sha256(code.read_bytes()).hexdigest() == sha
        print(f'RUN {i}/{len(tasks)} {task}', flush=True)
        cmd = [sys.executable, '-X', 'utf8', __file__, '--case', task['case'], '--workers', str(task['workers'])]
        if task['repeat']:
            cmd.append('--repeat')
        subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

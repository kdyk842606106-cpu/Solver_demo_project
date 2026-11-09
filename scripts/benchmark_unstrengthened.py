"""Check seed variability without mandatory-presence or causal-rank additions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/unstrengthened-20261106'
CASES = ['normal-a', 'late-material', 'recovery-current']
SEEDS = [11, 23, 37, 53, 71]
MODES = ['none', 'appended']


def single(case, seed, mode, label):
    import benchmark_linear_propagation as runner
    runner.OUT = OUT
    runner.CASES['late-material'] = ('output/mandatory-normal-late-20261106/late-input.json', 60)
    runner.single(case, 'new', seed, label, encoding=mode, causal_ranks=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--seed', type=int, choices=SEEDS)
    parser.add_argument('--mode', choices=MODES)
    parser.add_argument('--label', default='main')
    args = parser.parse_args()
    if args.case:
        assert args.seed is not None and args.mode is not None
        single(args.case, args.seed, args.mode, args.label)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for si, seed in enumerate(SEEDS):
        for ci, case in enumerate(CASES):
            for mode in (MODES if (si+ci) % 2 == 0 else MODES[::-1]):
                tasks.append(dict(case=case, seed=seed, mode=mode, label='main'))
    for seed in (11, 37):
        for case in CASES:
            tasks.append(dict(case=case, seed=seed, mode='none', label='repeat'))
    # Recheck the observed worst recovery seed, not only the shorter samples.
    tasks.append(dict(case='recovery-current', seed=53, mode='none', label='repeat'))
    (OUT/'matrix.json').write_text(json.dumps(tasks, indent=2), encoding='utf-8')
    code = ROOT/'app/core/joint_cpsat.py'
    sha = hashlib.sha256(code.read_bytes()).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps({
        'compiler_sha256': sha, 'production_mandatory_encoding': 'none', 'production_causal_ranks': False,
        'cases': CASES, 'seeds': SEEDS, 'runs': len(tasks), 'threads': 1, 'budget_seconds': 60,
        'new_linear_propagation': True, 'sequential_fresh_processes': True, 'database_writes': False,
        'retained': ['business constraints', 'occurrence pruning', 'incumbent feedback', 'lexicographic objective', 'replay validation']
    }, indent=2), encoding='utf-8')
    for i, task in enumerate(tasks, 1):
        assert hashlib.sha256(code.read_bytes()).hexdigest() == sha
        print(f'RUN {i}/{len(tasks)} {task}', flush=True)
        subprocess.run([sys.executable, '-X', 'utf8', __file__, '--case', task['case'],
                        '--seed', str(task['seed']), '--mode', task['mode'], '--label', task['label']],
                       cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

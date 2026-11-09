"""Three-way ranks comparison with five seeds and unchanged frozen inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/causal-rank-unbound-20261106'
SNAPSHOT_SHA = 'eebb3f5c5cbb6953e3ff39ef28d8f22594c667e25f424feb12e8b2be51793766'
CASES = ['normal-a', 'late-material', 'recovery-current']
MODES = ['off', 'legacy', 'unbound']
SEEDS = [11, 23, 37, 53, 71]


def load_legacy():
    path = OUT / 'joint_cpsat_before.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SNAPSHOT_SHA
    name = '_benchmark_joint_cpsat_rank_v1'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module._CAUSAL_RANKS = True
    module._MANDATORY_ENCODING = 'appended'
    return module


def single(case, seed, mode):
    sys.path.insert(0, str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.core import joint_cpsat as core
    import benchmark_linear_propagation as runner
    if mode == 'legacy':
        # Frozen compiler only. Shared runner, feedback, objective, replay and
        # parameters are identical; old constraint insertion order is retained.
        core._compile = load_legacy()._compile
    runner.OUT = OUT
    runner.CASES['late-material'] = ('output/mandatory-normal-late-20261106/late-input.json', 60)
    runner.single(case, 'new', seed, mode, encoding='appended', causal_ranks=mode != 'off')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES)
    p.add_argument('--seed', type=int, choices=SEEDS)
    p.add_argument('--mode', choices=MODES)
    args = p.parse_args()
    if args.case:
        assert args.seed is not None and args.mode is not None
        single(args.case, args.seed, args.mode)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for si, seed in enumerate(SEEDS):
        for ci, case in enumerate(CASES):
            offset = (si + ci) % 3
            for mode in MODES[offset:] + MODES[:offset]:
                tasks.append(dict(case=case, seed=seed, mode=mode))
    (OUT / 'matrix.json').write_text(json.dumps(tasks, indent=2), encoding='utf-8')
    source_path = ROOT / 'app/core/joint_cpsat.py'
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    (OUT / 'source-manifest.json').write_text(json.dumps({
        'legacy_sha256': SNAPSHOT_SHA, 'current_sha256': source_sha,
        'seeds': SEEDS, 'sequential_fresh_processes': True, 'database_writes': False,
        'budget_seconds': 60, 'threads': 1, 'mandatory_encoding': 'appended',
        'new_linear_propagation': True}, indent=2), encoding='utf-8')
    for index, task in enumerate(tasks, 1):
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_sha
        print(f'RUN {index}/{len(tasks)} {task}', flush=True)
        subprocess.run([sys.executable, '-X', 'utf8', __file__, '--case', task['case'],
                        '--seed', str(task['seed']), '--mode', task['mode']], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

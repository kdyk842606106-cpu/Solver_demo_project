"""Read-only isolated diagnostics: same frozen recovery input and seed 37."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/causal-rank-diagnosis-20261106'
MODES = ['off', 'on', 'bounds-only', 'edges-only', 'off-no-lp', 'on-no-lp',
         'no-absent', 'no-present']


def single(mode, label):
    import benchmark_linear_propagation as runner
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.core import joint_cpsat as core
    OUT.mkdir(parents=True, exist_ok=True)
    runner.OUT = OUT
    original = core.cp_model.CpSolver.solve
    calls = []
    tag = mode + ('-' + label if label else '')

    def solve(self, model, *args, **kwargs):
        actual = model
        removed = []
        if mode in ('bounds-only', 'edges-only', 'no-absent', 'no-present'):
            actual = model.clone()
            for c in actual.proto.constraints:
                is_edge = c.name.startswith('causal_rank:support:')
                is_bound = c.name in ('causal_rank:present', 'causal_rank:absent')
                if ((mode == 'bounds-only' and is_edge) or (mode == 'edges-only' and is_bound)
                    or (mode == 'no-absent' and c.name == 'causal_rank:absent')
                    or (mode == 'no-present' and c.name == 'causal_rank:present')):
                    removed.append(c.name)
                    c.copy_from(type(c)())
        if mode.endswith('no-lp'):
            self.parameters.linearization_level = 0
        self.parameters.log_search_progress = True
        self.parameters.log_to_stdout = False
        self.parameters.log_subsolver_statistics = True
        index = len(calls)
        entry = {'index': index, 'removed_auxiliary_constraints': removed,
                 'parameters': str(self.parameters),
                 'actual_model_sha256': hashlib.sha256(str(actual.proto).encode()).hexdigest()}
        calls.append(entry)
        assert not actual.validate()
        if index == 0:
            (OUT / f'{tag}-initial-model.pbtxt').write_text(str(actual.proto), encoding='utf-8')
        with (OUT / f'{tag}-call{index}.log').open('w', encoding='utf-8') as log:
            self.log_callback = lambda line: log.write(line + '\n')
            started = time.perf_counter()
            status = original(self, actual, *args, **kwargs)
            entry.update(elapsed_seconds=time.perf_counter()-started, response_stats=self.response_stats())
        self.log_callback = None
        return status

    core.cp_model.CpSolver.solve = solve
    runner.single('recovery-current', 'new', 37, tag, encoding='appended',
                  causal_ranks=mode not in ('off', 'off-no-lp'))
    (OUT / f'{tag}-diagnostics.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=MODES)
    parser.add_argument('--label', default='')
    args = parser.parse_args()
    if args.mode:
        single(args.mode, args.label)
    else:
        # Separate processes, never overlap CPU searches or write to the database.
        for mode, label in [(m, '') for m in MODES] + [('on', 'repeat'), ('off', 'repeat'), ('no-absent', 'repeat')]:
            print('RUN', mode, label, flush=True)
            subprocess.run([sys.executable, '-X', 'utf8', __file__, '--mode', mode, '--label', label],
                           cwd=ROOT, check=True)

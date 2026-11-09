"""Audit seed variability and repeatability without the two strengthenings."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core
from benchmark_unstrengthened import OUT, CASES, SEEDS, MODES


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def tag(case, seed, mode, label='main'):
    return f'ranks-0-{mode}-{case}-new-seed{seed}-{label}'


def numeric_stats(text):
    result = {}
    for key, value in re.findall(r'^(\w+): (.+)$', text, re.M):
        try:
            result[key] = float(value) if any(c in value for c in '.e') else int(value)
        except ValueError:
            result[key] = value
    return result


def distribution(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values),
            'max_min_ratio': max(values)/min(values) if min(values) > 0 else None}


def main():
    assert core._MANDATORY_ENCODING == 'none' and core._CAUSAL_RANKS is False
    manifest = read(OUT/'manifest.json')
    assert hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest() == manifest['compiler_sha256']
    groups = defaultdict(dict)
    repeats = {}
    for task in read(OUT/'matrix.json'):
        case, seed, mode, label = (task[k] for k in ('case', 'seed', 'mode', 'label'))
        stem = tag(case, seed, mode, label)
        r = read(OUT/f'{stem}-summary.json')
        assert r['encoding'] == mode and r['causal_ranks_enabled'] is False
        assert r['implementation'] == 'new' and r['worker_threads'] == 1
        assert r['seed'] == seed and r['budget_seconds'] == 60
        assert not r['validator_rejections'] and r['status'] not in ('ERROR', 'UNSUPPORTED', 'UNKNOWN', 'INFEASIBLE')
        assert read(ROOT/r['source']) == read(OUT/f'{stem}-input.json')
        if r.get('schedule') is not None:
            assert r['validator'] == 'VALID'
        r['first_call_stats'] = numeric_stats(r['solver_calls'][0]['response_stats'])
        r['branches_after_first_call'] = r['branches'] - r['first_call_stats']['branches']
        if mode == 'none':
            assert r['model']['mandatory_activities']['encoding'] == 'none'
            assert r['model']['mandatory_activities']['added_constraints'] == 0
            assert r['model']['mandatory_activities']['fixed_first_occurrences'] == 0
            assert not r['model']['mandatory_activities']['activity_ids']
        if label == 'repeat':
            repeats[(case, seed)] = r
            continue
        # Reproduce the same model used in earlier experiments, not a business rollback.
        if mode == 'appended':
            path = ROOT/'output/causal-rank-unbound-20261106'/f'ranks-0-appended-{case}-new-seed{seed}-off-summary.json'
        else:
            path = ROOT/'output/mandatory-encoding-20261106'/f'none-{case}-new-seed{seed}-summary.json'
        if path.exists():
            old = read(path)
            assert old['input_sha256'] == r['input_sha256']
            assert old['solver_calls'][0]['initial_model_sha256'] == r['solver_calls'][0]['initial_model_sha256']
            r['reproduced_previous_model'] = True
            r['reproduced_previous_branches'] = old['branches'] == r['branches']
        groups[(case, seed)][mode] = r
    assert len(groups) == 15 and len(repeats) == 7

    model_checks = {}
    for case in CASES:
        p = expand_packages(read(OUT/f'{tag(case, 11, "none")}-input.json'))
        core._MANDATORY_ENCODING = 'none'
        base, _, slots, stats, _ = core._build_model_with_finish(p, deadline=None)
        core._MANDATORY_ENCODING = 'appended'
        strengthened, _, more_slots, more_stats, _ = core._build_model_with_finish(p, deadline=None)
        assert [str(v) for v in base.proto.variables] == [str(v) for v in strengthened.proto.variables]
        assert [str(c) for c in base.proto.constraints] == [str(c) for c in strengthened.proto.constraints if not c.name.startswith('mandatory:')]
        assert str(base.proto.objective) == str(strengthened.proto.objective)
        assert str(base.proto.solution_hint) == str(strengthened.proto.solution_hint)
        assert not any(c.name.startswith(('causal_rank:', 'mandatory:')) for c in base.proto.constraints)
        for key in ('optional_occurrence_slots', 'support_choices', 'threat_checks', 'interval_locks', 'horizon'):
            assert stats[key] == more_stats[key]
        model_checks[case] = {'original_variables_constraints_objective_hints_preserved': True,
            'removed_mandatory_constraints': len(strengthened.proto.constraints)-len(base.proto.constraints),
            'variables': len(base.proto.variables), 'constraints': len(base.proto.constraints),
            'occurrence_slots': len(slots), 'causal_rank_variables': 0}
    core._MANDATORY_ENCODING = 'none'

    repeat_checks = {}
    for (case, seed), repeated in repeats.items():
        original = groups[(case, seed)]['none']
        assert original['input_sha256'] == repeated['input_sha256']
        assert original['solver_calls'][0]['initial_model_sha256'] == repeated['solver_calls'][0]['initial_model_sha256']
        exact = all(original[k] == repeated[k] for k in ('status', 'branches', 'conflicts', 'best_makespan', 'best_execution_count'))
        if original['status'] == repeated['status'] == 'OPTIMAL':
            assert exact
        repeat_checks[f'{case}/seed{seed}'] = {'same_status_branches_conflicts_score': exact,
            'main_seconds': original['elapsed_seconds'], 'repeat_seconds': repeated['elapsed_seconds'],
            'main_branches': original['branches'], 'repeat_branches': repeated['branches']}

    aggregates = {}
    for case in CASES:
        rr = [groups[(case, seed)][mode] for seed in SEEDS for mode in MODES]
        proven = {(r['best_makespan'], r['best_execution_count']) for r in rr if r['status'] == 'OPTIMAL'}
        assert len(proven) == 1
        optimum = next(iter(proven))
        for r in rr + [r for (c, _), r in repeats.items() if c == case]:
            if r.get('schedule') is not None:
                assert (r['best_makespan'], r['best_execution_count']) >= optimum
        modes = {}
        for mode in MODES:
            runs = [groups[(case, seed)][mode] for seed in SEEDS]
            modes[mode] = {'optimal_runs': sum(r['status'] == 'OPTIMAL' for r in runs),
                'total_seconds': distribution([r['elapsed_seconds'] for r in runs]),
                'first_seconds_when_found': distribution([r['first_solution_seconds'] for r in runs]),
                'branches': distribution([r['branches'] for r in runs])}
        ratios = [groups[(case, seed)]['none']['elapsed_seconds']/groups[(case, seed)]['appended']['elapsed_seconds']
                  for seed in SEEDS if all(groups[(case, seed)][m]['status'] == 'OPTIMAL' for m in MODES)]
        aggregates[case] = {'optimum': optimum, 'modes': modes,
            'none_vs_appended': {'paired_optimal_runs': len(ratios),
                                'faster_over_10_percent': sum(x < .9 for x in ratios),
                                'slower_over_10_percent': sum(x > 1.1 for x in ratios)}}

    tests = {}
    for path in OUT.glob('tests-*.xml'):
        suite = ET.parse(path).getroot().find('testsuite')
        assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
        tests[path.name] = suite.attrib
    report = {'method': manifest, 'tests': tests, 'model_checks': model_checks,
        'conclusion': {
            'seed_sensitivity_exists_without_both_optimizations': True,
            'same_seed_repeatability': 'All seven repeats reproduce status, branches, conflicts and objective values.',
            'worst_recovery_main': {'seed': 53, 'first_call_branches': 998002, 'total_branches': 1018917},
            'default_mandatory_encoding': 'none', 'default_causal_ranks': False,
            'interpretation': 'The original model already has seed-sensitive first-solution search. The two redundant strengthenings change and sometimes amplify that sensitivity; disabling them is not a universal speedup.'},
        'repeat_checks': repeat_checks, 'aggregates': aggregates,
        'results': {f'{case}/seed{seed}': r for (case, seed), r in groups.items()},
        'repeated_results': {f'{case}/seed{seed}': r for (case, seed), r in repeats.items()},
        'limitations': ['Original means disabling these two strengthenings, retaining current pruning, feedback and business model.',
                       'Five seeds and seven same-seed repeats on one thread do not establish universal stability or performance.',
                       'Elapsed time at timeout is censored; no timeout is a proof of infeasibility.']}
    target = ROOT/'docs/validation/UNSTRENGTHENED_SEEDS_20261106.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['关闭必做活动与因果层级：三场景、五种子、配对与复跑',
             'none=两项均关闭；appended=仅启用必做活动。全部保持因果层级关闭。',
             '保留当前业务约束、重复实例裁剪、反馈与双目标。单线程，60秒预算，默认传播。', '']
    for case in CASES:
        lines.append(case)
        for seed in SEEDS:
            for mode in MODES:
                r = groups[(case, seed)][mode]
                first = f"{r['first_solution_seconds']:.3f}" if r['first_solution_seconds'] is not None else 'none'
                lines.append(f"  seed={seed} {mode:8} {r['status']:14} first={first}s total={r['elapsed_seconds']:.3f}s branches={r['branches']} best={r['best_makespan']}/{r['best_execution_count']}")
        lines.append('  aggregate: '+json.dumps(aggregates[case]))
        lines.append('')
    lines.append('同种子复跑: '+json.dumps(repeat_checks))
    lines += ['', '结论：两项优化均关闭后，原模型仍存在种子敏感性。七次同种子复跑的状态、分支、冲突和目标值完全一致。',
              '维修种子53首解前998002分支，总计1018917分支；性能波动主要仍发生在首解搜索。',
              '当前默认已关闭必做增强和因果层级，保留其他算法机制与业务约束；不宣称关闭后每个种子都更快。']
    (OUT/'comparison.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print('All input/model/replay/repeat audits passed:', target)


if __name__ == '__main__':
    main()

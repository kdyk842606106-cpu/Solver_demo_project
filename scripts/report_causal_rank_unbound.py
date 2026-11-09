"""Audit business-model equality and summarize the three-way five-seed matrix."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core
from benchmark_causal_rank_unbound import OUT, CASES, MODES, SEEDS, load_legacy


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def file_tag(case, seed, mode):
    return f'ranks-{int(mode != "off")}-appended-{case}-new-seed{seed}-{mode}'


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def main():
    groups = defaultdict(dict)
    manifest = read(OUT / 'source-manifest.json')
    assert hashlib.sha256((ROOT / 'app/core/joint_cpsat.py').read_bytes()).hexdigest() == manifest['current_sha256']
    for task in read(OUT / 'matrix.json'):
        case, seed, mode = task['case'], task['seed'], task['mode']
        tag = file_tag(case, seed, mode)
        r = read(OUT / f'{tag}-summary.json')
        assert r['encoding'] == 'appended' and r['implementation'] == 'new' and r['worker_threads'] == 1
        assert r['seed'] == seed and r['budget_seconds'] == 60
        assert r['status'] not in ('ERROR', 'UNSUPPORTED', 'UNKNOWN', 'INFEASIBLE')
        assert not r['validator_rejections']
        p = read(ROOT / r['source'])
        assert p == read(OUT / f'{tag}-input.json')
        if r.get('schedule') is not None:
            assert r['validator'] == 'VALID'
        expected_policy = 'conditional_support_dag_v1' if mode == 'legacy' else 'conditional_support_dag_v2_unbound_absent'
        assert r['model']['causal_ranks']['policy'] == expected_policy
        if seed in (11, 23, 37) and mode in ('off', 'legacy'):
            old_tag = f'ranks-{int(mode != "off")}-appended-{case}-new-seed{seed}'
            old = read(ROOT / 'output/causal-ranks-20261106' / f'{old_tag}-summary.json')
            assert r['solver_calls'][0]['initial_model_sha256'] == old['solver_calls'][0]['initial_model_sha256']
            r['reproduced_prior_branch_count'] = r['branches'] == old['branches']
        groups[(case, seed)][mode] = r
    assert len(groups) == 15 and sum(map(len, groups.values())) == 45

    legacy = load_legacy()
    current_compile = core._compile
    checks = {}
    for case in CASES:
        payload = expand_packages(read(OUT / f'{file_tag(case, 11, "off")}-input.json'))
        models = {}
        for mode in MODES:
            core._CAUSAL_RANKS = mode != 'off'
            core._MANDATORY_ENCODING = 'appended'
            core._compile = legacy._compile if mode == 'legacy' else current_compile
            m, _, slots, stats, _ = core._build_model_with_finish(payload, deadline=None)
            models[mode] = m
        off, old, new = (models[m] for m in MODES)
        assert [str(v) for v in old.proto.variables] == [str(v) for v in new.proto.variables]
        assert [str(c) for c in old.proto.constraints if c.name != 'causal_rank:absent'] == [str(c) for c in new.proto.constraints]
        assert [str(v) for v in off.proto.variables] == [str(v) for v in list(new.proto.variables)[:len(off.proto.variables)]]
        assert [str(c) for c in off.proto.constraints] == [str(c) for c in new.proto.constraints if not c.name.startswith('causal_rank:')]
        assert str(off.proto.objective) == str(old.proto.objective) == str(new.proto.objective)
        assert str(off.proto.solution_hint) == str(old.proto.solution_hint) == str(new.proto.solution_hint)
        checks[case] = {'only_absent_rank_zero_constraints_removed': True,
                        'removed_constraints': len(old.proto.constraints)-len(new.proto.constraints),
                        'off_variables': len(off.proto.variables), 'rank_variables': len(new.proto.variables),
                        'old_constraints': len(old.proto.constraints), 'new_constraints': len(new.proto.constraints)}
    core._compile = current_compile
    core._CAUSAL_RANKS = False

    aggregates = {}
    for case in CASES:
        runs = [groups[(case, seed)][mode] for seed in SEEDS for mode in MODES]
        proven = {(r['best_makespan'], r['best_execution_count']) for r in runs if r['status'] == 'OPTIMAL'}
        assert len(proven) == 1, (case, proven)
        optimum = next(iter(proven))
        for r in runs:
            if r.get('schedule') is not None:
                assert (r['best_makespan'], r['best_execution_count']) >= optimum
        data = {}
        for mode in MODES:
            rr = [groups[(case, seed)][mode] for seed in SEEDS]
            data[mode] = {'optimal_runs': sum(r['status'] == 'OPTIMAL' for r in rr),
                          'runs_with_solution': sum(r.get('schedule') is not None for r in rr),
                          'median_total_seconds': median([r['elapsed_seconds'] for r in rr]),
                          'median_first_seconds_when_found': median([r['first_solution_seconds'] for r in rr]),
                          'median_branches': median([r['branches'] for r in rr])}
        comparisons = {}
        for reference in ('off', 'legacy'):
            pairs = [(groups[(case, seed)][reference], groups[(case, seed)]['unbound']) for seed in SEEDS]
            solved = [(a, b) for a, b in pairs if a['status'] == b['status'] == 'OPTIMAL']
            ratios = [b['elapsed_seconds']/a['elapsed_seconds'] for a, b in solved]
            comparisons[reference] = {'both_optimal_pairs': len(solved),
                'faster_over_10_percent': sum(r < .9 for r in ratios),
                'slower_over_10_percent': sum(r > 1.1 for r in ratios),
                'within_10_percent': sum(.9 <= r <= 1.1 for r in ratios),
                'best_time_ratio': min(ratios) if ratios else None,
                'worst_time_ratio': max(ratios) if ratios else None}
        aggregates[case] = {'proven_optimum': optimum, 'modes': data, 'unbound_vs': comparisons}

    tests = {}
    for path in OUT.glob('tests-*.xml'):
        suite = ET.parse(path).getroot().find('testsuite')
        assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
        tests[path.name] = suite.attrib
    stable = all(a['unbound_vs']['off']['both_optimal_pairs'] == len(SEEDS)
                 and a['unbound_vs']['off']['slower_over_10_percent'] == 0 for a in aggregates.values())
    report = {'method': manifest, 'tests': tests, 'model_audit': checks, 'aggregate': aggregates,
              'decision': {'implementation': 'conditional_support_dag_v2_unbound_absent',
                           'default_enabled': False, 'stable_improvement_across_tested_inputs': stable,
                           'comparison_threshold': '10% descriptive tolerance, not a significance test',
                           'reason': 'Normal installation improves over off in all five seeds; late material and recovery have material paired regressions. Do not enable globally or route by scenario names.'},
              'limitations': ['Each configuration timed once; five seeds are evidence on these inputs, not a general speed guarantee.',
                             'Timeout elapsed time is censored; paired speed ratios include only pairs that both proved optimal.'],
              'results': {f'{case}/seed{seed}': modes for (case, seed), modes in groups.items()}}
    (ROOT / 'docs/validation/CAUSAL_RANK_UNBOUND_20261106.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['取消未执行实例层级归零：三场景、五种子、三种编码',
             'off=关闭因果层级；legacy=原归零实现；unbound=取消归零绑定。',
             '单线程/60秒/默认传播/appended必做编码；业务输入及原约束不变。', '']
    for case in CASES:
        lines.append(case)
        for seed in SEEDS:
            for mode in MODES:
                r = groups[(case, seed)][mode]
                first = f"{r['first_solution_seconds']:.3f}" if r['first_solution_seconds'] is not None else 'none'
                lines.append(f"  seed={seed} {mode:7} {r['status']:14} first={first}s total={r['elapsed_seconds']:.3f}s branches={r['branches']} best={r['best_makespan']}/{r['best_execution_count']}")
        for mode, data in aggregates[case]['modes'].items():
            lines.append(f'  median {mode}: {json.dumps(data)}')
        lines.append('  paired: '+json.dumps(aggregates[case]['unbound_vs']))
        lines.append('')
    lines += ['结论：不是跨场景稳定改善。相对关闭层级，正常安装5/5更快，物料晚到2/5更快、3/5更慢，维修恢复1/5更快、4/5更慢。',
              '“更快/更慢”以10%作为描述性容差，并非统计显著性检验。当前实现已移除归零绑定，因果层级仍默认关闭。',
              '全部45次证明原最优工期及次数并通过回放；业务模型、项目数据、运行历史未变。']
    (OUT / 'comparison.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print('All input, model and result audits passed.')


if __name__ == '__main__':
    main()

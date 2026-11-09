"""Compare CPU portfolios by wall time and proofs, not incomparable branch totals."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_multicore import OUT, CASES, SEEDS, WORKERS

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def spread(values):
    values = [x for x in values if x is not None]
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)} if values else None

def main():
    manifest = read(OUT/'manifest.json')
    current_sha = hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest()
    assert current_sha == manifest.get('operational_compiler_sha256', manifest['compiler_sha256'])
    groups = defaultdict(dict)
    repeats = {}
    for task in read(OUT/'matrix.json'):
        case, seed, workers = task['case'], task['seed'], task['workers']
        label = f'w{workers}' + ('-repeat' if task['repeat'] else '')
        tag = f'ranks-0-none-{case}-new-seed{seed}-{label}'
        r = read(OUT/f'{tag}-summary.json')
        full = read(OUT/f'{tag}-result.json')
        assert r['encoding'] == 'none' and not r['causal_ranks_enabled']
        assert r['worker_threads'] == workers and r['budget_seconds'] == 60
        assert r['implementation'] == 'new' and r['seed'] == seed
        assert not r['validator_rejections'] and r['status'] not in ('ERROR', 'UNSUPPORTED', 'UNKNOWN', 'INFEASIBLE')
        assert read(ROOT/r['source']) == read(OUT/f'{tag}-input.json')
        assert r['model']['mandatory_activities']['added_constraints'] == 0
        assert r['model']['causal_ranks']['variables'] == 0
        assert r['solver_calls'][0]['worker_threads'] == workers
        assert all(c['worker_threads'] in (1, workers) for c in r['solver_calls'])
        if r.get('schedule'):
            assert r['validator'] == 'VALID'
        samples = [json.loads(line) for line in (OUT/f'{tag}-progress.jsonl').read_text(encoding='utf-8').splitlines()]
        counters = [m['branches'] for m in samples if 'branches' in m]
        assert counters == sorted(counters)
        if workers > 1:
            assert all(m.get('branches_per_second') is None for m in samples)
            assert full['stats']['search_counter_scope'] == 'solver_response_per_epoch'
        r['feedback_restarts'] = full['stats']['feedback_restarts']
        r['average_cpu_cores_over_result_wall_time'] = r['process_cpu_seconds']/r['elapsed_seconds']
        if task['repeat']:
            repeats[(case, seed, workers)] = r
        else:
            groups[(case, seed)][workers] = r
    assert len(groups) == 15 and len(repeats) == 6
    for (case, seed), modes in groups.items():
        assert len(modes) == 3
        one = modes[1]
        prior = read(ROOT/'output/unstrengthened-20261106'/f'ranks-0-none-{case}-new-seed{seed}-main-summary.json')
        for r in modes.values():
            assert r['input_sha256'] == one['input_sha256'] == prior['input_sha256']
            assert r['solver_calls'][0]['initial_model_sha256'] == prior['solver_calls'][0]['initial_model_sha256']
        if one['status'] == prior['status'] == 'OPTIMAL':
            assert one['branches'] == prior['branches']
    aggregates = {}
    for case in CASES:
        runs = [r for (c, _), modes in groups.items() if c == case for r in modes.values()]
        runs += [r for (c, _, _), r in repeats.items() if c == case]
        optima = {(r['best_makespan'], r['best_execution_count']) for r in runs if r['status'] == 'OPTIMAL'}
        assert len(optima) == 1
        optimum = next(iter(optima))
        for r in runs:
            if r.get('schedule'):
                assert (r['best_makespan'], r['best_execution_count']) >= optimum
        data = {}
        for workers in WORKERS:
            rr = [groups[(case, seed)][workers] for seed in SEEDS]
            pairs = [(groups[(case, seed)][1], groups[(case, seed)][workers]) for seed in SEEDS]
            ratios = [b['elapsed_seconds']/a['elapsed_seconds'] for a, b in pairs if a['status'] == b['status'] == 'OPTIMAL']
            data[workers] = {'optimal_runs': sum(r['status'] == 'OPTIMAL' for r in rr),
                'first_seconds': spread([r['first_solution_seconds'] for r in rr]),
                'total_seconds': spread([r['elapsed_seconds'] for r in rr]),
                'cpu_seconds': spread([r['process_cpu_seconds'] for r in rr]),
                'faster_than_single_over_10_percent': sum(x < .9 for x in ratios),
                'slower_than_single_over_10_percent': sum(x > 1.1 for x in ratios)}
        aggregates[case] = {'optimum': optimum, 'workers': data}
    repeat_data = {}
    for (case, seed, workers), r in repeats.items():
        base = groups[(case, seed)][workers]
        repeat_data[f'{case}/seed{seed}/w{workers}'] = {
            'first_seconds': [base['first_solution_seconds'], r['first_solution_seconds']],
            'total_seconds': [base['elapsed_seconds'], r['elapsed_seconds']],
            'status': [base['status'], r['status']],
            'reported_branches': [base['branches'], r['branches']]}
    tests = {}
    for path in OUT.glob('tests-*.xml'):
        suite = ET.parse(path).getroot().find('testsuite')
        assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
        tests[path.name] = suite.attrib
    report = {'method': manifest, 'tests': tests, 'aggregate': aggregates, 'repeats': repeat_data,
        'results': {f'{case}/seed{seed}': r for (case, seed), r in groups.items()},
        'repeat_results': {f'{case}/seed{seed}/w{workers}': r for (case, seed, workers), r in repeats.items()},
        'model_audit': 'Every initial model hash matches the prior single-thread unstrengthened model; no business constraint, hint or objective added.',
        'limitations': ['Parallel runs may differ even with the same seed; the six repeats sample this variability, not a deterministic guarantee.',
                       'CP-SAT response branch/conflict counts are from its first subsolver. They are not summed parallel work and not a speedup measure.',
                       'CPU seconds sum thread CPU usage; elapsed times include validation and feedback. No linear scaling guarantee.'],
        'references': ['https://github.com/google/or-tools/blob/v9.15/ortools/sat/sat_parameters.proto',
                       'https://github.com/google/or-tools/blob/v9.15/ortools/sat/cp_model.proto']}
    target = ROOT/'docs/validation/MULTICORE_20261106.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['联合求解CPU多线程对照：两项增强关闭，原业务模型不变', '1/4/8线程，五个种子；另对种子53复跑4/8线程。', '']
    for case in CASES:
        lines.append(case)
        for seed in SEEDS:
            for workers in WORKERS:
                r = groups[(case, seed)][workers]
                first = f"{r['first_solution_seconds']:.3f}" if r['first_solution_seconds'] is not None else 'none'
                lines.append(f"  seed={seed} workers={workers} {r['status']:14} first={first}s total={r['elapsed_seconds']:.3f}s CPU={r['process_cpu_seconds']:.3f}s best={r['best_makespan']}/{r['best_execution_count']}")
        lines.append('  aggregate: '+json.dumps(aggregates[case]))
        lines.append('')
    lines += ['复跑: '+json.dumps(repeat_data), '', '多线程报告分支数不代表所有线程总和，不以分支减少量计算加速比。']
    (OUT/'comparison.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print('All model, input, replay and progress checks passed:', target)

if __name__ == '__main__':
    main()

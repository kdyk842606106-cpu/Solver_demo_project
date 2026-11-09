"""Audit paired historical-hard-case replays; distinguish timeouts from proofs."""
import hashlib
import json
from pathlib import Path

from benchmark_multicore_hard import ROOT, OUT, CASES


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    manifest = read(OUT/'manifest.json')
    assert hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest() == manifest['compiler_sha256']
    records = {}
    for task in manifest['tasks']:
        case, workers = task['case'], task['workers']
        tag = f'ranks-0-none-{case}-new-seed11-w{workers}' + ('-repeat' if task['repeat'] else '')
        r = read(OUT/f'{tag}-summary.json')
        full = read(OUT/f'{tag}-result.json')
        source, seconds = CASES[case]
        assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest() == manifest['source_sha256'][case]
        original = read(ROOT/source)
        if case == 'calendar-night-150':
            original = original['request']['effective_scenario_snapshot']
        assert original == read(OUT/f'{tag}-input.json')
        assert r['encoding'] == 'none' and r['causal_ranks_enabled'] is False
        assert r['worker_threads'] == workers and r['budget_seconds'] == seconds and r['seed'] == 11
        assert r['model']['mandatory_activities']['added_constraints'] == 0
        assert r['model']['causal_ranks']['variables'] == 0
        assert not r['validator_rejections'] and not full.get('error')
        assert r['status'] in ['OPTIMAL', 'TIMEOUT_PARTIAL', 'TIMEOUT_EMPTY', 'FEASIBLE']
        if full['paths']:
            assert all(p['validator_status'] == 'VALID' for p in full['paths'])
        if r['status'] == 'OPTIMAL':
            assert r['makespan_proven_optimal'] and r['execution_count_proven_optimal']
        assert r['solver_calls'][0]['worker_threads'] == workers
        assert all(c['worker_threads'] in (1, workers) for c in r['solver_calls'])
        samples = [json.loads(line) for line in (OUT/f'{tag}-progress.jsonl').read_text(encoding='utf-8').splitlines()]
        counts = [s['branches'] for s in samples if 'branches' in s]
        assert counts == sorted(counts)
        if workers == 8:
            assert all(s.get('branches_per_second') is None for s in samples)
        improvements = [s for s in samples if s['improved']]
        r['improvements'] = [{k:s.get(k) for k in ['observed_seconds', 'best_makespan', 'best_execution_count', 'lower_bound']} for s in improvements]
        r['best_by_60_seconds'] = next((s for s in reversed(r['improvements']) if s['observed_seconds'] <= 60), None)
        r['feedback_restarts'] = full['stats']['feedback_restarts']
        r['activity_count'] = len(original['activities'])
        selected = full['paths'][0]['executions'] if full['paths'] else []
        used = {e['activity_id'] for e in selected}
        r['distinct_executed_activities'] = len(used)
        r['repeat_executions'] = len(selected) - len(used)
        r['average_cpu_cores'] = r['process_cpu_seconds']/r['elapsed_seconds']
        records[f'{case}/w{workers}' + ('/repeat' if task['repeat'] else '')] = r
    comparisons = {}
    for case in CASES:
        a, b = records[f'{case}/w1'], records[f'{case}/w8']
        rr = [v for k,v in records.items() if k.startswith(case+'/')]
        assert len({r['input_sha256'] for r in rr}) == 1
        assert len({r['solver_calls'][0]['initial_model_sha256'] for r in rr}) == 1
        proven = {(r['best_makespan'], r['best_execution_count']) for r in rr if r['status'] == 'OPTIMAL'}
        assert len(proven) <= 1
        if proven:
            optimum = next(iter(proven))
            assert all((r['best_makespan'], r['best_execution_count']) >= optimum for r in rr if r.get('schedule'))
        comparisons[case] = dict(
            total_time_ratio_single_over_eight=a['elapsed_seconds']/b['elapsed_seconds'] if a['status'] == b['status'] == 'OPTIMAL' else None,
            one_status=a['status'], eight_status=b['status'],
            one_score=[a['best_makespan'],a['best_execution_count']], eight_score=[b['best_makespan'],b['best_execution_count']],
        )
    result = dict(method=manifest, comparisons=comparisons, results=records,
        audits=['Identical frozen business inputs and initial CP-SAT model hashes for each thread pair.',
                'Both mandatory strengthening and causal ranks disabled; existing pruning/feedback unchanged.',
                'All displayed schedules replay VALID; no validation rejection.',
                'Fresh sequential processes; no database reads/writes, no manually supplied schedules or hints.'],
        limitations=['One paired seed plus three parallel repeats; not a broad performance guarantee.',
                     'Parallel reported branches/conflicts are first-subsolver statistics, not totals.',
                     'Historical results used older compilers; isolate CPU effects using the new paired runs.'])
    target = ROOT/'docs/validation/MULTICORE_HARD_20261106.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['历史难例：当前代码 1/8 线程对照，seed=11，业务输入和模型哈希一致。', '']
    for key, r in records.items():
        lines.append(f"{key}: {r['status']} first={r['first_solution_seconds']} total={r['elapsed_seconds']:.3f}s best={r['best_makespan']}/{r['best_execution_count']} bound={r['lower_bound']} reported_branches={r['branches']} replay={r.get('validator')}")
    lines.extend(['', '分支数不是所有线程合计；超时耗时不计算证明最优的加速比。', '所有输入、模型及回放检查通过。'])
    (OUT/'comparison.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print(target)


if __name__ == '__main__':
    main()

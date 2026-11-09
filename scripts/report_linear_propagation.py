"""Audit paired solver regression artifacts, preserving timeouts as timeouts."""
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/linear-propagation-regression-20261106'
from benchmark_linear_propagation import CASES

def load(case, implementation, suffix=''):
    return json.loads((OUT / f'{case}-{implementation}-seed11{suffix}-summary.json').read_text(encoding='utf-8'))

report = {'method': {'only_changed_parameter': 'new_linear_propagation',
    'new': True, 'old': False, 'mandatory_detection_enabled_in_both': True,
    'seed': 11, 'threads': 1, 'independent_sequential_processes': True,
    'constraints_preserved_within_each_pair': True, 'production_settings_changed': False,
    'project_or_history_writes': False,
    'scope': 'Frozen case-specific snapshots; historical repair and hypothetical disassembly-only cases retain their original rules.'},
    'cases': {}}
for case in CASES:
    pair = {implementation: load(case, implementation) for implementation in ('new','old')}
    new, old = pair['new'], pair['old']
    assert new['input_sha256'] == old['input_sha256']
    assert new['solver_calls'][0]['initial_model_sha256'] == old['solver_calls'][0]['initial_model_sha256']
    assert new['budget_seconds'] == old['budget_seconds']
    for result in pair.values():
        assert result['worker_threads'] == 1 and result['seed'] == 11
        assert not result['validator_rejections']
        if result.get('schedule') is not None:
            assert result['validator'] == 'VALID'
            result['execution_counts_by_activity'] = dict(Counter(x['name'] for x in result['schedule']))
        assert result['model']['mandatory_activities']['policy'] == 'unique_support_presence_v1'
    both_optimal = new['status'] == old['status'] == 'OPTIMAL'
    if both_optimal:
        assert new['best_makespan'] == old['best_makespan']
        assert new['best_execution_count'] == old['best_execution_count']
    report['cases'][case] = {
        'source': new['source'], 'identical_inputs_and_initial_models': True,
        'both_proven_optimal': both_optimal,
        'equal_best_makespan': new['best_makespan'] == old['best_makespan'],
        'equal_best_execution_count': new['best_execution_count'] == old['best_execution_count'],
        'old_to_new_elapsed_ratio': old['elapsed_seconds'] / new['elapsed_seconds'],
        'runs': pair}
    for mode in ('new','old'):
        repeat = OUT / f'{case}-{mode}-seed11-repeat-summary.json'
        if repeat.exists():
            again = load(case, mode, '-repeat')
            for key in ('input_sha256','status','best_makespan','best_execution_count','branches','conflicts'):
                assert again[key] == pair[mode][key], (case, mode, key)
            report['cases'][case].setdefault('repeat', {})[mode] = again

target = ROOT / 'docs/validation/LINEAR_PROPAGATION_REGRESSION_20261106.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('Report:', target)
for case, entry in report['cases'].items():
    for mode, r in entry['runs'].items():
        print(case, mode, r['status'], 'first', r['first_solution_seconds'], 'total', r['elapsed_seconds'],
              'branches',r['branches'], 'makespan',r['best_makespan'], 'executions',r['best_execution_count'])

"""Verify paired benchmark inputs/models/results and save the comparison report."""
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core

OUT = ROOT / 'output/mandatory-normal-late-20261106'
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

source = read(OUT / 'source.json')
report = {'source_revision': source['revision'], 'method': {
    'seed': 11, 'worker_threads': 1, 'budget_seconds': 60,
    'sequential_fresh_processes': True, 'project_or_history_writes': False,
    'only_toggle': 'unique-support mandatory activity presence constraints',
    'limits': 'One seed; late case repeated in reverse order. Not a general performance guarantee.'},
    'inputs': read(OUT / 'inputs-verified.json'), 'cases': {}}
for case, expected_count, makespan, executions in [('normal', 10, 400, 10), ('late', 11, 1570, 14)]:
    p = read(OUT / f'{case}-input.json')
    for key, value in source['scenario'].items():
        if key not in {'initial_state_ids', 'goal_state_ids', 'calendar_context', 'max_steps', 'run_time_windows'}:
            assert p[key] == value, key
    summaries = {}
    for mode in ('baseline', 'mandatory'):
        assert read(OUT / f'{case}-{mode}-seed11-input.json') == p
        s = read(OUT / f'{case}-{mode}-seed11-summary.json')
        assert s['status'] == 'OPTIMAL' and s['proven_optimal'] and s['validator'] == 'VALID'
        assert s['best_makespan'] == s['lower_bound'] == makespan
        assert s['best_execution_count'] == executions
        assert s['seed'] == 11 and s['worker_threads'] == 1 and s['budget_seconds'] == 60
        if case == 'late':
            counts = Counter(x['name'] for x in s['schedule'])
            assert counts['安全验收'] == counts['上电'] == 2
            install = next(x for x in s['schedule'] if x['name'] == '联调扩展件安装')
            assert install['start'] == 1440
            assert all(x['end'] < 1440 for x in s['schedule'] if x['name'] in ('模块A功能调测', '模块B调测'))
        summaries[mode] = s
    assert summaries['baseline']['input_sha256'] == summaries['mandatory']['input_sha256']
    effective = expand_packages(p)
    new, _, _, stats, _ = core._build_model_with_finish(effective, deadline=None)
    original = core.identify_mandatory_activities
    try:
        core.identify_mandatory_activities = lambda *a, **k: (set(), {'proofs': {}})
        old, _, _, _, _ = core._build_model_with_finish(effective, deadline=None)
    finally:
        core.identify_mandatory_activities = original
    assert [str(x) for x in old.proto.variables] == [str(x) for x in new.proto.variables]
    assert str(old.proto.objective) == str(new.proto.objective)
    assert str(old.proto.solution_hint) == str(new.proto.solution_hint)
    assert [str(c) for c in old.proto.constraints] == [str(c) for c in new.proto.constraints if not c.name.startswith('mandatory:')]
    assert len(new.proto.constraints) - len(old.proto.constraints) == expected_count
    assert len(stats['mandatory_activities']['activity_ids']) == expected_count
    entry = {'results': summaries, 'model_check': {
        'variables_objective_hints_and_existing_constraints_identical': True,
        'only_added_presence_constraints': expected_count,
        'paired_inputs_identical': True, 'source_business_configuration_preserved': True}}
    if case == 'late':
        entry['repeat_reverse_order'] = {}
        for mode in ('mandatory', 'baseline'):
            repeat = read(OUT / 'repeat' / f'{case}-{mode}-seed11-summary.json')
            for key in ('input_sha256', 'status', 'branches', 'conflicts', 'best_makespan', 'best_execution_count', 'validator'):
                assert repeat[key] == summaries[mode][key], key
            entry['repeat_reverse_order'][mode] = repeat
    report['cases'][case] = entry
report['conclusion'] = {
    'solution_quality': 'Both cases retain the proven optimal makespan and execution count; all returned schedules pass replay validation.',
    'normal': 'Small wall-time difference; branch count increases. Equal-optimal installation ordering may differ.',
    'late': 'Reproducible performance regression: about 6.1x wall time. Mandatory detection is not a universal acceleration.',
    'cause_limit': 'The only model delta is entailed presence constraints. The exact internal presolve/search cause was not profiled.'}
target = ROOT / 'docs/validation/MANDATORY_NORMAL_LATE_20261106.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(target), 'checks': 'passed', 'conclusion': report['conclusion']}, ensure_ascii=False))

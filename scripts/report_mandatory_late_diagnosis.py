"""Summarize diagnostic evidence without touching live projects or solver settings."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core

OUT = ROOT / 'output/mandatory-late-diagnosis-20261106'
def load(tag):
    return json.loads((OUT / f'{tag}.json').read_text(encoding='utf-8'))
def response_stats(text):
    values = {}
    for key, value in re.findall(r'^(\w+): ([^\n]+)', text, re.M):
        try:
            values[key] = float(value) if any(c in value for c in '.e') else int(value)
        except ValueError:
            values[key] = value
    return values

tags = ['baseline', 'mandatory', 'baseline-no-lp', 'mandatory-no-lp',
        'baseline-old-linear', 'mandatory-old-linear', 'mandatory-old-linear-repeat']
if (OUT / 'mandatory-loop-factor1.json').exists():
    tags.append('mandatory-loop-factor1')
report = {'ortools_version': '9.15.6755', 'seed': 11, 'threads': 1, 'budget_seconds': 60,
          'input': 'output/mandatory-normal-late-20261106/late-input.json',
          'business_constraints_changed': False, 'production_solver_settings_changed': False,
          'database_writes': False, 'runs': {}}
for tag in tags:
    data = load(tag)
    result = data['result']
    base = 'baseline' if tag.startswith('baseline') else 'mandatory'
    assert (OUT / f'{tag}-call1.pbtxt').read_bytes() == (OUT / f'{base}-call1.pbtxt').read_bytes()
    assert result['status'] == 'OPTIMAL' and result['proven_optimal']
    assert result['stats']['best_makespan'] == 1570 and result['stats']['best_execution_count'] == 14
    assert result['paths'][0]['validator_status'] == 'VALID'
    log = (OUT / f'{tag}-call1.log').read_text(encoding='utf-8')
    first = response_stats(data['solver_calls'][0]['response_stats'])
    pre = re.search(r'Starting search at ([\d.]+)s', log)
    lp = re.search(r"Lp stats[^\n]*\n\s*'main':\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", log)
    report['runs'][tag] = {
        'parameters': data['parameters'], 'status': result['status'],
        'first_solution_seconds': result['first_solution_seconds'], 'elapsed_seconds': result['elapsed_seconds'],
        'build_seconds': result['stats']['build_seconds'],
        'mandatory_identification_seconds': result['stats']['model']['mandatory_activities'].get('seconds'),
        'replay_seconds': sum(data['replay_seconds']),
        'after_first_solution_seconds': result['elapsed_seconds'] - result['first_solution_seconds'],
        'first_search': first, 'presolve_to_search_seconds_rounded': float(pre.group(1)) if pre else None,
        'lp_optimal_status_counter': int(lp.group(4).replace("'", '')) if lp else None,
        'total_branches': result['stats']['branches'],
        'total_conflicts': result['stats']['conflicts'], 'makespan': 1570, 'executions': 14, 'validator': 'VALID',
        'initial_model_identical_to_same_presence_mode': True}

for key in ('branches', 'conflicts', 'integer_propagations', 'propagations', 'lp_iterations', 'deterministic_time'):
    assert report['runs']['mandatory-old-linear']['first_search'][key] == report['runs']['mandatory-old-linear-repeat']['first_search'][key]

payload = json.loads((ROOT / report['input']).read_text(encoding='utf-8'))
model, _, slots, stats, _ = core._build_model_with_finish(expand_packages(payload), deadline=None)
baseline_domains = load('baseline-presolve')['solver_calls'][0]['tightened_domains']
mandatory_domains = load('mandatory-presolve')['solver_calls'][0]['tightened_domains']
names = {a['id']: a['name'] for a in payload['activities']}
fixed = []
for aid in stats['mandatory_activities']['activity_ids']:
    slot = next(s for s in slots if s.aid == aid and s.ordinal == 1)
    variable_name = model.proto.variables[slot.present.index].name
    assert baseline_domains[variable_name] == mandatory_domains[variable_name] == [1, 1]
    fixed.append({'activity': names[aid], 'presence_variable': variable_name, 'baseline_presolve_domain': [1, 1]})
report['presolve'] = {
    'all_11_mandatory_presences_already_fixed_by_baseline_presolve': fixed,
    'same_presolved_counts': {'variables': 564, 'booleans': 437, 'intervals': 30,
                            'optional_intervals': 19, 'linear2': 806, 'cumulative': 3, 'no_overlap': 5},
    'domain_differences': {k: {'baseline': v, 'mandatory': mandatory_domains[k]}
                           for k, v in baseline_domains.items() if v != mandatory_domains[k]},
    'model_horizon_working_minutes': stats['horizon']}
report['findings'] = [
    'The regression is almost entirely before the first validated candidate. Build, detection, replay, feedback certification and count minimization do not explain the 31-second increase.',
    'Baseline presolve already fixes the same 11 first-occurrence presence variables. The added constraints provide no additional presence reduction in this particular case, but change presolve transformations and search trajectory.',
    'Mandatory first search has 20,677,690 integer propagations versus 6,359,231; LP OPTIMAL counter is 1,765,413 versus 86,320. Branch count alone hides the much higher work per search.',
    'Ablation of LP relaxation alone reduces mandatory time to about 21 seconds but leaves a strong regression. It does not isolate LP as the sole cause.',
    'Switching only new_linear_propagation to false, with byte-identical initial models, reduces both modes to about 1.3 seconds. Mandatory repeat preserves exact branch/conflict counts. This isolates an unfavorable interaction with the default linear propagation/search path.',
    'Changing propagation_loop_detection_factor from 10 to 1 alone leaves the first-search branch, conflict and propagation counters identical; that threshold does not resolve this case.',
    'Large working-time domains (44,940) and conditional state support/threat/interval inequalities are present in both cases. They are plausible amplifiers, not a separately measured cause.',
    'This is not proof of an OR-Tools correctness bug, nor a C++ instruction-level profile. Parameter changes also change the search path; native per-propagator CPU attribution remains unavailable.',
    'No production solver setting or business rule was changed. These are independent diagnostic experiments on one frozen case and seed.'
]
report['official_parameter_reference'] = 'https://github.com/google/or-tools/blob/v9.15/ortools/sat/sat_parameters.proto#L1444-L1447'
target = ROOT / 'docs/validation/MANDATORY_LATE_DIAGNOSIS_20261106.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(target), 'checks': 'passed',
                  'baseline_already_fixed_mandatory_count': len(fixed),
                  'runs': report['runs']}, ensure_ascii=False))

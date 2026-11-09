"""Measure the fixed compiler on 0..5 renewable installation cycles.

No API/database writes, hints, or warm starts. Optional explicit per-activity cap.
Each measurement runs in a fresh process with the normal automatic budget.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAIRS = [
    ('传动单元吊装就位', '拆卸传动单元'),
    ('机架吊装就位', '拆卸机架'),
    ('电控柜安装接线', '拆卸电控柜'),
    ('管路安装与密封检查', '拆卸管路阀组'),
    ('传感器安装与标定', '拆卸传感器'),
]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def make_case(count, max_instances=None):
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    s = json.loads((ROOT/'deploy/examples/assembly-commissioning-20.json').read_text('utf-8'))
    s['id'] = f'benchmark:dismantle-{count}'
    s['name'] = f'机械组装拆卸循环规模测试｜{count}对'
    s['activity_packages'] = []
    s['activity_package_memberships'] = []
    s.pop('activity_package_scope_ids', None)
    for activity in s['activities']:
        activity['max_instances'] = None
    for index, (install_name, dismantle_name) in enumerate(PAIRS[:count], 1):
        install = next(a for a in s['activities'] if a['name'] == install_name)
        state = f'benchmark:dismantled:{index}'
        s['activities'].append({
            'id': f'benchmark:dismantle:{index}', 'name': dismantle_name,
            'duration': 15, 'output_state_id': state, 'max_instances': None,
            'preconditions': [{'state_id': install['output_state_id'], 'relation_role': 'transition'}],
            'resource_reqs': copy.deepcopy(install['resource_reqs']),
        })
        s['states'].append({'id': state, 'name': dismantle_name+'完成', 'state_kind': 'seed'})
        # The seed permits the first installation; subsequent installation
        # consumes the same state produced by dismantling. No dead-start cycle.
        s['initial_state_ids'].append(state)
        install['preconditions'].append({'state_id': state, 'relation_role': 'transition'})
    if max_instances is not None:
        for activity in s['activities']:
            activity['max_instances'] = max_instances
    bound = automatic_execution_bound(s)
    s['max_steps'] = bound['value']
    return s, bound, automatic_solver_budget(s)


def measure(count, out, max_instances=None):
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.core.joint_cpsat import solve_joint, prepare_payload, replay_candidate
    from planner_experiment.models import Budget, to_primitive
    from planner_experiment.scenario import scenario_from_dict
    s, bound, budget = make_case(count, max_instances)
    save(out/f'{count}-input.json', s)
    samples = []
    started = time.perf_counter()
    result = solve_joint(s, run_id=f'pairs-benchmark:{count}', seed=11,
                         budget=Budget(budget['time_limit_seconds'], 1, 3),
                         progress_observer=lambda m, p: samples.append({
                             'elapsed': time.perf_counter()-started, **m,
                             'improved_candidate': p is not None,
                         }))
    primitive = to_primitive(result)
    save(out/f'{count}-result.json', primitive)
    save(out/f'{count}-samples.json', samples)
    stats = result.stats
    model = stats.get('model', {})
    assert model.get('causal_protection_encoding') == 'shared_support_time_v1'
    best = result.paths[0] if result.paths else None
    summary = {
        'pairs': count, 'candidate_activities': len(s['activities']),
        'per_activity_max_instances': max_instances,
        'automatic_bound': bound, 'budget_seconds': budget['time_limit_seconds'],
        'status': result.status, 'elapsed_seconds': stats['elapsed_seconds'],
        'build_seconds': stats.get('build_seconds'), 'first_solution_seconds': result.first_solution_seconds,
        'branches': stats.get('branches'), 'conflicts': stats.get('conflicts'),
        'slots': model.get('optional_occurrence_slots'), 'variables': model.get('variables'),
        'constraints': model.get('constraints'), 'support_choices': model.get('support_choices'),
        'threat_checks': model.get('threat_checks'), 'interval_locks': model.get('interval_locks'),
        'lower_bound': stats.get('lower_bound'),
        'makespan': best.metrics.makespan if best else None,
        'executions': len(best.executions) if best else None,
        'dismantle_executions': sum(e.activity_id.startswith('benchmark:dismantle:') for e in best.executions) if best else None,
        'validator': best.validator_status if best else None,
        'error': result.error,
    }
    # Validate the baseline plan AFTER solving, never feed it to the solver.
    # This distinguishes search failure from actual infeasibility in timeouts.
    baseline = primitive if count == 0 else json.loads((out/'0-result.json').read_text('utf-8'))
    reference = baseline['paths'][0]
    rows = [{'activity_id': e['activity_id'], 'ordinal': e['ordinal'],
             'start': e['start_time'], 'end': e['end_time']} for e in reference['executions']]
    effective = prepare_payload(s)
    witness, _ = replay_candidate(s, scenario_from_dict(effective), rows, run_id='witness-after-solve', seed=11)
    assert witness.validator_status == 'VALID' and witness.metrics.makespan == 515
    summary['independent_515_minute_reference_replay'] = 'VALID; not provided to solver'
    save(out/f'{count}-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', type=int, choices=range(6))
    p.add_argument('--max-instances', type=int, help='Maximum executions per activity, including the first')
    args = p.parse_args()
    if args.max_instances is not None and args.max_instances < 1:
        p.error('--max-instances must be positive')
    out = args.output.resolve()
    if args.case is not None:
        measure(args.case, out, args.max_instances)
        return
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        'seed': 11, 'solver_threads': 1, 'repeat_measurements_per_case': 1,
        'per_activity_max_instances': args.max_instances,
        'python': sys.version, 'platform': platform.platform(), 'cpu_count': os.cpu_count(),
        'compiler_sha256': hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest(),
        'pairs': PAIRS, 'database_writes': False, 'same_machine': True,
        'notes': 'Optional dismantling only; extra initial dismantled tokens seed each cycle; no solver hints.',
    }
    save(out/'manifest.json', manifest)
    results = []
    for count in range(6):
        print(f'START {count} pairs (automatic budget 60 seconds)', flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), '--output', str(out), '--case', str(count)]
        if args.max_instances is not None:
            command.extend(['--max-instances', str(args.max_instances)])
        subprocess.run(command,
                       cwd=ROOT, check=True, timeout=150,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        results.append(json.loads((out/f'{count}-summary.json').read_text('utf-8')))
        save(out/'summary.json', {'settings': manifest, 'results': results})


if __name__ == '__main__':
    main()

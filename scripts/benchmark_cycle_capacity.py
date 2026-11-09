"""Isolated 5/10/15/20-pair capacity measurements; no API/database mutation.

Clone the existing 20-activity assembly fixture in blocks of five pairs,
sharing original resources. Compare optional dismantling with forced repair.
No hints are provided. A serial feasibility witness is replayed AFTER solving.
"""
import argparse
from collections import Counter
import copy
import ctypes
from ctypes import wintypes
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
from scripts.benchmark_install_dismantle_pairs import make_case, PAIRS, save


def make_capacity_case(pairs, forced):
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    assert pairs in (5, 10, 15, 20)
    base, _, _ = make_case(5, 3)
    result = copy.deepcopy(base)
    result.update(id=f'capacity:{pairs}:{forced}', name=f'{pairs}对拆装容量测试｜强制维修={forced}',
                  activities=[], states=[], initial_state_ids=[], goal_state_ids=[],
                  state_packages=[], state_package_memberships=[],
                  provenance={'fixture': 'cycle_capacity_cap3', 'pairs': pairs, 'required_repair': forced})
    pair_ids = []
    for block in range(pairs // 5):
        prefix = f'block:{block}:'
        ids = {x['id']: prefix + x['id'] for x in base['activities'] + base['states']}

        def remap(value):
            if isinstance(value, str):
                return ids.get(value, value)
            if isinstance(value, list):
                return [remap(v) for v in value]
            if isinstance(value, dict):
                return {k: remap(v) for k, v in value.items()}
            return value

        cloned = remap(base)
        result['activities'].extend(cloned['activities'])
        result['states'].extend(cloned['states'])
        result['initial_state_ids'].extend(cloned['initial_state_ids'])
        result['goal_state_ids'].extend(cloned['goal_state_ids'])
        for i, (install_name, _) in enumerate(PAIRS, 1):
            install = next(a for a in cloned['activities'] if a['name'] == install_name)
            dismantle = next(a for a in cloned['activities'] if a['id'] == prefix + f'benchmark:dismantle:{i}')
            repair_id = prefix + f'repair:{i}'
            pair_ids.append({'install': install['id'], 'dismantle': dismantle['id'],
                             'repair': repair_id if forced else None})
            if forced:
                # This certificate is absent initially and only dismantling produces it.
                certificate = prefix + f'dismantle-certificate:{i}'
                repaired = prefix + f'repaired:{i}'
                dismantle['additional_output_state_ids'] = [certificate]
                result['states'].extend([{'id': certificate, 'name': '拆卸实施完成'},
                                         {'id': repaired, 'name': '维修完成'}])
                result['activities'].append({
                    'id': repair_id, 'name': install_name + '拆后维修', 'duration': 20,
                    'output_state_id': repaired, 'max_instances': 3,
                    'preconditions': [{'state_id': certificate, 'relation_role': 'required'},
                                      {'state_id': dismantle['output_state_id'], 'relation_role': 'required'}],
                    'resource_reqs': copy.deepcopy(install['resource_reqs']),
                })
                result['goal_state_ids'].extend([repaired, install['output_state_id']])
    bound = automatic_execution_bound(result)
    result['max_steps'] = bound['value']
    return result, pair_ids, bound, automatic_solver_budget(result)


def peak_working_set_mib():
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                'PagefileUsage', 'PeakPagefileUsage')]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    values = Counters()
    values.cb = ctypes.sizeof(values)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return values.PeakWorkingSetSize / 1024**2


def serial_witness(payload, pairs, forced):
    baseline = json.loads((ROOT/'output/dismantle-five-pairs-20261105/0-result.json').read_text('utf-8'))
    base_order = sorted(baseline['paths'][0]['executions'], key=lambda e: (e['start_time'], e['end_time']))
    activities = {a['id']: a for a in payload['activities']}
    lookup = {p['install']: p for p in pairs}
    rows, counts, now = [], Counter(), 0

    def add(aid):
        nonlocal now
        end = now + activities[aid]['duration']
        counts[aid] += 1
        rows.append({'activity_id': aid, 'ordinal': counts[aid], 'start': now, 'end': end})
        now = end

    for block in range(len(pairs) // 5):
        for e in base_order:
            aid = f'block:{block}:' + e['activity_id']
            add(aid)
            if forced and aid in lookup:
                add(lookup[aid]['dismantle'])
                add(lookup[aid]['repair'])
                add(aid)
    assert max(counts.values()) <= 3
    return rows


def measure(pairs, mode, out):
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.core.joint_cpsat import solve_joint, prepare_payload, replay_candidate
    from planner_experiment.models import Budget, to_primitive
    from planner_experiment.scenario import scenario_from_dict
    forced = mode == 'required'
    payload, pair_ids, bound, auto_budget = make_capacity_case(pairs, forced)
    stem = f'{mode}-{pairs}'
    save(out/f'{stem}-input.json', payload)
    original = copy.deepcopy(payload)
    samples = []
    started = time.perf_counter()
    result = solve_joint(payload, run_id=stem, seed=11, budget=Budget(60, 1, 3),
                         progress_observer=lambda m, p: samples.append({
                             'elapsed': time.perf_counter()-started, **m, 'improved_candidate': p is not None}))
    peak = peak_working_set_mib()
    assert original == payload
    save(out/f'{stem}-result.json', to_primitive(result))
    save(out/f'{stem}-samples.json', samples)
    stats = result.stats
    model = stats.get('model', {})
    best = result.paths[0] if result.paths else None
    execution_counts = Counter(e.activity_id for e in best.executions) if best else Counter()
    if best:
        assert best.validator_status == 'VALID'
        assert max(execution_counts.values()) <= 3
        if forced:
            assert all(execution_counts[p['install']] >= 2 and execution_counts[p['dismantle']] >= 1
                       and execution_counts[p['repair']] >= 1 for p in pair_ids)
    # Replay both a known serial witness and the returned candidate independently after measurement.
    scenario = scenario_from_dict(prepare_payload(payload))
    witness, _ = replay_candidate(payload, scenario, serial_witness(payload, pair_ids, forced),
                                  run_id=stem+':witness', seed=11)
    assert witness.validator_status == 'VALID'
    if best:
        verified, _ = replay_candidate(payload, scenario, [
            {'activity_id': e.activity_id, 'ordinal': e.ordinal, 'start': e.start_time, 'end': e.end_time}
            for e in best.executions], run_id=stem+':verify', seed=11)
        assert verified.validator_status == 'VALID'
    summary = {
        'pairs': pairs, 'mode': mode, 'activities': len(payload['activities']),
        'states': len(payload['states']), 'resource_pools': len(payload['resources']),
        'per_activity_cap': 3, 'automatic_bound': bound, 'automatic_budget': auto_budget,
        'actual_budget_seconds': 60, 'status': result.status, 'error': result.error,
        'elapsed_seconds': stats.get('elapsed_seconds'), 'first_solution_seconds': result.first_solution_seconds,
        'build_seconds': stats.get('build_seconds'), 'slots': model.get('optional_occurrence_slots'),
        'variables': model.get('variables'), 'constraints': model.get('constraints'),
        'branches': stats.get('branches'), 'conflicts': stats.get('conflicts'),
        'lower_bound': stats.get('lower_bound'), 'peak_process_working_set_mib': peak,
        'makespan': best.metrics.makespan if best else None,
        'executions': len(best.executions) if best else None,
        'dismantle_executions': sum(execution_counts[p['dismantle']] for p in pair_ids) if best else None,
        'validator': best.validator_status if best else None,
        'makespan_proven_optimal': stats.get('makespan_proven_optimal'),
        'execution_count_proven_optimal': stats.get('execution_count_proven_optimal'),
        'inverse_cycles_pruned': len(model.get('occurrence_pruning', {}).get('scope_analysis', {}).get('inverse_cycle_proofs', [])),
        'independent_serial_witness': {'validator': witness.validator_status, 'makespan': witness.metrics.makespan,
                                       'executions': len(witness.executions), 'provided_to_solver': False},
    }
    save(out/f'{stem}-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pairs', type=int, choices=[5, 10, 15, 20])
    p.add_argument('--mode', choices=['optional', 'required'])
    args = p.parse_args()
    out = args.output.resolve()
    if args.pairs:
        assert args.mode
        measure(args.pairs, args.mode, out)
        return
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'seed': 11, 'threads': 1, 'budget_seconds': 60, 'repetitions': 1,
                'per_activity_cap': 3, 'platform': platform.platform(), 'python': sys.version,
                'cpu_count': os.cpu_count(), 'database_writes': False, 'hints': False,
                'memory': 'OS PeakWorkingSetSize of fresh solver process, including imports, sampled before post-run replay',
                'compiler_sha256': hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest(),
                'pruning_sha256': hashlib.sha256((ROOT/'app/core/joint_pruning.py').read_bytes()).hexdigest(),
                'method': 'Copies of original 20-activity/5-pair fixture, shared resource capacities; required group adds repair certificate and final installed goals.'}
    save(out/'manifest.json', manifest)
    results = []
    for pairs in [5, 10, 15, 20]:
        for mode in ['optional', 'required']:
            stem = f'{mode}-{pairs}'
            print(f'START {stem}', flush=True)
            with (out/f'{stem}.log').open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), '--output', str(out),
                                '--pairs', str(pairs), '--mode', mode], cwd=ROOT, check=True, timeout=120,
                               stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            summary = json.loads((out/f'{stem}-summary.json').read_text('utf-8'))
            results.append(summary)
            save(out/'summary.json', {'settings': manifest, 'results': results})
            print(f"DONE {stem}: {summary['status']}, {summary['elapsed_seconds']:.3f}s", flush=True)


if __name__ == '__main__':
    main()

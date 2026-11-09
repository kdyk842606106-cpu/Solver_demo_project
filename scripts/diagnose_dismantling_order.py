"""Read-only paired diagnosis; never changes projects or production solver settings."""
import copy
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_engine_bridge import run_engine, _planner_modules
from app.services.planner_scenarios import expand_packages
from app.services.planner_execution_bounds import automatic_execution_bound

SOURCE = ROOT / 'output/user-dismantling-order-20261109'
OUT = ROOT / 'output/user-dismantling-diagnosis-20261109'

def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')

def main():
    OUT.mkdir(exist_ok=False)
    before = json.loads((SOURCE / 'project-before.json').read_text('utf8'))['scenario']
    after = json.loads((SOURCE / 'after-input.json').read_text('utf8'))
    for s in (before, after):
        s['calendar_context'] = {'start_at': '2026-11-09T08:00:00+08:00', 'timezone': 'Asia/Shanghai'}
        s['max_steps'] = automatic_execution_bound(s)['value']
    _planner_modules()
    from app.core.joint_cpsat import build_model
    from ortools.sat.python import cp_model
    native_solve = cp_model.CpSolver.solve
    models = {}
    for label, s in [('before', before), ('after', after)]:
        model, scene, slots, stats = build_model(expand_packages(copy.deepcopy(s)))
        model.export_to_file(str(OUT / f'{label}-model.pbtxt'))
        names = {a.id: a.name for a in scene.activities}
        models[label] = {'stats': stats, 'slots': dict(Counter(names[x.aid] for x in slots)),
            'variable_prefixes': dict(Counter(v.name.split(':')[0] for v in model.proto.variables))}
    save('models.json', models)

    rows = []
    def run(label, source, workers, seed, repeat, logged=False):
        tag = f'{label}-w{workers}-s{seed}-r{repeat}' + ('-logged' if logged else '')
        phases = []
        def traced_solve(solver, model, *args, **kwargs):
            logs = []
            solver.parameters.log_search_progress = True
            solver.parameters.log_to_stdout = False
            solver.log_callback = logs.append
            result = native_solve(solver, model, *args, **kwargs)
            (OUT / f'{tag}-phase{len(phases)}.log').write_text(''.join(logs), encoding='utf8')
            phases.append({'workers': solver.parameters.num_search_workers,
                'solution_info': solver.solution_info(), 'response': solver.response_stats()})
            return result
        cp_model.CpSolver.solve = traced_solve if logged else native_solve
        try:
            result = run_engine(copy.deepcopy(source), engine='JOINT_CP_SAT', run_id='isolated:order-diagnosis', seed=seed,
                budget_override={'time_limit_seconds': 60}, run_options={'worker_threads': workers})
        finally:
            cp_model.CpSolver.solve = native_solve
        save(tag + '.json', result)
        p = result['paths'][0]; st = result['stats']
        assert result['status'] == 'OPTIMAL' and p['validator_status'] == 'VALID'
        assert p['metrics']['makespan'] == 90 and len(p['executions']) == 5
        row = {'case': label, 'workers': workers, 'seed': seed, 'repeat': repeat, 'logged': logged,
            'seconds': result['elapsed_seconds'], 'first': result['first_solution_seconds'],
            'build': st['build_seconds'], 'branches': st['branches'], 'conflicts': st['conflicts'],
            'epochs': st['search_epochs'], 'restarts': st['feedback_restarts'], 'candidates': st['candidate_count'],
            'normalization': st['normalization'], 'phases': phases}
        rows.append(row)
        print(json.dumps({k:row[k] for k in ('case','workers','seed','repeat','logged','seconds','branches','conflicts')}), flush=True)

    for workers in (1, 8):
        for seed in (11, 23, 37, 53, 71):
            for label, source in [('before',before), ('after',after)]:
                run(label,source,workers,seed,0)
        for repeat in range(1, 6):
            for label, source in [('before',before), ('after',after)]:
                run(label,source,workers,11,repeat)
        for label, source in [('before',before), ('after',after)]:
            run(label,source,workers,11,0,True)
    save('runs.json',rows)
    summary = {}
    for workers in (1,8):
        for label in ('before','after'):
            sub = [r for r in rows if r['workers']==workers and r['case']==label and not r['logged']]
            summary[f'{label}-w{workers}'] = {k:{'min':min(r[k] for r in sub),
                'median':statistics.median(r[k] for r in sub),'max':max(r[k] for r in sub)}
                for k in ('seconds','first','build','branches','conflicts','epochs','restarts')}
    save('summary.json',summary)
    save('source-fingerprints.json', {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'app/core/joint_cpsat.py', ROOT/'app/core/joint_pruning.py')})
    print(json.dumps(summary),flush=True)

if __name__ == '__main__': main()

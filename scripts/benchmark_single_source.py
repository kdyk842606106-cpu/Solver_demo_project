"""Singleton encoding A/B comparison, sequential fresh processes, no DB writes."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/single-source-20261109'
CASES = {
    'dismantling': 'output/user-dismantling-order-20261109/after-input.json',
    'normal': 'output/mandatory-normal-late-20261106/normal-input.json',
    'late': 'output/mandatory-normal-late-20261106/late-input.json',
    'recovery': 'output/test-a-b-d-repair-effects-20261106/after-input.json',
}
SEEDS = [11, 23, 37, 53, 71]

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def single(case, seed, mode, repeat):
    sys.path.insert(0, str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules, run_engine
    _planner_modules()
    from app.core import joint_cpsat as core
    core._SINGLE_SOURCE_DIRECT = mode == 'direct'
    assert core._MANDATORY_ENCODING == 'none' and not core._CAUSAL_RANKS
    payload = json.loads((OUT / f'{case}-input.json').read_text('utf8'))
    frozen = copy.deepcopy(payload)
    result = run_engine(payload, engine='JOINT_CP_SAT', run_id='isolated:single-source', seed=seed,
        budget_override={'time_limit_seconds': 60}, run_options={'worker_threads': 8, 'trace_memory': False})
    assert payload == frozen and result['status'] not in ('ERROR', 'UNSUPPORTED')
    tag = f'{case}-{mode}-s{seed}-r{repeat}'
    save(OUT / f'{tag}-result.json', result)
    st = result['stats']; paths = result['paths']
    row = dict(case=case, mode=mode, seed=seed, repeat=repeat, input_hash=digest(payload),
        status=result['status'], first=result['first_solution_seconds'], seconds=result['elapsed_seconds'],
        branches=st.get('branches'), conflicts=st.get('conflicts'), build=st.get('build_seconds'),
        makespan=paths[0]['metrics']['makespan'] if paths else None,
        executions=len(paths[0]['executions']) if paths else None,
        validator=paths[0]['validator_status'] if paths else None,
        model=st.get('model'), epochs=st.get('search_epochs'), restarts=st.get('feedback_restarts'))
    assert not st['validator_rejections']
    if paths:
        assert paths[0]['validator_status'] == 'VALID'
    save(OUT / f'{tag}-summary.json', row)
    print(json.dumps({k:v for k,v in row.items() if k!='model'}), flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES)
    p.add_argument('--seed', type=int)
    p.add_argument('--mode', choices=['original', 'direct'])
    p.add_argument('--repeat', type=int, default=0)
    args = p.parse_args()
    if args.case:
        single(args.case, args.seed, args.mode, args.repeat)
        return
    OUT.mkdir(exist_ok=True)
    assert not any(OUT.iterdir()), 'Refuse to overwrite existing benchmark evidence'
    for case, source in CASES.items():
        save(OUT / f'{case}-input.json', json.loads((ROOT / source).read_text('utf-8-sig')))
    source_hash = hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest()
    save(OUT/'manifest.json', dict(sources=CASES, seeds=SEEDS, workers=8, budget_seconds=60,
         compiler_sha256=source_hash, business_changes=False, database_writes=False,
         counter_scope='native response per epoch; not all worker branches', trace_memory=False))
    tasks = []
    for si, seed in enumerate(SEEDS):
        for ci, case in enumerate(CASES):
            for mode in (['original','direct'] if (si+ci)%2==0 else ['direct','original']):
                tasks.append((case,seed,mode,0))
    # Repeats of the fixed production seed distinguish thread timing noise.
    for repeat in (1, 2):
        for ci, case in enumerate(CASES):
            for mode in (['original','direct'] if (repeat+ci)%2==0 else ['direct','original']):
                tasks.append((case,11,mode,repeat))
    for index, (case,seed,mode,repeat) in enumerate(tasks,1):
        assert hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest()==source_hash
        print(f'RUN {index}/{len(tasks)} {case} {mode} seed={seed} repeat={repeat}',flush=True)
        subprocess.run([sys.executable,'-X','utf8',__file__,'--case',case,'--seed',str(seed),
                        '--mode',mode,'--repeat',str(repeat)],cwd=ROOT,check=True)
    rows=[json.loads(p.read_text('utf8')) for p in OUT.glob('*-summary.json')]
    summary={}
    for case in CASES:
        for mode in ('original','direct'):
            sub=[r for r in rows if r['case']==case and r['mode']==mode and r['repeat']==0]
            summary[f'{case}/{mode}']={k:{'min':min(v),'median':statistics.median(v),'max':max(v)}
                for k in ('first','seconds','branches','build','makespan','executions')
                if (v:=[r[k] for r in sub if r[k] is not None])}
    save(OUT/'comparison.json',dict(runs=rows,summary=summary))
    print(json.dumps(summary),flush=True)

if __name__=='__main__': main()

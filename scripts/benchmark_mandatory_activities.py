"""Compare mandatory-presence constraints only, on frozen local inputs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT/'output/mandatory-activities-20261106'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['baseline','mandatory'], required=True)
    parser.add_argument('--case', choices=['current','install-only','disassembly-only'], default='disassembly-only')
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--seed',type=int,default=11)
    parser.add_argument('--input',type=Path,help='Optional frozen scenario; never modifies the source file')
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--label',help='Output case label for an explicit input')
    args=parser.parse_args()
    path=(ROOT/'output/test-a-b-d-repair-effects-20261106/after-input.json' if args.case=='current'
          else ROOT/f'output/test-a-install-keeps-tests-20261106/{args.case}-input.json')
    path=args.input or path
    p=json.loads(path.read_text(encoding='utf-8-sig'))
    saved=copy.deepcopy(p)
    from app.services.planner_engine_bridge import _planner_modules,run_engine
    _planner_modules()
    from app.core import joint_cpsat
    if args.mode=='baseline' and hasattr(joint_cpsat,'identify_mandatory_activities'):
        joint_cpsat.identify_mandatory_activities=lambda *a,**k: (set(),{'policy':'disabled_for_comparison','proofs':{}})
    elif args.mode=='mandatory':
        assert hasattr(joint_cpsat,'identify_mandatory_activities')
    out=args.output
    out.mkdir(exist_ok=True,parents=True)
    tag=f'{args.label or args.case}-{args.mode}-seed{args.seed}'
    (out/(tag+'-input.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    started=time.perf_counter()
    with (out/(tag+'-progress.jsonl')).open('w',encoding='utf-8') as stream:
        def progress(metrics,best):
            stream.write(json.dumps(dict(metrics,observed_seconds=time.perf_counter()-started,improved=best is not None),ensure_ascii=False)+'\n')
            stream.flush()
        r=run_engine(p,engine='JOINT_CP_SAT',run_id='local:mandatory:'+tag,seed=args.seed,
                     budget_override={'time_limit_seconds':args.seconds},progress_observer=progress)
    assert p==saved
    (out/(tag+'-result.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    names={a['id']:a['name'] for a in p['activities']}
    summary={k:r.get(k) for k in ['status','first_solution_seconds','elapsed_seconds','lower_bound','proven_optimal']}
    summary.update({k:r['stats'].get(k) for k in ['branches','conflicts','best_makespan','best_execution_count','worker_threads']})
    summary['input_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    summary['model']={k:r['stats']['model'].get(k) for k in ['variables','constraints','optional_occurrence_slots','support_choices','threat_checks','interval_locks','mandatory_activities']}
    proof=summary['model'].get('mandatory_activities') or {}
    summary['mandatory_names']=[names[aid] for aid in proof.get('activity_ids',[])]
    if r['paths']:
        best=r['paths'][0]
        assert best['validator_status']=='VALID'
        summary['validator']=best['validator_status']
        summary['schedule']=[{'name':names[e['activity_id']],'ordinal':e['ordinal'],'start':e['start_time'],'end':e['end_time']} for e in best['executions']]
    summary.update(seed=args.seed,budget_seconds=args.seconds)
    (out/(tag+'-summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()

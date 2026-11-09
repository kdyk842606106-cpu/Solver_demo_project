"""Paired feedback fix benchmark; same recovery snapshot, singleton default off."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/latest-feedback-20261109'
INPUT=ROOT/'output/single-source-20261109/recovery-input.json'

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),'utf8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def single(mode,seed,repeat):
    sys.path.insert(0,str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules,run_engine
    _planner_modules()
    from app.core import joint_cpsat as core
    if mode=='before':
        # Exact pre-fix source, loaded only in this disposable child process.
        source=OUT/'joint_cpsat-before.py'
        exec(compile(source.read_text('utf8'),str(source),'exec'),core.__dict__)
    assert not core._SINGLE_SOURCE_DIRECT and core._MANDATORY_ENCODING=='none' and not core._CAUSAL_RANKS
    payload=json.loads((OUT/'input.json').read_text('utf8'));saved=copy.deepcopy(payload)
    builder=core._build_model_with_finish;initial={}
    def build(*a,**kw):
        result=builder(*a,**kw)
        initial['model_sha256']=hashlib.sha256(str(result[0].proto).encode()).hexdigest()
        return result
    core._build_model_with_finish=build
    result=run_engine(payload,engine='JOINT_CP_SAT',run_id='isolated:latest-feedback',seed=seed,
        budget_override={'time_limit_seconds':60},run_options={'worker_threads':8,'trace_memory':False})
    assert payload==saved and result['status']=='OPTIMAL'
    p=result['paths'][0];st=result['stats']
    assert p['validator_status']=='VALID' and p['metrics']['makespan']==390 and len(p['executions'])==10
    stale=[]
    for cert in st['feedback_certificates']:
        known=[c for c in st['candidate_history'] if c['seconds']<=cert['elapsed_seconds']]
        best=min(known,key=lambda c:(c['delivered_makespan'],c['execution_count']))
        if cert['applied'] and (cert['makespan'],cert['execution_count'])>(best['delivered_makespan'],best['execution_count']):
            stale.append(dict(certificate=cert,best=best))
    if mode=='after':assert not stale
    tag=f'{mode}-s{seed}-r{repeat}'
    save(OUT/f'{tag}-result.json',result)
    row=dict(mode=mode,seed=seed,repeat=repeat,first=result['first_solution_seconds'],seconds=result['elapsed_seconds'],
        branches=st['branches'],conflicts=st['conflicts'],restarts=st['feedback_restarts'],epochs=st['search_epochs'],
        refreshed=sum(c.get('selection',{}).get('refreshed_from_trigger',False) for c in st['feedback_certificates']),
        stale_count=len(stale),stale_records=stale,status=result['status'],makespan=390,executions=10,
        validator=p['validator_status'],model=st['model'],**initial)
    save(OUT/f'{tag}-summary.json',row)
    print(json.dumps({k:v for k,v in row.items() if k not in ['model','stale_records']}),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['before','after']);p.add_argument('--seed',type=int)
    p.add_argument('--repeat',type=int,default=0);a=p.parse_args()
    if a.mode:single(a.mode,a.seed,a.repeat);return
    assert not (OUT/'manifest.json').exists()
    save(OUT/'input.json',json.loads(INPUT.read_text('utf8')))
    source=ROOT/'app/core/joint_cpsat.py';source_hash=sha(source)
    save(OUT/'manifest.json',dict(input_sha256=sha(INPUT),before_sha256=sha(OUT/'joint_cpsat-before.py'),
        after_sha256=source_hash,threads=8,seeds=[23,71,11],repeats_per_seed=5,budget_seconds=60,
        single_source_direct=False,database_writes=False,business_changes=False,native_logging=False))
    for repeat in range(5):
        for index,seed in enumerate([23,71,11]):
            for mode in (['before','after'] if (repeat+index)%2==0 else ['after','before']):
                assert sha(source)==source_hash
                print(f'RUN {mode} seed={seed} repeat={repeat}',flush=True)
                subprocess.run([sys.executable,'-X','utf8',__file__,'--mode',mode,'--seed',str(seed),
                                '--repeat',str(repeat)],cwd=ROOT,check=True)
    rows=[json.loads(p.read_text('utf8')) for p in OUT.glob('*-summary.json')]
    assert len(rows)==30 and len({r['model_sha256'] for r in rows})==1
    summary={}
    for seed in [23,71,11]:
        for mode in ['before','after']:
            sub=[r for r in rows if r['seed']==seed and r['mode']==mode]
            summary[f'{seed}/{mode}']={k:dict(min=min(r[k] for r in sub),median=statistics.median(r[k] for r in sub),max=max(r[k] for r in sub))
                for k in ['first','seconds','branches','restarts','epochs']}
    save(OUT/'comparison.json',dict(summary=summary,runs=rows))
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()

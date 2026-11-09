"""Frozen recovery input; detailed per-solve/callback timings, no production writes."""
import argparse
import copy
import hashlib
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/single-source-recovery-diagnosis-20261109'
SOURCE = ROOT/'output/single-source-20261109/recovery-input.json'

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')

def single(mode, seed, repeat, workers):
    sys.path.insert(0,str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules, run_engine
    _planner_modules()
    from app.core import joint_cpsat as core
    if mode in ('initial_only','producer_only'):
        # Isolated diagnostic variant: substitute only one source category.
        # Production source remains byte-for-byte unchanged.
        source=inspect.getsource(core._compile)
        condition='if _SINGLE_SOURCE_DIRECT and len(options) == 1:'
        qualifier='options[0] is None' if mode=='initial_only' else 'options[0] is not None'
        assert source.count(condition)==1
        exec(compile(source.replace(condition,condition[:-1]+' and '+qualifier+':'),
                     '<isolated-source-category>', 'exec'),core.__dict__)
    core._SINGLE_SOURCE_DIRECT = mode != 'original'
    payload=json.loads(SOURCE.read_text('utf8')); frozen=copy.deepcopy(payload)
    tag=f'{mode}-s{seed}-r{repeat}-w{workers}'
    calls=[]; replays=[]; events=[]; stage='BUILDING'; started=time.perf_counter()
    original_solve=core.cp_model.CpSolver.solve
    original_replay=core.replay_candidate
    def replay(*args,**kwargs):
        begin=time.perf_counter()
        result=original_replay(*args,**kwargs)
        replays.append({'start':begin-started,'seconds':time.perf_counter()-begin,
                        'makespan':result[0].metrics.makespan,'executions':len(result[0].executions)})
        return result
    def observed(metrics,best):
        nonlocal stage
        stage=metrics.get('phase',stage)
        events.append(dict(metrics,observer_seconds=time.perf_counter()-started,improved=best is not None))
    def solve(self,model,*args,**kwargs):
        i=len(calls); logs=[]
        entry={'index':i,'phase':stage,'workers':self.parameters.num_search_workers,
               'start':time.perf_counter()-started,'model_hash':hashlib.sha256(str(model.proto).encode()).hexdigest()}
        calls.append(entry)
        if i==0:model.export_to_file(str(OUT/f'{tag}-model.pbtxt'))
        self.parameters.log_search_progress=True
        self.parameters.log_to_stdout=False
        self.parameters.log_subsolver_statistics=True
        self.log_callback=logs.append
        status=original_solve(self,model,*args,**kwargs)
        end=time.perf_counter()-started
        self.log_callback=None
        log='\n'.join(logs)
        (OUT/f'{tag}-call{i}.log').write_text(log,'utf8')
        presolved=re.search(r'Presolved optimization model.*?(?=Preloading model)',log,re.S)
        if presolved:(OUT/f'{tag}-call{i}-presolved.txt').write_text(presolved[0],'utf8')
        entry.update(end=end,seconds=end-entry['start'],status=self.status_name(status),
            solution_info=self.solution_info(),response=self.response_stats(),
            search_start=re.findall(r'Starting search at ([0-9.]+)s',log),
            first_native=re.findall(r'^#1\s+[^\n]*',log,re.M),
            native_solutions=re.findall(r'^#\d+\s+[^\n]*',log,re.M))
        return status
    core.cp_model.CpSolver.solve=solve;core.replay_candidate=replay
    result=run_engine(payload,engine='JOINT_CP_SAT',run_id='isolated:singleton-diagnosis',seed=seed,
        budget_override={'time_limit_seconds':60},run_options={'worker_threads':workers,'trace_memory':False},
        progress_observer=observed)
    assert payload==frozen and result['status']=='OPTIMAL' and result['paths'][0]['validator_status']=='VALID'
    assert result['paths'][0]['metrics']['makespan']==390 and len(result['paths'][0]['executions'])==10
    save(OUT/f'{tag}-result.json',result)
    save(OUT/f'{tag}-trace.json',{'calls':calls,'replays':replays,'events':events})
    st=result['stats']
    summary={'tag':tag,'mode':mode,'seed':seed,'repeat':repeat,'workers':workers,
        'first':result['first_solution_seconds'],'seconds':result['elapsed_seconds'],'build':st['build_seconds'],
        'branches':st['branches'],'epochs':st['search_epochs'],'restarts':st['feedback_restarts'],
        'replay_seconds':sum(x['seconds'] for x in replays),
        'certificate_seconds':sum(x['seconds'] for x in st['feedback_certificates']),
        'first_native':calls[0]['first_native'],'presolve':calls[0]['search_start']}
    save(OUT/f'{tag}-summary.json',summary)
    print(json.dumps(summary),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--seed',type=int)
    p.add_argument('--repeat',type=int,default=0);p.add_argument('--workers',type=int,default=8)
    a=p.parse_args()
    if a.mode:single(a.mode,a.seed,a.repeat,a.workers);return
    OUT.mkdir(exist_ok=False)
    save(OUT/'manifest.json',{'input_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'compiler_sha256':hashlib.sha256((ROOT/'app/core/joint_cpsat.py').read_bytes()).hexdigest(),
        'database_writes':False,'business_changes':False,'native_logging':True})
    for index,(seed,repeat) in enumerate([(23,0),(71,0),(11,0),(11,1),(11,2)]):
        for mode in (['original','direct'] if index%2==0 else ['direct','original']):
            print(f'RUN {mode} seed={seed} repeat={repeat}',flush=True)
            subprocess.run([sys.executable,'-X','utf8',__file__,'--mode',mode,'--seed',str(seed),'--repeat',str(repeat)],cwd=ROOT,check=True)

if __name__=='__main__':main()

"""Compare only instance causal ranks, keeping production encoding/search fixed."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import benchmark_linear_propagation as runner
ROOT=Path(__file__).resolve().parents[1]
runner.OUT=ROOT/'output/causal-ranks-20261106'
runner.CASES['late-material']=('output/mandatory-normal-late-20261106/late-input.json',60)
ORDER=['normal-a','late-material','recovery-current','disassembly-only','assembly-20',
       'required-cycles-5','calendar-night-150','repair-0042']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--case',choices=ORDER)
    p.add_argument('--ranks',type=int,choices=[0,1])
    p.add_argument('--seed',type=int,default=11)
    args=p.parse_args()
    if args.case:
        assert args.ranks is not None
        runner.single(args.case,'new',args.seed,'',encoding='appended',causal_ranks=bool(args.ranks))
        return
    tasks=[]
    for seed in (11,23,37):
        cases=ORDER if seed==11 else ['normal-a','late-material','recovery-current']
        for index,case in enumerate(cases):
            for ranks in ([0,1] if index%2==0 else [1,0]):
                tasks.append(dict(case=case,seed=seed,ranks=ranks))
    runner.OUT.mkdir(parents=True,exist_ok=True)
    (runner.OUT/'matrix.json').write_text(json.dumps(tasks,indent=2),encoding='utf-8')
    for i,t in enumerate(tasks,1):
        print(f'RUN {i}/{len(tasks)} {t}',flush=True)
        subprocess.run([sys.executable,'-X','utf8',__file__,'--case',t['case'],'--ranks',str(t['ranks']),
                        '--seed',str(t['seed'])],cwd=ROOT,check=True)

if __name__=='__main__':main()

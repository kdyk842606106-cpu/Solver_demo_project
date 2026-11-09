"""Three compilers x two propagators, without changing any business inputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import benchmark_linear_propagation as runner

ROOT=Path(__file__).resolve().parents[1]
runner.OUT=ROOT/'output/mandatory-encoding-20261106'
runner.CASES['late-material']=('output/mandatory-normal-late-20261106/late-input.json',60)
ORDER=['normal-a','late-material','recovery-current','disassembly-only','assembly-20',
       'required-cycles-5','calendar-night-150','repair-0042']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--case',choices=ORDER)
    p.add_argument('--encoding',choices=['none','appended','early'])
    p.add_argument('--linear',choices=['new','old'])
    p.add_argument('--seed',type=int,default=11)
    p.add_argument('--group',choices=['primary','seeds'],default='primary')
    args=p.parse_args()
    if args.case:
        assert args.encoding and args.linear
        runner.single(args.case,args.linear,args.seed,'',encoding=args.encoding)
        return
    seeds=[11] if args.group=='primary' else [23,37]
    cases=ORDER if args.group=='primary' else ['normal-a','late-material','recovery-current']
    tasks=[]
    for seed in seeds:
        for index,case in enumerate(cases):
            # Rotation avoids always running the candidate first or last.
            encodings=['none','appended','early']
            encodings=encodings[index%3:]+encodings[:index%3]
            for encoding in encodings:
                for linear in (['new','old'] if (index+seed)%2 else ['old','new']):
                    tasks.append(dict(case=case,encoding=encoding,linear=linear,seed=seed))
    runner.OUT.mkdir(parents=True,exist_ok=True)
    (runner.OUT/f'matrix-{args.group}.json').write_text(json.dumps(tasks,indent=2),encoding='utf-8')
    for number,t in enumerate(tasks,1):
        print(f"RUN {number}/{len(tasks)} {t}",flush=True)
        subprocess.run([sys.executable,'-X','utf8',__file__,'--case',t['case'],'--encoding',t['encoding'],
                        '--linear',t['linear'],'--seed',str(t['seed'])],cwd=ROOT,check=True)

if __name__=='__main__':main()

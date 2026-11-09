"""Freeze normal/late-arrival run inputs with Test A's unchanged current rules."""
import copy
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_execution_bounds import automatic_execution_bound,automatic_solver_budget
from app.services.planner_run_windows import ActivityTimeWindow,freeze_run_windows

OUT=ROOT/'output/mandatory-normal-late-20261106'
envelope=json.loads((OUT/'source.json').read_text(encoding='utf-8-sig'))
source=envelope['scenario']
a={x['name']:x for x in source['activities']}
anchor='2026-11-06T08:00:00+08:00'
metadata={'source_revision':envelope['revision'],'anchor':anchor,'seed':11,'cases':{}}
for case,goal in [('normal','模块联调'),('late','扩展功能联调')]:
    p=copy.deepcopy(source)
    p['initial_state_ids']=[a[n]['output_state_id'] for n in ['下电','模块A拆卸','模块C拆卸']]
    p['goal_state_ids']=[a[goal]['output_state_id']]
    p['calendar_context']={'start_at':anchor,'timezone':'Asia/Shanghai'}
    p['max_steps']=automatic_execution_bound(p)['value']
    requests=[] if case=='normal' else [ActivityTimeWindow(activity_id=a['联调扩展件安装']['id'],
                                                        earliest_start_at='2026-11-07T08:00:00+08:00')]
    p['run_time_windows']=freeze_run_windows(p,requests,datetime.fromisoformat(anchor))
    for key,value in source.items():
        if key not in {'initial_state_ids','goal_state_ids','calendar_context','max_steps','run_time_windows'}:
            assert p[key]==value,key
    (OUT/(case+'-input.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    metadata['cases'][case]={'initial':['下电完成','模块A拆卸完成','模块C拆卸完成'],
                             'goal':goal+'完成','budget':automatic_solver_budget(p),
                             'run_windows':p['run_time_windows'],'execution_bound':p['max_steps']}
(OUT/'inputs-verified.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False))

"""Locate the surviving presolve delta through equivalent, isolated substitutions."""
import copy
import inspect
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/single-source-recovery-diagnosis-20261109'
sys.path.insert(0,str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
from app.services.planner_scenarios import expand_packages
_planner_modules()
from app.core import joint_cpsat as core

p=json.loads((ROOT/'output/single-source-20261109/recovery-input.json').read_text('utf8'))
original=inspect.getsource(core._compile)
condition='if _SINGLE_SOURCE_DIRECT and len(options) == 1:'
# These are the four later optional A/C removal slots reading the initial fault.
removals={a['id'] for a in p['activities'] if a['name'] in ('模块A拆卸','模块C拆卸')}
fault=next(s['id'] for s in p['states'] if s['name']=='模块A待维修')
later=f'(consumer is not None and consumer.aid in {removals!r} and consumer.ordinal > 1 and fact == {fault!r})'
variants={'original':'False','direct':'True','initial_threat':'options[0] is None and bool(threats)',
          'initial_stable':'options[0] is None and not threats','producer_only':'options[0] is not None',
          'later_removal_only':later,'all_except_later_removal':f'not {later}'}
rows=[]
for label,extra in variants.items():
    exec(compile(original.replace(condition,condition[:-1]+' and ('+extra+'):'),
                 '<isolated-presolve-category>','exec'),core.__dict__)
    core._SINGLE_SOURCE_DIRECT=True
    model,_,_,stats=core.build_model(expand_packages(copy.deepcopy(p)))
    logs=[];solver=core.cp_model.CpSolver()
    solver.parameters.num_search_workers=8;solver.parameters.random_seed=23
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    solver.parameters.stop_after_presolve=True;solver.log_callback=logs.append
    solver.solve(model)
    log='\n'.join(logs);(OUT/f'presolve-{label}.log').write_text(log,'utf8')
    match=re.search(r"Presolved optimization model.*?model_fingerprint: ([^)]+).*?#Variables: ([\d,]+)",log,re.S)
    row={'variant':label,'model_variables':stats['variables'],'model_constraints':stats['constraints'],
         'compressed':stats['single_source_direct'],'fingerprint':match[1],
         'presolved_variables':match[2]}
    rows.append(row)
    print(json.dumps(row),flush=True)
(OUT/'presolve-ablation.json').write_text(json.dumps(rows,indent=2),'utf8')

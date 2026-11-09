"""Audit source/model deltas and all rank-only benchmark outcomes."""
from collections import defaultdict,Counter
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core
OUT=ROOT/'output/causal-ranks-20261106'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
groups=defaultdict(dict)
for task in read(OUT/'matrix.json'):
    tag=f"ranks-{task['ranks']}-appended-{task['case']}-new-seed{task['seed']}"
    r=read(OUT/f'{tag}-summary.json')
    assert r['encoding']=='appended' and r['implementation']=='new' and r['worker_threads']==1
    assert r['causal_ranks_enabled']==bool(task['ranks']) and not r['validator_rejections']
    assert r['status'] not in ('ERROR','UNSUPPORTED','UNKNOWN'), (tag,r['status'])
    source=read(ROOT/r['source'])
    if task['case']=='calendar-night-150':source=source['request']['effective_scenario_snapshot']
    assert source==read(OUT/f'{tag}-input.json')
    if r.get('schedule') is not None:
        assert r['validator']=='VALID'
        r['execution_counts_by_activity']=dict(Counter(x['name'] for x in r['schedule']))
    groups[(task['case'],task['seed'])][task['ranks']]=r

model_checks={}
core._MANDATORY_ENCODING='appended'
for (case,seed),pair in groups.items():
    off,on=pair[0],pair[1]
    assert off['input_sha256']==on['input_sha256']
    assert off['budget_seconds']==on['budget_seconds'] and off['seed']==on['seed']
    for key in ('optional_occurrence_slots','support_choices','threat_checks','interval_locks','horizon'):
        assert off['model'][key]==on['model'][key],(case,key)
    assert off['model']['mandatory_activities']['activity_ids']==on['model']['mandatory_activities']['activity_ids']
    if seed==11:
        p=read(OUT/f'ranks-0-appended-{case}-new-seed11-input.json')
        core._CAUSAL_RANKS=False
        old,_,_,_,_=core._build_model_with_finish(expand_packages(p),deadline=None)
        core._CAUSAL_RANKS=True
        new,_,slots,stats,_=core._build_model_with_finish(expand_packages(p),deadline=None)
        assert [str(v) for v in old.proto.variables]==[str(v) for v in list(new.proto.variables)[:len(old.proto.variables)]]
        assert [str(c) for c in old.proto.constraints]==[str(c) for c in new.proto.constraints if not c.name.startswith('causal_rank:')]
        assert str(old.proto.objective)==str(new.proto.objective)
        assert str(old.proto.solution_hint)==str(new.proto.solution_hint)
        assert len(new.proto.variables)-len(old.proto.variables)==len(slots)
        model_checks[case]={'original_variables_constraints_objective_hints_unchanged':True,
                           'added_rank_variables':len(slots),
                           'added_constraints':len(new.proto.constraints)-len(old.proto.constraints),
                           'causal_ranks':stats['causal_ranks']}
for case in {c for c,_ in groups}:
    runs=[r for (c,_),pair in groups.items() if c==case for r in pair.values()]
    proven={(r['best_makespan'],r['best_execution_count']) for r in runs if r['status']=='OPTIMAL'}
    assert len(proven)<=1,(case,proven)
    if proven:
        optimum=next(iter(proven))
        for r in runs:
            assert r['status']!='INFEASIBLE'
            if r.get('schedule') is not None:
                assert (r['best_makespan'],r['best_execution_count'])>=optimum

report={'method':{'runs':sum(len(x) for x in groups.values()),'single_toggle':'conditional_support_dag_v1',
    'mandatory_encoding':'appended','new_linear_propagation':True,'threads':1,
    'seeds':[11,23,37],'extra_seed_cases':['normal-a','late-material','recovery-current'],
    'budget':'60 seconds except calendar-night-150 120 seconds; same within each pair',
    'database_writes':False,'business_changes':False,'sequential_fresh_processes':True},
    'model_checks':model_checks,'tests':{},'results':{f'{case}/seed{seed}':pair for (case,seed),pair in groups.items()},
    'rollout':{'default_enabled':False,
        'reason':'Correctness checks passed, but seed 37 regresses for late-material and recovery-current; historical repair-0042 still has no solution within 60 seconds in either mode.',
        'limitations':'Single-thread experiments, three seeds for three cases only, one timing observation per configuration; no general speedup claim.'}}
for path in OUT.glob('tests-*.xml'):
    suite=ET.parse(path).getroot().find('testsuite')
    assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    report['tests'][path.name]=suite.attrib
target=ROOT/'docs/validation/CAUSAL_RANKS_20261106.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['Instance causal ranks comparison: off/on only','Same business constraints, mandatory encoding and propagation; independent processes.','']
for (case,seed),pair in groups.items():
    lines.append(f'{case} / seed {seed}')
    for enabled,r in pair.items():
        lines.append(f"  ranks={enabled} {r['status']:14} first={r['first_solution_seconds']} total={r['elapsed_seconds']:.3f}s branches={r['branches']} best={r['best_makespan']}/{r['best_execution_count']}")
(OUT/'comparison.txt').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
print('All checks passed:',target)

"""Read-only scenario audit with controlled replay witnesses; no DB writes."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/test-a-state-audit-20261106'
source = json.loads((OUT/'snapshot.json').read_text(encoding='utf-8-sig'))['scenario']

from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages, validate_scenario
from app.services.planner_execution_bounds import automatic_execution_bound
from app.core.joint_cpsat import prepare_payload, replay_candidate
from planner_experiment.scenario import scenario_from_dict
from planner_experiment.models import to_primitive, Action
from planner_experiment.simulator import PathSimulator
from planner_experiment.working_time import next_activity_start, work_end

acts = {a['name']: a for a in source['activities']}
state_names = {s['id']: s['name'] for s in source['states']}
fault = next(s['id'] for s in source['states'] if s['name'] == '模块A待维修')
def sid(name): return acts[name]['output_state_id']
def save(name, value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def payload(initial, faulted=False, goals=('扩展功能联调',)):
    p = copy.deepcopy(source)
    p['activity_package_scope_ids'] = []
    p['initial_state_ids'] = [sid(n) for n in initial] + ([fault] if faulted else [])
    p['goal_state_ids'] = [sid(n) for n in goals]
    p['calendar_context'] = {'start_at': '2026-11-06T08:00:00+08:00', 'timezone': 'Asia/Shanghai'}
    p['run_time_windows'] = []
    p['max_steps'] = automatic_execution_bound(p)['value']
    return p

def replay(case, p, order):
    issues = validate_scenario(copy.deepcopy(p))
    p = expand_packages(p)
    sc = scenario_from_dict(prepare_payload(p))
    lookup = {a.name:a for a in sc.activities}
    rows=[]; t=0; counts={}
    for name in order:
        a=lookup[name]; counts[name]=counts.get(name,0)+1
        start=next_activity_start(sc.working_intervals,t,a)
        t=work_end(sc.working_intervals,start,a.duration)
        rows.append({'activity_id':a.id,'ordinal':counts[name],'start':start,'end':t})
    candidate,_=replay_candidate(p,sc,rows,run_id='local:audit:'+case,seed=11)
    assert candidate.validator_status=='VALID'
    save(case+'-candidate.json',to_primitive(candidate))
    sim=PathSimulator(sc); state=sim.initial_state(); trace=[]
    for action in candidate.actions:
        before=state;state=sim.transition(state,action)
        if len(state.executions)>len(before.executions):
            trace.append({'time':state.time,'completed':[acts_by_id[e.activity_id]['name'] for e in state.executions[len(before.executions):]],
                          'states': [state_names[x] for x in state.active_state_ids]})
    result={'case':case,'input_validation_issues':issues,'initial':[state_names[x] for x in p['initial_state_ids']],
            'validator':candidate.validator_status,'makespan':candidate.metrics.makespan,
            'schedule':[{'name':acts_by_id[e.activity_id]['name'],'start':e.start_time,'end':e.end_time} for e in candidate.executions],
            'final':[state_names[x] for x in candidate.final_state_ids], 'trace':trace}
    save(case+'-witness.json',result)
    return result

acts_by_id={a['id']:a for a in source['activities']}
ready=['集成检测完成','模块A安装','模块B安装','模块C安装','模块D安装','安全验收','上电','模块A功能调测','模块B调测','模块联调']
results=[]
for name,case in [('模块B安装','b-install-stale-tests'),('模块D安装','d-install-stale-acceptance')]:
    r=replay(case,payload(ready),[name,'下电','联调扩展件安装','安全验收','上电','扩展功能联调'])
    assert '上电完成' in r['trace'][0]['states']
    assert {'安全验收完成','模块B调测完成','模块联调完成'}.issubset(r['trace'][0]['states'])
    results.append(r)

r=replay('extension-survives-disassembly',payload(ready,True),
         ['下电','联调扩展件安装','模块C拆卸','模块A拆卸','模块A维修','模块A安装','模块C安装','安全验收','上电','模块A功能调测','扩展功能联调'])
assert all('联调扩展件安装完成' in row['states'] for row in r['trace'] if row['time']>=40)
results.append(r)

stale=['下电','模块A拆卸','模块C拆卸','模块A功能调测','模块B调测','模块联调','扩展功能联调']
r=replay('repair-retains-imported-stale-results',payload(stale,True),['模块A维修'])
assert '扩展功能联调完成' in r['final'] and '模块A安装完成' not in r['final']
results.append(r)

# Input consistency is not an inferred invariant: explicitly expose contradictory pairs.
p=payload(['下电','上电','模块A安装','模块A拆卸','模块C安装','模块C拆卸'],False,('模块A安装',))
issues=validate_scenario(copy.deepcopy(p))
save('initial-contradictions.json',{'issues':issues,'initial':[state_names[x] for x in p['initial_state_ids']]})
assert not issues

# The current transition semantics reject repair/reassembly overlap while disassembly
# facts are read-locked; power-off preservation is explicitly intended by the user.
p=payload(['下电','模块A拆卸','模块C拆卸','集成检测完成','模块B安装'],True,('模块A维修',))
sc=scenario_from_dict(prepare_payload(expand_packages(p)))
sim=PathSimulator(sc); state=sim.initial_state()
state=sim.transition(state,Action('START',activity_id=acts['模块A维修']['id']))
enabled={x.activity_id for x in sim.enabled_actions(state) if x.kind=='START'}
assert acts['模块A安装']['id'] not in enabled and acts['模块C安装']['id'] not in enabled
save('protected-behavior.json',{'repair_blocks_reassembly':True,'power_off_keeps_test_results_by_design':True})

save('summary.json',{'revision':source['revision'],'witnesses':[{'case':r['case'],'validator':r['validator'],'makespan':r['makespan'],'steps':len(r['schedule'])} for r in results],
                     'contradictory_initial_facts_accepted':not issues,'repair_blocks_reassembly':True})
print(json.dumps(json.loads((OUT/'summary.json').read_text(encoding='utf-8')),ensure_ascii=False))

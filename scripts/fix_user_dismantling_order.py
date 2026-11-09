"""Require completed B/C/D and AB removal before A removal; compare unchanged solver."""
import copy
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_scenarios import expand_packages,validate_scenario
from app.services.planner_execution_bounds import automatic_execution_bound
from app.services.planner_engine_bridge import run_engine,_planner_modules

BASE='http://127.0.0.1:8016/api/v1'
SID='scenario:08c442a9-6af4-47cc-a618-e75c002de898'
OUT=ROOT/'output/user-dismantling-order-20261109'
def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as res:return json.load(res)
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
def runtime(s):
    s=copy.deepcopy(s)
    s['calendar_context']={'start_at':'2026-11-09T08:00:00+08:00','timezone':'Asia/Shanghai'}
    s['max_steps']=automatic_execution_bound(s)['value']
    return s

def main():
    OUT.mkdir(exist_ok=False)
    before=api('/planner-scenarios/'+SID);save('project-before.json',before)
    baseline=before['scenario'];changed=copy.deepcopy(baseline)
    assert len(baseline['activities'])==17
    by_name={a['name']:a for a in changed['activities']}
    a=by_name['拆卸模块A']
    blockers=['拆卸线缆AB','拆卸模块B','拆卸模块C','拆卸模块D']
    old_relations=copy.deepcopy(a['preconditions'])
    for name in blockers:
        sid=by_name[name]['output_state_id']
        if not any(p['state_id']==sid for p in a['preconditions']):
            a['preconditions'].append({'state_id':sid,'relation_role':'required'})
    metadata=copy.deepcopy(a.get('metadata',{}))
    metadata['description']='时长、资源沿用模块A安装；拆卸前须完成AB线缆及B/C/D模块拆卸，转移消耗模块A安装完成。'
    a['metadata']=metadata
    operations=[{'operation':'update_activity','object_id':a['id'],
                 'payload':{'preconditions':a['preconditions'],'metadata':metadata}}]
    save('operations.json',operations)
    assert old_relations!=a['preconditions']
    assert not validate_scenario(copy.deepcopy(changed))
    save('after-input.json',runtime(changed))
    # Confirm the formerly displayed schedule now fails the independent simulator.
    old_run=api('/planner-runs/planner-run:a8bb6d3b-fb7e-4b9e-a904-28a1ccc641cc')
    save('old-workbench-run.json',old_run)
    _planner_modules()
    from app.core.joint_cpsat import prepare_payload,replay_candidate
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.simulator import PathSimulator,InvalidAction
    from planner_experiment.models import Action
    expanded=expand_packages(runtime(changed));scene=scenario_from_dict(prepare_payload(expanded))
    sim=PathSimulator(scene);state=sim.initial_state()
    assert not any(x.kind=='START' and x.activity_id==a['id'] for x in sim.enabled_actions(state))
    state=sim.transition(state,Action('START',activity_id=by_name['拆卸模块D']['id']))
    state=sim.transition(state,next(x for x in sim.enabled_actions(state) if x.kind=='ADVANCE'))
    assert not any(x.kind=='START' and x.activity_id==a['id'] for x in sim.enabled_actions(state))
    old_rows=[{'activity_id':e['activity_id'],'ordinal':e['ordinal'],'start':e['start_time'],'end':e['end_time']}
              for e in old_run['result']['results']['JOINT_CP_SAT']['paths'][0]['executions']]
    try:replay_candidate(expanded,scene,old_rows,run_id='negative:old-order',seed=11)
    except InvalidAction as exc:save('old-order-rejected.json',{'status':'PASS','reason':str(exc)})
    else:raise AssertionError('Old D -> A order must be rejected')
    rows=[]
    for seed in [11,23,37,53,71]:
        for label,source in [('before',baseline),('after',changed)]:
            result=run_engine(runtime(source),engine='JOINT_CP_SAT',run_id='independent:order-comparison',seed=seed,
                budget_override={'time_limit_seconds':60},run_options={'worker_threads':8})
            save(f'{label}-seed{seed}.json',result)
            assert result['status']=='OPTIMAL'
            p=result['paths'][0];st=result['stats'];m=st['model']
            assert p['validator_status']=='VALID' and p['metrics']['makespan']==90 and len(p['executions'])==5
            if label=='after':
                starts={e['activity_id']:e['start_time'] for e in p['executions']}
                ends={e['activity_id']:e['end_time'] for e in p['executions']}
                assert all(ends[by_name[name]['id']]<=starts[a['id']] for name in blockers)
                assert ends[by_name['拆卸模块B']['id']]<=starts[by_name['拆卸模块C']['id']]
            row={'case':label,'seed':seed,'threads':st['worker_threads'],'first_seconds':result['first_solution_seconds'],
                'seconds':result['elapsed_seconds'],'build_seconds':st['build_seconds'],'branches':st['branches'],
                'conflicts':st['conflicts'],'variables':m['variables'],'constraints':m['constraints'],
                'effective_slots':m['optional_occurrence_slots'],'makespan':90,'executions':5,'status':result['status'],'validator':p['validator_status']}
            rows.append(row);print(json.dumps(row),flush=True)
    aggregates={}
    for label in ['before','after']:
        sub=[r for r in rows if r['case']==label]
        aggregates[label]={key:{'min':min(r[key] for r in sub),'median':statistics.median(r[key] for r in sub),'max':max(r[key] for r in sub)}
                           for key in ['branches','first_seconds','seconds','variables','constraints','effective_slots']}
    save('comparison.json',{'runs':rows,'summary':aggregates})
    assert api('/planner-scenarios/'+SID)==before,'Concurrent edits detected; saved draft not committed'
    committed=api('/planner-scenarios/'+SID+'/draft-commit',{'expected_revision':before['revision'],'operations':operations})
    save('committed.json',committed)
    current=api('/planner-scenarios/'+SID);save('project-after.json',current)
    # Only the A disassembly definition may have changed.
    previous={x['id']:x for x in baseline['activities'] if x['id']!=a['id']}
    assert {x['id']:x for x in current['scenario']['activities'] if x['id']!=a['id']}==previous
    for field in ['initial_state_ids','goal_state_ids','resources','work_calendars','work_calendar_id','exclusive_rules','night_lift_rule']:
        assert current['scenario'].get(field)==baseline.get(field),field
    final=current['scenario']
    body={'scenario_id':SID,'expected_revision':current['revision'],'engine':'JOINT_CP_SAT',
        'current_state_ids':final['initial_state_ids'],'target_state_ids':final['goal_state_ids'],
        'execution_bound_mode':'auto','budget_mode':'auto','seed':11,'client_request_id':'fix-dismantling-order-20261109',
        'display_start_at':'2026-11-09T08:00:00+08:00','display_timezone':'Asia/Shanghai'}
    job=api('/planner-runs/async',body);save('submitted.json',job)
    for _ in range(45):
        job=api('/planner-runs/'+job['id'])
        if job['job_status'] in ['FINISHED','FAILED']:break
        time.sleep(2)
    save('workbench-run.json',job)
    engine=job['result']['results']['JOINT_CP_SAT'];p=engine['paths'][0]
    assert engine['status']=='OPTIMAL' and p['validator_status']=='VALID' and p['metrics']['makespan']==90
    assert api('/planner-runs/'+old_run['id'])==old_run
    print(json.dumps({'revision':current['revision'],'run_id':job['id'],'summary':aggregates,
        'schedule':[{'name':e['activity_name'],'start':e['start_time'],'end':e['end_time']} for e in p['executions']]},ensure_ascii=False),flush=True)

if __name__=='__main__':main()

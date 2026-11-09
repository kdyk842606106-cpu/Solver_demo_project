"""Add user-approved A/D disassembly and compare with the saved 15-activity case."""
import copy
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_scenarios import create_activity,validate_scenario
from app.services.planner_execution_bounds import automatic_execution_bound
from app.services.planner_engine_bridge import run_engine

BASE='http://127.0.0.1:8016/api/v1'
SID='scenario:08c442a9-6af4-47cc-a618-e75c002de898'
OUT=ROOT/'output/user-dismantling-extension-20261109'
def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as res:return json.load(res)
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')

def main():
    OUT.mkdir(exist_ok=False)
    before=api('/planner-scenarios/'+SID);save('project-before.json',before)
    baseline=copy.deepcopy(before['scenario']);changed=copy.deepcopy(baseline)
    assert len(baseline['activities'])==15
    assert all(a.get('max_instances')==3 for a in baseline['activities'])
    old_runs=api('/planner-runs?scenario_id='+SID)
    history={r['id']:api('/planner-runs/'+r['id']) for r in old_runs}
    save('history-before.json',history)
    by_name={a['name']:a for a in baseline['activities']}
    operations=[];targets=list(baseline['goal_state_ids'])
    for i,module in enumerate(['A','D'],16):
        source=by_name['模块'+module+'安装']
        ref='draft:disassemble-'+module
        payload={'name':'拆卸模块'+module,'output_state_name':'模块'+module+'未安装',
            'duration':source['duration'],'resource_reqs':copy.deepcopy(source['resource_reqs']),
            'metadata':copy.deepcopy(source.get('metadata',{})), 'max_instances':3,
            'preconditions':[copy.deepcopy(p) for p in source['preconditions'] if p['relation_role']=='required']+
                            [{'state_id':source['output_state_id'],'relation_role':'transition'}],
            'delete_effect_state_ids':[]}
        payload['metadata']['description']='新增拆卸对照：时长、资源与对应安装相同，保留其普通前置并转移消耗本模块安装状态。'
        operations.append({'operation':'create_activity','client_ref':ref,'payload':payload})
        created=create_activity(changed,payload,display_number=i)
        changed['goal_state_ids'].append(created['output_state_id'])
        targets.append(ref+':output')
    changed['name']='模块A/B/C/D与AB线缆拆卸｜17活动｜日历与独占'
    operations.append({'operation':'update_scenario','payload':{'name':changed['name'],'goal_state_ids':targets}})
    save('operations.json',operations)
    rows=[]
    for seed in [11,23,37,53,71]:
        for label,source in [('before',baseline),('after',changed)]:
            s=copy.deepcopy(source)
            s['calendar_context']={'start_at':'2026-11-09T08:00:00+08:00','timezone':'Asia/Shanghai'}
            s['max_steps']=automatic_execution_bound(s)['value']
            assert not validate_scenario(s),validate_scenario(s)
            result=run_engine(s,engine='JOINT_CP_SAT',run_id='independent:extend-disassembly',seed=seed,
                budget_override={'time_limit_seconds':60},run_options={'worker_threads':8})
            save(f'{label}-seed{seed}.json',result)
            assert result['status']=='OPTIMAL',result['status']
            candidate=result['paths'][0];st=result['stats'];m=st['model']
            assert candidate['validator_status']=='VALID'
            assert candidate['metrics']['makespan']==(60 if label=='before' else 90)
            assert len(candidate['executions'])==(3 if label=='before' else 5)
            assert set(s['goal_state_ids'])<=set(candidate['final_state_ids'])
            row={'case':label,'seed':seed,'threads':st['worker_threads'],'first_seconds':result['first_solution_seconds'],
                'seconds':result['elapsed_seconds'],'branches':st['branches'],'conflicts':st['conflicts'],
                'variables':m['variables'],'constraints':m['constraints'],'input_slots':m['occurrence_pruning']['input_slots'],
                'effective_slots':m['optional_occurrence_slots'],'makespan':candidate['metrics']['makespan'],
                'executions':len(candidate['executions']),'status':result['status'],'validator':candidate['validator_status']}
            rows.append(row);print(json.dumps(row),flush=True)
    aggregates={}
    for label in ['before','after']:
        subset=[r for r in rows if r['case']==label]
        aggregates[label]={key:{'min':min(r[key] for r in subset),'median':statistics.median(r[key] for r in subset),'max':max(r[key] for r in subset)}
                           for key in ['branches','first_seconds','seconds','variables','constraints','effective_slots']}
    save('comparison.json',{'runs':rows,'summary':aggregates})
    # One revision-checked atomic commit; no mutation before both cases pass replay.
    assert api('/planner-scenarios/'+SID)==before,'Project changed during verification; review saved draft before retrying'
    committed=api('/planner-scenarios/'+SID+'/draft-commit',{'expected_revision':before['revision'],'operations':operations})
    save('committed.json',committed)
    current=api('/planner-scenarios/'+SID);save('project-after.json',current)
    final=current['scenario']
    assert len(final['activities'])==17 and len(final['goal_state_ids'])==5
    old_ids={a['id']:a for a in baseline['activities']}
    assert {a['id']:a for a in final['activities'] if a['id'] in old_ids}==old_ids
    assert final['initial_state_ids']==baseline['initial_state_ids']
    body={'scenario_id':SID,'expected_revision':current['revision'],'engine':'JOINT_CP_SAT',
        'current_state_ids':final['initial_state_ids'],'target_state_ids':final['goal_state_ids'],
        'execution_bound_mode':'auto','budget_mode':'auto','seed':11,'client_request_id':'extend-dismantling-a-d-20261109',
        'display_start_at':'2026-11-09T08:00:00+08:00','display_timezone':'Asia/Shanghai'}
    job=api('/planner-runs/async',body);save('submitted.json',job)
    for _ in range(45):
        job=api('/planner-runs/'+job['id'])
        if job['job_status'] in ['FINISHED','FAILED']:break
        time.sleep(2)
    save('workbench-run.json',job)
    engine=job['result']['results']['JOINT_CP_SAT'];p=engine['paths'][0]
    assert engine['status']=='OPTIMAL' and p['validator_status']=='VALID' and p['metrics']['makespan']==90
    assert all(api('/planner-runs/'+rid)==value for rid,value in history.items())
    print(json.dumps({'project':final['name'],'revision':current['revision'],'run_id':job['id'],'summary':aggregates,
        'schedule':[{'name':e['activity_name'],'start':e['start_time'],'end':e['end_time']} for e in p['executions']]},ensure_ascii=False),flush=True)

if __name__=='__main__':main()

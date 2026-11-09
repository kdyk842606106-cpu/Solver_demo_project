"""Remove duplicate activities, reuse power-down, verify a run-only start window."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import urllib.request
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/test-a-simplify-late-20261106'
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
REMOVED = ['扩展件补装前下电', '扩展件到货验收']

def load(name): return json.loads((OUT/name).read_text('utf-8'))
def save(name, data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def api(path, data=None):
    req=urllib.request.Request('http://127.0.0.1:8016/api/v1/'+path,
        data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)

def prepare():
    from app.services.planner_scenarios import update_activity,delete_activity,add_membership,validate_scenario
    before=load('before.json');s=copy.deepcopy(before['scenario']);a={x['name']:x for x in s['activities']}
    assert len(a)==18
    fault=next(x['id'] for x in s['states'] if x['name']=='模块A待维修')
    install=a['联调扩展件安装'];down=a['下电']
    removed_states={a[n]['output_state_id'] for n in REMOVED}
    pre=[r for r in install['preconditions'] if r['state_id'] not in removed_states]
    for n in ('模块A功能调测','模块B调测'):
        if not any(r['state_id']==a[n]['output_state_id'] for r in pre):
            pre.append({'state_id':a[n]['output_state_id'],'relation_role':'required'})
    ops=[{'operation':'update_activity','object_id':install['id'],'payload':{'preconditions':pre,
          'metadata':{**install.get('metadata',{}),'description':'复用原下电活动后补装；要求A/B调测已完成并保留结果。到货限制请在求解页本次活动时间窗设置最早开始，基准2026-11-07 08:00；刷新后需重新设置。补装使安全验收及整机联调失效。'}}},
         {'operation':'update_activity','object_id':down['id'],'payload':{
          'preconditions':[r for r in down['preconditions'] if r['state_id']!=fault],
          'metadata':{**down.get('metadata',{}),'description':'维修与扩展件补装共用的下电活动；消耗上电完成，产生下电完成。下电不破坏A/B调测及联调结果。'}}}]
    package=next(p for p in s['activity_packages'] if p['name']=='到料与补装')
    ops.append({'operation':'add_membership','payload':{'package_id':package['id'],'activity_id':down['id'],'sort_order':0}})
    for n in REMOVED: ops.append({'operation':'delete_activity','object_id':a[n]['id'],'payload':{}})
    for op in ops:
        if op['operation']=='update_activity': update_activity(s,op['object_id'],op['payload'])
        elif op['operation']=='delete_activity': delete_activity(s,op['object_id'])
        elif op['operation']=='add_membership':
            p=op['payload'];add_membership(s,p['package_id'],p['activity_id'],sort_order=p['sort_order'])
    assert not validate_scenario(copy.deepcopy(s))
    assert len(s['activities'])==16
    assert all(not removed_states.intersection(x.get('additional_output_state_ids',[])) for x in s['activities'])
    assert not any(x.get('event_reqs') for x in s['activities'])
    save('draft-commit.json',{'expected_revision':before['revision'],'operations':ops})
    save('preview.json',s)
    print('Prepared 5 atomic operations; 16 activities, no active arrival-event references.')

def payload(s, with_window=True):
    from app.services.planner_execution_bounds import automatic_execution_bound
    from app.services.planner_run_windows import ActivityTimeWindow,freeze_run_windows
    p=copy.deepcopy(s)
    p['calendar_context']={'start_at':'2026-11-06T08:00:00+08:00','timezone':'Asia/Shanghai'}
    p['max_steps']=automatic_execution_bound(p)['value']
    aid=next(a['id'] for a in s['activities'] if a['name']=='联调扩展件安装')
    if with_window:
        # Same frozen representation as the asynchronous request API.
        p['run_time_windows']=freeze_run_windows(p,[ActivityTimeWindow(activity_id=aid,
            earliest_start_at='2026-11-07T08:00:00+08:00')],datetime.fromisoformat(p['calendar_context']['start_at']))
    return p

def verify(s):
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.services.planner_scenarios import expand_packages
    from app.core.joint_cpsat import prepare_payload,replay_candidate,_occurrence_limits
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.models import Action,to_primitive
    from planner_experiment.simulator import PathSimulator
    from planner_experiment.working_time import next_activity_start,work_end
    p=expand_packages(payload(s));scene=scenario_from_dict(prepare_payload(p));a={x.name:x for x in scene.activities}
    order=['集成检测完成','模块A安装','模块B安装','模块D安装','模块C安装','安全验收','上电','模块B调测','模块A功能调测','下电','联调扩展件安装','安全验收','上电','扩展功能联调']
    t=0;counts={};rows=[]
    for name in order:
        act=a[name];counts[act.id]=counts.get(act.id,0)+1
        start=next_activity_start(scene.working_intervals,max(t,1440 if name=='联调扩展件安装' else 0),act)
        t=work_end(scene.working_intervals,start,act.duration)
        rows.append({'activity_id':act.id,'ordinal':counts[act.id],'start':start,'end':t})
    candidate,_=replay_candidate(p,scene,rows,run_id='local:simplify:reference',seed=11)
    assert candidate.validator_status=='VALID' and len(candidate.executions)==14
    caps,proofs=_occurrence_limits(scene)
    assert caps[a['上电'].id]>=2 and caps[a['安全验收'].id]>=2 and caps[a['下电'].id]>=1
    sim=PathSimulator(scene);state=sim.initial_state();preserved=False;invalidated=False
    def fact(n): return a[n].output_state_id in state.active_state_ids
    def enabled(n): return any(x.kind=='START' and x.activity_id==a[n].id for x in sim.enabled_actions(state))
    for action in candidate.actions:
        if state.time<1440 or fact('上电'): assert not enabled('联调扩展件安装')
        state=sim.transition(state,action)
        if fact('下电') and fact('模块A功能调测') and fact('模块B调测'): preserved=True
        if fact('联调扩展件安装') and not fact('安全验收'):
            invalidated=True;assert not enabled('上电') and not enabled('扩展功能联调')
    assert preserved and invalidated and sim.is_goal(state)
    save('reference.json',to_primitive(candidate));save('pruning.json',proofs)
    # Reuse the existing repair reference against generalized power-down.
    rp=payload(s,False)
    old=json.loads((ROOT/'output/test-a-repair-page-diagnosis/page-input.json').read_text('utf-8'))
    for k in ('initial_state_ids','goal_state_ids','forbidden_state_ids','activity_package_scope_ids','calendar_context'):rp[k]=old[k]
    rp=expand_packages(rp);rs=scenario_from_dict(prepare_payload(rp))
    reference=json.loads((ROOT/'output/test-a-late-material-20261106/repair-replay.json').read_text('utf-8'))
    repaired,_=replay_candidate(rp,rs,[{'activity_id':e['activity_id'],'ordinal':e['ordinal'],'start':e['start_time'],'end':e['end_time']} for e in reference['executions']],run_id='local:simplify:repair',seed=11)
    assert repaired.validator_status=='VALID'
    save('checks.json',{'passed':True,'earliest_start_enforced':True,'powered_install_rejected':True,'test_results_preserved':True,
        'safety_invalidated':True,'repeat_slots_retained':True,'repair_reference':'VALID','reference_makespan':candidate.metrics.makespan})

def solve(case):
    from app.services.planner_engine_bridge import _planner_modules,run_engine
    _planner_modules()
    from planner_experiment.models import to_primitive
    s=load('preview.json');verify(s);p=payload(s,case=='window');save(case+'-input.json',p)
    started=time.perf_counter()
    with (OUT/(case+'-progress.jsonl')).open('w',encoding='utf-8') as log:
        def progress(metrics,best):
            row=dict(metrics,observed_seconds=time.perf_counter()-started,improved=best is not None)
            log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush()
            if best is not None: print(json.dumps(row,ensure_ascii=False),flush=True)
        r=run_engine(p,engine='JOINT_CP_SAT',run_id='local:simplify:'+case,seed=11,budget_override={'time_limit_seconds':600},progress_observer=progress)
    save(case+'-result.json',r)
    assert r['paths'] and r['paths'][0]['validator_status']=='VALID'
    names={a['id']:a['name'] for a in s['activities']}
    summary={k:r.get(k) for k in ('status','first_solution_seconds','elapsed_seconds','lower_bound','proven_optimal')}
    summary.update({k:r['stats'].get(k) for k in ('branches','conflicts','best_makespan','best_execution_count')})
    summary['schedule']=[{'name':names[e['activity_id']],'ordinal':e['ordinal'],'start':e['start_time'],'end':e['end_time']} for e in r['paths'][0]['executions']]
    install=next(e for e in summary['schedule'] if e['name']=='联调扩展件安装' and e['ordinal']==1)
    assert (install['start']>=1440) if case=='window' else (install['start']<1440)
    save(case+'-summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)

def apply():
    assert load('checks.json')['passed']
    assert load('window-summary.json')['proven_optimal'] and load('no-window-summary.json')['proven_optimal']
    before=load('before.json');assert api('planner-scenarios/'+SID)==before,'Revision changed; rebase required'
    save('commit-response.json',api('planner-scenarios/'+SID+'/draft-commit',load('draft-commit.json')))
    after=api('planner-scenarios/'+SID);save('after.json',after)
    assert after['revision']==before['revision']+1
    verify(after['scenario'])
    assert len(after['scenario']['activities'])==16
    assert api('planner-runs?scenario_id='+SID)==load('history-before.json')
    assert not after['scenario'].get('run_time_windows')
    save('validation.json',{'revision':after['revision'],'activities':16,'history_unchanged':True,'window_is_run_only':True})
    print(json.dumps(load('validation.json')))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','window','no-window','apply'])
    action=parser.parse_args().action
    if action=='prepare': prepare()
    elif action=='apply': apply()
    else: solve(action)

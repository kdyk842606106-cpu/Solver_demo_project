"""Back up, configure and verify the approved Test A maintenance package.

Only --apply sends a single draft-commit. Reference replay is never inserted
into run history. --verify repeats read-only checks after an interrupted run.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
EXPECTED_HASH = '294ff7d7b9d9219f0e37d8c8c05ca1ebc3ab89eaa41ae2dc349afec11a286400'
BASE = 'http://127.0.0.1:8016/api/v1'
OUT = ROOT/'output/test-a-repair-20261105'


def api(path, data=None):
    request = urllib.request.Request(BASE+path, data=None if data is None else json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def save(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def draft(s):
    acts = {a['name']: a for a in s['activities']}
    states = {name: a['output_state_id'] for name, a in acts.items()}
    resources = {r['name']: r['id'] for r in s['resources']}
    refs = {n: f'draft:repair:activity:{i}' for i,n in enumerate(['下电','模块C拆卸','模块A拆卸','模块A维修'])}
    states.update({n: ref+':output' for n,ref in refs.items()})
    fault = 'draft:repair:fault'
    operations = []

    def op(operation, payload, *, ref=None, object_id=None):
        operations.append({'operation': operation, 'payload': payload,
                           **({'client_ref': ref} if ref else {}), **({'object_id': object_id} if object_id else {})})

    def pre(names, role='required'):
        return [{'state_id': states[n], 'relation_role': role} for n in names]

    root = 'draft:repair:root'
    op('create_package', {'name': '维修模块A', 'sort_order': 0}, ref=root)
    groups = [('停机与拆卸', ['下电','模块C拆卸','模块A拆卸']),
              ('维修与回装', ['模块A维修','模块A安装','模块C安装']),
              ('验收与调测', ['安全验收','上电','模块A功能调测','模块B调测','模块联调'])]
    for index,(name,_) in enumerate(groups):
        op('create_package', {'name':name,'parent_id':root,'sort_order':index}, ref=f'draft:repair:group:{index}')
    op('create_seed_state', {'name':'模块A待维修'}, ref=fault)
    definitions = [
        ('下电',10,[],['上电'],['模块A功能调测','模块B调测','模块联调'],{'A':2}),
        ('模块C拆卸',20,['下电'],['模块C安装'],['安全验收','模块A功能调测','模块联调'],{'B':2,'左':1,'右':1}),
        ('模块A拆卸',30,['下电','模块C拆卸'],['模块A安装'],['安全验收','模块A功能调测','模块联调'],{'A':2,'行吊1':1,'左':1}),
        ('模块A维修',60,['下电','模块A拆卸','模块C拆卸'],[],[],{'A':2,'左':1}),
    ]
    for name,duration,required,transition,deletes,reqs in definitions:
        op('create_activity', {'name':name,'duration':duration,'max_instances':3,
           'output_state_name':name+'完成','preconditions':pre(required)+pre(transition,'transition')+[
               {'state_id':fault,'relation_role':'transition' if name=='模块A维修' else 'required'}],
           'delete_effect_state_ids':[states[n] for n in deletes],
           'resource_reqs':{resources[n]:q for n,q in reqs.items()},
           'metadata':{'activity_type':'机械集成','precision_fragile':name=='模块A拆卸',
                       'description':'测试A单次已知故障维修；按已确认测试参数配置。'}}, ref=refs[name])
    for name,a in acts.items():
        payload = {'max_instances':3}
        conditions = copy.deepcopy(a['preconditions'])
        deletes = list(a.get('delete_effect_state_ids', []))
        if name in ('模块A安装','模块C安装'):
            conditions += pre(['下电'])
            counterpart = '模块A拆卸' if name=='模块A安装' else '模块C拆卸'
            deletes += [states[n] for n in [counterpart,'安全验收','模块A功能调测','模块联调']]
        elif name=='安全验收':
            conditions += pre(['下电'])
        elif name=='上电':
            conditions += pre(['下电'],'transition')
        elif name in ('模块A功能调测','模块B调测'):
            conditions += pre(['模块A安装' if name=='模块A功能调测' else '模块B安装','安全验收'])
        elif name=='模块联调':
            conditions += pre(['上电','安全验收'])
        payload.update(preconditions=conditions, delete_effect_state_ids=sorted(set(deletes)))
        op('update_activity', payload, object_id=a['id'])
    for index,(_,names) in enumerate(groups):
        for order,name in enumerate(names):
            op('add_membership', {'package_id':f'draft:repair:group:{index}',
                                  'activity_id':refs[name] if name in refs else acts[name]['id'],'sort_order':order})
    initial_names = ['集成检测完成','模块A安装','模块B安装','模块C安装','模块D安装','安全验收','上电','模块B调测']
    op('update_scenario', {'initial_state_ids':[states[n] for n in initial_names]+[fault],
                          'goal_state_ids':[states['模块A维修'],states['模块联调']],
                          'forbidden_state_ids':[fault], 'activity_package_scope_ids':[root]})
    return {'expected_revision':6,'operations':operations}


def preview(s, request):
    """Apply the operations to a disposable copy using the server's domain helpers."""
    from app.services.planner_scenarios import (create_package, create_activity, update_activity,
        add_membership, technical_id, rebuild_mirror, validate_scenario)
    result, refs = copy.deepcopy(s), {}

    def resolve(v):
        if isinstance(v,str) and v.startswith('draft:'): return refs[v]
        if isinstance(v,list): return [resolve(x) for x in v]
        if isinstance(v,dict): return {resolve(k):resolve(x) for k,x in v.items()}
        return v
    activity_number, package_number = 11, 1
    for item in request['operations']:
        data, kind = resolve(item['payload']), item['operation']
        if kind=='create_package':
            created=create_package(result,data,display_number=package_number);package_number+=1
        elif kind=='create_activity':
            created=create_activity(result,data,display_number=activity_number);activity_number+=1
        elif kind=='update_activity':
            created=update_activity(result,item['object_id'],data)
        elif kind=='add_membership':
            created=add_membership(result,data['package_id'],data['activity_id'],sort_order=data['sort_order'])
        elif kind=='create_seed_state':
            created={'id':technical_id('state')+':seed','name':data['name'],'state_kind':'seed','managed':True}
            result['states'].append(created)
        elif kind=='update_scenario':
            result.update(data);created=result
        else: raise AssertionError(kind)
        if item.get('client_ref'):
            refs[item['client_ref']]=created['id']
            if kind=='create_activity':refs[item['client_ref']+':output']=created['output_state_id']
    rebuild_mirror(result)
    assert not validate_scenario(copy.deepcopy(result)), validate_scenario(copy.deepcopy(result))
    return result


def verify(s, *, full=False):
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.services.planner_scenarios import expand_packages, validate_scenario
    from app.services.planner_execution_bounds import automatic_execution_bound
    from app.core.joint_cpsat import build_model, replay_candidate, solve_joint, _occurrence_limits
    from planner_experiment.models import Budget, Action, to_primitive
    from planner_experiment.simulator import PathSimulator
    assert len(s['activities'])==14 and len(s['activity_packages'])==4
    assert len(s['activity_package_memberships'])==11
    assert all(a['max_instances']==3 for a in s['activities'])
    assert not validate_scenario(copy.deepcopy(s))
    scoped=expand_packages(copy.deepcopy(s))
    assert len(scoped['activities'])==11
    acts={a['name']:a for a in s['activities']}
    scoped['max_steps']=automatic_execution_bound(s)['value']
    scoped['calendar_context']={'start_at':'2026-11-09T08:00:00+08:00','timezone':'Asia/Shanghai'}
    _,scene,_,_=build_model(scoped)
    schedule=[('下电',0,10),('模块C拆卸',10,30),('模块A拆卸',30,60),('模块A维修',60,120),
              ('模块A安装',120,180),('模块C安装',180,200),('安全验收',200,240),('上电',300,330),
              ('模块A功能调测',330,360),('模块B调测',360,410),('模块联调',410,440)]
    rows=[{'activity_id':acts[n]['id'],'ordinal':1,'start':a,'end':b} for n,a,b in schedule]
    candidate,_=replay_candidate(scoped,scene,rows,run_id='reference-only:not-a-solver-run',seed=11)
    assert candidate.validator_status=='VALID' and candidate.metrics.makespan==440
    assert len(candidate.executions)==11
    caps,proofs=_occurrence_limits(scene)
    assert all(caps[acts[n]['id']]>0 for n in ['下电','模块C拆卸','模块A拆卸','模块A维修','模块A安装','模块C安装'])
    fault=next(x['id'] for x in s['states'] if x['name']=='模块A待维修')
    assert fault not in candidate.final_state_ids
    sim=PathSimulator(scene);state=sim.initial_state()
    def enabled(name):
        return any(a.kind=='START' and a.activity_id==acts[name]['id'] for a in sim.enabled_actions(state))
    assert not enabled('模块A维修')
    for name in ['下电','模块C拆卸','模块A拆卸']:
        if name=='模块C拆卸':assert not enabled('模块A拆卸')
        state=sim.transition(state,Action('START',activity_id=acts[name]['id']))
        state=sim.transition(state,next(a for a in sim.enabled_actions(state) if a.kind=='ADVANCE'))
    state=sim.transition(state,Action('START',activity_id=acts['模块A维修']['id']))
    assert not enabled('模块A安装') and not enabled('模块C安装') and not enabled('上电')
    report={'activities':14,'packages':4,'references':11,'reference_validator':'VALID',
            'reference_makespan':440,'reference_executions':11,'reference_start':'2026-11-09T08:00:00+08:00',
            'reference_finish':'2026-11-09T15:20:00+08:00','reference_only':True,
            'unsafe_actions_rejected':True,'required_recovery_retained':True,
            'solver_performance_limitation':'Planning-stage free search timed out without a candidate; not fixed in this change.'}
    if full:
        save('reference-path.json',to_primitive(candidate))
        save('reference-input.json',scoped)
        missing=copy.deepcopy(scoped);missing['initial_state_ids'].remove(fault)
        r=solve_joint(missing,run_id='local-check:no-fault',seed=11,budget=Budget(10,1,3))
        assert r.status=='INFEASIBLE'
        report['missing_fault_result']=r.status
        normal=copy.deepcopy(s);normal['activity_package_scope_ids']=[]
        normal['initial_state_ids']=[acts['下电']['output_state_id']]
        normal['goal_state_ids']=[acts['模块联调']['output_state_id']]
        normal=expand_packages(normal);normal['calendar_context']=scoped['calendar_context']
        normal['max_steps']=automatic_execution_bound(normal)['value']
        r=solve_joint(normal,run_id='local-check:normal',seed=11,budget=Budget(60,1,3))
        save('normal-check-result.json',to_primitive(r))
        assert r.paths and r.paths[0].validator_status=='VALID',r.status
        report['normal_result']={'status':r.status,'makespan':r.paths[0].metrics.makespan,'validator':'VALID'}
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    path='/planner-scenarios/'+SID
    if not args.verify:
        before=api(path)
        assert before['revision']==6 and before['scenario_hash']==EXPECTED_HASH,'Scenario changed; rebase draft before applying.'
        OUT.mkdir(parents=True,exist_ok=False)
        save('before.json',before)
        save('before-export.json',api(path+'/export'))
        save('projects-before.json',api('/planner-scenarios'))
        history=api('/planner-runs?scenario_id='+SID)
        details={r['id']:api('/planner-runs/'+r['id']) for r in history}
        save('history-before.json',details)
        request=draft(before['scenario']);save('draft-commit.json',request)
        local=preview(before['scenario'],request)
        save('preview-validation.json',verify(local))
        if not args.apply:
            print('Draft prepared and locally validated; no server writes.');return
        latest=api(path)
        assert latest['revision']==before['revision'] and latest['scenario_hash']==before['scenario_hash'],'Conflict: draft retained without submission.'
        try:
            committed=api(path+'/draft-commit',request)
        except urllib.error.HTTPError as error:
            save('commit-error.json',{'status':error.code,'body':error.read().decode()});raise
        save('commit-response.json',committed)
        print('Committed Test A revision',committed['revision'],flush=True)
    before=json.loads((OUT/'before.json').read_text('utf-8'))
    after=api(path);save('after.json',after)
    assert after['revision']==before['revision']+1
    original_activities={a['id']:a for a in before['scenario']['activities']}
    updated={a['id']:a for a in after['scenario']['activities']}
    for aid,a in original_activities.items():
        for field in ('name','duration','resource_reqs','metadata','output_state_id'):
            assert a.get(field)==updated[aid].get(field),(aid,field)
    for field in ('resources','work_calendars','work_calendar_id','night_lift_rule','exclusive_rules','default_budget'):
        assert before['scenario'][field]==after['scenario'][field],field
    old_history=json.loads((OUT/'history-before.json').read_text('utf-8'))
    assert all(digest(saved)==digest(api('/planner-runs/'+rid)) for rid,saved in old_history.items())
    assert {r['id'] for r in api('/planner-runs?scenario_id='+SID)}==set(old_history)
    other_before={x['id']:x for x in json.loads((OUT/'projects-before.json').read_text('utf-8')) if x['id']!=SID}
    other_after={x['id']:x for x in api('/planner-scenarios') if x['id']!=SID}
    assert other_before==other_after
    report=verify(after['scenario'],full=True)
    report.update(scenario_id=SID,revision=after['revision'],historical_runs_unchanged=len(old_history),
                  other_projects_unchanged=True,atomic_commit=True)
    save('validation.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()

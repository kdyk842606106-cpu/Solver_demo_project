"""Complete three activity delete effects; compare latest request without DB runs."""
import argparse
import copy
import json
import time
import verify_test_a_all_scope as base

base.OUT = base.ROOT / 'output/test-a-b-d-repair-effects-20261106'
EFFECTS = {
    '模块B安装': ['模块B调测', '安全验收', '模块联调', '扩展功能联调'],
    '模块D安装': ['安全验收', '模块联调', '扩展功能联调'],
    '模块A维修': ['模块A功能调测', '安全验收', '模块联调', '扩展功能联调'],
}

def read(name):
    return json.loads((base.OUT/name).read_text(encoding='utf-8-sig'))

def prepare():
    from app.services.planner_scenarios import update_activity, validate_scenario
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    before = read('before.json')
    s = copy.deepcopy(before['scenario'])
    acts = {a['name']: a for a in s['activities']}
    ops = []
    for name, names in EFFECTS.items():
        a = acts[name]
        effects = sorted(set(a.get('delete_effect_state_ids', [])) | {acts[n]['output_state_id'] for n in names})
        op = {'operation': 'update_activity', 'object_id': a['id'], 'payload': {'delete_effect_state_ids': effects}}
        ops.append(op)
        update_activity(s, a['id'], op['payload'])
    assert not validate_scenario(copy.deepcopy(s))
    base.save('preview.json', s)
    base.save('draft-commit.json', {'expected_revision': before['revision'], 'operations': ops})
    req = read('previous-run.json')['request']
    for case, source in [('before', before['scenario']), ('after', s)]:
        p = copy.deepcopy(source)
        p['initial_state_ids'] = req['current_state_ids']
        p['goal_state_ids'] = req['target_state_ids']
        p['calendar_context'] = req['effective_scenario_snapshot']['calendar_context']
        p['run_time_windows'] = req['effective_scenario_snapshot'].get('run_time_windows', [])
        p['max_steps'] = automatic_execution_bound(p)['value']
        base.save(case+'-input.json', p)
    base.save('budget.json', automatic_solver_budget(p))
    print(json.dumps({'initial_count': len(p['initial_state_ids']), 'goal_count':len(p['goal_state_ids']),
                      'effects':EFFECTS, 'budget':read('budget.json')},ensure_ascii=False))

def checks():
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.services.planner_scenarios import expand_packages
    from app.core.joint_cpsat import prepare_payload, replay_candidate
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.models import to_primitive, Action
    from planner_experiment.simulator import PathSimulator
    p=expand_packages(read('after-input.json'))
    sc=scenario_from_dict(prepare_payload(p))
    old=read('previous-run.json')['result']['results']['JOINT_CP_SAT']['paths'][0]
    rows=[{'activity_id':e['activity_id'],'ordinal':e['ordinal'],'start':e['start_time'],'end':e['end_time']} for e in old['executions']]
    candidate,_=replay_candidate(p,sc,rows,run_id='local:effects:reference',seed=11)
    assert candidate.validator_status=='VALID'
    base.save('reference.json',to_primitive(candidate))
    a={x['name']:x for x in read('preview.json')['activities']}
    all_effects={a[n]['output_state_id'] for v in EFFECTS.values() for n in v}
    audit=[]
    for name, names in EFFECTS.items():
        q=copy.deepcopy(read('after-input.json'))
        # Controlled inputs include all required states and stale result facts.
        required={r['state_id'] for r in a[name]['preconditions']}
        q['initial_state_ids']=sorted(required | all_effects)
        q['goal_state_ids']=[a[name]['output_state_id']]
        sq=scenario_from_dict(prepare_payload(expand_packages(q)))
        sim=PathSimulator(sq); state=sim.initial_state()
        state=sim.transition(state,Action('START',activity_id=a[name]['id']))
        while state.running:
            advance=next(x for x in sim.enabled_actions(state) if x.kind=='ADVANCE')
            state=sim.transition(state,advance)
        expected={a[n]['output_state_id'] for n in names}
        assert not expected.intersection(state.active_state_ids)
        audit.append({'activity':name,'cleared':names})
    base.save('checks.json',{'passed':True,'previous_plan_validator':candidate.validator_status,
                             'previous_plan_makespan':candidate.metrics.makespan,'effect_checks':audit})
    print(json.dumps(read('checks.json'),ensure_ascii=False))

def solve(case):
    from app.services.planner_engine_bridge import run_engine
    p=read(case+'-input.json'); budget=read('budget.json')
    started=time.perf_counter()
    with (base.OUT/(case+'-progress.jsonl')).open('w',encoding='utf-8') as stream:
        def progress(metrics,best):
            stream.write(json.dumps(dict(metrics,observed_seconds=time.perf_counter()-started,improved=best is not None),ensure_ascii=False)+'\n')
            stream.flush()
        result=run_engine(p,engine='JOINT_CP_SAT',run_id='local:b-d-repair:'+case,seed=11,
                          budget_override={'time_limit_seconds':budget['time_limit_seconds']},progress_observer=progress)
    base.save(case+'-result.json',result)
    stats=result['stats']; acts={a['id']:a for a in p['activities']}
    summary={k:result.get(k) for k in ('status','elapsed_seconds','first_solution_seconds','lower_bound','proven_optimal')}
    summary.update({k:stats.get(k) for k in ('branches','conflicts','best_makespan','best_execution_count','worker_threads','model')})
    summary['schedule']=[]
    if result['paths']:
        path=result['paths'][0]
        assert path['validator_status']=='VALID'
        assert set(p['goal_state_ids']).issubset(path['final_state_ids'])
        assert not set(p['forbidden_state_ids']).intersection(path['final_state_ids'])
        summary['validator']=path['validator_status']
        summary['schedule']=[{'name':acts[e['activity_id']]['name'],'ordinal':e['ordinal'],
                              'start':e['start_time'],'end':e['end_time']} for e in path['executions']]
        summary['final_state_ids']=path['final_state_ids']
    base.save(case+'-summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('model','final_state_ids')},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','checks','before','after','apply','verify'])
    action=parser.parse_args().action
    if action in ('apply','verify'):
        if action=='apply':
            assert read('checks.json')['passed']
            assert read('after-summary.json')['validator']=='VALID'
        getattr(base,action)()
    elif action in ('before','after'):
        solve(action)
    else:
        globals()[action]()

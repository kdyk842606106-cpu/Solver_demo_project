"""Hypothetical local tests only; never commit or create planner-run records."""
import argparse
import copy
import json
import fix_test_a_b_d_repair_effects as runner

runner.base.OUT = runner.base.ROOT / 'output/test-a-install-keeps-tests-20261106'
INSTALLS = ['模块A安装', '模块B安装', '模块C安装', '模块D安装', '联调扩展件安装']

def prepare():
    from app.services.planner_scenarios import update_activity, validate_scenario
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    source=runner.read('source.json')['scenario']
    req=runner.read('previous-run.json')['request']
    acts={a['name']:a for a in source['activities']}
    tests={acts[n]['output_state_id'] for n in ['模块A功能调测','模块B调测','模块联调','扩展功能联调']}
    for case in ['install-only','disassembly-only']:
        p=copy.deepcopy(source)
        names=set(INSTALLS + (['模块A维修'] if case=='disassembly-only' else []))
        changes=[]
        for a in p['activities']:
            if a['name'] not in names:
                continue
            old=a.get('delete_effect_state_ids',[])
            removed=set(old)&tests
            update_activity(p,a['id'],{'delete_effect_state_ids':[x for x in old if x not in tests]})
            changes.append({'activity':a['name'],'removed_test_deletions':sorted(removed),'remaining_deletions':a['delete_effect_state_ids']})
        p['initial_state_ids']=req['current_state_ids']
        p['goal_state_ids']=req['target_state_ids']
        p['calendar_context']=req['effective_scenario_snapshot']['calendar_context']
        p['run_time_windows']=req['effective_scenario_snapshot'].get('run_time_windows',[])
        p['max_steps']=automatic_execution_bound(p)['value']
        assert not validate_scenario(copy.deepcopy(p))
        runner.base.save(case+'-input.json',p)
        runner.base.save(case+'-changes.json',changes)
    runner.base.save('budget.json',automatic_solver_budget(p))
    previous=json.loads((runner.base.ROOT/'output/test-a-b-d-repair-effects-20261106/after-input.json').read_text(encoding='utf-8'))
    keys=['initial_state_ids','goal_state_ids','calendar_context','run_time_windows','forbidden_state_ids','activity_package_scope_ids']
    assert all(p.get(k)==previous.get(k) for k in keys)
    print(json.dumps({'source_revision':source['revision'],'same_previous_request':True,'budget':runner.read('budget.json')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','install-only','disassembly-only'])
    action=parser.parse_args().action
    if action=='prepare': prepare()
    else: runner.solve(action)

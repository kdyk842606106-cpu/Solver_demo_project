"""Repair Test A's missing extended-commissioning invalidation edges."""
import argparse
import copy
import json
import verify_test_a_all_scope as base

base.OUT = base.ROOT / 'output/test-a-extended-invalidation-20261106'
base.RUN = 'planner-run:c085bba0-ad5e-46d7-875e-5479673fc722'
TARGETS = ('模块A安装', '模块C安装', '模块A拆卸', '模块C拆卸')

def prepare():
    from app.services.planner_scenarios import update_activity, validate_scenario
    from app.services.planner_execution_bounds import automatic_execution_bound, automatic_solver_budget
    before = base.api('planner-scenarios/' + base.SID)
    base.save('before.json', before)
    base.save('history-before.json', base.api('planner-runs?scenario_id=' + base.SID))
    old = base.api('planner-runs/' + base.RUN)
    base.save('previous-run.json', old)
    s = copy.deepcopy(before['scenario'])
    acts = {a['name']: a for a in s['activities']}
    goal = acts['扩展功能联调']['output_state_id']
    ops = []
    for name in TARGETS:
        a = acts[name]
        effects = list(dict.fromkeys([*a.get('delete_effect_state_ids', []), goal]))
        op = {'operation': 'update_activity', 'object_id': a['id'],
              'payload': {'delete_effect_state_ids': effects}}
        ops.append(op)
        update_activity(s, a['id'], op['payload'])
    assert not validate_scenario(copy.deepcopy(s))
    base.save('preview.json', s)
    base.save('draft-commit.json', {'expected_revision': before['revision'], 'operations': ops})
    p = copy.deepcopy(s)
    req = old['request']
    for key, source in [('initial_state_ids', 'current_state_ids'), ('goal_state_ids', 'target_state_ids')]:
        p[key] = req[source]
    p['calendar_context'] = req['effective_scenario_snapshot']['calendar_context']
    p['run_time_windows'] = req['effective_scenario_snapshot'].get('run_time_windows', [])
    p['max_steps'] = automatic_execution_bound(p)['value']
    base.save('input.json', p)
    base.save('budget.json', automatic_solver_budget(p))
    print(json.dumps({'revision': before['revision'], 'updated': TARGETS, 'budget': base.load('budget.json')}, ensure_ascii=False))

def checks():
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.services.planner_scenarios import expand_packages
    from app.core.joint_cpsat import prepare_payload, replay_candidate
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.working_time import next_activity_start, work_end
    from planner_experiment.models import to_primitive
    p = expand_packages(base.load('input.json'))
    scenario = scenario_from_dict(prepare_payload(p))
    old = base.load('previous-run.json')['result']['results']['JOINT_CP_SAT']['paths'][0]
    rows = [{'activity_id': e['activity_id'], 'ordinal': e['ordinal'], 'start': e['start_time'], 'end': e['end_time']} for e in old['executions']]
    try:
        replay_candidate(p, scenario, rows, run_id='local:invalidation:old', seed=11)
    except ValueError as error:
        assert 'goal' in str(error).lower(), str(error)
        rejected = str(error)
    else:
        raise AssertionError('Old incomplete terminal plan remains valid')
    names = {a.name: a for a in scenario.activities}
    # Independent feasibility witness, never supplied as a hint to free search.
    order = ['下电', '联调扩展件安装', '模块C拆卸', '模块A拆卸', '模块A维修',
             '模块A安装', '模块C安装', '安全验收', '上电', '模块A功能调测', '扩展功能联调']
    rows = []
    t = 0
    for name in order:
        a = names[name]
        start = next_activity_start(scenario.working_intervals, t, a)
        t = work_end(scenario.working_intervals, start, a.duration)
        rows.append({'activity_id': a.id, 'ordinal': 1, 'start': start, 'end': t})
    candidate, _ = replay_candidate(p, scenario, rows, run_id='local:invalidation:reference', seed=11)
    base.save('reference.json', to_primitive(candidate))
    base.save('checks.json', {'old_plan_rejected': rejected, 'reference_validator': candidate.validator_status,
                              'reference_makespan': candidate.metrics.makespan, 'reference_executions': len(candidate.executions)})
    print(json.dumps(base.load('checks.json'), ensure_ascii=False))

def solve():
    base.solve()
    result = base.load('result.json')
    if result['paths']:
        p = base.load('input.json')
        acts = {a['name']: a for a in p['activities']}
        final = set(result['paths'][0]['final_state_ids'])
        required = ['模块A安装', '模块C安装', '安全验收', '上电', '模块A功能调测', '扩展功能联调', '模块A维修']
        assert all(acts[n]['output_state_id'] in final for n in required)
        assert not final.intersection(p['forbidden_state_ids'])
        base.save('terminal-checks.json', {'passed': True, 'final_outputs': required})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'checks', 'solve', 'apply', 'verify'])
    action = parser.parse_args().action
    if action in ('apply', 'verify'):
        if action == 'apply':
            assert base.load('checks.json')['reference_validator'] == 'VALID'
        getattr(base, action)()
    else:
        globals()[action]()

"""Prepare, independently test, and atomically commit the approved late-material case.

No planner-run POST is used. Each solve writes only local evidence.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/test-a-late-material-20261106'
SID = 'scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
ANCHOR = {'start_at': '2026-11-06T08:00:00+08:00', 'timezone': 'Asia/Shanghai'}
NEW = ['扩展件到货验收', '扩展件补装前下电', '联调扩展件安装', '扩展功能联调']
BASE = ['集成检测完成', '模块A安装', '模块B安装', '模块C安装', '模块D安装', '安全验收', '上电', '模块A功能调测', '模块B调测']

def api(path, data=None):
    req = urllib.request.Request('http://127.0.0.1:8016/api/v1/' + path,
        data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def load(name):
    return json.loads((OUT / name).read_text('utf-8'))

def prepare():
    OUT.mkdir(parents=True, exist_ok=False)
    before = api('planner-scenarios/' + SID)
    save('before.json', before)
    save('before-export.json', api('planner-scenarios/' + SID + '/export'))
    history = api('planner-runs?scenario_id=' + SID)
    save('history-before.json', history)
    save('history-details-before.json', {r['id']: api('planner-runs/' + r['id']) for r in history})
    s = before['scenario']
    assert len(s['activities']) == 14 and len(s['activity_packages']) == 4
    acts = {a['name']: a for a in s['activities']}
    states = {n: a['output_state_id'] for n, a in acts.items()}
    resources = {r['name']: r['id'] for r in s['resources']}
    refs = {n: 'draft:late:activity:' + str(i) for i, n in enumerate(NEW)}
    states.update({n: ref + ':output' for n, ref in refs.items()})
    operations = []
    def op(kind, data, ref=None, object_id=None):
        operations.append({'operation': kind, 'payload': data,
            **({'client_ref': ref} if ref else {}), **({'object_id': object_id} if object_id else {})})
    def pre(required=(), transition=()):
        return [{'state_id': states[n], 'relation_role': role} for role, ns in [('required', required), ('transition', transition)] for n in ns]
    root = 'draft:late:root'
    op('create_package', {'name': '晚到物料补装', 'sort_order': 1}, root)
    groups = [('预装与单模块调测', BASE), ('到料与补装', NEW[:3]), ('最终联调', NEW[3:])]
    for i, (name, _) in enumerate(groups):
        op('create_package', {'name': name, 'parent_id': root, 'sort_order': i}, 'draft:late:group:' + str(i))
    event_ref = 'draft:late:arrival'
    op('create_event', {'name': '联调扩展件到位（计划起点后24小时）', 'time': int(s.get('start_time', 0)) + 1440,
                        'add_state_ids': [], 'remove_state_ids': []}, event_ref)
    definitions = [
        (NEW[0], 10, pre(), {'B': 1}, {'event_reqs': [event_ref], 'output_state_name': '扩展件验收完成'},
         '扩展件在计划起点后1440个自然分钟到位，之后才能验收。基准2026-11-06 08:00开始，2026-11-07 08:00到货；开始日期改变，到货日期随之移动。'),
        (NEW[1], 10, pre([NEW[0], '模块A功能调测', '模块B调测'], ['上电']), {'A': 2},
         {'additional_output_state_ids': [states['下电']]}, '补装前下电，同时产生通用下电完成状态；保留A/B调测及联调结果。'),
        (NEW[2], 30, pre(['下电', '模块A安装', '模块B安装', NEW[0]], [NEW[1]]), {'B': 2, '行吊1': 1, '右': 1},
         {}, '下电后安装晚到扩展件；保留A/B单模块调测结果，使安全验收及整机联调失效，需要重新验收、上电和扩展功能联调。'),
        (NEW[3], 30, pre([NEW[2], '模块A功能调测', '模块B调测', '安全验收', '上电']), {'A': 3},
         {}, '扩展件补装及再次安全验收、上电后进行最终联调；沿用提前完成的A/B单模块调测结果。'),
    ]
    for n, duration, conditions, reqs, extra, description in definitions:
        op('create_activity', {'name': n, 'duration': duration, 'max_instances': 3, 'preconditions': conditions,
            'resource_reqs': {resources[k]: v for k, v in reqs.items()},
            'metadata': {'activity_type': '功能调测' if n == NEW[3] else '机械集成',
                         'precision_fragile': False, 'description': description}, **extra}, refs[n])
    op('update_activity', {'delete_effect_state_ids': [states[n] for n in ['安全验收', '模块联调', NEW[3]]]}, object_id=refs[NEW[2]])
    old_down = acts['下电']
    removed = {states[n] for n in ['模块A功能调测', '模块B调测', '模块联调']}
    op('update_activity', {'delete_effect_state_ids': [x for x in old_down.get('delete_effect_state_ids', []) if x not in removed],
        'metadata': {**old_down.get('metadata', {}), 'description': '已知故障维修下电；保留A/B调测和联调结果，拆装活动另按其影响使结果失效。'}}, object_id=old_down['id'])
    for i, (_, ns) in enumerate(groups):
        for order, n in enumerate(ns):
            op('add_membership', {'package_id': 'draft:late:group:' + str(i),
                                 'activity_id': refs.get(n) or acts[n]['id'], 'sort_order': order})
    op('update_scenario', {'activity_package_scope_ids': [root], 'goal_state_ids': [states[NEW[3]]],
        'initial_state_ids': [states[n] for n in ['下电', '模块A拆卸', '模块C拆卸']]})
    request = {'expected_revision': before['revision'], 'operations': operations}
    save('draft-commit.json', request)

    from app.services.planner_scenarios import create_package, create_activity, update_activity, add_membership, technical_id, rebuild_mirror, validate_scenario
    from app.api.v1.planner_scenarios import ActivityCreate, ActivityUpdate, PackageCreate, ScenarioUpdate, EventCreate
    preview, mapping = copy.deepcopy(s), {}
    def resolve(v):
        if isinstance(v, str) and v.startswith('draft:'): return mapping[v]
        if isinstance(v, list): return [resolve(x) for x in v]
        if isinstance(v, dict): return {resolve(k): resolve(x) for k, x in v.items()}
        return v
    for item in operations:
        kind, data = item['operation'], resolve(item['payload'])
        schema = {'create_package': PackageCreate, 'create_activity': ActivityCreate, 'update_activity': ActivityUpdate,
                  'update_scenario': ScenarioUpdate, 'create_event': EventCreate}.get(kind)
        if schema: data = schema.model_validate(data).model_dump(exclude_unset=True)
        if kind == 'create_package': created = create_package(preview, data, display_number=len(preview['activity_packages']) + 1)
        elif kind == 'create_activity': created = create_activity(preview, data, display_number=len(preview['activities']) + 1)
        elif kind == 'update_activity': created = update_activity(preview, resolve(item['object_id']), data)
        elif kind == 'create_event':
            created = {'id': technical_id('event'), **data}
            preview.setdefault('external_events', []).append(created)
        elif kind == 'add_membership': created = add_membership(preview, data['package_id'], data['activity_id'], sort_order=data['sort_order'])
        elif kind == 'update_scenario': preview.update(data); created = preview
        else: raise AssertionError(kind)
        if item.get('client_ref'):
            mapping[item['client_ref']] = created['id']
            if kind == 'create_activity': mapping[item['client_ref'] + ':output'] = created['output_state_id']
    rebuild_mirror(preview)
    assert not validate_scenario(copy.deepcopy(preview)), validate_scenario(copy.deepcopy(preview))
    save('preview.json', preview)
    save('preview-refs.json', mapping)
    print(json.dumps({'revision': before['revision'], 'operations': len(operations), 'activities': len(preview['activities']), 'output': str(OUT)}, ensure_ascii=False))

def payload_for(s, case):
    from app.services.planner_execution_bounds import automatic_execution_bound
    p = copy.deepcopy(s)
    p['calendar_context'] = ANCHOR
    if case == 'repair':
        old = json.loads((ROOT / 'output/test-a-repair-page-diagnosis/page-input.json').read_text('utf-8'))
        for k in ('initial_state_ids', 'goal_state_ids', 'forbidden_state_ids', 'activity_package_scope_ids', 'calendar_context'):
            p[k] = copy.deepcopy(old[k])
    if case == 'deferred':
        event = next(e for e in p['external_events'] if e['name'].startswith('联调扩展件到位'))
        for a in p['activities']:
            if a['name'] in ('模块A功能调测', '模块B调测'):
                a.setdefault('event_reqs', []).append(event['id'])
    p['max_steps'] = automatic_execution_bound(p)['value']
    return p

def verify_semantics(s):
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.services.planner_scenarios import expand_packages
    from app.core.joint_cpsat import prepare_payload, replay_candidate, _occurrence_limits
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.simulator import PathSimulator
    from planner_experiment.models import Action, to_primitive
    from planner_experiment.working_time import next_activity_start, work_end
    p = expand_packages(payload_for(s, 'late'))
    scene = scenario_from_dict(prepare_payload(p))
    acts = {a.name: a for a in scene.activities}
    assert len(s['activities']) == 18 and len(scene.activities) == 13 and len(s['activity_packages']) == 8
    caps, proofs = _occurrence_limits(scene)
    assert caps[acts['安全验收'].id] >= 2 and caps[acts['上电'].id] >= 2
    order = ['集成检测完成', '模块B安装', '模块D安装', '模块A安装', '模块C安装', '安全验收', '上电',
             '模块A功能调测', '模块B调测', *NEW[:3], '安全验收', '上电', NEW[3]]
    cursor, counts, rows = 0, {}, []
    for name in order:
        a = acts[name]
        counts[a.id] = counts.get(a.id, 0) + 1
        start = next_activity_start(scene.working_intervals, max(cursor, 1440 if name == NEW[0] else 0), a)
        end = work_end(scene.working_intervals, start, a.duration)
        rows.append({'activity_id': a.id, 'ordinal': counts[a.id], 'start': start, 'end': end})
        cursor = end
    candidate, _ = replay_candidate(p, scene, rows, run_id='local:late:reference', seed=11)
    assert candidate.validator_status == 'VALID' and len(candidate.executions) == 15
    sim = PathSimulator(scene); state = sim.initial_state(); checks = []
    def enabled(name): return any(a.kind == 'START' and a.activity_id == acts[name].id for a in sim.enabled_actions(state))
    output_ids = {a['name']: a['output_state_id'] for a in s['activities']}
    def fact(name): return output_ids[name] in state.active_state_ids
    assert not enabled(NEW[0]) and not enabled(NEW[2])
    for action in candidate.actions:
        if state.time < 1440: assert not enabled(NEW[0]) and not enabled(NEW[2])
        if fact('上电'): assert not enabled(NEW[2])
        state = sim.transition(state, action)
        if fact(NEW[1]) and fact('下电'):
            assert fact('模块A功能调测') and fact('模块B调测')
            checks.append('power_down_preserves_tests')
        if fact(NEW[2]) and not fact('安全验收'):
            assert not enabled(NEW[3]) and fact('模块A功能调测') and fact('模块B调测')
            checks.append('installation_invalidates_safety_not_tests')
    assert sim.is_goal(state)
    assert set(checks) == {'power_down_preserves_tests', 'installation_invalidates_safety_not_tests'}
    save('reference-replay.json', to_primitive(candidate))
    save('pruning.json', proofs)
    # Changed repair semantics: power-down keeps B's initial result; disassembly invalidates A's.
    rp = expand_packages(payload_for(s, 'repair'))
    rs = scenario_from_dict(prepare_payload(rp)); ra = {a.name: a for a in rs.activities}
    rsim = PathSimulator(rs); rstate = rsim.initial_state()
    rstate = rsim.transition(rstate, Action('START', activity_id=ra['下电'].id))
    rstate = rsim.transition(rstate, next(a for a in rsim.enabled_actions(rstate) if a.kind == 'ADVANCE'))
    assert ra['模块B调测'].output_state_id in rstate.active_state_ids
    old_reference = json.loads((ROOT / 'output/incumbent-feedback-20261105/after-600s-best.json').read_text('utf-8'))
    repaired, _ = replay_candidate(rp, rs, [{'activity_id': e['activity_id'], 'ordinal': e['ordinal'], 'start': e['start_time'], 'end': e['end_time']} for e in old_reference['executions']], run_id='local:late:repair-reference', seed=11)
    assert repaired.validator_status == 'VALID'
    for n in ('模块C拆卸', '模块A拆卸', '模块A安装', '模块C安装'):
        assert ra['模块A功能调测'].output_state_id in ra[n].delete_effect_state_ids
    save('semantics.json', {'passed': True, 'checks': sorted(set(checks)), 'arrival_enforced': True, 'powered_install_rejected': True,
        'reference_makespan': candidate.metrics.makespan, 'reference_executions': len(candidate.executions),
        'repair_reference_valid': True, 'repair_down_preserves_B': True, 'repair_disassembly_invalidates_A': True})
    return candidate

def solve(case):
    from app.services.planner_engine_bridge import _planner_modules, run_engine
    _planner_modules()
    from app.services.planner_scenarios import expand_packages
    from app.core.joint_cpsat import prepare_payload, replay_candidate
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.models import to_primitive
    s = load('preview.json')
    verify_semantics(s)
    p = payload_for(s, case); save(case + '-input.json', p)
    started = time.perf_counter()
    with (OUT / (case + '-progress.jsonl')).open('w', encoding='utf-8') as log:
        def progress(metrics, candidate):
            sample = dict(metrics, observed_seconds=time.perf_counter()-started, improved=candidate is not None)
            log.write(json.dumps(sample, ensure_ascii=False) + '\n'); log.flush()
            if candidate is not None: print(json.dumps(sample, ensure_ascii=False), flush=True)
        result = run_engine(p, engine='JOINT_CP_SAT', run_id='local:late-material:' + case, seed=11,
                            budget_override={'time_limit_seconds': 600}, progress_observer=progress)
    save(case + '-result.json', result)
    summary = {k: result.get(k) for k in ('status', 'elapsed_seconds', 'first_solution_seconds', 'lower_bound', 'proven_optimal')}
    summary.update({k: result['stats'].get(k) for k in ('branches', 'conflicts', 'best_makespan', 'best_execution_count', 'model')})
    if result['paths']:
        domain = expand_packages(p)
        path = result['paths'][0]
        checked, _ = replay_candidate(domain, scenario_from_dict(prepare_payload(domain)), [
            {'activity_id': e['activity_id'], 'ordinal': e['ordinal'], 'start': e['start_time'], 'end': e['end_time']}
            for e in path['executions']], run_id='local:late-material:' + case + ':replay', seed=11)
        assert checked.validator_status == 'VALID'
        save(case + '-replay.json', to_primitive(checked))
        names = {a['id']: a['name'] for a in s['activities']}
        summary['validator'] = checked.validator_status
        summary['schedule'] = [{'name': names[e.activity_id], 'ordinal': e.ordinal, 'start': e.start_time, 'end': e.end_time} for e in checked.executions]
        if case == 'late':
            assert all(e['end'] < 1440 for e in summary['schedule'] if e['name'] in ('模块A功能调测', '模块B调测'))
            assert sum(e['name'] == '上电' for e in summary['schedule']) >= 2
            assert sum(e['name'] == '安全验收' for e in summary['schedule']) >= 2
    save(case + '-summary.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k != 'model'}, ensure_ascii=False), flush=True)

def apply():
    before = load('before.json')
    assert load('semantics.json')['passed']
    early, deferred, repair = [load(case + '-summary.json') for case in ('late', 'deferred', 'repair')]
    assert all(x.get('validator') == 'VALID' for x in (early, deferred, repair))
    assert early['best_makespan'] < deferred['best_makespan']
    latest = api('planner-scenarios/' + SID)
    assert latest == before, 'Live scenario changed; rebase rather than overwrite'
    result = api('planner-scenarios/' + SID + '/draft-commit', load('draft-commit.json'))
    save('commit-response.json', result)
    after = api('planner-scenarios/' + SID); save('after.json', after)
    assert after['revision'] == before['revision'] + 1
    verify_semantics(after['scenario'])
    for a in before['scenario']['activities']:
        current = next(x for x in after['scenario']['activities'] if x['id'] == a['id'])
        if a['name'] != '下电': assert current == a, a['name']
    assert after['scenario']['resources'] == before['scenario']['resources']
    for k in ('work_calendars', 'work_calendar_id', 'exclusive_rules', 'night_lift_rule', 'default_budget'):
        assert after['scenario'].get(k) == before['scenario'].get(k), k
    history = api('planner-runs?scenario_id=' + SID)
    assert history == load('history-before.json')
    assert {r['id']: api('planner-runs/' + r['id']) for r in history} == load('history-details-before.json')
    save('validation.json', {'revision': after['revision'], 'activities': len(after['scenario']['activities']),
        'packages': len(after['scenario']['activity_packages']), 'memberships': len(after['scenario']['activity_package_memberships']),
        'history_unchanged': True, 'early_makespan': early['best_makespan'], 'deferred_makespan': deferred['best_makespan'],
        'saved_minutes': deferred['best_makespan']-early['best_makespan']})
    print(json.dumps(load('validation.json'), ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'late', 'deferred', 'repair', 'apply'])
    action = parser.parse_args().action
    if action == 'prepare': prepare()
    elif action == 'apply': apply()
    else: solve(action)

"""Create and verify the 20-activity assembly/commissioning example via the API."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_scenarios import new_scenario, technical_id, create_activity, create_package, add_membership, validate_scenario

OUT = ROOT / 'output/fixtures/assembly-commissioning-20'
BASE = 'http://127.0.0.1:8016/api/v1'
NAME = '20活动机械组装→功能调测｜集成验收到功能联调'

# One initial fact. Early branches have fewer inputs; later integration gates
# combine more completed activities. The total remains 60 dependencies / 20.
SINGLE_INITIAL_DEPENDENCIES = {
    1: ['start'], 2: [1], 3: [1], 4: [1], 5: [2, 1], 6: [3, 1], 7: [1],
    8: [4, 5, 6], 9: [5, 6, 2, 3], 10: [7, 5, 6], 11: [8, 9, 10, 4],
    12: [11, 8, 9], 13: [11, 4, 8], 14: [11, 8, 9, 10],
    15: [9, 12, 14, 13], 16: [10, 12, 14, 13], 17: [13, 14, 12, 8],
    18: [15, 16, 17, 11, 14], 19: [18, 11, 14, 15, 16], 20: [19, 17, 16, 18, 15],
}


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def api(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def build():
    s = new_scenario(NAME)
    s.update(execution_mode='parallel', max_steps=20,
             default_budget={'time_limit_seconds': 60, 'transition_limit': 20000, 'max_solutions': 20},
             exclusive_rules={'crane': False, 'commissioning': False},
             night_lift_rule={'enabled': False, 'night_start': '20:00', 'night_end': '08:00'})
    s['provenance'].update(fixture='assembly_commissioning_20_v2',
                           description='唯一初始状态为集成验收待开展；60条普通前置依赖，平均每活动3条。人力、行吊和空间均为可重复占用容量资源。')
    seeds = {}
    for key, name in [('start', '集成验收待开展')]:
        sid = technical_id('state')
        s['states'].append({'id': sid, 'name': name, 'state_kind': 'seed', 'managed': True})
        s['initial_state_ids'].append(sid)
        seeds[key] = sid
    resources = {}
    for key, name, kind, capacity in [
        ('mechanical', '机械装配组', 'crew', 4), ('electrical', '电气调测组', 'crew', 3),
        ('crane', '共享行吊', 'crane', 1), ('prep', '部件预装区', 'workspace', 2),
        ('assembly', '机械总装区', 'workspace', 2), ('testing', '功能调测工位', 'workspace', 1),
    ]:
        r = {'id': technical_id('resource'), 'name': name, 'kind': kind, 'capacity': capacity, 'is_active': True}
        s['resources'].append(r)
        resources[key] = r['id']
    root = create_package(s, {'name': '机械组装—功能调测', 'sort_order': 0}, display_number=1)
    packs = []
    for i, name in enumerate(['01 集成验收', '02 机械组装', '03 功能调测', '04 功能联调']):
        packs.append(create_package(s, {'name': name, 'parent_id': root['id'], 'sort_order': i}, display_number=i+2)['id'])
    # Integer prerequisites refer to earlier activity outputs; names refer to initial facts.
    rows = [
        ('集成验收', 30, [], {'mechanical':1,'electrical':1,'prep':1}, 0),
        ('基座与机架预装', 45, [], {'mechanical':2,'prep':1}, 1),
        ('驱动传动单元预装', 40, [], {'mechanical':3,'prep':1}, 1),
        ('电控柜与线束预装', 35, [], {'electrical':2,'prep':1}, 1),
        ('机架吊装就位', 20, [], {'mechanical':2,'crane':1,'assembly':1}, 1),
        ('传动单元吊装就位', 25, [], {'mechanical':2,'crane':1,'assembly':1}, 1),
        ('管路与阀组预装', 35, [], {'mechanical':2,'prep':1}, 1),
        ('电控柜安装接线', 45, [], {'electrical':2,'assembly':1}, 1),
        ('传动机构紧固找正', 40, [], {'mechanical':3,'assembly':1}, 1),
        ('管路安装与密封检查', 40, [], {'mechanical':2,'assembly':1}, 1),
        ('机械装配验收', 25, [], {'mechanical':2,'assembly':2}, 1),
        ('传感器安装与标定', 30, [], {'electrical':2,'assembly':1}, 2),
        ('控制程序下载与参数配置', 25, [], {'electrical':1,'testing':1}, 2),
        ('电源与安全回路测试', 30, [], {'electrical':2,'assembly':1}, 2),
        ('执行机构单机调试', 35, [], {'mechanical':1,'electrical':2,'testing':1}, 2),
        ('液压与气动功能调试', 35, [], {'mechanical':2,'electrical':1,'testing':1}, 2),
        ('控制逻辑与联锁验证', 30, [], {'electrical':2,'testing':1}, 2),
        ('机械电气接口联调', 40, [], {'mechanical':2,'electrical':2,'assembly':1,'testing':1}, 3),
        ('负载运行与节拍调测', 45, [], {'mechanical':2,'electrical':1,'testing':1}, 3),
        ('整机功能联调与验收', 30, [], {'mechanical':1,'electrical':2,'testing':1}, 3),
    ]
    rows = [(name, duration, SINGLE_INITIAL_DEPENDENCIES[i], demand, phase)
            for i, (name, duration, _, demand, phase) in enumerate(rows, 1)]
    assert sum(len(row[2]) for row in rows) == 60
    activities = {}
    for i, (name, duration, deps, demand, phase) in enumerate(rows, 1):
        required = [activities[d]['output_state_id'] if isinstance(d, int) else seeds[d] for d in deps]
        assert required and len(required) == len(set(required))
        payload = {'name': name, 'duration': duration, 'max_instances': 1,
                   'preconditions': [{'state_id': sid, 'relation_role': 'required'} for sid in required],
                   'resource_reqs': {resources[key]: qty for key, qty in demand.items()},
                   'metadata': {'activity_type': '功能调测' if phase >= 2 else '机械集成',
                                'description': '20活动教学实例；所有前置须同时满足，平均每活动3项。唯一初始事实为集成验收待开展，后续依靠活动完成状态推进。资源完成后释放。',
                                'risk_jobs': ['吊装作业'] if demand.get('crane') else [], 'precision_fragile': False}}
        if i == 20:
            payload['output_state_name'] = '功能联调完成'
        activities[i] = create_activity(s, payload, display_number=i)
        add_membership(s, packs[phase], activities[i]['id'], sort_order=i)
    s['goal_state_ids'] = [activities[20]['output_state_id']]
    assert not validate_scenario(s)
    needed = set()
    def visit(number):
        if number in needed: return
        needed.add(number)
        for dep in rows[number-1][2]:
            if isinstance(dep, int): visit(dep)
    visit(20)
    assert len(needed) == 20
    save('scenario.json', s)
    save('activity-guide.json', [{'number': i, 'name': row[0], 'minutes': row[1], 'dependencies': row[2], 'resources': row[3]}
                                 for i, row in enumerate(rows, 1)])
    return s


def main():
    # Preserve evidence and prevent duplicate imports on retry.
    if (OUT/'imported.json').exists():
        imported = json.loads((OUT/'imported.json').read_text(encoding='utf-8'))
        assert api('/planner-scenarios/'+imported['id'])['revision'] == imported['revision']
    else:
        imported = api('/planner-scenarios/import', {'scenario': build(), 'preserve_ids': False})
        save('imported.json', imported)
    s = imported['scenario']
    assert len(s['activities']) == 20
    assert sum(len(a['preconditions']) for a in s['activities']) == 60
    if (OUT/'submitted.json').exists():
        run = json.loads((OUT/'submitted.json').read_text(encoding='utf-8'))
    else:
        payload = {'scenario_id': imported['id'], 'expected_revision': imported['revision'],
                   'current_state_ids': s['initial_state_ids'], 'target_state_ids': s['goal_state_ids'],
                   'engine': 'JOINT_CP_SAT', 'budget_mode': 'auto', 'execution_bound_mode': 'auto',
                   'seed': 11, 'client_request_id': str(uuid.uuid4()),
                   'display_start_at': datetime.now().date().isoformat()+'T08:00:00+08:00', 'display_timezone': 'Asia/Shanghai'}
        save('request.json', payload)
        run = api('/planner-runs/async', payload)
        save('submitted.json', run)
    print(json.dumps({'project_id': imported['id'], 'run_id': run['id'], 'activities': 20, 'preconditions': 60}), flush=True)
    deadline = time.monotonic()+150
    while time.monotonic() < deadline:
        run = api('/planner-runs/'+run['id'])
        if run['job_status'] in ('FINISHED','FAILED'): break
        time.sleep(2)
    save('result.json', run)
    result = run['result']['results']['JOINT_CP_SAT']
    assert result['status'] in ('OPTIMAL','FEASIBLE','TIMEOUT_PARTIAL'), result
    candidate = result['paths'][0]
    assert candidate['validator_status'] == 'VALID'
    executions = candidate['executions']
    assert len(executions) == len({e['activity_id'] for e in executions}) == 20
    by_id = {a['id']: a for a in s['activities']}
    ends = {by_id[e['activity_id']]['output_state_id']: e['end_time'] for e in executions}
    for e in executions:
        a = by_id[e['activity_id']]
        assert e['end_time']-e['start_time'] == a['duration']
        assert all(p['state_id'] in s['initial_state_ids'] or ends[p['state_id']] <= e['start_time'] for p in a['preconditions'])
    capacity_checks = []
    for resource in s['resources']:
        events = defaultdict(int)
        for e in executions:
            q = by_id[e['activity_id']]['resource_reqs'].get(resource['id'], 0)
            events[e['start_time']] += q
            events[e['end_time']] -= q
        used = peak = 0
        for t in sorted(events):
            used += events[t]
            assert 0 <= used <= resource['capacity']
            peak = max(peak, used)
        capacity_checks.append({'name': resource['name'], 'capacity': resource['capacity'], 'peak': peak})
    parallel = [(a['activity_name'], b['activity_name']) for i, a in enumerate(executions) for b in executions[i+1:]
                if max(a['start_time'], b['start_time']) < min(a['end_time'], b['end_time'])]
    assert parallel, 'The example must contain actual parallel work'
    audit = {'name': s['name'], 'scenario_id': imported['id'], 'run_id': run['id'], 'activities': 20,
             'required_preconditions': 60, 'mean_preconditions': 3, 'initial_states': len(s['initial_state_ids']),
             'status': result['status'], 'validator': candidate['validator_status'],
             'makespan': candidate['metrics']['makespan'], 'elapsed_seconds': result['elapsed_seconds'],
             'serial_duration_sum': sum(a['duration'] for a in s['activities']),
             'parallel_pairs': parallel, 'capacity_checks': capacity_checks, 'dependencies_check': 'PASS'}
    save('audit.json', audit)
    print(json.dumps(audit, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()

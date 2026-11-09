"""Submit and inspect an isolated copy of the existing 150-activity fixture."""
import argparse
import json
import sys
import urllib.request
import uuid
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/fixtures/night-calendar-150'
BASE = 'http://127.0.0.1:8016/api/v1'


def api(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def submit(exclusive=False):
    if (OUT / 'submitted.json').exists():
        raise RuntimeError('Existing run retained; use status instead of creating a duplicate')
    s = json.loads((ROOT / 'output/fixtures/calendar-150/scenario.json').read_text(encoding='utf-8-sig'))
    s['name'] = '150活动夜班填补验收｜工作日历＋精密吊装禁夜'
    s['night_lift_rule'] = {'enabled': True, 'night_start': '20:00', 'night_end': '08:00'}
    if exclusive:
        s['name'] = '150活动独占验收｜行吊＋调测＋日历＋禁夜'
        s['exclusive_rules'] = {'crane': True, 'commissioning': True}
    calendar = next(c for c in s['work_calendars'] if c['id'] == s['work_calendar_id'])
    calendar.update(name='验收两班日历（08–12 / 13–24）', weekdays=[0, 1, 2, 3, 4],
                    periods=[{'start': '08:00', 'end': '12:00'}, {'start': '13:00', 'end': '24:00'}], exceptions=[])
    imported = api('/planner-scenarios/import', {'scenario': s, 'preserve_ids': False})
    save('imported.json', imported)
    scenario = imported['scenario']
    request = {'scenario_id': imported['id'], 'expected_revision': imported['revision'],
               'current_state_ids': scenario['initial_state_ids'], 'target_state_ids': scenario['goal_state_ids'],
               'engine': 'JOINT_CP_SAT', 'execution_bound_mode': 'auto', 'budget_mode': 'auto',
               'seed': 11, 'client_request_id': str(uuid.uuid4()),
               'display_start_at': '2026-11-04T19:00:00+08:00', 'display_timezone': 'Asia/Shanghai'}
    save('request.json', request)
    run = api('/planner-runs/async', request)
    save('submitted.json', run)
    print(json.dumps({'scenario_id': imported['id'], 'run_id': run['id'],
                      'activities': len(scenario['activities']), 'budget': run['request'].get('effective_budget')}, ensure_ascii=False))


def status():
    submitted = json.loads((OUT / 'submitted.json').read_text(encoding='utf-8'))
    run = api('/planner-runs/' + submitted['id'])
    save('result.json', run)
    result = (run.get('result') or {}).get('results', {}).get('JOINT_CP_SAT', {})
    print(json.dumps({k: run.get(k) for k in ('id', 'status', 'job_status', 'phase', 'error_message')}, ensure_ascii=False))
    if result:
        print(json.dumps({k: result.get(k) for k in ('status', 'elapsed_seconds', 'lower_bound', 'proven_optimal', 'diagnosis')}, ensure_ascii=False))
        for path in result.get('paths', [])[:1]:
            print(json.dumps({'metrics': path['metrics'], 'validator': path['validator_status'], 'executions': len(path['executions'])}))


def audit():
    sys.path.insert(0, str(ROOT))
    from app.services.planner_engine_bridge import _planner_modules
    _planner_modules()
    from app.core.joint_cpsat import prepare_payload
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.simulator import PathSimulator
    from planner_experiment.models import Action
    from planner_experiment.working_time import work_segments

    run = json.loads((OUT / 'result.json').read_text(encoding='utf-8'))
    result = run['result']['results']['JOINT_CP_SAT']
    path = result['paths'][0]
    snapshot = run['request']['effective_scenario_snapshot']
    resource_names = {r['id']: r.get('name', r['id']) for r in snapshot['resources']}
    scenario = scenario_from_dict(prepare_payload(snapshot))
    sim = PathSimulator(scenario)
    # Counterfactual eligibility at an identical replay state: remove only the
    # daylight restriction, retaining dependencies, resources, limits and locks.
    unrestricted = replace(scenario, activities=tuple(replace(a, allowed_execution_windows=None) for a in scenario.activities))
    ordinary_sim = PathSimulator(unrestricted)
    restricted = {a.id for a in scenario.activities if a.allowed_execution_windows is not None}
    origin = datetime.fromisoformat(run['request']['display_start_at'])
    def at(minute):
        return (origin + timedelta(minutes=minute-scenario.start_time)).isoformat()
    def names(ids):
        return [scenario.activity_by_id[aid].name for aid in sorted(ids)]
    state = sim.initial_state()
    evidence = []
    idle = []
    for raw in path['actions']:
        action = Action(**raw)
        # Canonical same-time ID ordering is a search symmetry breaker, not a
        # business restriction. Ignore it only for eligibility diagnostics.
        probe = replace(state, last_started_id=None)
        normal_enabled = {a.activity_id for a in ordinary_sim.enabled_actions(probe) if a.kind == 'START'}
        enabled = {a.activity_id for a in sim.enabled_actions(probe) if a.kind == 'START'}
        blocked = (normal_enabled-enabled) & restricted
        if blocked and action.kind == 'START' and action.activity_id not in restricted:
            evidence.append({'time': state.time, 'at': at(state.time), 'waiting_ids': sorted(blocked),
                             'waiting_names': names(blocked), 'scheduled_id': action.activity_id,
                             'scheduled_name': scenario.activity_by_id[action.activity_id].name})
        if action.kind == 'ADVANCE' and not state.running and blocked:
            idle.append({'start': at(state.time), 'end': at(action.target_time),
                         'waiting_names': names(blocked), 'ordinary_eligible_names': names(enabled)})
        state = sim.transition(state, action)
    assert sim.is_goal(state)
    executions = path['executions']
    assert len(executions) == len({e['activity_id'] for e in executions}) == 150
    exclusive_ids = {a.id for a in scenario.activities if a.exclusive_execution}
    for a in executions:
        if a['activity_id'] in exclusive_ids:
            for b in executions:
                if a is not b:
                    assert a['end_time'] <= b['start_time'] or b['end_time'] <= a['start_time']
    capacity_checks = []
    for resource in scenario.resources:
        delta = defaultdict(int)
        for e in executions:
            demand = dict(scenario.activity_by_id[e['activity_id']].resource_reqs).get(resource.id, 0)
            delta[e['start_time']] += demand
            delta[e['end_time']] -= demand
        used = peak = 0
        for instant in sorted(delta):
            used += delta[instant]
            assert 0 <= used <= resource.capacity
            peak = max(used, peak)
        capacity_checks.append({'name': resource_names[resource.id], 'capacity': resource.capacity, 'peak': peak})
    table = []
    for e in executions:
        a = scenario.activity_by_id[e['activity_id']]
        segments = work_segments(scenario.working_intervals, e['start_time'], e['end_time'])
        assert sum(right-left for left,right in segments) == a.duration
        if a.id in restricted:
            assert any(left <= e['start_time'] and e['end_time'] <= right for left,right in a.allowed_execution_windows)
        table.append({'id': a.id, 'name': a.name, 'start': at(e['start_time']), 'end': at(e['end_time']),
                      'work_minutes': a.duration, 'fragile_lift': a.id in restricted,
                      'resources': {resource_names[rid]: qty for rid,qty in a.resource_reqs}})
    save('schedule.json', table)
    report = {'scenario_id': run['scenario_id'], 'run_id': run['id'], 'status': result['status'],
              'validator': path['validator_status'], 'solve_seconds': result['elapsed_seconds'],
              'executions': len(executions), 'fragile_lifts': len(restricted),
              'exclusive_activities': len(exclusive_ids), 'exclusive_interval_sweep': 'PASS',
              'makespan_minutes': path['metrics']['makespan'], 'lower_bound': result['lower_bound'],
              'start': at(scenario.start_time), 'finish': at(scenario.start_time+path['metrics']['makespan']),
              'capacity_checks': capacity_checks, 'independent_replay': 'PASS',
              'work_durations_and_daylight_windows': 'PASS',
              'ordinary_starts_while_fragile_lift_ready_except_for_daylight': evidence,
              'idle_intervals_with_daylight_blocked_lifts': idle}
    save('audit.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['submit', 'status', 'audit'])
    parser.add_argument('--exclusive', action='store_true', help='Use a separate copy with both global exclusivity rules enabled')
    args = parser.parse_args()
    if args.exclusive:
        OUT = ROOT / 'output/fixtures/exclusive-calendar-150'
    if args.action == 'submit':
        submit(exclusive=args.exclusive)
    else:
        {'status': status, 'audit': audit}[args.action]()

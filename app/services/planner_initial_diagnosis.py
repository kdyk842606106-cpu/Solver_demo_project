"""Read-only structural diagnosis; suggestions never become assumed facts."""
from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from app.services.planner_preflight import explain_unreachable_goals, reachable_states
from app.services.planner_scenarios import expand_packages, scenario_hash, validate_scenario


def diagnose_initial_states(source: dict[str, Any], current: list[str], targets: list[str]) -> dict[str, Any]:
    scenario = copy.deepcopy(source)
    scenario['initial_state_ids'] = list(dict.fromkeys(current))
    scenario['goal_state_ids'] = list(dict.fromkeys(targets))
    states = {s['id']: s for s in scenario.get('states', [])}
    activities = scenario.get('activities', [])
    initial, goals = set(current), set(targets)
    issues = validate_scenario(copy.deepcopy(scenario))
    structural_codes = {'GOAL_STRUCTURALLY_UNREACHABLE', 'GOAL_WITHOUT_PROVIDER'}
    errors = [i for i in issues if i['code'] not in structural_codes]
    if not goals:
        errors.append({'code': 'TARGET_STATE_REQUIRED', 'message': '请先选择目标状态。'})
    result = dict(input_signature=scenario_hash(scenario), status='INVALID_INPUT' if errors else 'STRUCTURALLY_REACHABLE',
                  groups=[], blocked_goals=[], input_issues=errors, already_satisfied_goal_ids=sorted(goals & initial),
                  analysis_complete=True, constraints_checked=False,
                  scope_package_ids=scenario.get('activity_package_scope_ids', []), activity_count=0)
    if errors:
        return result
    expanded = expand_packages(scenario)
    active = expanded['activities']
    result['activity_count'] = len(active)
    event_facts = {s for e in scenario.get('external_events', []) for s in e.get('add_state_ids', [])}
    reachable = reachable_states(active, initial | event_facts)
    missing_goals = goals - reachable
    if not missing_goals:
        return result
    result['status'] = 'STRUCTURALLY_BLOCKED'
    explanations = explain_unreachable_goals(scenario, active, reachable, missing_goals)
    packages = {p['id']: p for p in scenario.get('activity_packages', [])}
    paths = defaultdict(list)
    for member in scenario.get('activity_package_memberships', []):
        parts, seen, pid = [], set(), member['package_id']
        while pid in packages and pid not in seen:
            seen.add(pid)
            parts.append(packages[pid]['name'])
            pid = packages[pid].get('parent_id')
        paths[member['activity_id']].append(' / '.join(reversed(parts)))

    def activity_info(a):
        return dict(id=a['id'], name=a.get('name', a['id']), display_code=a.get('display_code'),
                    package_paths=paths[a['id']], is_active=a.get('is_active', True),
                    in_scope=a['id'] in active_ids)

    active_ids = {a['id'] for a in active}
    groups = {}
    for goal, explanation in explanations.items():
        result['blocked_goals'].append(dict(id=goal, name=states[goal].get('name', goal),
                                           blocked_activities=explanation['blocked_activities']))
        for group in explanation['confirmation_groups']:
            ids = sorted(s['id'] for s in group['states'])
            key = (group['reason'], tuple(ids))
            if key not in groups:
                candidates = []
                for sid in ids:
                    producers = [a for a in activities if sid in [a.get('output_state_id'), *a.get('additional_output_state_ids', [])]]
                    consumers = [a for a in activities if any(p.get('state_id') == sid for p in a.get('preconditions', []))]
                    # Final-forbidden facts may be true initially and require cleanup.
                    # Targets require explicit selection in the normal picker, not a repair shortcut.
                    confirmable = sid in states and sid not in initial and sid not in goals and group['reason'] != 'provider_unavailable'
                    candidates.append(dict(id=sid, name=states[sid].get('name', sid), confirmable=confirmable,
                        is_goal=sid in goals, forbidden_at_finish=sid in scenario.get('forbidden_state_ids', []),
                        producer_activities=[activity_info(a) for a in producers],
                        consumer_activities=[activity_info(a) for a in consumers]))
                groups[key] = dict(reason=group['reason'], message=group['message'], states=candidates, affected_goals=[])
            groups[key]['affected_goals'].append(dict(id=goal, name=states[goal].get('name', goal)))
    result['groups'] = list(groups.values())
    return result

"""Explicit business rules derived from structured activity data."""


def validate_exclusive_rules(scenario):
    rules = scenario.get('exclusive_rules')
    if rules is not None and (
        not isinstance(rules, dict)
        or set(rules) != {'crane', 'commissioning'}
        or any(type(value) is not bool for value in rules.values())
    ):
        raise ValueError('独占规则需要 crane/commissioning 两个布尔开关')


def exclusivity_enabled(scenario):
    validate_exclusive_rules(scenario)
    return any((scenario.get('exclusive_rules') or {}).values())


def exclusive_activity_ids(scenario):
    validate_exclusive_rules(scenario)
    rules = scenario.get('exclusive_rules') or {}
    cranes = {r['id'] for r in scenario.get('resources', []) if r.get('kind') == 'crane'}
    return {
        a['id'] for a in scenario.get('activities', []) if a.get('is_active', True) and (
            (rules.get('crane') and any(rid in cranes and qty > 0 for rid, qty in a.get('resource_reqs', {}).items()))
            or (rules.get('commissioning') and (a.get('metadata') or {}).get('activity_type') == '功能调测')
        )
    }

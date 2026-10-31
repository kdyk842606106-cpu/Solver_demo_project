"""Explain missing structural inputs without inventing initial facts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def reachable_states(activities: list[dict[str, Any]], available: set[str]) -> set[str]:
    """Optimistic closure only; temporal/resource feasibility is left to engines."""
    reachable = set(available)
    changed = True
    while changed:
        changed = False
        for activity in activities:
            required = {item.get("state_id") for item in activity.get("preconditions", [])}
            if required <= reachable:
                outputs = {activity.get("output_state_id"), *activity.get("additional_output_state_ids", [])} - {None}
                if not outputs <= reachable:
                    reachable.update(outputs)
                    changed = True
    return reachable


def explain_unreachable_goals(
    scenario: dict[str, Any], activities: list[dict[str, Any]], reachable: set[str], goals: set[str]
) -> dict[str, dict[str, Any]]:
    """Trace unmet dependencies, grouping cycles instead of recursing forever.

    Groups describe possible sources of missing facts, not mandatory additions or
    sufficient repair sets: producer alternatives are OR, their inputs are AND.
    Only the user can confirm that a suggested initial fact is actually true.
    """
    states = {item["id"]: item for item in scenario.get("states", [])}
    forbidden = set(scenario.get("forbidden_state_ids", []))
    providers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_providers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for items, destination in ((activities, providers), (scenario.get("activities", []), all_providers)):
        for activity in items:
            for state_id in [activity.get("output_state_id"), *activity.get("additional_output_state_ids", [])]:
                if state_id:
                    destination[state_id].append(activity)

    def describe(state_id: str) -> dict[str, str]:
        return {"id": state_id, "name": states.get(state_id, {}).get("name") or state_id}

    graph: dict[str, set[str]] = {}
    pending = list(sorted(goals))
    while pending:
        state_id = pending.pop()
        if state_id in reachable or state_id in graph:
            continue
        dependencies = {
            relation["state_id"]
            for activity in providers[state_id]
            for relation in activity.get("preconditions", [])
            if relation.get("state_id") and relation["state_id"] not in reachable
        }
        graph[state_id] = dependencies
        pending.extend(sorted(dependencies))

    groups = []
    for component in _components(graph):
        cyclic = len(component) > 1 or any(node in graph[node] for node in component)
        if cyclic:
            reason = "dependency_cycle"
            message = "循环依赖缺少已知起点，请确认其中实际已成立的状态；若均未成立，请检查循环入口配置。"
        elif not providers[component[0]]:
            reason = "provider_unavailable" if all_providers[component[0]] else "missing_initial_fact"
            message = (
                "产生该状态的活动未启用或不在本次求解范围内，请检查活动配置。"
                if reason == "provider_unavailable"
                else "该状态没有活动或事件可提供，请确认它当前是否已经成立，或补充产生它的规则。"
            )
        else:
            continue
        groups.append({
            "reason": reason,
            "message": message,
            "states": [describe(node) for node in component],
            "confirmable_state_ids": [
                node for node in component
                if node in states and node not in forbidden and reason != "provider_unavailable"
            ],
            "provider_activities": [
                {"id": activity["id"], "name": activity.get("name") or activity["id"]}
                for node in component for activity in all_providers[node]
            ] if reason == "provider_unavailable" else [],
        })

    details = {}
    for goal in sorted(goals):
        ancestors: set[str] = set()
        pending = [goal]
        while pending:
            node = pending.pop()
            if node in ancestors:
                continue
            ancestors.add(node)
            pending.extend(graph.get(node, set()))
        details[goal] = {
            "state_name": describe(goal)["name"],
            "blocked_activities": [
                {
                    "id": activity["id"],
                    "name": activity.get("name") or activity["id"],
                    "missing_preconditions": [
                        describe(relation["state_id"])
                        for relation in activity.get("preconditions", [])
                        if relation.get("state_id") and relation["state_id"] not in reachable
                    ],
                }
                for activity in providers[goal]
            ],
            "confirmation_groups": [
                group for group in groups if any(state["id"] in ancestors for state in group["states"])
            ],
        }
    return details


def _components(graph: dict[str, set[str]]) -> list[list[str]]:
    """Iterative Kosaraju: long dependency chains must not hit recursion limits."""
    visited: set[str] = set()
    order = []
    reverse: dict[str, set[str]] = defaultdict(set)
    for node, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(node)
    for root in sorted(graph):
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, iter(sorted(graph[root])))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(graph[child]))))
    visited.clear()
    components = []
    for root in reversed(order):
        if root in visited:
            continue
        component = []
        pending = [root]
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            pending.extend(sorted(reverse[node]))
        components.append(sorted(component))
    return sorted(components)

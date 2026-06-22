"""Layered activity/state reachability and health-check service."""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StateNode
from app.db.schemas import LayeredExpansionRequest
from app.services.layered_expansion import expand_layered_context

FactKey = tuple[str, str]

EXACT_EFFECT_TYPES = {"set", "reset"}
EXACT_OPERATORS = {"eq", "completed"}
BLOCKING_CODES = {"NO_PROVIDER", "BROKEN_CHAIN", "SELF_DEPENDENCY", "CONFLICTING_GOAL"}


def _to_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _fact_key(feature_key: Any, value: Any) -> FactKey | None:
    text_value = _to_value(value)
    if not feature_key or text_value is None:
        return None
    return (str(feature_key), text_value)


def _goal_fact_key(goal: dict[str, Any]) -> FactKey | None:
    if goal.get("operator") not in EXACT_OPERATORS:
        return None
    return _fact_key(goal.get("feature_key"), goal.get("target_value"))


def _effect_fact_key(effect: dict[str, Any]) -> FactKey | None:
    if effect.get("effect_type", "set") not in EXACT_EFFECT_TYPES:
        return None
    return _fact_key(effect.get("feature_key"), effect.get("new_value"))


def _state_children_by_parent(state_nodes: list[StateNode]) -> dict[int | None, list[StateNode]]:
    children: dict[int | None, list[StateNode]] = defaultdict(list)
    for node in state_nodes:
        children[node.parent_id].append(node)
    return children


def _state_leaf_fact_keys(
    state_node_id: int,
    state_by_id: dict[int, StateNode],
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[FactKey]:
    node = state_by_id.get(state_node_id)
    if node is None:
        return []

    leaves: list[StateNode] = []
    active_children = [
        child for child in children_by_parent.get(node.id, [])
        if include_inactive or child.is_active
    ]
    if not active_children:
        leaves = [node]
    else:
        stack = list(active_children)
        while stack:
            current = stack.pop(0)
            if not include_inactive and not current.is_active:
                continue
            current_children = [
                child for child in children_by_parent.get(current.id, [])
                if include_inactive or child.is_active
            ]
            if not current_children:
                leaves.append(current)
            else:
                stack.extend(current_children)

    keys: list[FactKey] = []
    for leaf in leaves:
        if not include_inactive and not leaf.is_active:
            continue
        if leaf.operator not in EXACT_OPERATORS:
            continue
        key = _fact_key(leaf.feature_key, leaf.target_value)
        if key is not None:
            keys.append(key)
    return keys


def _precondition_fact_keys(
    precondition: dict[str, Any],
    state_by_id: dict[int, StateNode],
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[FactKey]:
    operator = precondition.get("operator")
    feature_key = precondition.get("feature_key")

    if feature_key and operator == "in":
        return [
            key
            for key in (_fact_key(feature_key, value) for value in precondition.get("value_list") or [])
            if key is not None
        ]

    if feature_key and operator in EXACT_OPERATORS:
        key = _fact_key(feature_key, precondition.get("feature_value"))
        return [key] if key is not None else []

    state_node_id = precondition.get("state_node_id")
    if operator == "completed" and state_node_id:
        return _state_leaf_fact_keys(
            int(state_node_id),
            state_by_id,
            children_by_parent,
            include_inactive=include_inactive,
        )

    return []


def _provider_entry(rule: dict[str, Any], source_activity_node_id: int | None) -> dict[str, Any]:
    return {
        "op_rule_id": rule["op_rule_id"],
        "op_rule_code": rule["op_rule_code"],
        "activity_node_id": rule["activity_node_id"],
        "activity_node_code": rule["activity_node_code"],
        "atomic_activity_id": rule.get("atomic_activity_id"),
        "source_activity_node_id": source_activity_node_id,
    }


def _consumer_entry(rule: dict[str, Any], precondition: dict[str, Any]) -> dict[str, Any]:
    return {
        "op_rule_id": rule["op_rule_id"],
        "op_rule_code": rule["op_rule_code"],
        "activity_node_id": rule["activity_node_id"],
        "activity_node_code": rule["activity_node_code"],
        "atomic_activity_id": rule.get("atomic_activity_id"),
        "source_type": precondition["source_type"],
        "scope_guard_id": precondition.get("scope_guard_id"),
        "scope_guard_name": precondition.get("scope_guard_name"),
        "source_activity_node_id": precondition.get("source_activity_node_id"),
    }


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, Any], ...]] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        key = tuple(sorted(entry.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _activity_path_ids(candidate: dict[str, Any]) -> set[int]:
    return {int(item["id"]) for item in candidate.get("source_path") or []}


def _is_inside_guarded_scope(provider: dict[str, Any], guarded_activity_node_id: int | None, path_ids_by_activity: dict[int, set[int]]) -> bool:
    if guarded_activity_node_id is None:
        return False
    return guarded_activity_node_id in path_ids_by_activity.get(provider["activity_node_id"], set())


def _add_diagnostic(
    diagnostics: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    diagnostic: dict[str, Any],
) -> None:
    key = (
        diagnostic.get("code"),
        diagnostic.get("feature_key"),
        diagnostic.get("target_value"),
        diagnostic.get("op_rule_id"),
        diagnostic.get("activity_node_id"),
        diagnostic.get("state_node_id"),
        diagnostic.get("source_type"),
    )
    if key in seen:
        return
    seen.add(key)
    diagnostics.append(diagnostic)


async def check_layered_health(
    session: AsyncSession,
    machine_type_id: int,
    payload: LayeredExpansionRequest,
) -> dict[str, Any]:
    """Build a Provider/Consumer graph and rule-health diagnostics."""

    expansion = await expand_layered_context(session, machine_type_id, payload)

    state_result = await session.execute(
        select(StateNode).where(StateNode.machine_type_id == machine_type_id)
    )
    state_nodes = list(state_result.scalars().all())
    state_by_id = {node.id: node for node in state_nodes}
    state_children = _state_children_by_parent(state_nodes)

    candidate_by_activity = {
        item["activity_node_id"]: item for item in expansion["candidate_activities"]
    }
    path_ids_by_activity = {
        item["activity_node_id"]: _activity_path_ids(item)
        for item in expansion["candidate_activities"]
    }

    provider_map: dict[FactKey, list[dict[str, Any]]] = defaultdict(list)
    consumer_map: dict[FactKey, list[dict[str, Any]]] = defaultdict(list)
    goal_map: dict[FactKey, list[dict[str, Any]]] = defaultdict(list)
    fact_keys: set[FactKey] = set()

    for goal in expansion["goal_facts"]:
        key = _goal_fact_key(goal)
        if key is None:
            continue
        goal_map[key].append(goal)
        fact_keys.add(key)

    for rule in expansion["effective_rules"]:
        source_activity_node_id = candidate_by_activity.get(rule["activity_node_id"], {}).get(
            "source_activity_node_id"
        )
        for effect in rule["effects"]:
            key = _effect_fact_key(effect)
            if key is None:
                continue
            provider_map[key].append(_provider_entry(rule, source_activity_node_id))
            fact_keys.add(key)

    precondition_records: list[tuple[dict[str, Any], dict[str, Any], list[FactKey]]] = []
    for rule in expansion["effective_rules"]:
        for precondition in rule["preconditions"]:
            keys = _precondition_fact_keys(
                precondition,
                state_by_id,
                state_children,
                include_inactive=payload.include_inactive,
            )
            precondition_records.append((rule, precondition, keys))
            for key in keys:
                consumer_map[key].append(_consumer_entry(rule, precondition))
                fact_keys.add(key)

    diagnostics: list[dict[str, Any]] = []
    seen_diagnostics: set[tuple[Any, ...]] = set()

    for item in expansion["diagnostics"]:
        _add_diagnostic(
            diagnostics,
            seen_diagnostics,
            {
                "code": item["code"],
                "severity": item.get("severity", "warning"),
                "message": item["message"],
                "details": {"node_id": item.get("node_id"), "node_type": item.get("node_type")},
            },
        )

    goals_by_feature: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    for goal in expansion["goal_facts"]:
        goals_by_feature[goal["feature_key"]].add((goal["operator"], goal.get("target_value")))
    for feature_key, goals in goals_by_feature.items():
        if len(goals) <= 1:
            continue
        _add_diagnostic(
            diagnostics,
            seen_diagnostics,
            {
                "code": "CONFLICTING_GOAL",
                "severity": "error",
                "message": f"Feature {feature_key} has conflicting target values",
                "feature_key": feature_key,
                "details": {"targets": sorted([{"operator": op, "target_value": value} for op, value in goals], key=lambda item: str(item))},
            },
        )

    for key, goals in goal_map.items():
        providers = _dedupe_entries(provider_map.get(key, []))
        feature_key, target_value = key
        if not providers:
            for goal in goals:
                _add_diagnostic(
                    diagnostics,
                    seen_diagnostics,
                    {
                        "code": "NO_PROVIDER",
                        "severity": "error",
                        "message": f"No candidate activity can provide {feature_key}={target_value}",
                        "feature_key": feature_key,
                        "operator": goal["operator"],
                        "target_value": target_value,
                        "state_node_id": goal["state_node_id"],
                        "provider_count": 0,
                    },
                )
        elif len(providers) > 1:
            _add_diagnostic(
                diagnostics,
                seen_diagnostics,
                {
                    "code": "AMBIGUOUS_PROVIDER",
                    "severity": "warning",
                    "message": f"Multiple candidate activities can provide {feature_key}={target_value}",
                    "feature_key": feature_key,
                    "operator": "eq",
                    "target_value": target_value,
                    "provider_count": len(providers),
                    "details": {"providers": providers},
                },
            )

    for rule, precondition, keys in precondition_records:
        if not keys:
            continue

        providers_for_any_key = [
            provider
            for key in keys
            for provider in _dedupe_entries(provider_map.get(key, []))
        ]
        has_goal_fallback = any(key in goal_map for key in keys)
        if not providers_for_any_key and not has_goal_fallback:
            feature_key = precondition.get("feature_key") or (keys[0][0] if keys else None)
            target_value = precondition.get("feature_value") or (keys[0][1] if keys else None)
            _add_diagnostic(
                diagnostics,
                seen_diagnostics,
                {
                    "code": "BROKEN_CHAIN",
                    "severity": "error",
                    "message": f"Effective precondition for {rule['op_rule_code']} has no provider",
                    "feature_key": feature_key,
                    "operator": precondition.get("operator"),
                    "target_value": target_value,
                    "op_rule_id": rule["op_rule_id"],
                    "activity_node_id": rule["activity_node_id"],
                    "source_type": precondition.get("source_type"),
                    "provider_count": 0,
                    "details": {
                        "required_facts": [{"feature_key": key[0], "target_value": key[1]} for key in keys],
                    },
                },
            )

        guarded_activity_node_id = precondition.get("source_activity_node_id")
        if (
            precondition.get("source_type") in {"parent_level_1_scope_guard", "parent_level_2_scope_guard"}
            and providers_for_any_key
            and all(
                _is_inside_guarded_scope(provider, guarded_activity_node_id, path_ids_by_activity)
                for provider in providers_for_any_key
            )
        ):
            feature_key = precondition.get("feature_key") or (keys[0][0] if keys else None)
            target_value = precondition.get("feature_value") or (keys[0][1] if keys else None)
            _add_diagnostic(
                diagnostics,
                seen_diagnostics,
                {
                    "code": "SELF_DEPENDENCY",
                    "severity": "error",
                    "message": "Scope Guard depends on a fact only produced inside its own guarded subtree",
                    "feature_key": feature_key,
                    "operator": precondition.get("operator"),
                    "target_value": target_value,
                    "op_rule_id": rule["op_rule_id"],
                    "activity_node_id": rule["activity_node_id"],
                    "source_type": precondition.get("source_type"),
                    "provider_count": len(providers_for_any_key),
                    "details": {
                        "guarded_activity_node_id": guarded_activity_node_id,
                        "scope_guard_id": precondition.get("scope_guard_id"),
                        "providers": providers_for_any_key,
                    },
                },
            )

    provider_graph = []
    for feature_key, target_value in sorted(fact_keys):
        key = (feature_key, target_value)
        provider_graph.append({
            "feature_key": feature_key,
            "target_value": target_value,
            "goal_state_node_ids": sorted({item["state_node_id"] for item in goal_map.get(key, [])}),
            "providers": _dedupe_entries(provider_map.get(key, [])),
            "consumers": _dedupe_entries(consumer_map.get(key, [])),
        })

    blocking_count = sum(1 for item in diagnostics if item["code"] in BLOCKING_CODES)
    status = "blocked" if blocking_count else "warning" if diagnostics else "ok"

    return {
        "machine_type_id": machine_type_id,
        "status": status,
        "summary": {
            "goal_fact_count": len(expansion["goal_facts"]),
            "candidate_activity_count": len(expansion["candidate_activities"]),
            "effective_rule_count": len(expansion["effective_rules"]),
            "provider_fact_count": sum(1 for item in provider_graph if item["providers"]),
            "consumer_fact_count": sum(1 for item in provider_graph if item["consumers"]),
            "diagnostic_count": len(diagnostics),
            "blocking_count": blocking_count,
        },
        "goal_facts": expansion["goal_facts"],
        "candidate_activities": expansion["candidate_activities"],
        "effective_rules": expansion["effective_rules"],
        "provider_graph": provider_graph,
        "diagnostics": diagnostics,
    }

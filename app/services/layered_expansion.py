"""Layered activity/state expansion service.

This service normalizes the Phase 1 hierarchy data into a preview shape that a
future Planner integration can consume: leaf goal facts, level-3 candidate
activities, and effective preconditions with explicit source metadata.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    AtomicActivity,
    OpRule,
    ScopeGuard,
    ScopeGuardPrecond,
    StateNode,
)
from app.db.schemas import LayeredExpansionRequest


def _path_for_node(node: ActivityNode | StateNode, nodes_by_id: dict[int, ActivityNode | StateNode]) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    current: ActivityNode | StateNode | None = node
    while current is not None:
        node_type = "activity_node" if isinstance(current, ActivityNode) else "state_node"
        path.append({
            "id": current.id,
            "code": current.code,
            "name": current.name,
            "level": current.level,
            "node_type": node_type,
        })
        current = nodes_by_id.get(current.parent_id) if current.parent_id is not None else None
    return list(reversed(path))


def _is_leaf_node(
    node: ActivityNode | StateNode,
    children_by_parent: dict[int | None, list[ActivityNode | StateNode]],
    *,
    include_inactive: bool,
) -> bool:
    return not [
        child
        for child in children_by_parent.get(node.id, [])
        if include_inactive or child.is_active
    ]


def _descendant_state_leaf_nodes(
    root: StateNode,
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[StateNode]:
    if not include_inactive and not root.is_active:
        return []
    if _is_leaf_node(root, children_by_parent, include_inactive=include_inactive):
        return [root]

    leaves: list[StateNode] = []
    stack = list(children_by_parent.get(root.id, []))
    while stack:
        node = stack.pop(0)
        if not include_inactive and not node.is_active:
            continue
        if _is_leaf_node(node, children_by_parent, include_inactive=include_inactive):
            leaves.append(node)
        else:
            stack.extend(children_by_parent.get(node.id, []))
    return leaves


def _descendant_legacy_activity_leaves(
    root: ActivityNode,
    children_by_parent: dict[int | None, list[ActivityNode]],
    *,
    include_inactive: bool,
) -> list[ActivityNode | StateNode]:
    if root.level == 3:
        return [root] if include_inactive or root.is_active else []

    leaves: list[ActivityNode | StateNode] = []
    stack = list(children_by_parent.get(root.id, []))
    while stack:
        node = stack.pop(0)
        if not include_inactive and not node.is_active:
            continue
        if node.level == 3:
            leaves.append(node)
        else:
            stack.extend(children_by_parent.get(node.id, []))
    return leaves


def _activity_level2_packages_for_scope(
    root: ActivityNode,
    children_by_parent: dict[int | None, list[ActivityNode]],
    *,
    include_inactive: bool,
) -> list[ActivityNode]:
    if not include_inactive and not root.is_active:
        return []
    if root.level == 2:
        return [root]
    if root.level > 2:
        return []

    packages: list[ActivityNode] = []
    stack = list(children_by_parent.get(root.id, []))
    while stack:
        node = stack.pop(0)
        if not include_inactive and not node.is_active:
            continue
        if node.level == 2:
            packages.append(node)
            continue
        stack.extend(children_by_parent.get(node.id, []))
    return packages


def _atomic_path_item(activity: AtomicActivity) -> dict[str, Any]:
    return {
        "id": -activity.id,
        "code": activity.code,
        "name": activity.name,
        "level": 3,
        "node_type": "atomic_activity",
        "atomic_activity_id": activity.id,
    }


def _scope_guard_source_type(activity_node: ActivityNode) -> str:
    if activity_node.level == 1:
        return "parent_level_1_scope_guard"
    if activity_node.level == 2:
        return "parent_level_2_scope_guard"
    return "scope_guard"


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _scope_precondition_to_effective(
    precond: ScopeGuardPrecond,
    guard: ScopeGuard,
    source_activity: ActivityNode,
    state_children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> dict[str, Any]:
    state_node = precond.state_node
    operator = precond.operator
    feature_value = precond.expected_value
    feature_key = None
    is_leaf = _is_leaf_node(state_node, state_children_by_parent, include_inactive=include_inactive)

    if operator == "completed" and is_leaf:
        feature_key = state_node.feature_key
        operator = state_node.operator
        feature_value = state_node.target_value
    elif operator != "completed":
        feature_key = state_node.feature_key if is_leaf else None

    return {
        "source_type": _scope_guard_source_type(source_activity),
        "feature_key": feature_key,
        "operator": operator,
        "feature_value": feature_value,
        "value_list": precond.value_list,
        "state_node_id": state_node.id,
        "state_node_code": state_node.code,
        "state_node_name": state_node.name,
        "scope_guard_id": guard.id,
        "scope_guard_name": guard.name,
        "source_activity_node_id": source_activity.id,
        "source_activity_node_code": source_activity.code,
    }


async def expand_layered_context(
    session: AsyncSession,
    machine_type_id: int,
    payload: LayeredExpansionRequest,
) -> dict[str, Any]:
    """Expand selected layered nodes into facts and effective-rule previews."""

    activity_result = await session.execute(
        select(ActivityNode)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .options(
            selectinload(ActivityNode.op_rules).selectinload(OpRule.preconditions),
            selectinload(ActivityNode.op_rules).selectinload(OpRule.effects),
            selectinload(ActivityNode.op_rules).selectinload(OpRule.resource_reqs),
            selectinload(ActivityNode.scope_guards)
            .selectinload(ScopeGuard.preconditions)
            .selectinload(ScopeGuardPrecond.state_node),
        )
    )
    activity_nodes = list(activity_result.scalars().all())
    atomic_ref_result = await session.execute(
        select(ActivityPackageAtomicRef)
        .join(ActivityNode, ActivityPackageAtomicRef.activity_node_id == ActivityNode.id)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .options(
            selectinload(ActivityPackageAtomicRef.activity_node),
            selectinload(ActivityPackageAtomicRef.atomic_activity)
            .selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.preconditions),
            selectinload(ActivityPackageAtomicRef.atomic_activity)
            .selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.effects),
            selectinload(ActivityPackageAtomicRef.atomic_activity)
            .selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.resource_reqs),
        )
    )
    atomic_refs = list(atomic_ref_result.scalars().all())
    state_result = await session.execute(
        select(StateNode).where(StateNode.machine_type_id == machine_type_id)
    )
    state_nodes = list(state_result.scalars().all())

    activity_by_id = {node.id: node for node in activity_nodes}
    state_by_id = {node.id: node for node in state_nodes}
    activity_children: dict[int | None, list[ActivityNode]] = defaultdict(list)
    state_children: dict[int | None, list[StateNode]] = defaultdict(list)
    for node in activity_nodes:
        activity_children[node.parent_id].append(node)
    for node in state_nodes:
        state_children[node.parent_id].append(node)
    atomic_refs_by_package: dict[int, list[ActivityPackageAtomicRef]] = defaultdict(list)
    for ref in atomic_refs:
        atomic_refs_by_package[ref.activity_node_id].append(ref)
    for refs in atomic_refs_by_package.values():
        refs.sort(key=lambda item: (item.sort_order, item.id))

    diagnostics: list[dict[str, Any]] = []
    goal_facts: list[dict[str, Any]] = []
    seen_goal_pairs: set[tuple[int, int]] = set()

    for selected_id in payload.target_state_node_ids:
        selected = state_by_id.get(selected_id)
        if selected is None:
            raise HTTPException(status_code=404, detail=f"State node {selected_id} not found")
        if not payload.include_inactive and not selected.is_active:
            diagnostics.append({
                "code": "SELECTED_STATE_INACTIVE",
                "message": f"Selected state node {selected.code} is inactive and was skipped",
                "node_id": selected.id,
                "node_type": "state_node",
            })
            continue
        leaves = _descendant_state_leaf_nodes(selected, state_children, include_inactive=payload.include_inactive)
        if not leaves:
            diagnostics.append({
                "code": "TARGET_STATE_HAS_NO_LEAF",
                "message": f"Selected state node {selected.code} has no active atomic descendants",
                "node_id": selected.id,
                "node_type": "state_node",
            })
            continue
        for leaf in leaves:
            key = (selected.id, leaf.id)
            if key in seen_goal_pairs:
                continue
            seen_goal_pairs.add(key)
            if not leaf.feature_key:
                diagnostics.append({
                    "code": "LEAF_STATE_WITHOUT_FEATURE",
                    "message": f"Atomic state node {leaf.code} has no feature_key",
                    "node_id": leaf.id,
                    "node_type": "state_node",
                })
                continue
            goal_facts.append({
                "source_state_node_id": selected.id,
                "state_node_id": leaf.id,
                "state_node_code": leaf.code,
                "state_node_name": leaf.name,
                "feature_key": leaf.feature_key,
                "operator": leaf.operator,
                "target_value": leaf.target_value,
                "source_path": _path_for_node(leaf, state_by_id),
            })

    goals_by_feature: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    for goal in goal_facts:
        goals_by_feature[goal["feature_key"]].add((goal["operator"], goal.get("target_value")))
    for feature_key, goals in goals_by_feature.items():
        if len(goals) <= 1:
            continue
        diagnostics.append({
            "code": "CONFLICTING_GOAL",
            "severity": "error",
            "message": f"Feature {feature_key} has conflicting target values",
            "node_id": None,
            "node_type": "state_node",
        })

    candidate_activities: list[dict[str, Any]] = []
    effective_rules: list[dict[str, Any]] = []
    candidate_keys: set[tuple[str, int]] = set()
    effective_rule_ids: set[int] = set()

    def build_inherited_preconditions(path: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ancestor_nodes = [
            activity_by_id[item["id"]]
            for item in path
            if item.get("node_type", "activity_node") == "activity_node" and item["level"] in (1, 2)
        ]
        inherited_preconditions: list[dict[str, Any]] = []
        for ancestor in ancestor_nodes:
            guards = [
                guard for guard in ancestor.scope_guards
                if payload.include_inactive or guard.is_active
            ]
            for guard in guards:
                if not guard.preconditions:
                    diagnostics.append({
                        "code": "SCOPE_GUARD_WITHOUT_PRECONDITION",
                        "message": f"Scope Guard {guard.name} has no preconditions",
                        "node_id": guard.id,
                        "node_type": "scope_guard",
                    })
                for precond in guard.preconditions:
                    inherited_preconditions.append(
                        _scope_precondition_to_effective(
                            precond,
                            guard,
                            ancestor,
                            state_children,
                            include_inactive=payload.include_inactive,
                        )
                    )
        return inherited_preconditions

    def append_effective_rules(
        *,
        rules: list[OpRule],
        executable_id: int,
        executable_code: str,
        executable_name: str,
        inherited_preconditions: list[dict[str, Any]],
        atomic_activity_id: int | None = None,
    ) -> None:
        for rule in rules:
            if rule.id in effective_rule_ids:
                continue
            effective_rule_ids.add(rule.id)
            self_preconditions = [
                {
                    "source_type": "self_activity_rule",
                    "feature_key": item.feature_key,
                    "operator": item.operator,
                    "feature_value": item.feature_value,
                    "value_list": item.value_list,
                    "state_node_id": None,
                    "state_node_code": None,
                    "state_node_name": None,
                    "scope_guard_id": None,
                    "scope_guard_name": None,
                    "source_activity_node_id": executable_id,
                    "source_activity_node_code": executable_code,
                }
                for item in rule.preconditions
            ]
            effective_rules.append({
                "op_rule_id": rule.id,
                "op_rule_code": rule.code,
                "op_rule_name": rule.name,
                "activity_node_id": executable_id,
                "activity_node_code": executable_code,
                "activity_node_name": executable_name,
                "atomic_activity_id": atomic_activity_id,
                "duration_min": rule.duration_min,
                "preconditions": self_preconditions + inherited_preconditions,
                "effects": [
                    {
                        "feature_key": item.feature_key,
                        "new_value": item.new_value,
                        "effect_type": item.effect_type,
                        "delta_value": _decimal_to_float(item.delta_value),
                    }
                    for item in rule.effects
                ],
                "resource_reqs": [
                    {
                        "resource_type": item.resource_type,
                        "quantity": item.quantity,
                        "is_required": item.is_required,
                    }
                    for item in rule.resource_reqs
                ],
            })

    for selected_id in payload.activity_scope_node_ids:
        selected = activity_by_id.get(selected_id)
        if selected is None:
            raise HTTPException(status_code=404, detail=f"Activity node {selected_id} not found")
        if not payload.include_inactive and not selected.is_active:
            diagnostics.append({
                "code": "SELECTED_ACTIVITY_INACTIVE",
                "message": f"Selected activity node {selected.code} is inactive and was skipped",
                "node_id": selected.id,
                "node_type": "activity_node",
            })
            continue
        packages = _activity_level2_packages_for_scope(
            selected,
            activity_children,
            include_inactive=payload.include_inactive,
        )
        legacy_leaves = _descendant_legacy_activity_leaves(
            selected,
            activity_children,
            include_inactive=payload.include_inactive,
        )
        if not packages and not legacy_leaves:
            diagnostics.append({
                "code": "ACTIVITY_SCOPE_HAS_NO_LEAF",
                "message": f"Selected activity node {selected.code} has no active atomic activities",
                "node_id": selected.id,
                "node_type": "activity_node",
            })
            continue

        for package in packages:
            refs = [
                ref
                for ref in atomic_refs_by_package.get(package.id, [])
                if payload.include_inactive or ref.is_active
            ]
            legacy_under_package = _descendant_legacy_activity_leaves(
                package,
                activity_children,
                include_inactive=payload.include_inactive,
            )
            if not refs and not legacy_under_package:
                diagnostics.append({
                    "code": "ACTIVITY_PACKAGE_WITHOUT_ATOMIC_REF",
                    "message": f"Level-2 activity package {package.code} has no active atomic activity reference",
                    "node_id": package.id,
                    "node_type": "activity_node",
                })
            package_path = _path_for_node(package, activity_by_id)
            inherited_preconditions = build_inherited_preconditions(package_path)
            for ref in refs:
                atomic = ref.atomic_activity
                if atomic is None:
                    diagnostics.append({
                        "code": "ATOMIC_REF_WITHOUT_ACTIVITY",
                        "message": f"Activity package ref {ref.id} has no atomic activity",
                        "node_id": ref.id,
                        "node_type": "activity_package_atomic_ref",
                    })
                    continue
                if not payload.include_inactive and not atomic.is_active:
                    diagnostics.append({
                        "code": "ATOMIC_ACTIVITY_INACTIVE",
                        "message": f"Atomic activity {atomic.code} is inactive and was skipped",
                        "node_id": atomic.id,
                        "node_type": "atomic_activity",
                    })
                    continue
                candidate_key = ("atomic", atomic.id)
                raw_active_rules = [
                    rule
                    for rule in atomic.op_rules
                    if payload.include_inactive or rule.is_active
                ]
                if candidate_key in candidate_keys:
                    continue
                candidate_keys.add(candidate_key)
                active_rules = [rule for rule in raw_active_rules if rule.id not in effective_rule_ids]
                if not active_rules:
                    diagnostics.append({
                        "code": "ATOMIC_ACTIVITY_WITHOUT_RULE",
                        "message": f"Atomic activity {atomic.code} has no active op rule",
                        "node_id": atomic.id,
                        "node_type": "atomic_activity",
                    })
                atomic_path = package_path + [_atomic_path_item(atomic)]
                executable_id = -atomic.id
                candidate_activities.append({
                    "source_activity_node_id": package.id,
                    "activity_node_id": executable_id,
                    "activity_node_code": atomic.code,
                    "activity_node_name": atomic.name,
                    "activity_category": atomic.activity_category,
                    "node_type": "atomic_activity",
                    "atomic_activity_id": atomic.id,
                    "activity_package_atomic_ref_id": ref.id,
                    "op_rule_ids": [rule.id for rule in active_rules],
                    "source_path": atomic_path,
                })
                append_effective_rules(
                    rules=active_rules,
                    executable_id=executable_id,
                    executable_code=atomic.code,
                    executable_name=atomic.name,
                    inherited_preconditions=inherited_preconditions,
                    atomic_activity_id=atomic.id,
                )

        for leaf in legacy_leaves:
            candidate_key = ("legacy", leaf.id)
            if candidate_key in candidate_keys:
                continue
            candidate_keys.add(candidate_key)
            raw_active_rules = [
                rule
                for rule in leaf.op_rules
                if payload.include_inactive or rule.is_active
            ]
            active_rules = [rule for rule in raw_active_rules if rule.id not in effective_rule_ids]
            if not active_rules and raw_active_rules:
                continue
            if not active_rules:
                diagnostics.append({
                    "code": "ACTIVITY_WITHOUT_RULE",
                    "message": f"Level-3 activity node {leaf.code} has no active op rule",
                    "node_id": leaf.id,
                    "node_type": "activity_node",
                })
            candidate_activities.append({
                "source_activity_node_id": selected.id,
                "activity_node_id": leaf.id,
                "activity_node_code": leaf.code,
                "activity_node_name": leaf.name,
                "activity_category": leaf.activity_category,
                "node_type": "legacy_activity_node",
                "atomic_activity_id": None,
                "op_rule_ids": [rule.id for rule in active_rules],
                "source_path": _path_for_node(leaf, activity_by_id),
            })

            path = _path_for_node(leaf, activity_by_id)
            inherited_preconditions = build_inherited_preconditions(path)
            append_effective_rules(
                rules=active_rules,
                executable_id=leaf.id,
                executable_code=leaf.code,
                executable_name=leaf.name,
                inherited_preconditions=inherited_preconditions,
                atomic_activity_id=None,
            )

    return {
        "machine_type_id": machine_type_id,
        "goal_facts": goal_facts,
        "candidate_activities": candidate_activities,
        "effective_rules": effective_rules,
        "diagnostics": diagnostics,
    }

"""Resolve package selections into canonical state facts and atomic activities."""

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
    StateNode,
    StateNodeReference,
)
from app.db.schemas import LayeredExpansionRequest
from app.core.modeling.semantics import is_atomic_state


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


def _path_items_for_nodes(nodes: list[ActivityNode | StateNode]) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for node in nodes:
        node_type = "activity_node" if isinstance(node, ActivityNode) else "state_node"
        path.append({
            "id": node.id,
            "code": node.code,
            "name": node.name,
            "level": node.level,
            "node_type": node_type,
        })
    return path


def _state_path_from_root(
    root: StateNode,
    leaf_id: int,
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[StateNode]:
    if root.id == leaf_id:
        return [root]

    queue: list[tuple[StateNode, list[StateNode]]] = [(root, [root])]
    seen_edges: set[tuple[int, int]] = set()
    while queue:
        node, path = queue.pop(0)
        for child in children_by_parent.get(node.id, []):
            if not include_inactive and not child.is_active:
                continue
            edge = (node.id, child.id)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            if any(item.id == child.id for item in path):
                continue
            next_path = [*path, child]
            if child.id == leaf_id:
                return next_path
            queue.append((child, next_path))
    return []


def _state_children_by_parent(
    state_nodes: list[StateNode],
    state_refs: list[StateNodeReference],
    *,
    include_inactive: bool,
) -> dict[int | None, list[StateNode]]:
    children: dict[int | None, list[StateNode]] = defaultdict(list)
    by_id = {node.id: node for node in state_nodes}
    seen: set[tuple[int | None, int]] = set()
    for node in state_nodes:
        parent = by_id.get(node.parent_id) if node.parent_id is not None else None
        if not include_inactive and (not node.is_active or (parent is not None and not parent.is_active)):
            continue
        children[node.parent_id].append(node)
        seen.add((node.parent_id, node.id))

    for ref in state_refs:
        if not ref.is_active:
            continue
        node = by_id.get(ref.state_node_id)
        parent = by_id.get(ref.parent_state_node_id)
        if node is None or parent is None:
            continue
        if not include_inactive and (not node.is_active or not parent.is_active):
            continue
        key = (ref.parent_state_node_id, ref.state_node_id)
        if key in seen:
            continue
        children[ref.parent_state_node_id].append(node)
        seen.add(key)

    for values in children.values():
        values.sort(key=lambda item: (item.sort_order, item.id))
    return children


def _descendant_state_leaf_nodes(
    root: StateNode,
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[StateNode]:
    if not include_inactive and not root.is_active:
        return []
    if is_atomic_state(root):
        return [root]

    leaves: list[StateNode] = []
    stack = list(children_by_parent.get(root.id, []))
    while stack:
        node = stack.pop(0)
        if not include_inactive and not node.is_active:
            continue
        if is_atomic_state(node):
            leaves.append(node)
        else:
            stack.extend(children_by_parent.get(node.id, []))
    return leaves


def _atomic_path_item(activity: AtomicActivity) -> dict[str, Any]:
    return {
        "id": -activity.id,
        "code": activity.code,
        "name": activity.name,
        "level": 3,
        "node_type": "atomic_activity",
        "atomic_activity_id": activity.id,
    }


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


async def expand_layered_context(
    session: AsyncSession,
    machine_type_id: int,
    payload: LayeredExpansionRequest,
) -> dict[str, Any]:
    """Expand selected layered nodes into facts and effective-rule previews."""

    activity_result = await session.execute(
        select(ActivityNode)
        .where(ActivityNode.machine_type_id == machine_type_id)
    )
    activity_nodes = list(activity_result.scalars().all())
    atomic_ref_result = await session.execute(
        select(ActivityPackageAtomicRef)
        .join(ActivityNode, ActivityPackageAtomicRef.activity_node_id == ActivityNode.id)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .options(selectinload(ActivityPackageAtomicRef.activity_node))
    )
    atomic_refs = list(atomic_ref_result.scalars().all())
    atomic_result = await session.execute(
        select(AtomicActivity)
        .where(AtomicActivity.machine_type_id == machine_type_id)
        .options(
            selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.preconditions),
            selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.effects),
            selectinload(AtomicActivity.op_rules)
            .selectinload(OpRule.resource_reqs),
        )
    )
    atomic_activities = list(atomic_result.scalars().all())
    state_result = await session.execute(
        select(StateNode).where(StateNode.machine_type_id == machine_type_id)
    )
    state_nodes = list(state_result.scalars().all())
    state_ref_result = await session.execute(
        select(StateNodeReference)
        .join(StateNode, StateNodeReference.state_node_id == StateNode.id)
        .where(StateNode.machine_type_id == machine_type_id)
    )
    state_refs = list(state_ref_result.scalars().all())

    activity_by_id = {node.id: node for node in activity_nodes}
    state_by_id = {node.id: node for node in state_nodes}
    activity_children: dict[int | None, list[ActivityNode]] = defaultdict(list)
    for node in activity_nodes:
        activity_children[node.parent_id].append(node)
    state_children = _state_children_by_parent(
        state_nodes,
        state_refs,
        include_inactive=payload.include_inactive,
    )
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
            source_path = _state_path_from_root(
                selected,
                leaf.id,
                state_children,
                include_inactive=payload.include_inactive,
            )
            goal_facts.append({
                "source_state_node_id": selected.id,
                "state_node_id": leaf.id,
                "state_node_code": leaf.code,
                "state_node_name": leaf.name,
                "feature_key": leaf.feature_key,
                "operator": leaf.operator,
                "target_value": leaf.target_value,
                "source_path": _path_items_for_nodes(source_path) if source_path else _path_for_node(leaf, state_by_id),
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

    def append_atomic_candidate(
        *,
        atomic: AtomicActivity | None,
        source_activity_node_id: int | None,
        package_ref_id: int | None,
        source_path: list[dict[str, Any]],
        inherited_preconditions: list[dict[str, Any]],
        missing_ref_id: int | None = None,
    ) -> None:
        if atomic is None:
            diagnostics.append({
                "code": "ATOMIC_REF_WITHOUT_ACTIVITY",
                "message": f"Activity package ref {missing_ref_id} has no atomic activity",
                "node_id": missing_ref_id,
                "node_type": "activity_package_atomic_ref",
            })
            return
        if not payload.include_inactive and not atomic.is_active:
            diagnostics.append({
                "code": "ATOMIC_ACTIVITY_INACTIVE",
                "message": f"Atomic activity {atomic.code} is inactive and was skipped",
                "node_id": atomic.id,
                "node_type": "atomic_activity",
            })
            return

        candidate_key = ("atomic", atomic.id)
        raw_active_rules = [
            rule
            for rule in atomic.op_rules
            if payload.include_inactive or rule.is_active
        ]
        if candidate_key in candidate_keys:
            return
        candidate_keys.add(candidate_key)
        active_rules = [rule for rule in raw_active_rules if rule.id not in effective_rule_ids]
        if not active_rules:
            diagnostics.append({
                "code": "ATOMIC_ACTIVITY_WITHOUT_RULE",
                "message": f"Atomic activity {atomic.code} has no active op rule",
                "node_id": atomic.id,
                "node_type": "atomic_activity",
            })

        executable_id = -atomic.id
        candidate_activities.append({
            "source_activity_node_id": source_activity_node_id if source_activity_node_id is not None else executable_id,
            "activity_node_id": executable_id,
            "activity_node_code": atomic.code,
            "activity_node_name": atomic.name,
            "activity_category": atomic.activity_category,
            "node_type": "atomic_activity",
            "atomic_activity_id": atomic.id,
            "activity_package_atomic_ref_id": package_ref_id,
            "op_rule_ids": [rule.id for rule in active_rules],
            "source_path": source_path + [_atomic_path_item(atomic)],
        })
        append_effective_rules(
            rules=active_rules,
            executable_id=executable_id,
            executable_code=atomic.code,
            executable_name=atomic.name,
            inherited_preconditions=inherited_preconditions,
            atomic_activity_id=atomic.id,
        )

    requested_atomic_ids = {
        int(item) for item in payload.atomic_activity_scope_ids
    }
    if payload.activity_scope_node_ids:
        resolved_from_packages: set[int] = set()
        for selected_id in payload.activity_scope_node_ids:
            selected = activity_by_id.get(selected_id)
            if selected is None:
                raise HTTPException(status_code=404, detail=f"Activity node {selected_id} not found")
            stack = [selected]
            scoped_package_ids: set[int] = set()
            while stack:
                current = stack.pop()
                if payload.include_inactive or current.is_active:
                    scoped_package_ids.add(current.id)
                    stack.extend(activity_children.get(current.id, []))
            for package_id in scoped_package_ids:
                for ref in atomic_refs_by_package.get(package_id, []):
                    if payload.include_inactive or ref.is_active:
                        resolved_from_packages.add(ref.atomic_activity_id)
        requested_atomic_ids.update(resolved_from_packages)
        diagnostics.append({
            "code": "ACTIVITY_PACKAGE_SCOPE_DEPRECATED",
            "severity": "warning",
            "message": "Package scope was resolved to canonical atomic activities; package paths were discarded.",
            "node_id": None,
            "node_type": "activity_node",
            "details": {
                "activity_scope_node_ids": payload.activity_scope_node_ids,
                "resolved_atomic_activity_ids": sorted(resolved_from_packages),
            },
        })

    atomic_by_id = {activity.id: activity for activity in atomic_activities}
    if requested_atomic_ids:
        unknown_atomic_ids = sorted(requested_atomic_ids - set(atomic_by_id))
        if unknown_atomic_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Atomic activities not found: {unknown_atomic_ids}",
            )
        selected_atomic_activities = [
            atomic_by_id[item_id] for item_id in sorted(requested_atomic_ids)
        ]
    else:
        selected_atomic_activities = sorted(
            atomic_activities,
            key=lambda item: (item.sort_order, item.id),
        )

    for atomic in selected_atomic_activities:
        append_atomic_candidate(
            atomic=atomic,
            source_activity_node_id=None,
            package_ref_id=None,
            source_path=[],
            inherited_preconditions=[],
        )

    return {
        "machine_type_id": machine_type_id,
        "goal_facts": goal_facts,
        "candidate_activities": candidate_activities,
        "effective_rules": effective_rules,
        "diagnostics": diagnostics,
    }

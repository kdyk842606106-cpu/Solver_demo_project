"""Network-editor graph projection, validation, and solver precheck services."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    ActivityStateBinding,
    AtomicActivity,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    StateNode,
    StateNodeReference,
)
from app.db.schemas import LayeredExpansionRequest, NetworkEditorImpactRequest, NetworkEditorRequest
from app.services.layered_health import check_layered_health
from app.services.scheduling_rule_config import validate_machine_type_scheduling_rules


INPUT_ROLES = {"input"}
OUTPUT_ROLES = {"output"}
BLOCKING_HEALTH_CODES = {"NO_PROVIDER", "BROKEN_CHAIN", "SELF_DEPENDENCY", "CONFLICTING_GOAL"}
LARGE_COVERAGE_LEAF_THRESHOLD = 8
CROSS_LEVEL_BINDING_MANY_THRESHOLD = 3


@dataclass
class NetworkEditorContext:
    machine_type_id: int
    state_nodes: list[StateNode]
    state_refs: list[StateNodeReference]
    activity_nodes: list[ActivityNode]
    atomic_activities: list[AtomicActivity]
    package_refs: list[ActivityPackageAtomicRef]
    bindings: list[ActivityStateBinding]
    op_rules: list[OpRule]

    @property
    def state_by_id(self) -> dict[int, StateNode]:
        return {node.id: node for node in self.state_nodes}

    @property
    def activity_by_id(self) -> dict[int, ActivityNode]:
        return {node.id: node for node in self.activity_nodes}

    @property
    def atomic_by_id(self) -> dict[int, AtomicActivity]:
        return {activity.id: activity for activity in self.atomic_activities}


def _network_editor_revision(context: NetworkEditorContext) -> str:
    """Content fingerprint for concurrent edit-session conflict detection."""

    records: list[dict[str, Any]] = []

    def add(kind: str, item_id: int, **fields: Any) -> None:
        records.append({"kind": kind, "id": item_id, **fields})

    for node in sorted(context.state_nodes, key=lambda item: item.id):
        add(
            "state_node",
            node.id,
            parent_id=node.parent_id,
            level=node.level,
            code=node.code,
            name=node.name,
            feature_key=node.feature_key,
            operator=node.operator,
            target_value=node.target_value,
            state_kind=node.state_kind,
            sort_order=node.sort_order,
            is_active=node.is_active,
            metadata_json=node.metadata_json,
        )
    for ref in sorted(context.state_refs, key=lambda item: item.id):
        add(
            "state_node_reference",
            ref.id,
            state_node_id=ref.state_node_id,
            parent_state_node_id=ref.parent_state_node_id,
            sort_order=ref.sort_order,
            is_active=ref.is_active,
            metadata_json=ref.metadata_json,
        )
    for node in sorted(context.activity_nodes, key=lambda item: item.id):
        add(
            "activity_node",
            node.id,
            parent_id=node.parent_id,
            level=node.level,
            code=node.code,
            name=node.name,
            description=node.description,
            activity_category=node.activity_category,
            sort_order=node.sort_order,
            is_active=node.is_active,
            metadata_json=node.metadata_json,
        )
    for activity in sorted(context.atomic_activities, key=lambda item: item.id):
        add(
            "atomic_activity",
            activity.id,
            code=activity.code,
            name=activity.name,
            description=activity.description,
            activity_category=activity.activity_category,
            sort_order=activity.sort_order,
            is_active=activity.is_active,
            metadata_json=activity.metadata_json,
        )
    for ref in sorted(context.package_refs, key=lambda item: item.id):
        add(
            "activity_package_atomic_ref",
            ref.id,
            activity_node_id=ref.activity_node_id,
            atomic_activity_id=ref.atomic_activity_id,
            sort_order=ref.sort_order,
            is_active=ref.is_active,
            metadata_json=ref.metadata_json,
        )
    for binding in sorted(context.bindings, key=lambda item: item.id):
        add(
            "activity_state_binding",
            binding.id,
            activity_node_id=binding.activity_node_id,
            atomic_activity_id=binding.atomic_activity_id,
            op_rule_id=binding.op_rule_id,
            state_node_id=binding.state_node_id,
            binding_role=binding.binding_role,
            binding_type=binding.binding_type,
            coverage_policy=binding.coverage_policy,
            covered_leaf_state_ids=binding.covered_leaf_state_ids,
            coverage_status=binding.coverage_status,
            is_inherited=binding.is_inherited,
            is_active=binding.is_active,
            metadata_json=binding.metadata_json,
        )
    for rule in sorted(context.op_rules, key=lambda item: item.id):
        add(
            "op_rule",
            rule.id,
            activity_node_id=rule.activity_node_id,
            atomic_activity_id=rule.atomic_activity_id,
            code=rule.code,
            name=rule.name,
            duration_min=rule.duration_min,
            description=rule.description,
            is_active=rule.is_active,
            is_repair=rule.is_repair,
            valid_from=rule.valid_from,
            valid_to=rule.valid_to,
            preconditions=[
                {
                    "id": item.id,
                    "feature_key": item.feature_key,
                    "operator": item.operator,
                    "feature_value": item.feature_value,
                    "value_list": item.value_list,
                }
                for item in sorted(rule.preconditions, key=lambda child: child.id)
            ],
            effects=[
                {
                    "id": item.id,
                    "feature_key": item.feature_key,
                    "new_value": item.new_value,
                    "effect_type": item.effect_type,
                    "delta_value": item.delta_value,
                }
                for item in sorted(rule.effects, key=lambda child: child.id)
            ],
            resource_reqs=[
                {
                    "id": item.id,
                    "resource_type": item.resource_type,
                    "quantity": item.quantity,
                    "is_required": item.is_required,
                }
                for item in sorted(rule.resource_reqs, key=lambda child: child.id)
            ],
        )

    payload = json.dumps(records, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_network_editor_revision(session: AsyncSession, machine_type_id: int) -> str:
    context = await _load_context(session, machine_type_id)
    return _network_editor_revision(context)


def _node_id(prefix: str, id_value: int) -> str:
    return f"{prefix}:{id_value}"


def _state_graph_id(state_node_id: int) -> str:
    return _node_id("state_node", state_node_id)


def _state_reference_graph_id(state_node_id: int, ref_id: int) -> str:
    return f"state_node:{state_node_id}:ref:{ref_id}"


def _state_node_id_from_graph_id(graph_id: str) -> int | None:
    if not graph_id.startswith("state_node:"):
        return None
    parts = graph_id.split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _activity_graph_id(activity_node_id: int) -> str:
    return _node_id("activity_node", activity_node_id)


def _atomic_graph_id(atomic_activity_id: int) -> str:
    return _node_id("atomic_activity", atomic_activity_id)


def _children_by_parent(nodes: list[StateNode] | list[ActivityNode]) -> dict[int | None, list[Any]]:
    children: dict[int | None, list[Any]] = defaultdict(list)
    for node in nodes:
        children[node.parent_id].append(node)
    for values in children.values():
        values.sort(key=lambda item: (item.sort_order, item.id))
    return children


def _state_display_children_by_parent(
    nodes: list[StateNode],
    references: list[StateNodeReference],
    *,
    include_inactive: bool,
) -> dict[int | None, list[StateNode]]:
    children: dict[int | None, list[StateNode]] = defaultdict(list)
    by_id = {node.id: node for node in nodes}
    seen: set[tuple[int | None, int]] = set()
    for node in nodes:
        parent = by_id.get(node.parent_id) if node.parent_id is not None else None
        if not include_inactive and (not node.is_active or (parent is not None and not parent.is_active)):
            continue
        children[node.parent_id].append(node)
        seen.add((node.parent_id, node.id))

    for ref in references:
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


def _state_leaf_ids_under(
    state_node_id: int,
    state_by_id: dict[int, StateNode],
    state_children: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[int]:
    root = state_by_id.get(state_node_id)
    if root is None:
        return []
    if not include_inactive and not root.is_active:
        return []

    leaves: list[int] = []
    stack = [root]
    seen: set[int] = set()
    while stack:
        node = stack.pop(0)
        if node.id in seen:
            continue
        seen.add(node.id)
        if not include_inactive and not node.is_active:
            continue
        children = [
            child for child in state_children.get(node.id, [])
            if include_inactive or child.is_active
        ]
        if children:
            stack.extend(children)
        elif node.feature_key and node.target_value:
            leaves.append(node.id)
    return leaves


def _coverage_status(
    binding: ActivityStateBinding,
    state_by_id: dict[int, StateNode],
    state_children: dict[int | None, list[StateNode]],
) -> str:
    active_leaf_ids = set(
        _state_leaf_ids_under(binding.state_node_id, state_by_id, state_children, include_inactive=False)
    )
    all_leaf_ids = set(
        _state_leaf_ids_under(binding.state_node_id, state_by_id, state_children, include_inactive=True)
    )
    covered_ids = {int(item) for item in (binding.covered_leaf_state_ids or [])}

    if not covered_ids:
        return "stale"
    if not covered_ids.issubset(all_leaf_ids):
        return "stale"
    if covered_ids == active_leaf_ids and active_leaf_ids:
        return "complete"
    if covered_ids.issubset(active_leaf_ids):
        return "partial" if binding.coverage_status == "partial" else "stale"
    return "stale"


def _state_path(node: StateNode, state_by_id: dict[int, StateNode]) -> list[int]:
    path: list[int] = []
    current: StateNode | None = node
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        path.append(current.id)
        current = state_by_id.get(current.parent_id) if current.parent_id is not None else None
    return list(reversed(path))


def _activity_path(node: ActivityNode, activity_by_id: dict[int, ActivityNode]) -> list[int]:
    path: list[int] = []
    current: ActivityNode | None = node
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        path.append(current.id)
        current = activity_by_id.get(current.parent_id) if current.parent_id is not None else None
    return list(reversed(path))


def _selected_descendant_depths(
    selected_ids: list[int],
    children: dict[int | None, list[Any]],
    all_ids: set[int],
    *,
    max_depth: int = 0,
) -> dict[int, int]:
    if not selected_ids and max_depth <= 0:
        return {item_id: 0 for item_id in all_ids}

    roots = [node_id for node_id in selected_ids if node_id in all_ids]
    if not roots:
        roots = [node.id for node in children.get(None, []) if node.id in all_ids]

    selected: dict[int, int] = {}
    stack = [(node_id, 1) for node_id in roots]
    while stack:
        node_id, depth = stack.pop(0)
        if node_id in selected and selected[node_id] <= depth:
            continue
        selected[node_id] = depth
        if max_depth > 0 and depth >= max_depth:
            continue
        stack.extend((child.id, depth + 1) for child in children.get(node_id, []) if child.id in all_ids)
    return selected


def _state_fact(state: StateNode) -> dict[str, Any]:
    return {
        "state_node_id": state.id,
        "state_node_code": state.code,
        "state_node_name": state.name,
        "feature_key": state.feature_key,
        "operator": state.operator,
        "value": state.target_value,
    }


def _binding_leaf_facts(
    binding: ActivityStateBinding,
    state_by_id: dict[int, StateNode],
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for leaf_id in binding.covered_leaf_state_ids or []:
        leaf = state_by_id.get(int(leaf_id))
        if leaf and (include_inactive or leaf.is_active) and leaf.feature_key and leaf.target_value:
            facts.append(_state_fact(leaf))
    return facts


def _legacy_precondition_state_ids(
    precond: OpRulePrecond,
    state_nodes: list[StateNode],
    *,
    include_inactive: bool,
) -> list[int]:
    if not precond.feature_key or not precond.feature_value:
        return []
    return [
        node.id for node in state_nodes
        if (include_inactive or node.is_active)
        and node.feature_key == precond.feature_key
        and node.operator == precond.operator
        and node.target_value == precond.feature_value
    ]


def _legacy_effect_state_ids(
    effect: OpRuleEffect,
    state_nodes: list[StateNode],
    *,
    include_inactive: bool,
) -> list[int]:
    if not effect.feature_key or effect.new_value is None:
        return []
    return [
        node.id for node in state_nodes
        if (include_inactive or node.is_active)
        and node.feature_key == effect.feature_key
        and node.target_value == effect.new_value
    ]


def _activity_id_for_rule(rule: OpRule) -> str | None:
    if rule.atomic_activity_id is not None:
        return _atomic_graph_id(rule.atomic_activity_id)
    if rule.activity_node_id is not None:
        return _activity_graph_id(rule.activity_node_id)
    return None


def _rule_activity_is_visible(
    rule: OpRule,
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> bool:
    if include_inactive:
        return True
    if not rule.is_active:
        return False
    if rule.atomic_activity_id is not None:
        atomic = context.atomic_by_id.get(rule.atomic_activity_id)
        return atomic is not None and atomic.is_active
    if rule.activity_node_id is not None:
        activity = context.activity_by_id.get(rule.activity_node_id)
        return activity is not None and activity.is_active
    return False


def _state_summary(node: StateNode | dict[str, Any] | None) -> dict[str, Any]:
    if node is None:
        return {}
    if isinstance(node, dict):
        return {
            "id": node["id"],
            "state_node_id": node["state_node_id"],
            "code": node["code"],
            "name": node["name"],
            "level": node["level"],
            "state_kind": node.get("state_kind"),
            "feature_key": node.get("feature_key"),
            "operator": node.get("operator"),
            "target_value": node.get("target_value"),
            "is_leaf": node.get("is_leaf"),
            "leaf_state_ids": node.get("leaf_state_ids", []),
        }
    return {
        "id": _state_graph_id(node.id),
        "state_node_id": node.id,
        "code": node.code,
        "name": node.name,
        "level": node.level,
        "state_kind": node.state_kind,
        "feature_key": node.feature_key,
        "operator": node.operator,
        "target_value": node.target_value,
        "is_leaf": bool(node.feature_key and node.target_value),
    }


def _activity_summary(node: ActivityNode | AtomicActivity | dict[str, Any] | None) -> dict[str, Any]:
    if node is None:
        return {}
    if isinstance(node, dict):
        return {
            "id": node["id"],
            "activity_node_id": node.get("activity_node_id"),
            "atomic_activity_id": node.get("atomic_activity_id"),
            "code": node["code"],
            "name": node["name"],
            "level": node["level"],
            "activity_type": node.get("activity_type"),
            "activity_category": node.get("activity_category"),
            "solver_participation": node.get("solver_participation"),
            "parent_graph_id": node.get("parent_graph_id"),
            "parent_activity_node_ids": node.get("parent_activity_node_ids", []),
            "path_ids": node.get("path_ids", []),
        }
    if isinstance(node, AtomicActivity):
        return {
            "id": _atomic_graph_id(node.id),
            "activity_node_id": None,
            "atomic_activity_id": node.id,
            "code": node.code,
            "name": node.name,
            "level": 3,
            "activity_type": "executable",
            "activity_category": node.activity_category,
            "solver_participation": True,
        }
    return {
        "id": _activity_graph_id(node.id),
        "activity_node_id": node.id,
        "atomic_activity_id": None,
        "code": node.code,
        "name": node.name,
        "level": node.level,
        "activity_type": "virtual" if node.level in (1, 2) else "executable",
        "activity_category": node.activity_category,
        "solver_participation": node.level == 3,
    }


def _binding_summary(binding: ActivityStateBinding | dict[str, Any]) -> dict[str, Any]:
    if isinstance(binding, dict):
        return {
            "id": binding["id"],
            "activity_node_id": binding.get("activity_node_id"),
            "atomic_activity_id": binding.get("atomic_activity_id"),
            "op_rule_id": binding.get("op_rule_id"),
            "state_node_id": binding["state_node_id"],
            "binding_role": binding["binding_role"],
            "binding_type": binding["binding_type"],
            "coverage_status": binding["coverage_status"],
            "covered_leaf_state_ids": binding.get("covered_leaf_state_ids", []),
        }
    return {
        "id": binding.id,
        "activity_node_id": binding.activity_node_id,
        "atomic_activity_id": binding.atomic_activity_id,
        "op_rule_id": binding.op_rule_id,
        "state_node_id": binding.state_node_id,
        "binding_role": binding.binding_role,
        "binding_type": binding.binding_type,
        "coverage_status": binding.coverage_status,
        "covered_leaf_state_ids": binding.covered_leaf_state_ids or [],
    }


def _unique_dicts(items: list[dict[str, Any]], key: str = "id") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in items:
        marker = item.get(key)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


async def _load_context(session: AsyncSession, machine_type_id: int) -> NetworkEditorContext:
    state_result = await session.execute(
        select(StateNode)
        .where(StateNode.machine_type_id == machine_type_id)
        .order_by(StateNode.level, StateNode.sort_order, StateNode.id)
    )
    state_nodes = list(state_result.scalars().all())

    ref_result = await session.execute(
        select(StateNodeReference)
        .join(StateNodeReference.state_node)
        .where(StateNode.machine_type_id == machine_type_id)
        .options(
            selectinload(StateNodeReference.state_node),
            selectinload(StateNodeReference.parent_state_node),
        )
        .order_by(StateNodeReference.parent_state_node_id, StateNodeReference.sort_order, StateNodeReference.id)
    )
    state_refs = list(ref_result.scalars().all())

    activity_result = await session.execute(
        select(ActivityNode)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .order_by(ActivityNode.level, ActivityNode.sort_order, ActivityNode.id)
    )
    activity_nodes = list(activity_result.scalars().all())

    atomic_result = await session.execute(
        select(AtomicActivity)
        .where(AtomicActivity.machine_type_id == machine_type_id)
        .order_by(AtomicActivity.sort_order, AtomicActivity.id)
    )
    atomic_activities = list(atomic_result.scalars().all())

    package_ref_result = await session.execute(
        select(ActivityPackageAtomicRef)
        .join(ActivityNode, ActivityPackageAtomicRef.activity_node_id == ActivityNode.id)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .options(
            selectinload(ActivityPackageAtomicRef.activity_node),
            selectinload(ActivityPackageAtomicRef.atomic_activity),
        )
        .order_by(ActivityPackageAtomicRef.activity_node_id, ActivityPackageAtomicRef.sort_order, ActivityPackageAtomicRef.id)
    )
    package_refs = list(package_ref_result.scalars().all())

    binding_result = await session.execute(
        select(ActivityStateBinding)
        .where(ActivityStateBinding.machine_type_id == machine_type_id)
        .options(
            selectinload(ActivityStateBinding.activity_node),
            selectinload(ActivityStateBinding.atomic_activity),
            selectinload(ActivityStateBinding.op_rule),
            selectinload(ActivityStateBinding.state_node),
        )
        .order_by(ActivityStateBinding.id)
    )
    bindings = list(binding_result.scalars().all())

    rule_result = await session.execute(
        select(OpRule)
        .where(OpRule.machine_type_id == machine_type_id)
        .options(
            selectinload(OpRule.preconditions),
            selectinload(OpRule.effects),
            selectinload(OpRule.resource_reqs),
        )
        .order_by(OpRule.id)
    )
    op_rules = list(rule_result.scalars().all())

    return NetworkEditorContext(
        machine_type_id=machine_type_id,
        state_nodes=state_nodes,
        state_refs=state_refs,
        activity_nodes=activity_nodes,
        atomic_activities=atomic_activities,
        package_refs=package_refs,
        bindings=bindings,
        op_rules=op_rules,
    )


def _binding_activity_graph_id(binding: ActivityStateBinding) -> str:
    if binding.atomic_activity_id is not None:
        return _atomic_graph_id(binding.atomic_activity_id)
    if binding.activity_node_id is not None:
        return _activity_graph_id(binding.activity_node_id)
    raise ValueError("Binding has no activity identity")


def _project_binding_edge(binding: ActivityStateBinding, status: str) -> dict[str, Any]:
    state_id = _state_graph_id(binding.state_node_id)
    activity_id = _binding_activity_graph_id(binding)
    if binding.binding_role in INPUT_ROLES:
        source_id = state_id
        target_id = activity_id
        edge_type = "STATE_TO_ACTIVITY"
    else:
        source_id = activity_id
        target_id = state_id
        edge_type = "ACTIVITY_TO_STATE"

    return {
        "id": f"binding:{binding.id}:{edge_type}",
        "source_id": source_id,
        "target_id": target_id,
        "type": edge_type,
        "binding_id": binding.id,
        "binding_role": binding.binding_role,
        "source_kind": "activity_state_binding",
        "coverage_status": status,
    }


def _project_legacy_rule_edges(
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for rule in context.op_rules:
        if not _rule_activity_is_visible(rule, context, include_inactive=include_inactive):
            continue
        activity_id = _activity_id_for_rule(rule)
        if activity_id is None:
            continue
        for precond in rule.preconditions:
            for state_id in _legacy_precondition_state_ids(
                precond,
                context.state_nodes,
                include_inactive=include_inactive,
            ):
                edges.append({
                    "id": f"op_rule:{rule.id}:precondition:{precond.id}:state:{state_id}",
                    "source_id": _state_graph_id(state_id),
                    "target_id": activity_id,
                    "type": "STATE_TO_ACTIVITY",
                    "binding_id": None,
                    "binding_role": "input",
                    "source_kind": "op_rule_precond",
                    "coverage_status": "complete",
                })
        for effect in rule.effects:
            for state_id in _legacy_effect_state_ids(
                effect,
                context.state_nodes,
                include_inactive=include_inactive,
            ):
                edges.append({
                    "id": f"op_rule:{rule.id}:effect:{effect.id}:state:{state_id}",
                    "source_id": activity_id,
                    "target_id": _state_graph_id(state_id),
                    "type": "ACTIVITY_TO_STATE",
                    "binding_id": None,
                    "binding_role": "output",
                    "source_kind": "op_rule_effect",
                    "coverage_status": "complete",
                })
    return edges


def _solver_ready_leaf_edge(
    *,
    binding: ActivityStateBinding,
    leaf_state_id: int,
    activity_id: str,
    role: str,
    source_kind: str,
    coverage_status: str,
) -> dict[str, Any]:
    state_id = _state_graph_id(leaf_state_id)
    if role in INPUT_ROLES:
        source_id = state_id
        target_id = activity_id
        edge_type = "STATE_TO_ACTIVITY"
    else:
        source_id = activity_id
        target_id = state_id
        edge_type = "ACTIVITY_TO_STATE"

    return {
        "id": f"{source_kind}:{binding.id}:{role}:leaf:{leaf_state_id}:{activity_id}",
        "source_id": source_id,
        "target_id": target_id,
        "type": edge_type,
        "binding_id": binding.id,
        "binding_role": role,
        "source_kind": source_kind,
        "coverage_status": coverage_status,
        "expanded_from_state_node_id": binding.state_node_id,
        "leaf_state_node_id": leaf_state_id,
        "is_inherited": source_kind == "inherited_context_binding",
    }


def _dedupe_solver_ready_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge["source_id"], edge["target_id"], edge["type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped


def _project_solver_ready_edges(
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
    legacy_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    state_by_id = context.state_by_id
    state_children = _state_display_children_by_parent(
        context.state_nodes,
        context.state_refs,
        include_inactive=include_inactive,
    )
    edges: list[dict[str, Any]] = []

    active_bindings = [
        binding for binding in context.bindings
        if include_inactive or binding.is_active
    ]
    for binding in active_bindings:
        if binding.atomic_activity_id is None or binding.binding_role not in {"input", "output"}:
            continue
        activity_id = _atomic_graph_id(binding.atomic_activity_id)
        coverage_status = _coverage_status(binding, state_by_id, state_children)
        for leaf_id in binding.covered_leaf_state_ids or []:
            leaf = state_by_id.get(int(leaf_id))
            if leaf is None or (not include_inactive and not leaf.is_active):
                continue
            edges.append(
                _solver_ready_leaf_edge(
                    binding=binding,
                    leaf_state_id=leaf.id,
                    activity_id=activity_id,
                    role=binding.binding_role,
                    source_kind="activity_state_binding_leaf",
                    coverage_status=coverage_status,
                )
            )

    edges.extend(legacy_edges)
    return _dedupe_solver_ready_edges(edges)


def _activity_package_refs_by_atomic(context: NetworkEditorContext) -> dict[int, list[ActivityPackageAtomicRef]]:
    refs: dict[int, list[ActivityPackageAtomicRef]] = defaultdict(list)
    for ref in context.package_refs:
        refs[ref.atomic_activity_id].append(ref)
    return refs


def _activity_descendant_ids(
    activity_node_id: int,
    activity_children: dict[int | None, list[ActivityNode]],
) -> set[int]:
    ids: set[int] = set()
    stack = [activity_node_id]
    while stack:
        current = stack.pop(0)
        if current in ids:
            continue
        ids.add(current)
        stack.extend(child.id for child in activity_children.get(current, []))
    return ids


def _atomic_ids_under_activity(
    activity_node_id: int,
    activity_children: dict[int | None, list[ActivityNode]],
    package_refs: list[ActivityPackageAtomicRef],
    *,
    include_inactive: bool,
) -> set[int]:
    activity_ids = _activity_descendant_ids(activity_node_id, activity_children)
    return {
        ref.atomic_activity_id
        for ref in package_refs
        if ref.activity_node_id in activity_ids
        and (include_inactive or ref.is_active)
    }


def _filter_graph(
    graph: dict[str, Any],
    *,
    selected_state_ids: set[int],
    selected_state_root_ids: list[int],
    selected_activity_ids: set[int],
    selected_atomic_ids: set[int],
    view_mode: str,
) -> dict[str, Any]:
    state_node_ids = {_state_graph_id(item_id) for item_id in selected_state_ids}
    activity_node_ids = {_activity_graph_id(item_id) for item_id in selected_activity_ids}
    atomic_node_ids = {_atomic_graph_id(item_id) for item_id in selected_atomic_ids}
    allowed_activity_ids = activity_node_ids | atomic_node_ids
    if view_mode == "solver_ready":
        allowed_activity_ids = atomic_node_ids | {
            node_id for node_id in activity_node_ids
            if any(item["id"] == node_id and item["activity_type"] == "executable" for item in graph["activity_nodes"])
        }
    selected_state_roots = set(selected_state_root_ids or [])

    reference_state_ids_in_selected_roots = {
        node["state_node_id"] for node in graph["state_nodes"]
        if view_mode != "solver_ready"
        and selected_state_roots
        and node.get("reference_id")
        and any(root_id in (node.get("path_ids") or []) for root_id in selected_state_roots)
    }
    graph["state_nodes"] = [
        node for node in graph["state_nodes"]
        if node["state_node_id"] in selected_state_ids
        and (
            (view_mode == "solver_ready" and not node.get("reference_id"))
            or (
                view_mode != "solver_ready"
                and (
                    not selected_state_roots
                    or any(root_id in (node.get("path_ids") or []) for root_id in selected_state_roots)
                    or (not node.get("reference_id") and node["state_node_id"] not in reference_state_ids_in_selected_roots)
                )
            )
        )
    ]
    preferred_state_graph_ids: dict[int, str] = {}
    if view_mode != "solver_ready" and selected_state_roots:
        reference_candidates = [
            node for node in graph["state_nodes"]
            if node.get("reference_id")
            and any(root_id in (node.get("path_ids") or []) for root_id in selected_state_roots)
        ]
        reference_candidates.sort(key=lambda item: (len(item.get("path_ids") or []), item.get("reference_id") or 0))
        for node in reference_candidates:
            preferred_state_graph_ids.setdefault(node["state_node_id"], node["id"])

    visible_state_graph_ids = {node["id"] for node in graph["state_nodes"]}
    allowed_ids = visible_state_graph_ids | allowed_activity_ids
    graph["activity_nodes"] = [node for node in graph["activity_nodes"] if node["id"] in allowed_activity_ids]
    if preferred_state_graph_ids:
        remapped_edges = []
        for edge in graph["edges"]:
            next_edge = dict(edge)
            for field in ("source_id", "target_id"):
                state_node_id = _state_node_id_from_graph_id(next_edge[field])
                if state_node_id is not None and state_node_id in preferred_state_graph_ids:
                    canonical_field = f"canonical_{field}"
                    next_edge[canonical_field] = next_edge.get(canonical_field, next_edge[field])
                    next_edge[field] = preferred_state_graph_ids[state_node_id]
            remapped_edges.append(next_edge)
        graph["edges"] = remapped_edges
    graph["edges"] = [
        edge for edge in graph["edges"]
        if edge["source_id"] in allowed_ids and edge["target_id"] in allowed_ids
    ]
    if view_mode == "solver_ready":
        incident_state_ids = {
            node_id
            for edge in graph["edges"]
            for node_id in (edge["source_id"], edge["target_id"])
            if node_id.startswith("state_node:")
        }
        incident_state_node_ids = {
            state_node_id for state_node_id in (_state_node_id_from_graph_id(node_id) for node_id in incident_state_ids)
            if state_node_id is not None
        }
        graph["state_nodes"] = [node for node in graph["state_nodes"] if node["state_node_id"] in incident_state_node_ids]
    graph["bindings"] = [
        item for item in graph["bindings"]
        if item["state_node_id"] in selected_state_ids
        and (
            (item.get("activity_node_id") and _activity_graph_id(item["activity_node_id"]) in allowed_activity_ids)
            or (item.get("atomic_activity_id") and _atomic_graph_id(item["atomic_activity_id"]) in allowed_activity_ids)
        )
    ]
    return graph


def _longest_dependency_chain_depth(edges: list[dict[str, Any]]) -> int:
    adjacency: dict[str, set[str]] = defaultdict(set)
    node_ids: set[str] = set()
    for edge in edges:
        source_id = edge["source_id"]
        target_id = edge["target_id"]
        adjacency[source_id].add(target_id)
        node_ids.add(source_id)
        node_ids.add(target_id)

    def walk(node_id: str, path: set[str]) -> int:
        longest = 0
        for target_id in adjacency.get(node_id, set()):
            if target_id in path:
                continue
            longest = max(longest, 1 + walk(target_id, path | {target_id}))
        return longest

    return max((walk(node_id, {node_id}) for node_id in node_ids), default=0)


def _find_dependency_cycle(edges: list[dict[str, Any]]) -> list[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    node_ids: set[str] = set()
    for edge in edges:
        source_id = edge["source_id"]
        target_id = edge["target_id"]
        adjacency[source_id].append(target_id)
        node_ids.add(source_id)
        node_ids.add(target_id)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        if node_id in visiting:
            start = stack.index(node_id)
            return stack[start:] + [node_id]
        if node_id in visited:
            return None
        visiting.add(node_id)
        stack.append(node_id)
        for target_id in adjacency.get(node_id, []):
            cycle = visit(target_id)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return None

    for node_id in sorted(node_ids):
        cycle = visit(node_id)
        if cycle:
            return cycle
    return []


def _find_int_cycle(adjacency: dict[int, list[int]], node_ids: set[int]) -> list[int]:
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def visit(node_id: int) -> list[int] | None:
        if node_id in visiting:
            start = stack.index(node_id)
            return stack[start:] + [node_id]
        if node_id in visited:
            return None
        visiting.add(node_id)
        stack.append(node_id)
        for target_id in adjacency.get(node_id, []):
            if target_id not in node_ids:
                continue
            cycle = visit(target_id)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return None

    for node_id in sorted(node_ids):
        cycle = visit(node_id)
        if cycle:
            return cycle
    return []


def _find_int_path(
    adjacency: dict[int, list[int]],
    start_id: int,
    target_id: int,
    node_ids: set[int],
) -> list[int]:
    stack: list[tuple[int, list[int]]] = [(start_id, [start_id])]
    seen: set[int] = set()
    while stack:
        current_id, path = stack.pop()
        if current_id == target_id:
            return path
        if current_id in seen:
            continue
        seen.add(current_id)
        for next_id in adjacency.get(current_id, []):
            if next_id not in node_ids or next_id in path:
                continue
            stack.append((next_id, path + [next_id]))
    return []


def _build_graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    state_nodes = graph["state_nodes"]
    activity_nodes = graph["activity_nodes"]
    bindings = graph["bindings"]
    edges = graph["edges"]

    state_by_id = {node["state_node_id"]: node for node in state_nodes}
    state_graph_ids = {node["id"] for node in state_nodes}
    unique_state_nodes = {
        node["state_node_id"]: node for node in state_nodes
    }
    activity_by_graph_id = {node["id"]: node for node in activity_nodes}
    incident_state_node_ids: set[int] = set()
    incident_activity_ids: set[str] = set()
    for edge in edges:
        if edge["source_id"] in state_graph_ids:
            state_node_id = _state_node_id_from_graph_id(edge["source_id"])
            if state_node_id is not None:
                incident_state_node_ids.add(state_node_id)
        if edge["target_id"] in state_graph_ids:
            state_node_id = _state_node_id_from_graph_id(edge["target_id"])
            if state_node_id is not None:
                incident_state_node_ids.add(state_node_id)
        if edge["source_id"] in activity_by_graph_id:
            incident_activity_ids.add(edge["source_id"])
        if edge["target_id"] in activity_by_graph_id:
            incident_activity_ids.add(edge["target_id"])

    cross_level_binding_count = 0
    for binding in bindings:
        state = state_by_id.get(binding["state_node_id"])
        activity_graph_id = (
            _atomic_graph_id(binding["atomic_activity_id"])
            if binding.get("atomic_activity_id") else _activity_graph_id(binding["activity_node_id"])
        )
        activity = activity_by_graph_id.get(activity_graph_id)
        if state and activity and state["level"] != activity["level"]:
            cross_level_binding_count += 1

    stale_binding_count = sum(1 for item in bindings if item["coverage_status"] == "stale")
    partial_binding_count = sum(1 for item in bindings if item["coverage_status"] == "partial")
    virtual_activity_count = sum(1 for item in activity_nodes if item["activity_type"] == "virtual")
    executable_activity_count = sum(1 for item in activity_nodes if item["activity_type"] == "executable")
    return {
        "state_node_count": len(unique_state_nodes),
        "state_instance_count": len(state_nodes),
        "state_reference_instance_count": sum(1 for item in state_nodes if item.get("reference_id")),
        "state_package_count": sum(1 for item in unique_state_nodes.values() if not item["is_leaf"]),
        "atomic_state_count": sum(1 for item in unique_state_nodes.values() if item["is_leaf"]),
        "activity_node_count": len(activity_nodes),
        "virtual_activity_count": virtual_activity_count,
        "executable_activity_count": executable_activity_count,
        "binding_count": len(bindings),
        "edge_count": len(edges),
        "state_package_binding_count": sum(1 for item in bindings if item["binding_type"] == "state_package"),
        "atomic_state_binding_count": sum(1 for item in bindings if item["binding_type"] == "atomic_state"),
        "context_input_binding_count": sum(1 for item in bindings if item["binding_role"] == "context_input"),
        "declared_output_binding_count": sum(1 for item in bindings if item["binding_role"] == "declared_output"),
        "stale_binding_count": stale_binding_count,
        "partial_binding_count": partial_binding_count,
        "coverage_gap_count": stale_binding_count + partial_binding_count,
        "cross_level_binding_count": cross_level_binding_count,
        "orphan_state_count": sum(
            1 for item in unique_state_nodes.values()
            if item["is_active"] and item["state_node_id"] not in incident_state_node_ids
        ),
        "orphan_activity_count": sum(
            1 for item in activity_nodes if item["is_active"] and item["id"] not in incident_activity_ids
        ),
        "max_state_depth": max((item["level"] for item in state_nodes), default=0),
        "max_activity_depth": max((item["level"] for item in activity_nodes), default=0),
        "longest_dependency_chain_depth": _longest_dependency_chain_depth(edges),
    }


def _add_issue_counts_to_summary(
    graph: dict[str, Any],
    modeling_issues: list[dict[str, Any]],
    solver_ready_issues: list[dict[str, Any]],
) -> None:
    graph.setdefault("summary", {}).update({
        "modeling_issue_count": len(modeling_issues),
        "solver_ready_issue_count": len(solver_ready_issues),
        "blocking_issue_count": sum(1 for issue in solver_ready_issues if issue["severity"] == "error"),
        "partial_virtual_activity_count": 0,
    })


def _build_graph_from_context(context: NetworkEditorContext, payload: NetworkEditorRequest) -> dict[str, Any]:
    state_by_id = context.state_by_id
    activity_by_id = context.activity_by_id
    atomic_refs_by_atomic = _activity_package_refs_by_atomic(context)
    state_display_children = _state_display_children_by_parent(
        context.state_nodes,
        context.state_refs,
        include_inactive=payload.include_inactive,
    )
    activity_children = _children_by_parent(context.activity_nodes)
    selected_state_depths = _selected_descendant_depths(
        payload.state_root_ids,
        state_display_children,
        {node.id for node in context.state_nodes},
        max_depth=payload.state_depth,
    )
    selected_state_ids = set(selected_state_depths)
    selected_activity_depths = _selected_descendant_depths(
        payload.activity_scope_node_ids,
        activity_children,
        {node.id for node in context.activity_nodes},
        max_depth=payload.activity_depth,
    )
    selected_activity_ids = set(selected_activity_depths)

    state_ref_parent_ids: dict[int, list[int]] = defaultdict(list)
    state_ref_ids: dict[int, list[int]] = defaultdict(list)
    active_state_refs: list[StateNodeReference] = []
    for ref in context.state_refs:
        if payload.include_inactive or ref.is_active:
            state_ref_parent_ids[ref.state_node_id].append(ref.parent_state_node_id)
            state_ref_ids[ref.state_node_id].append(ref.id)
            active_state_refs.append(ref)

    state_nodes = []
    for node in context.state_nodes:
        if not payload.include_inactive and not node.is_active:
            continue
        leaf_ids = _state_leaf_ids_under(
            node.id,
            state_by_id,
            state_display_children,
            include_inactive=payload.include_inactive,
        )
        state_nodes.append({
            "id": _state_graph_id(node.id),
            "state_node_id": node.id,
            "parent_id": node.parent_id,
            "primary_parent_graph_id": _state_graph_id(node.parent_id) if node.parent_id else None,
            "reference_parent_ids": state_ref_parent_ids.get(node.id, []),
            "reference_ids": state_ref_ids.get(node.id, []),
            "child_ids": [child.id for child in state_display_children.get(node.id, [])],
            "level": node.level,
            "code": node.code,
            "name": node.name,
            "state_kind": node.state_kind,
            "feature_key": node.feature_key,
            "operator": node.operator,
            "target_value": node.target_value,
            "is_active": node.is_active,
            "is_leaf": bool(node.feature_key and node.target_value),
            "leaf_state_ids": leaf_ids,
            "leaf_count": len(leaf_ids),
            "path_ids": _state_path(node, state_by_id),
            "metadata_json": node.metadata_json,
            "reference_id": None,
            "is_reference_instance": False,
        })

    for ref in active_state_refs:
        node = state_by_id.get(ref.state_node_id)
        parent = state_by_id.get(ref.parent_state_node_id)
        if node is None or parent is None:
            continue
        if not payload.include_inactive and (not node.is_active or not parent.is_active):
            continue
        leaf_ids = _state_leaf_ids_under(
            node.id,
            state_by_id,
            state_display_children,
            include_inactive=payload.include_inactive,
        )
        state_nodes.append({
            "id": _state_reference_graph_id(node.id, ref.id),
            "state_node_id": node.id,
            "parent_id": ref.parent_state_node_id,
            "primary_parent_graph_id": _state_graph_id(ref.parent_state_node_id),
            "reference_parent_ids": [ref.parent_state_node_id],
            "reference_ids": [ref.id],
            "child_ids": [child.id for child in state_display_children.get(node.id, [])],
            "level": node.level,
            "code": node.code,
            "name": node.name,
            "state_kind": node.state_kind,
            "feature_key": node.feature_key,
            "operator": node.operator,
            "target_value": node.target_value,
            "is_active": node.is_active and ref.is_active,
            "is_leaf": bool(node.feature_key and node.target_value),
            "leaf_state_ids": leaf_ids,
            "leaf_count": len(leaf_ids),
            "path_ids": [*_state_path(parent, state_by_id), node.id],
            "metadata_json": ref.metadata_json,
            "reference_id": ref.id,
            "is_reference_instance": True,
            "reference_parent_id": ref.parent_state_node_id,
        })

    activity_nodes = []
    for node in context.activity_nodes:
        if not payload.include_inactive and not node.is_active:
            continue
        activity_nodes.append({
            "id": _activity_graph_id(node.id),
            "activity_node_id": node.id,
            "atomic_activity_id": None,
            "parent_id": node.parent_id,
            "parent_graph_id": _activity_graph_id(node.parent_id) if node.parent_id else None,
            "child_activity_node_ids": [child.id for child in activity_children.get(node.id, [])],
            "level": node.level,
            "code": node.code,
            "name": node.name,
            "description": node.description,
            "activity_type": "virtual" if node.level in (1, 2) else "executable",
            "activity_category": node.activity_category,
            "solver_participation": node.level == 3,
            "is_active": node.is_active,
            "path_ids": _activity_path(node, activity_by_id),
            "metadata_json": node.metadata_json,
        })

    for activity in context.atomic_activities:
        if not payload.include_inactive and not activity.is_active:
            continue
        refs = [
            ref for ref in atomic_refs_by_atomic.get(activity.id, [])
            if payload.include_inactive or ref.is_active
        ]
        scoped_refs = [ref for ref in refs if ref.activity_node_id in selected_activity_ids]
        primary_ref = scoped_refs[0] if scoped_refs else (refs[0] if refs else None)
        metadata_json = (
            primary_ref.metadata_json
            if primary_ref is not None and primary_ref.metadata_json is not None
            else activity.metadata_json
        )
        activity_nodes.append({
            "id": _atomic_graph_id(activity.id),
            "activity_node_id": None,
            "atomic_activity_id": activity.id,
            "parent_id": None,
            "parent_graph_id": _activity_graph_id(primary_ref.activity_node_id) if primary_ref else None,
            "parent_activity_node_ids": [ref.activity_node_id for ref in refs],
            "package_ref_ids": [ref.id for ref in refs],
            "reference_id": primary_ref.id if primary_ref else None,
            "reference_ids": [ref.id for ref in refs],
            "level": 3,
            "code": activity.code,
            "name": activity.name,
            "description": activity.description,
            "activity_type": "executable",
            "activity_category": activity.activity_category,
            "solver_participation": True,
            "is_active": activity.is_active,
            "path_ids": [
                _activity_path(ref.activity_node, activity_by_id) for ref in refs if ref.activity_node
            ],
            "metadata_json": metadata_json,
            "atomic_metadata_json": activity.metadata_json,
        })

    bindings = []
    edges = []
    for binding in context.bindings:
        if not payload.include_inactive and not binding.is_active:
            continue
        status = _coverage_status(binding, state_by_id, state_display_children)
        bindings.append({
            "id": binding.id,
            "machine_type_id": binding.machine_type_id,
            "activity_node_id": binding.activity_node_id,
            "atomic_activity_id": binding.atomic_activity_id,
            "op_rule_id": binding.op_rule_id,
            "state_node_id": binding.state_node_id,
            "binding_role": binding.binding_role,
            "binding_type": binding.binding_type,
            "coverage_policy": binding.coverage_policy,
            "covered_leaf_state_ids": binding.covered_leaf_state_ids or [],
            "coverage_status": status,
            "is_inherited": binding.is_inherited,
            "is_active": binding.is_active,
            "metadata_json": binding.metadata_json,
        })
        edges.append(_project_binding_edge(binding, status))

    legacy_edges = _project_legacy_rule_edges(
        context,
        include_inactive=payload.include_inactive,
    )
    if payload.view_mode == "solver_ready":
        edges = _project_solver_ready_edges(
            context,
            include_inactive=payload.include_inactive,
            legacy_edges=legacy_edges,
        )
    else:
        edges.extend(legacy_edges)

    if not payload.activity_scope_node_ids and payload.activity_depth <= 0:
        selected_atomic_ids = {activity.id for activity in context.atomic_activities}
    elif payload.activity_depth <= 0:
        selected_atomic_ids = set()
        for activity_node_id in payload.activity_scope_node_ids:
            selected_atomic_ids.update(
                _atomic_ids_under_activity(
                    activity_node_id,
                    activity_children,
                    context.package_refs,
                    include_inactive=payload.include_inactive,
                )
            )
    else:
        selected_atomic_ids = set()
        for ref in context.package_refs:
            package_depth = selected_activity_depths.get(ref.activity_node_id)
            if package_depth is None:
                continue
            if package_depth + 1 > payload.activity_depth:
                continue
            if not payload.include_inactive and not ref.is_active:
                continue
            package_node = activity_by_id.get(ref.activity_node_id)
            package_is_top_level = package_node is not None and package_node.parent_id is None
            if package_depth == 1 and package_is_top_level and payload.activity_depth < 3:
                continue
            selected_atomic_ids.add(ref.atomic_activity_id)

    graph = {
        "machine_type_id": context.machine_type_id,
        "view_mode": payload.view_mode,
        "state_nodes": state_nodes,
        "activity_nodes": activity_nodes,
        "bindings": bindings,
        "edges": edges,
        "summary": {},
    }
    graph = _filter_graph(
        graph,
        selected_state_ids=selected_state_ids,
        selected_state_root_ids=payload.state_root_ids,
        selected_activity_ids=selected_activity_ids,
        selected_atomic_ids=selected_atomic_ids,
        view_mode=payload.view_mode,
    )
    graph["summary"] = _build_graph_summary(graph)
    return graph


def _make_issue(
    code: str,
    severity: str,
    category: str,
    message: str,
    *,
    related_state_ids: list[int] | None = None,
    related_activity_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
    suggested_action: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{category}:{code}:{len(str(details or {}))}:{','.join(map(str, related_state_ids or []))}:{','.join(related_activity_ids or [])}",
        "code": code,
        "severity": severity,
        "category": category,
        "message": message,
        "related_state_ids": related_state_ids or [],
        "related_activity_ids": related_activity_ids or [],
        "details": details,
        "suggested_action": suggested_action,
    }


def _health_diagnostic_details(diagnostic: dict[str, Any]) -> dict[str, Any] | None:
    keys = (
        "feature_key",
        "operator",
        "target_value",
        "op_rule_id",
        "activity_node_id",
        "source_type",
        "provider_count",
        "node_id",
        "node_type",
    )
    details = {
        key: diagnostic[key]
        for key in keys
        if diagnostic.get(key) is not None
    }
    if diagnostic.get("details"):
        details.update(diagnostic["details"])
    return details or None


def _health_diagnostic_state_ids(diagnostic: dict[str, Any]) -> list[int]:
    state_node_id = diagnostic.get("state_node_id")
    if state_node_id is not None:
        return [int(state_node_id)]
    if diagnostic.get("node_type") == "state_node" and diagnostic.get("node_id") is not None:
        return [int(diagnostic["node_id"])]
    return []


def _health_diagnostic_activity_ids(
    diagnostic: dict[str, Any],
    context: NetworkEditorContext,
) -> list[str]:
    op_rule_id = diagnostic.get("op_rule_id")
    if op_rule_id is not None:
        rule = next((item for item in context.op_rules if item.id == op_rule_id), None)
        if rule is not None:
            if rule.atomic_activity_id is not None:
                return [_atomic_graph_id(rule.atomic_activity_id)]
            if rule.activity_node_id is not None:
                return [_activity_graph_id(rule.activity_node_id)]

    activity_node_id = diagnostic.get("activity_node_id")
    if activity_node_id is not None:
        activity_node_id = int(activity_node_id)
        if activity_node_id < 0:
            return [_atomic_graph_id(abs(activity_node_id))]
        return [_activity_graph_id(activity_node_id)]

    node_id = diagnostic.get("node_id")
    node_type = diagnostic.get("node_type")
    if node_id is not None and node_type == "atomic_activity":
        return [_atomic_graph_id(int(node_id))]
    if node_id is not None and node_type == "activity_node":
        return [_activity_graph_id(int(node_id))]
    return []


def _health_diagnostics_to_issues(
    diagnostics: list[dict[str, Any]],
    context: NetworkEditorContext,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        severity = diagnostic.get("severity", "warning")
        issues.append(
            _make_issue(
                diagnostic["code"],
                "error" if diagnostic["code"] in BLOCKING_HEALTH_CODES else severity,
                "layered_health",
                diagnostic["message"],
                related_state_ids=_health_diagnostic_state_ids(diagnostic),
                related_activity_ids=_health_diagnostic_activity_ids(diagnostic, context),
                details=_health_diagnostic_details(diagnostic),
                suggested_action="Fix the missing provider chain or narrow the export target/scope.",
            )
        )
    return issues


def _edge_activity_id(edge: dict[str, Any]) -> str | None:
    if edge["type"] == "STATE_TO_ACTIVITY":
        return edge["target_id"]
    if edge["type"] == "ACTIVITY_TO_STATE":
        return edge["source_id"]
    return None


def _activity_descendant_graph_ids(
    activity_node_id: int,
    activity_children: dict[int | None, list[ActivityNode]],
    package_refs: list[ActivityPackageAtomicRef],
    *,
    include_inactive: bool,
) -> set[str]:
    activity_ids = _activity_descendant_ids(activity_node_id, activity_children)
    result = {_activity_graph_id(item_id) for item_id in activity_ids}
    for ref in package_refs:
        if ref.activity_node_id in activity_ids and (include_inactive or ref.is_active):
            result.add(_atomic_graph_id(ref.atomic_activity_id))
    return result


def _validate_projected_graph(
    context: NetworkEditorContext,
    graph: dict[str, Any],
    *,
    include_inactive: bool,
    target_state_node_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    modeling_issues: list[dict[str, Any]] = []
    solver_ready_issues: list[dict[str, Any]] = []
    state_by_id = {node["state_node_id"]: node for node in graph["state_nodes"]}
    activity_by_graph_id = {node["id"]: node for node in graph["activity_nodes"]}
    activity_children = _children_by_parent(context.activity_nodes)
    goal_state_ids: set[int] = set()
    for state_id in target_state_node_ids or []:
        goal_state_ids.add(state_id)
        if state_id in state_by_id:
            goal_state_ids.update(int(item) for item in state_by_id[state_id].get("leaf_state_ids", []))

    connected_state_ids: set[int] = set()
    input_state_graph_ids: set[str] = set()
    input_activity_ids: set[str] = set()
    output_activity_ids: set[str] = set()
    output_activity_ids_by_state: dict[str, set[str]] = defaultdict(set)
    output_providers_by_state: dict[str, set[str]] = defaultdict(set)
    active_rule_ids_by_activity: dict[str, set[int]] = defaultdict(set)
    explicit_rule_ids_by_activity: dict[str, set[int]] = defaultdict(set)
    for rule in context.op_rules:
        if not rule.is_active:
            continue
        if rule.atomic_activity_id is not None:
            active_rule_ids_by_activity[_atomic_graph_id(rule.atomic_activity_id)].add(rule.id)
        elif rule.activity_node_id is not None:
            active_rule_ids_by_activity[_activity_graph_id(rule.activity_node_id)].add(rule.id)
    for binding in graph["bindings"]:
        if not binding.get("op_rule_id"):
            continue
        activity_id = (
            _atomic_graph_id(binding["atomic_activity_id"])
            if binding.get("atomic_activity_id") is not None else _activity_graph_id(binding["activity_node_id"])
        )
        explicit_rule_ids_by_activity[activity_id].add(int(binding["op_rule_id"]))
    for edge in graph["edges"]:
        if edge["type"] == "STATE_TO_ACTIVITY":
            source_state_id = _state_node_id_from_graph_id(edge.get("canonical_source_id") or edge["source_id"])
            if source_state_id is not None:
                connected_state_ids.add(source_state_id)
            input_state_graph_ids.add(edge.get("canonical_source_id") or edge["source_id"])
            input_activity_ids.add(edge["target_id"])
        elif edge["type"] == "ACTIVITY_TO_STATE":
            target_state_id = _state_node_id_from_graph_id(edge.get("canonical_target_id") or edge["target_id"])
            if target_state_id is not None:
                connected_state_ids.add(target_state_id)
            output_activity_ids.add(edge["source_id"])
            output_state_graph_id = edge.get("canonical_target_id") or edge["target_id"]
            output_activity_ids_by_state[output_state_graph_id].add(edge["source_id"])
            if edge.get("binding_role") == "output":
                output_providers_by_state[output_state_graph_id].add(edge["source_id"])

    dependency_cycle = _find_dependency_cycle(graph["edges"])
    if dependency_cycle:
        related_state_ids = [
            state_id for state_id in (_state_node_id_from_graph_id(node_id) for node_id in dependency_cycle)
            if state_id is not None
        ]
        related_activity_ids = [
            node_id for node_id in dependency_cycle
            if node_id.startswith("activity_node:") or node_id.startswith("atomic_activity:")
        ]
        solver_ready_issues.append(
            _make_issue(
                "GRAPH_DEPENDENCY_CYCLE",
                "error",
                "solver_ready",
                "State-activity dependency cycle detected",
                related_state_ids=related_state_ids,
                related_activity_ids=related_activity_ids,
                details={"cycle_node_ids": dependency_cycle},
                suggested_action="Break the loop by removing or redirecting one input/output binding.",
            )
        )

    visible_state_ids = {node["state_node_id"] for node in graph["state_nodes"]}
    primary_state_adjacency: dict[int, list[int]] = defaultdict(list)
    reference_state_adjacency: dict[int, list[int]] = defaultdict(list)
    reference_edges: set[tuple[int, int]] = set()
    for node in graph["state_nodes"]:
        state_id = node["state_node_id"]
        parent_id = node.get("parent_id")
        if parent_id in visible_state_ids:
            primary_state_adjacency[parent_id].append(state_id)
            reference_state_adjacency[parent_id].append(state_id)
        for reference_parent_id in node.get("reference_parent_ids") or []:
            if reference_parent_id in visible_state_ids:
                reference_state_adjacency[reference_parent_id].append(state_id)
                reference_edges.add((reference_parent_id, state_id))

    state_cycle = _find_int_cycle(primary_state_adjacency, visible_state_ids)
    if state_cycle:
        issue = _make_issue(
            "STATE_AGGREGATION_CYCLE",
            "error",
            "hierarchy",
            "State aggregation hierarchy contains a cycle",
            related_state_ids=state_cycle,
            details={"cycle_state_node_ids": state_cycle},
            suggested_action="Remove or redirect one primary parent relation in the cycle.",
        )
        modeling_issues.append(issue)
        solver_ready_issues.append(issue)

    reference_cycle: list[int] = []
    for reference_parent_id, state_id in sorted(reference_edges):
        return_path = _find_int_path(
            reference_state_adjacency,
            state_id,
            reference_parent_id,
            visible_state_ids,
        )
        if return_path:
            reference_cycle = [reference_parent_id, *return_path]
            break
    if reference_cycle:
        issue = _make_issue(
            "STATE_REFERENCE_CYCLE",
            "error",
            "hierarchy",
            "State primary/reference parent graph contains a cycle",
            related_state_ids=reference_cycle,
            details={"cycle_state_node_ids": reference_cycle},
            suggested_action="Remove one reference parent that points back into its own descendant graph.",
        )
        modeling_issues.append(issue)
        solver_ready_issues.append(issue)

    visible_activity_ids = {
        node["activity_node_id"]
        for node in graph["activity_nodes"]
        if node.get("activity_node_id") is not None
    }
    activity_adjacency: dict[int, list[int]] = defaultdict(list)
    for node in graph["activity_nodes"]:
        activity_node_id = node.get("activity_node_id")
        parent_id = node.get("parent_id")
        if activity_node_id is not None and parent_id in visible_activity_ids:
            activity_adjacency[parent_id].append(activity_node_id)
    activity_cycle = _find_int_cycle(activity_adjacency, visible_activity_ids)
    if activity_cycle:
        issue = _make_issue(
            "ACTIVITY_CONTAINER_CYCLE",
            "error",
            "hierarchy",
            "Activity container hierarchy contains a cycle",
            related_activity_ids=[_activity_graph_id(activity_id) for activity_id in activity_cycle],
            details={"cycle_activity_node_ids": activity_cycle},
            suggested_action="Remove or redirect one activity parent relation in the cycle.",
        )
        modeling_issues.append(issue)
        solver_ready_issues.append(issue)

    state_name_groups: dict[tuple[int | None, str], list[dict[str, Any]]] = defaultdict(list)
    for node in graph["state_nodes"]:
        name_key = str(node.get("name") or "").strip().lower()
        if not name_key:
            continue
        display_parent_ids = [node.get("parent_id"), *node.get("reference_parent_ids", [])]
        for parent_id in display_parent_ids:
            state_name_groups[(parent_id, name_key)].append(node)

    for (parent_id, _), nodes in state_name_groups.items():
        unique_nodes = {node["state_node_id"]: node for node in nodes}
        if len(unique_nodes) <= 1:
            continue
        related_state_ids = sorted(unique_nodes)
        modeling_issues.append(
            _make_issue(
                "DUPLICATE_STATE_NAME",
                "warning",
                "naming",
                "Multiple visible state nodes share the same name under one parent scope",
                related_state_ids=related_state_ids,
                details={"parent_state_node_id": parent_id, "state_node_ids": related_state_ids},
                suggested_action="Rename one state or move it to a clearer parent scope.",
            )
        )

    for node in graph["state_nodes"]:
        reference_parent_ids = node.get("reference_parent_ids") or []
        if reference_parent_ids:
            solver_ready_issues.append(
                _make_issue(
                    "MULTI_PARENT_STATE_NOTICE",
                    "warning",
                    "hierarchy",
                    "State is displayed under one or more reference parents",
                    related_state_ids=[node["state_node_id"]],
                    details={
                        "primary_parent_id": node.get("parent_id"),
                        "reference_parent_ids": reference_parent_ids,
                    },
                    suggested_action="Confirm this shared state is intentional before export.",
                )
            )

    for state_graph_id, provider_ids in output_providers_by_state.items():
        if len(provider_ids) <= 1:
            continue
        state_id = _state_node_id_from_graph_id(state_graph_id)
        if state_id is None:
            continue
        solver_ready_issues.append(
            _make_issue(
                "MULTIPLE_OUTPUT_PROVIDERS",
                "warning",
                "solver_ready",
                "Multiple executable activities output the same state",
                related_state_ids=[state_id],
                related_activity_ids=sorted(provider_ids),
                details={"state_node_id": state_id, "provider_activity_ids": sorted(provider_ids)},
                suggested_action="Confirm duplicate providers are intentional or split the output state.",
            )
        )

    for state_graph_id, provider_ids in output_activity_ids_by_state.items():
        if state_graph_id in input_state_graph_ids:
            continue
        state_id = _state_node_id_from_graph_id(state_graph_id)
        if state_id is None:
            continue
        if state_id in goal_state_ids:
            continue
        solver_ready_issues.append(
            _make_issue(
                "OUTPUT_STATE_UNUSED",
                "warning",
                "solver_ready",
                "Output state has no downstream activity in this graph",
                related_state_ids=[state_id],
                related_activity_ids=sorted(provider_ids),
                details={"state_node_id": state_id, "provider_activity_ids": sorted(provider_ids)},
                suggested_action="Confirm this is an intended terminal state or add downstream consumers.",
            )
        )

    cross_level_bindings: list[dict[str, Any]] = []
    for binding in graph["bindings"]:
        state = state_by_id.get(binding["state_node_id"])
        activity_graph_id = (
            _atomic_graph_id(binding["atomic_activity_id"])
            if binding.get("atomic_activity_id") else _activity_graph_id(binding["activity_node_id"])
        )
        activity = activity_by_graph_id.get(activity_graph_id)
        if state and activity and state["level"] != activity["level"]:
            cross_level_bindings.append({
                "binding_id": binding["id"],
                "state_node_id": binding["state_node_id"],
                "activity_graph_id": activity_graph_id,
                "state_level": state["level"],
                "activity_level": activity["level"],
            })
            modeling_issues.append(
                _make_issue(
                    "CROSS_LEVEL_BINDING_NOTICE",
                    "info",
                    "hierarchy",
                    "Activity binding crosses state/activity hierarchy levels",
                    related_state_ids=[binding["state_node_id"]],
                    related_activity_ids=[activity_graph_id],
                    details={
                        "binding_id": binding["id"],
                        "state_level": state["level"],
                        "activity_level": activity["level"],
                    },
                    suggested_action="Review whether this cross-level package binding is intentional.",
                )
            )
        if binding["coverage_status"] in {"partial", "stale"}:
            issue = _make_issue(
                "BINDING_COVERAGE_NOT_COMPLETE",
                "warning",
                "coverage",
                f"Binding {binding['id']} coverage is {binding['coverage_status']}",
                related_state_ids=[binding["state_node_id"]],
                related_activity_ids=[
                    _activity_graph_id(binding["activity_node_id"])
                    if binding.get("activity_node_id") else _atomic_graph_id(binding["atomic_activity_id"])
                ],
                details={"binding_id": binding["id"], "coverage_status": binding["coverage_status"]},
                suggested_action="Refresh or explicitly confirm the state package coverage.",
            )
            modeling_issues.append(issue)
            solver_ready_issues.append({**issue, "severity": "error"})
        covered_leaf_count = len(binding.get("covered_leaf_state_ids") or [])
        if binding["binding_type"] == "state_package" and covered_leaf_count > LARGE_COVERAGE_LEAF_THRESHOLD:
            solver_ready_issues.append(
                _make_issue(
                    "STATE_PACKAGE_COVERAGE_LARGE",
                    "warning",
                    "coverage",
                    "State package binding covers many leaf states",
                    related_state_ids=[binding["state_node_id"]],
                    related_activity_ids=[activity_graph_id],
                    details={
                        "binding_id": binding["id"],
                        "covered_leaf_count": covered_leaf_count,
                        "threshold": LARGE_COVERAGE_LEAF_THRESHOLD,
                    },
                    suggested_action="Confirm this broad package binding is intentional or split it into smaller packages.",
                )
            )

    if len(cross_level_bindings) > CROSS_LEVEL_BINDING_MANY_THRESHOLD:
        solver_ready_issues.append(
            _make_issue(
                "CROSS_LEVEL_BINDING_MANY",
                "warning",
                "hierarchy",
                "Many bindings cross state/activity hierarchy levels",
                related_state_ids=sorted({item["state_node_id"] for item in cross_level_bindings}),
                related_activity_ids=sorted({item["activity_graph_id"] for item in cross_level_bindings}),
                details={
                    "cross_level_binding_count": len(cross_level_bindings),
                    "threshold": CROSS_LEVEL_BINDING_MANY_THRESHOLD,
                    "bindings": cross_level_bindings,
                },
                suggested_action="Review whether these package-level shortcuts should be narrowed or documented.",
            )
        )

    for node in graph["state_nodes"]:
        if node["is_active"] and node["state_node_id"] not in connected_state_ids:
            modeling_issues.append(
                _make_issue(
                    "ORPHAN_STATE",
                    "info",
                    "orphan",
                    f"State {node['code']} is not connected to an activity in this graph",
                    related_state_ids=[node["state_node_id"]],
                )
            )

    for node in graph["activity_nodes"]:
        activity_id = node["id"]
        if not node["is_active"]:
            continue
        has_input = activity_id in input_activity_ids
        has_output = activity_id in output_activity_ids
        if not has_input and not has_output:
            modeling_issues.append(
                _make_issue(
                    "ORPHAN_ACTIVITY",
                    "info",
                    "orphan",
                    f"Activity {node['code']} is not connected to a state in this graph",
                    related_activity_ids=[activity_id],
                )
            )
        elif not has_input:
            modeling_issues.append(
                _make_issue(
                    "ACTIVITY_MISSING_INPUT",
                    "warning",
                    "modeling",
                    f"Activity {node['code']} has output bindings but no input state",
                    related_activity_ids=[activity_id],
                    suggested_action="Add an input/context state binding or confirm this is an initial activity.",
                )
            )
        elif not has_output:
            modeling_issues.append(
                _make_issue(
                    "ACTIVITY_MISSING_OUTPUT",
                    "warning",
                    "modeling",
                    f"Activity {node['code']} has input bindings but no output state",
                    related_activity_ids=[activity_id],
                    suggested_action="Add an output/declared output state binding.",
                )
            )
        if node["activity_type"] == "virtual" and node.get("activity_node_id"):
            descendant_graph_ids = _activity_descendant_graph_ids(
                node["activity_node_id"],
                activity_children,
                context.package_refs,
                include_inactive=include_inactive,
            )
            executable_descendants = [
                descendant_id for descendant_id in descendant_graph_ids
                if descendant_id != activity_id
                and activity_by_graph_id.get(descendant_id, {}).get("activity_type") == "executable"
            ]
            if not executable_descendants:
                modeling_issues.append(
                    _make_issue(
                        "VIRTUAL_ACTIVITY_NOT_DECOMPOSED",
                        "warning",
                        "implementation",
                        f"Virtual activity {node['code']} has no executable descendants in this graph",
                        related_activity_ids=[activity_id],
                        details={"activity_node_id": node["activity_node_id"]},
                        suggested_action="Add a child package with atomic activity refs before solver-ready export.",
                    )
                )
        if node["activity_type"] == "executable":
            if not node.get("solver_participation"):
                solver_ready_issues.append(
                    _make_issue(
                        "ACTIVITY_SOLVER_PARTICIPATION_MISMATCH",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} is not marked as participating in solver export",
                        related_activity_ids=[activity_id],
                        suggested_action="Repair activity type metadata so executable activities participate in export.",
                    )
                )
            if activity_id not in input_activity_ids:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_MISSING_INPUT",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} has no input state",
                        related_activity_ids=[activity_id],
                    )
                )
            if activity_id not in output_activity_ids:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_MISSING_OUTPUT",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} has no output state",
                        related_activity_ids=[activity_id],
                    )
                )
            active_rule_ids = active_rule_ids_by_activity.get(activity_id, set())
            explicit_rule_ids = explicit_rule_ids_by_activity.get(activity_id, set())
            invalid_explicit_rule_ids = sorted(explicit_rule_ids - active_rule_ids)
            if not active_rule_ids:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_MISSING_RULE",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} has no active op rule",
                        related_activity_ids=[activity_id],
                        suggested_action="Create or activate an op_rule for this executable activity before export.",
                    )
                )
            elif invalid_explicit_rule_ids:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_RULE_BINDING_INVALID",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} references inactive or unrelated op rules",
                        related_activity_ids=[activity_id],
                        details={"op_rule_ids": invalid_explicit_rule_ids},
                        suggested_action="Update bindings to reference an active op_rule for this executable activity.",
                    )
                )
            elif len(explicit_rule_ids) > 1:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_RULE_AMBIGUOUS",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} has bindings pointing at multiple op rules",
                        related_activity_ids=[activity_id],
                        details={"op_rule_ids": sorted(explicit_rule_ids)},
                        suggested_action="Use one explicit op_rule_id for all executable bindings on this activity.",
                    )
                )
            elif len(active_rule_ids) > 1 and not explicit_rule_ids:
                solver_ready_issues.append(
                    _make_issue(
                        "EXECUTABLE_RULE_NOT_EXPLICIT",
                        "error",
                        "solver_ready",
                        f"Executable activity {node['code']} has multiple active op rules and no explicit binding rule",
                        related_activity_ids=[activity_id],
                        details={"op_rule_ids": sorted(active_rule_ids)},
                        suggested_action="Select the exact op_rule_id on this executable activity's input/output bindings.",
                    )
                )
        elif node.get("solver_participation"):
            solver_ready_issues.append(
                _make_issue(
                    "ACTIVITY_SOLVER_PARTICIPATION_MISMATCH",
                    "error",
                    "solver_ready",
                    f"Virtual activity {node['code']} is incorrectly marked for solver export",
                    related_activity_ids=[activity_id],
                    suggested_action="Repair activity type metadata so virtual activities remain display-only.",
                )
            )

    return modeling_issues, solver_ready_issues


async def project_network_editor_graph(
    session: AsyncSession,
    machine_type_id: int,
    payload: NetworkEditorRequest,
) -> dict[str, Any]:
    context = await _load_context(session, machine_type_id)
    graph = _build_graph_from_context(context, payload)
    modeling_issues, solver_ready_issues = _validate_projected_graph(
        context,
        graph,
        include_inactive=payload.include_inactive,
        target_state_node_ids=payload.state_root_ids,
    )
    _add_issue_counts_to_summary(graph, modeling_issues, solver_ready_issues)
    graph["validation_summary"] = {
        "modeling_issue_count": len(modeling_issues),
        "solver_ready_issue_count": len(solver_ready_issues),
        "blocking_count": sum(1 for issue in solver_ready_issues if issue["severity"] == "error"),
    }
    graph["revision"] = _network_editor_revision(context)
    return graph


async def validate_network_editor_model(
    session: AsyncSession,
    machine_type_id: int,
    payload: NetworkEditorRequest,
) -> dict[str, Any]:
    context = await _load_context(session, machine_type_id)
    graph = _build_graph_from_context(context, payload)
    modeling_issues, solver_ready_issues = _validate_projected_graph(
        context,
        graph,
        include_inactive=payload.include_inactive,
        target_state_node_ids=payload.state_root_ids,
    )
    _add_issue_counts_to_summary(graph, modeling_issues, solver_ready_issues)

    if payload.state_root_ids or payload.activity_scope_node_ids:
        health = await check_layered_health(
            session,
            machine_type_id,
            LayeredExpansionRequest(
                target_state_node_ids=payload.state_root_ids,
                activity_scope_node_ids=payload.activity_scope_node_ids,
                include_inactive=payload.include_inactive,
            ),
        )
        solver_ready_issues.extend(_health_diagnostics_to_issues(health["diagnostics"], context))

    rule_modeling_issues, rule_solver_ready_issues = await validate_machine_type_scheduling_rules(
        machine_type_id,
        session,
    )
    modeling_issues.extend(rule_modeling_issues)
    solver_ready_issues.extend(rule_solver_ready_issues)

    blocking_count = sum(1 for issue in solver_ready_issues if issue["severity"] == "error")
    summary = {
        **graph["summary"],
        "modeling_issue_count": len(modeling_issues),
        "solver_ready_issue_count": len(solver_ready_issues),
        "blocking_count": blocking_count,
        "blocking_issue_count": blocking_count,
    }
    return {
        "machine_type_id": machine_type_id,
        "status": "blocked" if blocking_count else "warning" if modeling_issues or solver_ready_issues else "ok",
        "summary": summary,
        "modeling_issues": modeling_issues,
        "solver_ready_issues": solver_ready_issues,
    }


def _state_summaries_for_ids(
    state_ids: list[int] | set[int],
    state_by_id: dict[int, StateNode],
) -> list[dict[str, Any]]:
    return [
        _state_summary(state_by_id.get(state_id))
        for state_id in state_ids
        if state_by_id.get(state_id) is not None
    ]


def _state_summaries_for_graph_ids(
    state_graph_ids: list[str],
    graph_state_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return _unique_dicts([
        _state_summary(graph_state_by_id.get(graph_id))
        for graph_id in state_graph_ids
        if graph_state_by_id.get(graph_id) is not None
    ])


def _activity_summaries_for_graph_ids(
    activity_graph_ids: list[str],
    graph_activity_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return _unique_dicts([
        _activity_summary(graph_activity_by_id.get(graph_id))
        for graph_id in activity_graph_ids
        if graph_activity_by_id.get(graph_id) is not None
    ])


def _activity_graph_ids_from_bindings(bindings: list[dict[str, Any]]) -> list[str]:
    graph_ids: list[str] = []
    for binding in bindings:
        if binding.get("atomic_activity_id") is not None:
            graph_ids.append(_atomic_graph_id(binding["atomic_activity_id"]))
        elif binding.get("activity_node_id") is not None:
            graph_ids.append(_activity_graph_id(binding["activity_node_id"]))
    return graph_ids


def _owner_virtual_activity_ids_for_atomic(
    atomic_activity_id: int,
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> list[int]:
    activity_by_id = context.activity_by_id
    owner_ids: list[int] = []
    for ref in _activity_package_refs_by_atomic(context).get(atomic_activity_id, []):
        if not include_inactive and not ref.is_active:
            continue
        current = activity_by_id.get(ref.activity_node_id)
        while current is not None:
            if (
                current.level in (1, 2)
                and current.id not in owner_ids
                and (include_inactive or current.is_active)
            ):
                owner_ids.append(current.id)
            current = activity_by_id.get(current.parent_id) if current.parent_id is not None else None
    return owner_ids


def _owner_virtual_activities_for_graph_id(
    activity_graph_id: str,
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    activity_by_id = context.activity_by_id
    owner_ids: list[int] = []
    if activity_graph_id.startswith("atomic_activity:"):
        atomic_id = int(activity_graph_id.split(":", 1)[1])
        owner_ids = _owner_virtual_activity_ids_for_atomic(
            atomic_id,
            context,
            include_inactive=include_inactive,
        )
    elif activity_graph_id.startswith("activity_node:"):
        activity_id = int(activity_graph_id.split(":", 1)[1])
        current = activity_by_id.get(activity_id)
        while current is not None:
            if (
                current.level in (1, 2)
                and current.id not in owner_ids
                and (include_inactive or current.is_active)
            ):
                owner_ids.append(current.id)
            current = activity_by_id.get(current.parent_id) if current.parent_id is not None else None
    return [
        _activity_summary(activity_by_id.get(activity_id))
        for activity_id in owner_ids
        if activity_by_id.get(activity_id) is not None
        and (include_inactive or activity_by_id[activity_id].is_active)
    ]


def _bindings_related_to_state(
    graph_bindings: list[dict[str, Any]],
    state_node_id: int,
    leaf_ids: set[int],
) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    for binding in graph_bindings:
        covered = {int(item) for item in binding.get("covered_leaf_state_ids", [])}
        if (
            binding["state_node_id"] == state_node_id
            or state_node_id in covered
            or bool(leaf_ids & covered)
        ):
            related.append(binding)
    return related


def _parent_states_for_state_ids(
    state_ids: set[int],
    state_by_id: dict[int, StateNode],
) -> list[dict[str, Any]]:
    parent_ids: list[int] = []
    for state_id in state_ids:
        node = state_by_id.get(state_id)
        while node is not None and node.parent_id is not None:
            if node.parent_id not in parent_ids:
                parent_ids.append(node.parent_id)
            node = state_by_id.get(node.parent_id)
    return [_state_summary(state_by_id.get(parent_id)) for parent_id in parent_ids if state_by_id.get(parent_id)]


def _edge_state_ids(
    edges: list[dict[str, Any]],
    *,
    activity_graph_id: str,
    edge_type: str,
    roles: set[str] | None = None,
    source_kinds: set[str] | None = None,
) -> list[str]:
    graph_ids: list[str] = []
    for edge in edges:
        if edge["type"] != edge_type:
            continue
        if roles is not None and edge.get("binding_role") not in roles:
            continue
        if source_kinds is not None and edge.get("source_kind") not in source_kinds:
            continue
        if edge_type == "STATE_TO_ACTIVITY" and edge["target_id"] == activity_graph_id:
            graph_ids.append(edge["source_id"])
        elif edge_type == "ACTIVITY_TO_STATE" and edge["source_id"] == activity_graph_id:
            graph_ids.append(edge["target_id"])
    return graph_ids


async def analyze_network_editor_impact(
    session: AsyncSession,
    machine_type_id: int,
    payload: NetworkEditorImpactRequest,
) -> dict[str, Any]:
    context = await _load_context(session, machine_type_id)
    graph = _build_graph_from_context(context, payload)
    modeling_issues, solver_ready_issues = _validate_projected_graph(
        context,
        graph,
        include_inactive=payload.include_inactive,
        target_state_node_ids=payload.state_root_ids,
    )
    _add_issue_counts_to_summary(graph, modeling_issues, solver_ready_issues)

    graph_state_by_id = {node["id"]: node for node in graph["state_nodes"]}
    graph_activity_by_id = {node["id"]: node for node in graph["activity_nodes"]}
    state_by_id = context.state_by_id
    state_children = _state_display_children_by_parent(
        context.state_nodes,
        context.state_refs,
        include_inactive=payload.include_inactive,
    )
    all_issues = modeling_issues + solver_ready_issues

    base = {
        "machine_type_id": machine_type_id,
        "view_mode": payload.view_mode,
        "selection_type": "state" if payload.state_node_id else "activity",
        "selection_id": (
            _state_graph_id(payload.state_node_id)
            if payload.state_node_id else str(payload.activity_graph_id)
        ),
        "status": "ok",
        "selected": {},
        "summary": {},
        "parent_state_chain": [],
        "child_coverage": {},
        "reference_parent_states": [],
        "upstream_activities": [],
        "downstream_activities": [],
        "direct_precondition_states": [],
        "inherited_precondition_states": [],
        "output_states": [],
        "owner_virtual_activities": [],
        "affected_parent_states": [],
        "affected_virtual_activities": [],
        "affected_executable_activities": [],
        "package_bindings": [],
        "bindings": [],
        "participates_in_solver": None,
        "issues": [],
    }

    if payload.state_node_id is not None:
        state = state_by_id.get(payload.state_node_id)
        if state is None:
            return {**base, "status": "not_found"}
        graph_state_id = _state_graph_id(state.id)
        leaf_ids = set(_state_leaf_ids_under(state.id, state_by_id, state_children, include_inactive=False))
        related_bindings = _bindings_related_to_state(graph["bindings"], state.id, leaf_ids)
        related_activity_ids = _activity_graph_ids_from_bindings(related_bindings)
        upstream_activity_ids = [
            edge["source_id"] for edge in graph["edges"]
            if edge["type"] == "ACTIVITY_TO_STATE" and edge["target_id"] == graph_state_id
        ]
        downstream_activity_ids = [
            edge["target_id"] for edge in graph["edges"]
            if edge["type"] == "STATE_TO_ACTIVITY" and edge["source_id"] == graph_state_id
        ]
        affected_activity_ids = list(dict.fromkeys(upstream_activity_ids + downstream_activity_ids + related_activity_ids))
        affected_activity_nodes = _activity_summaries_for_graph_ids(affected_activity_ids, graph_activity_by_id)
        affected_virtual = [
            item for item in affected_activity_nodes
            if item.get("activity_type") == "virtual"
        ]
        affected_executable = [
            item for item in affected_activity_nodes
            if item.get("activity_type") == "executable"
        ]
        for item in list(affected_executable):
            for owner in _owner_virtual_activities_for_graph_id(
                item["id"],
                context,
                include_inactive=payload.include_inactive,
            ):
                if owner and owner.get("id") not in {existing.get("id") for existing in affected_virtual}:
                    affected_virtual.append(owner)

        reference_parent_ids = [
            ref.parent_state_node_id for ref in context.state_refs
            if ref.state_node_id == state.id and (payload.include_inactive or ref.is_active)
        ]
        parent_chain = _state_summaries_for_ids(_state_path(state, state_by_id), state_by_id)
        package_bindings = [
            _binding_summary(binding) for binding in related_bindings
            if binding["binding_type"] == "state_package"
        ]
        related_issues = [
            issue for issue in all_issues
            if state.id in issue.get("related_state_ids", [])
            or bool(leaf_ids & {int(item) for item in issue.get("related_state_ids", [])})
        ]
        return {
            **base,
            "selected": _state_summary(state),
            "summary": {
                "upstream_activity_count": len(set(upstream_activity_ids)),
                "downstream_activity_count": len(set(downstream_activity_ids)),
                "binding_count": len(related_bindings),
                "package_binding_count": len(package_bindings),
                "leaf_state_count": len(leaf_ids),
                "reference_parent_count": len(reference_parent_ids),
                "affected_virtual_activity_count": len(_unique_dicts(affected_virtual)),
                "affected_executable_activity_count": len(_unique_dicts(affected_executable)),
                "issue_count": len(related_issues),
            },
            "parent_state_chain": parent_chain,
            "child_coverage": {
                "state_node_id": state.id,
                "leaf_state_count": len(leaf_ids),
                "leaf_states": _state_summaries_for_ids(sorted(leaf_ids), state_by_id),
                "package_binding_count": len(package_bindings),
                "binding_ids": [binding["id"] for binding in related_bindings],
            },
            "reference_parent_states": _state_summaries_for_ids(reference_parent_ids, state_by_id),
            "upstream_activities": _activity_summaries_for_graph_ids(upstream_activity_ids, graph_activity_by_id),
            "downstream_activities": _activity_summaries_for_graph_ids(downstream_activity_ids, graph_activity_by_id),
            "affected_virtual_activities": _unique_dicts(affected_virtual),
            "affected_executable_activities": _unique_dicts(affected_executable),
            "package_bindings": package_bindings,
            "bindings": [_binding_summary(binding) for binding in related_bindings],
            "issues": related_issues,
        }

    activity_graph_id = str(payload.activity_graph_id)
    activity = graph_activity_by_id.get(activity_graph_id)
    if activity is None:
        return {**base, "status": "not_found"}

    direct_state_ids = _edge_state_ids(
        graph["edges"],
        activity_graph_id=activity_graph_id,
        edge_type="STATE_TO_ACTIVITY",
        roles={"input"},
    )
    inherited_state_ids: list[str] = []
    output_state_ids = _edge_state_ids(
        graph["edges"],
        activity_graph_id=activity_graph_id,
        edge_type="ACTIVITY_TO_STATE",
        roles={"output"},
    )

    output_state_node_ids = {
        state_id for state_id in (_state_node_id_from_graph_id(graph_id) for graph_id in output_state_ids)
        if state_id is not None
    }
    downstream_activity_ids: list[str] = []
    for output_state_id in output_state_node_ids:
        output_leaf_ids = set(
            _state_leaf_ids_under(output_state_id, state_by_id, state_children, include_inactive=payload.include_inactive)
        ) or {output_state_id}
        output_graph_ids = {_state_graph_id(state_id) for state_id in output_leaf_ids | {output_state_id}}
        downstream_activity_ids.extend(
            edge["target_id"] for edge in graph["edges"]
            if edge["type"] == "STATE_TO_ACTIVITY"
            and edge["source_id"] in output_graph_ids
            and edge["target_id"] != activity_graph_id
        )

    activity_bindings = [
        binding for binding in graph["bindings"]
        if activity_graph_id == (
            _atomic_graph_id(binding["atomic_activity_id"])
            if binding.get("atomic_activity_id") is not None else _activity_graph_id(binding["activity_node_id"])
        )
    ]
    owner_virtuals = _owner_virtual_activities_for_graph_id(
        activity_graph_id,
        context,
        include_inactive=payload.include_inactive,
    )
    affected_parent_states = _parent_states_for_state_ids(output_state_node_ids, state_by_id)
    related_issues = [
        issue for issue in all_issues
        if activity_graph_id in issue.get("related_activity_ids", [])
    ]
    return {
        **base,
        "selected": _activity_summary(activity),
        "summary": {
            "direct_precondition_count": len(set(direct_state_ids)),
            "inherited_precondition_count": len(set(inherited_state_ids)),
            "output_state_count": len(set(output_state_ids)),
            "owner_virtual_activity_count": len(owner_virtuals),
            "downstream_activity_count": len(set(downstream_activity_ids)),
            "affected_parent_state_count": len(affected_parent_states),
            "binding_count": len(activity_bindings),
            "issue_count": len(related_issues),
        },
        "direct_precondition_states": _state_summaries_for_graph_ids(direct_state_ids, graph_state_by_id),
        "inherited_precondition_states": _state_summaries_for_graph_ids(inherited_state_ids, graph_state_by_id),
        "output_states": _state_summaries_for_graph_ids(output_state_ids, graph_state_by_id),
        "owner_virtual_activities": _unique_dicts(owner_virtuals),
        "affected_parent_states": affected_parent_states,
        "downstream_activities": _activity_summaries_for_graph_ids(downstream_activity_ids, graph_activity_by_id),
        "package_bindings": [
            _binding_summary(binding) for binding in activity_bindings
            if binding["binding_type"] == "state_package"
        ],
        "bindings": [_binding_summary(binding) for binding in activity_bindings],
        "participates_in_solver": bool(activity.get("solver_participation")),
        "issues": related_issues,
    }


def _rules_by_atomic(
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> dict[int, list[OpRule]]:
    rules: dict[int, list[OpRule]] = defaultdict(list)
    for rule in context.op_rules:
        if rule.atomic_activity_id is not None and (include_inactive or rule.is_active):
            rules[rule.atomic_activity_id].append(rule)
    return rules


def _bindings_by_atomic(
    context: NetworkEditorContext,
    *,
    include_inactive: bool,
) -> dict[int, list[ActivityStateBinding]]:
    bindings: dict[int, list[ActivityStateBinding]] = defaultdict(list)
    for binding in context.bindings:
        if binding.atomic_activity_id is not None and (include_inactive or binding.is_active):
            bindings[binding.atomic_activity_id].append(binding)
    return bindings


def _state_aggregation_rules(
    context: NetworkEditorContext,
    payload: NetworkEditorRequest,
    graph: dict[str, Any],
    selected_atomic_ids: set[int],
) -> list[dict[str, Any]]:
    state_by_id = context.state_by_id
    state_display_children = _state_display_children_by_parent(
        context.state_nodes,
        context.state_refs,
        include_inactive=payload.include_inactive,
    )
    package_ids: set[int] = set()

    selected_state_ids = _selected_descendant_depths(
        payload.state_root_ids,
        state_display_children,
        {node.id for node in context.state_nodes},
        max_depth=payload.state_depth,
    )
    for state_id in selected_state_ids:
        if state_display_children.get(state_id):
            package_ids.add(state_id)

    for binding in graph["bindings"]:
        if binding.get("binding_type") == "state_package":
            package_ids.add(binding["state_node_id"])

    rules: list[dict[str, Any]] = []
    for state_id in sorted(package_ids):
        state = state_by_id.get(state_id)
        if state is None or (not payload.include_inactive and not state.is_active):
            continue
        children = [
            child for child in state_display_children.get(state.id, [])
            if payload.include_inactive or child.is_active
        ]
        leaf_ids = _state_leaf_ids_under(
            state.id,
            state_by_id,
            state_display_children,
            include_inactive=payload.include_inactive,
        )
        rules.append({
            "state_node_id": state.id,
            "state_node_code": state.code,
            "state_node_name": state.name,
            "parent_state_node_id": state.parent_id,
            "aggregation_rule": "AND",
            "direct_child_state_node_ids": [child.id for child in children],
            "leaf_state_ids": leaf_ids,
            "leaf_count": len(leaf_ids),
        })
    return rules


def _virtual_activity_groups(
    context: NetworkEditorContext,
    payload: NetworkEditorRequest,
    graph: dict[str, Any],
    selected_atomic_ids: set[int],
) -> list[dict[str, Any]]:
    activity_by_id = context.activity_by_id
    activity_children = _children_by_parent(context.activity_nodes)
    group_ids: set[int] = {
        node["activity_node_id"]
        for node in graph["activity_nodes"]
        if node.get("activity_node_id") is not None and node["activity_type"] == "virtual"
    }

    selected_activity_ids = _selected_descendant_depths(
        payload.activity_scope_node_ids,
        activity_children,
        {node.id for node in context.activity_nodes},
        max_depth=payload.activity_depth,
    )
    for activity_id in selected_activity_ids:
        activity = activity_by_id.get(activity_id)
        if activity and activity.level in (1, 2):
            group_ids.add(activity_id)

    for atomic_id in selected_atomic_ids:
        group_ids.update(
            _owner_virtual_activity_ids_for_atomic(
                atomic_id,
                context,
                include_inactive=payload.include_inactive,
            )
        )

    groups: list[dict[str, Any]] = []
    for activity_id in sorted(group_ids):
        activity = activity_by_id.get(activity_id)
        if activity is None or activity.level not in (1, 2):
            continue
        if not payload.include_inactive and not activity.is_active:
            continue
        children = [
            child for child in activity_children.get(activity.id, [])
            if payload.include_inactive or child.is_active
        ]
        descendant_atomic_ids = sorted(
            atomic_id
            for atomic_id in _atomic_ids_under_activity(
                activity.id,
                activity_children,
                context.package_refs,
                include_inactive=payload.include_inactive,
            )
            if payload.include_inactive or (
                context.atomic_by_id.get(atomic_id) is not None and context.atomic_by_id[atomic_id].is_active
            )
        )
        groups.append({
            "activity_node_id": activity.id,
            "activity_node_code": activity.code,
            "activity_node_name": activity.name,
            "level": activity.level,
            "parent_activity_node_id": activity.parent_id,
            "child_activity_node_ids": [child.id for child in children],
            "descendant_atomic_activity_ids": descendant_atomic_ids,
            "solver_participation": False,
            "reason": "virtual_activity_group_metadata",
        })
    return groups


def _default_solve_activity_scope_ids(
    context: NetworkEditorContext,
    payload: NetworkEditorRequest,
) -> list[int]:
    if payload.activity_scope_node_ids:
        return payload.activity_scope_node_ids

    activity_children = _children_by_parent(context.activity_nodes)

    def has_executable_descendant(activity: ActivityNode) -> bool:
        atomic_ids = _atomic_ids_under_activity(
            activity.id,
            activity_children,
            context.package_refs,
            include_inactive=payload.include_inactive,
        )
        if any(
            context.atomic_by_id.get(atomic_id) is not None
            and (payload.include_inactive or context.atomic_by_id[atomic_id].is_active)
            for atomic_id in atomic_ids
        ):
            return True

        descendant_ids = _activity_descendant_ids(activity.id, activity_children)
        return any(
            rule.activity_node_id in descendant_ids
            and (payload.include_inactive or rule.is_active)
            for rule in context.op_rules
        )

    scopes = [
        node.id
        for node in context.activity_nodes
        if node.level == 1
        and (payload.include_inactive or node.is_active)
        and has_executable_descendant(node)
    ]
    if scopes:
        return sorted(scopes)

    return sorted(
        node.id
        for node in context.activity_nodes
        if node.parent_id is None
        and (payload.include_inactive or node.is_active)
        and has_executable_descendant(node)
    )


def _solve_request_template(
    *,
    machine_type_id: int,
    context: NetworkEditorContext,
    payload: NetworkEditorRequest,
    model_status: str = "ready",
    blocking_issue_count: int = 0,
) -> dict[str, Any]:
    activity_scope_node_ids = _default_solve_activity_scope_ids(context, payload)
    required_runtime_fields = ["machine_id", "current_state_id"]
    if not payload.state_root_ids:
        required_runtime_fields.append("target_state_node_ids")
    if not activity_scope_node_ids:
        required_runtime_fields.append("activity_scope_node_ids")

    return {
        "endpoint": "POST /api/v1/solve/layered",
        "handoff_mode": "database_precheck_summary",
        "model_status": model_status,
        "solver_handoff_ready": model_status == "ready",
        "blocking_issue_count": blocking_issue_count,
        "required_runtime_fields": required_runtime_fields,
        "body": {
            "machine_id": None,
            "current_state_id": None,
            "target_state_node_ids": payload.state_root_ids,
            "activity_scope_node_ids": activity_scope_node_ids,
            "include_inactive": payload.include_inactive,
            "objective": "minimize_makespan",
            "objectives": None,
            "constraints": None,
            "current_state_overrides": {},
            "direct_goal_facts": [],
            "context": {
                "mode": "network_editor_solver_precheck",
                "machine_type_id": machine_type_id,
                "view_mode": payload.view_mode,
                "activity_scope_inferred": not bool(payload.activity_scope_node_ids) and bool(activity_scope_node_ids),
            },
        },
    }


def _solver_precheck_summary(
    *,
    executable_activities: list[dict[str, Any]],
    excluded_virtual_activities: list[dict[str, Any]],
    virtual_activity_groups: list[dict[str, Any]],
    state_aggregation_rules: list[dict[str, Any]],
    blocking_issues: list[dict[str, Any]],
    layered_health: dict[str, Any],
) -> dict[str, Any]:
    return {
        "executable_activity_count": len(executable_activities),
        "excluded_virtual_activity_count": len(excluded_virtual_activities),
        "virtual_activity_group_count": len(virtual_activity_groups),
        "state_aggregation_rule_count": len(state_aggregation_rules),
        "inherited_precondition_count": sum(
            len(item["inherited_preconditions"]) for item in executable_activities
        ),
        "own_precondition_count": sum(
            len(item["own_preconditions"]) for item in executable_activities
        ),
        "own_effect_count": sum(
            len(item["own_effects"]) for item in executable_activities
        ),
        "resource_req_count": sum(
            len(item["resource_reqs"]) for item in executable_activities
        ),
        "blocking_issue_count": len(blocking_issues),
        "goal_fact_count": layered_health["summary"]["goal_fact_count"],
        "candidate_activity_count": layered_health["summary"]["candidate_activity_count"],
        "effective_rule_count": layered_health["summary"]["effective_rule_count"],
        "layered_health_blocking_count": layered_health["summary"]["blocking_count"],
    }


async def precheck_network_editor_solver(
    session: AsyncSession,
    machine_type_id: int,
    payload: NetworkEditorRequest,
) -> dict[str, Any]:
    context = await _load_context(session, machine_type_id)
    graph = _build_graph_from_context(context, payload)
    validation = await validate_network_editor_model(session, machine_type_id, payload)
    layered_health = await check_layered_health(
        session,
        machine_type_id,
        LayeredExpansionRequest(
            target_state_node_ids=payload.state_root_ids,
            activity_scope_node_ids=payload.activity_scope_node_ids,
            include_inactive=payload.include_inactive,
        ),
    )

    state_by_id = context.state_by_id
    rules_by_atomic = _rules_by_atomic(context, include_inactive=payload.include_inactive)
    bindings_by_atomic = _bindings_by_atomic(context, include_inactive=payload.include_inactive)
    selected_atomic_ids = {
        int(node["atomic_activity_id"]) for node in graph["activity_nodes"]
        if node.get("atomic_activity_id") is not None and node["solver_participation"]
    }

    executable_activities: list[dict[str, Any]] = []
    for atomic_id in sorted(selected_atomic_ids):
        atomic = context.atomic_by_id.get(atomic_id)
        if atomic is None:
            continue
        rules = rules_by_atomic.get(atomic_id, [])
        own_bindings = bindings_by_atomic.get(atomic_id, [])
        explicit_rule_ids = {binding.op_rule_id for binding in own_bindings if binding.op_rule_id is not None}
        linked_rule: OpRule | None = None
        if len(explicit_rule_ids) == 1:
            linked_rule = next((rule for rule in rules if rule.id in explicit_rule_ids), None)
        elif len(rules) == 1:
            linked_rule = rules[0]

        inherited_context: list[dict[str, Any]] = []
        own_inputs = [
            fact
            for binding in own_bindings
            if binding.binding_role == "input"
            for fact in _binding_leaf_facts(
                binding,
                state_by_id,
                include_inactive=payload.include_inactive,
            )
        ]
        own_outputs = [
            fact
            for binding in own_bindings
            if binding.binding_role == "output"
            for fact in _binding_leaf_facts(
                binding,
                state_by_id,
                include_inactive=payload.include_inactive,
            )
        ]

        executable_activities.append({
            "atomic_activity_id": atomic.id,
            "atomic_activity_code": atomic.code,
            "atomic_activity_name": atomic.name,
            "op_rule_id": linked_rule.id if linked_rule else None,
            "op_rule_code": linked_rule.code if linked_rule else None,
            "inherited_preconditions": inherited_context,
            "own_preconditions": own_inputs,
            "own_effects": own_outputs,
            "resource_reqs": [
                {
                    "resource_type": req.resource_type,
                    "quantity": req.quantity,
                    "is_required": req.is_required,
                }
                for req in (linked_rule.resource_reqs if linked_rule else [])
            ],
        })

    virtual_activity_groups = _virtual_activity_groups(context, payload, graph, selected_atomic_ids)
    excluded_virtual_activities = [
        {
            **group,
            "reason": "virtual_activity",
        }
        for group in virtual_activity_groups
    ]
    state_aggregation_rules = _state_aggregation_rules(context, payload, graph, selected_atomic_ids)

    blocking_issues = [
        issue for issue in validation["solver_ready_issues"]
        if issue["severity"] == "error"
    ]
    status = "blocked" if blocking_issues else "ready"
    summary = _solver_precheck_summary(
        executable_activities=executable_activities,
        excluded_virtual_activities=excluded_virtual_activities,
        virtual_activity_groups=virtual_activity_groups,
        state_aggregation_rules=state_aggregation_rules,
        blocking_issues=blocking_issues,
        layered_health=layered_health,
    )
    return {
        "machine_type_id": machine_type_id,
        "status": status,
        "summary": summary,
        "executable_activities": executable_activities,
        "excluded_virtual_activities": excluded_virtual_activities,
        "virtual_activity_groups": virtual_activity_groups,
        "state_aggregation_rules": state_aggregation_rules,
        "blocking_issues": blocking_issues,
        "request_preview": {
            "target_state_node_ids": payload.state_root_ids,
            "activity_scope_node_ids": payload.activity_scope_node_ids,
            "include_inactive": payload.include_inactive,
        },
        "solve_request_template": _solve_request_template(
            machine_type_id=machine_type_id,
            context=context,
            payload=payload,
            model_status=status,
            blocking_issue_count=len(blocking_issues),
        ),
        "goal_facts": layered_health["goal_facts"],
        "candidate_activities": layered_health["candidate_activities"],
        "effective_rules": layered_health["effective_rules"],
        "layered_health_summary": layered_health["summary"],
        "layered_health_diagnostics": layered_health["diagnostics"],
    }


async def preview_network_editor_export(
    session: AsyncSession,
    machine_type_id: int,
    payload: NetworkEditorRequest,
) -> dict[str, Any]:
    return await precheck_network_editor_solver(session, machine_type_id, payload)

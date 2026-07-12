"""Layered solve service that connects expansion output to Planner/Scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.planner.partial_order import partial_order_plan
from app.core.planner.search import RAG, RAGNode, has_cycle, save_candidate_plan
from app.core.planner.state import compute_state_delta, load_state
from app.core.scheduler.solver import save_schedule_result, solve_schedule
from app.core.solver.rule_evaluator import RuleEvaluator
from app.core.solver.step_role import compute_step_role_diff
from app.db.models import (
    BlockageEvent,
    CandidatePlan,
    CandidatePlanStep,
    Machine,
    MachineState,
    MachineStateFeature,
    SolveRequest,
    StateFeatureDef,
    StateNode,
)
from app.db.schemas import LayeredExpansionRequest, LayeredSolveRequest
from app.services.layered_expansion import expand_layered_context
from app.services.layered_health import check_layered_health


@dataclass(frozen=True)
class _EffectivePrecond:
    feature_key: str
    operator: str
    feature_value: str
    value_list: list[Any] | None = None


@dataclass(frozen=True)
class _EffectiveEffect:
    feature_key: str
    new_value: str
    effect_type: str = "set"
    delta_value: float | None = None


@dataclass
class _EffectiveRule:
    id: int
    code: str
    name: str
    duration_min: int
    preconditions: list[_EffectivePrecond] = field(default_factory=list)
    effects: list[_EffectiveEffect] = field(default_factory=list)
    resource_reqs: list[Any] = field(default_factory=list)
    is_repair: bool = False


class _AmbiguousBlockedStepError(Exception):
    """Raised when a repeated parent task cannot be mapped to one new step."""


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _expanded_payload(payload: LayeredSolveRequest) -> LayeredExpansionRequest:
    return LayeredExpansionRequest(
        target_state_node_ids=payload.target_state_node_ids,
        activity_scope_node_ids=payload.activity_scope_node_ids,
        include_inactive=payload.include_inactive,
    )


async def _resolve_blocked_step_for_new_plan(
    session: AsyncSession,
    plan_id: int,
    blocked_step_id: int | None,
    blocked_op_rule_id: int | None,
) -> CandidatePlanStep | None:
    parent_step: CandidatePlanStep | None = None
    if blocked_step_id is not None:
        parent_step = await session.get(CandidatePlanStep, blocked_step_id)
        if parent_step is not None:
            step_result = await session.execute(
                select(CandidatePlanStep)
                .where(CandidatePlanStep.candidate_plan_id == plan_id)
                .where(CandidatePlanStep.step_order == parent_step.step_order)
            )
            blocked_step = step_result.scalar_one_or_none()
            if blocked_step is not None:
                return blocked_step
            blocked_op_rule_id = parent_step.op_rule_id

    if blocked_op_rule_id is None:
        return None

    step_result = await session.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id == plan_id)
        .where(CandidatePlanStep.op_rule_id == blocked_op_rule_id)
        .order_by(CandidatePlanStep.step_order)
    )
    matching_steps = step_result.scalars().all()
    if not matching_steps:
        return None
    if len(matching_steps) == 1:
        return matching_steps[0]
    if parent_step is not None:
        for step in matching_steps:
            if step.step_order == parent_step.step_order:
                return step
    raise _AmbiguousBlockedStepError(
        "AMBIGUOUS_BLOCKED_STEP: repeated task requires blocked_step_id"
    )


async def _load_feature_defs(
    machine_type_id: int,
    session: AsyncSession,
) -> dict[str, StateFeatureDef]:
    result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    return {item.feature_key: item for item in result.scalars().all()}


async def _load_state_nodes(
    machine_type_id: int,
    session: AsyncSession,
) -> tuple[dict[int, StateNode], dict[int | None, list[StateNode]]]:
    result = await session.execute(
        select(StateNode).where(StateNode.machine_type_id == machine_type_id)
    )
    nodes = list(result.scalars().all())
    by_id = {node.id: node for node in nodes}
    children: dict[int | None, list[StateNode]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    return by_id, children


def _descendant_state_leaves(
    node: StateNode,
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[StateNode]:
    active_children = [
        child for child in children_by_parent.get(node.id, [])
        if include_inactive or child.is_active
    ]
    if not active_children:
        return [node] if include_inactive or node.is_active else []

    leaves: list[StateNode] = []
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
    return leaves


def _is_leaf_path_node(path_node: dict[str, Any], path: list[dict[str, Any]]) -> bool:
    state_items = [
        item
        for item in path
        if item.get("node_type", "state_node") == "state_node"
    ]
    return bool(state_items) and path_node.get("id") == state_items[-1].get("id")


def _precondition_dicts_to_effective(
    precondition: dict[str, Any],
    state_by_id: dict[int, StateNode],
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> list[_EffectivePrecond]:
    feature_key = precondition.get("feature_key")
    operator = precondition.get("operator")
    feature_value = precondition.get("feature_value")

    if feature_key:
        if feature_value is None and operator != "in":
            return []
        return [
            _EffectivePrecond(
                feature_key=str(feature_key),
                operator=str(operator),
                feature_value=str(feature_value or ""),
                value_list=precondition.get("value_list"),
            )
        ]

    state_node_id = precondition.get("state_node_id")
    if operator != "completed" or not state_node_id:
        return []
    state_node = state_by_id.get(int(state_node_id))
    if state_node is None:
        return []

    result: list[_EffectivePrecond] = []
    for leaf in _descendant_state_leaves(
        state_node,
        children_by_parent,
        include_inactive=include_inactive,
    ):
        if not leaf.feature_key or leaf.target_value is None:
            continue
        result.append(
            _EffectivePrecond(
                feature_key=leaf.feature_key,
                operator=leaf.operator,
                feature_value=leaf.target_value,
                value_list=None,
            )
        )
    return result


def _build_effective_rules(
    expansion: dict[str, Any],
    state_by_id: dict[int, StateNode],
    children_by_parent: dict[int | None, list[StateNode]],
    *,
    include_inactive: bool,
) -> tuple[list[_EffectiveRule], dict[int, list[_EffectivePrecond]]]:
    rules: list[_EffectiveRule] = []
    preconditions_by_rule_id: dict[int, list[_EffectivePrecond]] = {}

    for item in expansion["effective_rules"]:
        preconditions: list[_EffectivePrecond] = []
        for precondition in item["preconditions"]:
            preconditions.extend(
                _precondition_dicts_to_effective(
                    precondition,
                    state_by_id,
                    children_by_parent,
                    include_inactive=include_inactive,
                )
            )

        effects = [
            _EffectiveEffect(
                feature_key=effect["feature_key"],
                new_value=effect["new_value"],
                effect_type=effect.get("effect_type", "set"),
                delta_value=_decimal_to_float(effect.get("delta_value")),
            )
            for effect in item["effects"]
        ]
        rule = _EffectiveRule(
            id=item["op_rule_id"],
            code=item["op_rule_code"],
            name=item["op_rule_name"],
            duration_min=item["duration_min"],
            preconditions=preconditions,
            effects=effects,
        )
        rules.append(rule)
        preconditions_by_rule_id[rule.id] = preconditions

    return rules, preconditions_by_rule_id


def _build_layered_target_state(
    current_state: dict[str, str],
    goal_facts: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    target_state = dict(current_state)
    conflicts: list[dict[str, Any]] = []
    requested: dict[str, str] = {}

    for fact in goal_facts:
        if fact["operator"] != "eq":
            conflicts.append({
                "code": "UNSUPPORTED_LAYERED_GOAL_OPERATOR",
                "feature_key": fact["feature_key"],
                "operator": fact["operator"],
                "state_node_id": fact.get("state_node_id"),
            })
            continue
        target_value = fact.get("target_value")
        if target_value is None:
            conflicts.append({
                "code": "MISSING_LAYERED_GOAL_VALUE",
                "feature_key": fact["feature_key"],
                "state_node_id": fact.get("state_node_id"),
            })
            continue
        feature_key = fact["feature_key"]
        if feature_key in requested and requested[feature_key] != target_value:
            conflicts.append({
                "code": "CONFLICTING_LAYERED_GOAL",
                "feature_key": feature_key,
                "values": sorted({requested[feature_key], target_value}),
            })
            continue
        requested[feature_key] = target_value
        target_state[feature_key] = target_value

    return target_state, conflicts


def _direct_goal_fact_dicts(request: LayeredSolveRequest) -> list[dict[str, Any]]:
    facts = []
    for fact in request.direct_goal_facts:
        facts.append({
            "state_node_id": None,
            "state_node_code": f"DIRECT_{fact.feature_key}",
            "state_node_name": fact.feature_key,
            "feature_key": fact.feature_key,
            "operator": fact.operator,
            "target_value": fact.value,
            "source_path": [],
            "source_type": "direct_goal_fact",
        })
    return facts


async def _create_synthetic_target_state(
    session: AsyncSession,
    machine_id: int,
    target_features: dict[str, str],
) -> int:
    target = MachineState(
        machine_id=machine_id,
        state_type="target",
        label=f"Layered target {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
    )
    session.add(target)
    await session.flush()
    for feature_key, feature_value in sorted(target_features.items()):
        session.add(
            MachineStateFeature(
                machine_state_id=target.id,
                feature_key=feature_key,
                feature_value=feature_value,
            )
        )
    await session.flush()
    return target.id


def _error_payload(
    solve_request_id: int | None,
    error_code: str,
    error_message: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "solve_request_id": solve_request_id,
        "status": "failed",
        "error_code": error_code,
        "error_message": error_message,
        "diagnostics": diagnostics or {},
    }


def _activity_summary(
    tasks: list[dict[str, Any]],
    expansion: dict[str, Any],
) -> list[dict[str, Any]]:
    path_by_rule_id: dict[int, list[dict[str, Any]]] = {}
    for candidate in expansion["candidate_activities"]:
        for op_rule_id in candidate["op_rule_ids"]:
            path_by_rule_id[op_rule_id] = candidate["source_path"]

    summary: dict[int, dict[str, Any]] = {}
    for task in tasks:
        for node in path_by_rule_id.get(task["op_rule_id"], []):
            item = summary.setdefault(
                node["id"],
                {
                    "activity_node_id": node["id"],
                    "activity_node_code": node["code"],
                    "activity_node_name": node["name"],
                    "level": node["level"],
                    "scheduled_task_count": 0,
                    "task_step_orders": [],
                },
            )
            item["scheduled_task_count"] += 1
            item["task_step_orders"].append(task["step_order"])

    return sorted(summary.values(), key=lambda item: (item["level"], item["activity_node_code"]))


def _activity_tree(
    tasks: list[dict[str, Any]],
    expansion: dict[str, Any],
) -> list[dict[str, Any]]:
    path_by_rule_id: dict[int, list[dict[str, Any]]] = {}
    for candidate in expansion["candidate_activities"]:
        for op_rule_id in candidate["op_rule_ids"]:
            path_by_rule_id[op_rule_id] = candidate["source_path"]

    nodes: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []

    def ensure_node(path_node: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
        node_id = path_node["id"]
        node = nodes.get(node_id)
        if node is None:
            node = {
                "activity_node_id": node_id,
                "activity_node_code": path_node["code"],
                "activity_node_name": path_node["name"],
                "level": path_node["level"],
                "scheduled_task_count": 0,
                "task_step_orders": [],
                "children": [],
            }
            nodes[node_id] = node
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return node

    for task in tasks:
        parent = None
        for path_node in path_by_rule_id.get(task["op_rule_id"], []):
            node = ensure_node(path_node, parent)
            node["scheduled_task_count"] += 1
            node["task_step_orders"].append(task["step_order"])
            parent = node

    def finalize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for item in sorted(items, key=lambda node: (node["level"], node["activity_node_code"])):
            item["task_step_orders"] = sorted(dict.fromkeys(item["task_step_orders"]))
            item["children"] = finalize(item["children"])
            result.append(item)
        return result

    return finalize(roots)


def _goal_satisfied(evaluator: RuleEvaluator, state: dict[str, str], fact: dict[str, Any]) -> bool:
    if fact["target_value"] is None:
        return False
    return evaluator.evaluate_precondition(
        state,
        _EffectivePrecond(
            feature_key=fact["feature_key"],
            operator=fact["operator"],
            feature_value=fact["target_value"],
        ),  # type: ignore[arg-type]
    )


def _goal_result_sources(goal_results: list[dict[str, Any]] | None) -> dict[int, dict[str, Any]]:
    if not goal_results:
        return {}
    return {
        int(item["state_node_id"]): item.get("source") or {}
        for item in goal_results
        if item.get("state_node_id") is not None
    }


def _append_unique(target: list[Any], value: Any) -> None:
    if value is not None and value not in target:
        target.append(value)


def _state_summary(
    final_state: dict[str, str],
    expansion: dict[str, Any],
    goal_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evaluator = RuleEvaluator()
    summary: dict[int, dict[str, Any]] = {}
    sources_by_state_id = _goal_result_sources(goal_results)

    for fact in expansion["goal_facts"]:
        satisfied = _goal_satisfied(evaluator, final_state, fact)
        path = fact.get("source_path") or []
        for node in path:
            item = summary.setdefault(
                node["id"],
                {
                    "state_node_id": node["id"],
                    "state_node_code": node["code"],
                    "state_node_name": node["name"],
                    "level": node["level"],
                    "goal_leaf_count": 0,
                    "satisfied_leaf_count": 0,
                    "status": "pending",
                    "source_step_orders": [],
                    "source_op_rule_codes": [],
                    "source_activity_node_codes": [],
                },
            )
            item["goal_leaf_count"] += 1
            if satisfied:
                item["satisfied_leaf_count"] += 1
            if _is_leaf_path_node(node, path):
                source = sources_by_state_id.get(node["id"], {})
                _append_unique(item["source_step_orders"], source.get("step_order"))
                _append_unique(item["source_op_rule_codes"], source.get("op_rule_code"))
                _append_unique(item["source_activity_node_codes"], source.get("activity_node_code"))

    for item in summary.values():
        if item["goal_leaf_count"] and item["goal_leaf_count"] == item["satisfied_leaf_count"]:
            item["status"] = "complete"
        elif item["satisfied_leaf_count"]:
            item["status"] = "partial"
        else:
            item["status"] = "pending"

    return sorted(summary.values(), key=lambda item: (item["level"], item["state_node_code"]))


def _state_tree(
    final_state: dict[str, str],
    expansion: dict[str, Any],
    goal_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evaluator = RuleEvaluator()
    nodes: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    sources_by_state_id = _goal_result_sources(goal_results)

    def ensure_node(path_node: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
        node_id = path_node["id"]
        node = nodes.get(node_id)
        if node is None:
            node = {
                "state_node_id": node_id,
                "state_node_code": path_node["code"],
                "state_node_name": path_node["name"],
                "level": path_node["level"],
                "goal_leaf_count": 0,
                "satisfied_leaf_count": 0,
                "status": "pending",
                "source_step_orders": [],
                "source_op_rule_codes": [],
                "source_activity_node_codes": [],
                "children": [],
            }
            nodes[node_id] = node
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return node

    for fact in expansion["goal_facts"]:
        satisfied = _goal_satisfied(evaluator, final_state, fact)
        parent = None
        path = fact.get("source_path") or []
        for path_node in path:
            node = ensure_node(path_node, parent)
            node["goal_leaf_count"] += 1
            if satisfied:
                node["satisfied_leaf_count"] += 1
            if _is_leaf_path_node(path_node, path):
                source = sources_by_state_id.get(path_node["id"], {})
                _append_unique(node["source_step_orders"], source.get("step_order"))
                _append_unique(node["source_op_rule_codes"], source.get("op_rule_code"))
                _append_unique(node["source_activity_node_codes"], source.get("activity_node_code"))
            parent = node

    for node in nodes.values():
        if node["goal_leaf_count"] and node["goal_leaf_count"] == node["satisfied_leaf_count"]:
            node["status"] = "complete"
        elif node["satisfied_leaf_count"]:
            node["status"] = "partial"

    def finalize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for item in sorted(items, key=lambda node: (node["level"], node["state_node_code"])):
            item["children"] = finalize(item["children"])
            result.append(item)
        return result

    return finalize(roots)


def _replay_schedule(
    current_state: dict[str, str],
    tasks: list[dict[str, Any]],
    rule_by_id: dict[int, _EffectiveRule],
    expansion: dict[str, Any],
) -> dict[str, Any]:
    evaluator = RuleEvaluator()
    state = dict(current_state)
    steps: list[dict[str, Any]] = []
    writer_by_feature: dict[str, dict[str, Any]] = {}

    for task in sorted(tasks, key=lambda item: (item["start_min"], item["step_order"])):
        rule = rule_by_id.get(task["op_rule_id"])
        if rule is None:
            continue
        unmet = []
        for precondition in rule.preconditions:
            if evaluator.evaluate_precondition(state, precondition):  # type: ignore[arg-type]
                continue
            unmet.append({
                "feature_key": precondition.feature_key,
                "operator": precondition.operator,
                "feature_value": precondition.feature_value,
            })
        before_state = dict(state)
        state = evaluator.apply_effects(state, rule.effects)  # type: ignore[arg-type]
        changed = {
            key: {"from_value": before_state.get(key), "to_value": value}
            for key, value in state.items()
            if before_state.get(key) != value
        }
        steps.append({
            "step_order": task["step_order"],
            "op_rule_id": task["op_rule_id"],
            "op_rule_code": task["op_rule_code"],
            "op_rule_name": task.get("op_rule_name"),
            "activity_node_id": task.get("activity_node_id"),
            "activity_node_code": task.get("activity_node_code"),
            "activity_node_name": task.get("activity_node_name"),
            "activity_group_id": task.get("activity_group_id"),
            "activity_group_code": task.get("activity_group_code"),
            "activity_group_name": task.get("activity_group_name"),
            "preconditions_satisfied": not unmet,
            "unmet_preconditions": unmet,
            "changed_features": changed,
        })
        for feature_key, value in changed.items():
            writer_by_feature[feature_key] = {
                "source_type": "activity",
                "step_order": task["step_order"],
                "op_rule_id": task["op_rule_id"],
                "op_rule_code": task["op_rule_code"],
                "op_rule_name": task.get("op_rule_name"),
                "activity_node_id": task.get("activity_node_id"),
                "activity_node_code": task.get("activity_node_code"),
                "activity_node_name": task.get("activity_node_name"),
                "activity_group_id": task.get("activity_group_id"),
                "activity_group_code": task.get("activity_group_code"),
                "activity_group_name": task.get("activity_group_name"),
                "value": value["to_value"],
            }

    goal_results = []
    for fact in expansion["goal_facts"]:
        satisfied = _goal_satisfied(evaluator, state, fact)
        source = None
        writer = writer_by_feature.get(fact["feature_key"])
        if writer and str(writer.get("value")) == str(state.get(fact["feature_key"])):
            source = writer
        elif satisfied:
            source = {
                "source_type": "current_state",
                "value": state.get(fact["feature_key"]),
            }
        goal_results.append({
            "state_node_id": fact.get("state_node_id"),
            "state_node_code": fact.get("state_node_code"),
            "feature_key": fact["feature_key"],
            "operator": fact["operator"],
            "target_value": fact["target_value"],
            "satisfied": satisfied,
            "final_value": state.get(fact["feature_key"]),
            "source": source,
        })

    unmet_goals = [item for item in goal_results if not item["satisfied"]]
    unmet_steps = [item for item in steps if not item["preconditions_satisfied"]]

    return {
        "status": "ok" if not unmet_goals and not unmet_steps else "failed",
        "final_state": state,
        "steps": steps,
        "goal_results": goal_results,
        "satisfied_goal_count": len(goal_results) - len(unmet_goals),
        "goal_count": len(goal_results),
        "unmet_goal_count": len(unmet_goals),
        "unmet_precondition_step_count": len(unmet_steps),
    }


def _effective_precondition_explanations(
    expansion: dict[str, Any],
    scheduled_op_rule_ids: set[int],
) -> list[dict[str, Any]]:
    result = []
    for rule in expansion["effective_rules"]:
        if rule["op_rule_id"] not in scheduled_op_rule_ids:
            continue
        result.append({
            "op_rule_id": rule["op_rule_id"],
            "op_rule_code": rule["op_rule_code"],
            "activity_node_id": rule["activity_node_id"],
            "activity_node_code": rule["activity_node_code"],
            "preconditions": rule["preconditions"],
        })
    return result


def _effect_fact(effect: _EffectiveEffect) -> tuple[str, str] | None:
    if effect.effect_type not in ("set", "reset"):
        return None
    if effect.new_value is None:
        return None
    return (effect.feature_key, str(effect.new_value))


def _precondition_fact(precondition: _EffectivePrecond) -> tuple[str, str] | None:
    if precondition.operator != "eq":
        return None
    return (precondition.feature_key, str(precondition.feature_value))


def _goal_fact(fact: dict[str, Any]) -> tuple[str, str] | None:
    if fact.get("operator") != "eq" or fact.get("target_value") is None:
        return None
    return (fact["feature_key"], str(fact["target_value"]))


def _state_package_groups_for_goal(fact: dict[str, Any]) -> list[dict[str, Any]]:
    path = [
        item
        for item in fact.get("source_path") or []
        if item.get("node_type", "state_node") == "state_node"
    ]
    if len(path) < 2:
        return []

    groups: list[dict[str, Any]] = []
    for index, node in enumerate(path[:-1]):
        groups.append({
            "state_group_id": node["id"],
            "state_group_code": node.get("code"),
            "state_group_name": node.get("name"),
            "state_group_level": node.get("level"),
            "parent_state_group_id": path[index - 1]["id"] if index > 0 else None,
        })
    return groups


def _append_state_group(target: list[dict[str, Any]], group: dict[str, Any]) -> None:
    group_id = group.get("state_group_id")
    if group_id is None:
        return
    if any(item.get("state_group_id") == group_id for item in target):
        return
    target.append(group)


def _state_continuity_groups_by_step(
    plan_nodes: list[Any],
    effective_rules: list[_EffectiveRule],
    expansion: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    """Build target-state-package continuity memberships for scheduled steps."""
    groups_by_goal_fact: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for goal in expansion["goal_facts"]:
        goal_key = _goal_fact(goal)
        if goal_key is None:
            continue
        groups = _state_package_groups_for_goal(goal)
        if not groups:
            continue
        groups_by_goal_fact.setdefault(goal_key, [])
        for group in groups:
            _append_state_group(groups_by_goal_fact[goal_key], group)

    if not groups_by_goal_fact:
        return {}

    rule_by_id = {rule.id: rule for rule in effective_rules}
    groups_by_step: dict[int, list[dict[str, Any]]] = {}
    for node in plan_nodes:
        rule = rule_by_id.get(node.op_rule_id)
        if rule is None:
            continue
        for effect in rule.effects:
            effect_fact = _effect_fact(effect)
            if effect_fact is None:
                continue
            for group in groups_by_goal_fact.get(effect_fact, []):
                _append_state_group(groups_by_step.setdefault(node.id, []), group)
    return groups_by_step


def _activity_selection_explanations(
    current_state: dict[str, str],
    tasks: list[dict[str, Any]],
    effective_rules: list[_EffectiveRule],
    expansion: dict[str, Any],
) -> list[dict[str, Any]]:
    """Explain which candidate activity rules were selected or skipped."""
    scheduled_by_rule_id = {task["op_rule_id"]: task for task in tasks}
    rule_by_id = {rule.id: rule for rule in effective_rules}
    expansion_rule_by_id = {
        rule["op_rule_id"]: rule
        for rule in expansion["effective_rules"]
    }
    selected_rules = [
        rule_by_id[rule_id]
        for rule_id in scheduled_by_rule_id
        if rule_id in rule_by_id
    ]
    selected_precondition_demands = {
        fact
        for rule in selected_rules
        for precondition in rule.preconditions
        for fact in [_precondition_fact(precondition)]
        if fact is not None
    }
    goal_demands = {
        fact
        for goal in expansion["goal_facts"]
        for fact in [_goal_fact(goal)]
        if fact is not None
    }
    demanded_facts = goal_demands | selected_precondition_demands

    result: list[dict[str, Any]] = []
    for rule in sorted(effective_rules, key=lambda item: item.code):
        expansion_rule = expansion_rule_by_id.get(rule.id, {})
        effect_facts = {
            fact
            for effect in rule.effects
            for fact in [_effect_fact(effect)]
            if fact is not None
        }
        goal_consumers = [
            {
                "type": "goal_fact",
                "feature_key": goal["feature_key"],
                "target_value": goal.get("target_value"),
                "state_node_code": goal.get("state_node_code"),
            }
            for goal in expansion["goal_facts"]
            if _goal_fact(goal) in effect_facts
        ]
        downstream_consumers = []
        for consumer_rule in selected_rules:
            if consumer_rule.id == rule.id:
                continue
            for precondition in consumer_rule.preconditions:
                if _precondition_fact(precondition) not in effect_facts:
                    continue
                downstream_consumers.append({
                    "type": "scheduled_precondition",
                    "op_rule_id": consumer_rule.id,
                    "op_rule_code": consumer_rule.code,
                    "feature_key": precondition.feature_key,
                    "feature_value": precondition.feature_value,
                })

        consumers = [*goal_consumers, *downstream_consumers]
        selected = rule.id in scheduled_by_rule_id
        if selected:
            status = "selected"
            reason = "selected_by_planner"
        elif effect_facts and all(current_state.get(feature_key) == value for feature_key, value in effect_facts):
            status = "skipped"
            reason = "effects_already_satisfied"
        elif effect_facts and not (effect_facts & demanded_facts):
            status = "skipped"
            reason = "not_demanded_by_selected_plan"
        else:
            status = "skipped"
            reason = "not_required_by_minimal_plan"

        result.append({
            "op_rule_id": rule.id,
            "op_rule_code": rule.code,
            "op_rule_name": rule.name,
            "activity_node_id": expansion_rule.get("activity_node_id"),
            "activity_node_code": expansion_rule.get("activity_node_code"),
            "activity_node_name": expansion_rule.get("activity_node_name"),
            "status": status,
            "reason": reason,
            "selected_step_order": scheduled_by_rule_id.get(rule.id, {}).get("step_order"),
            "effect_facts": [
                {"feature_key": feature_key, "value": value}
                for feature_key, value in sorted(effect_facts)
            ],
            "consumers": consumers,
            "consumer_count": len(consumers),
            "is_shared_provider": selected and len(consumers) > 1,
        })

    return result


def _preflight_health_summary(health: dict[str, Any]) -> dict[str, Any]:
    diagnostics = health.get("diagnostics") or []
    blocking = [item for item in diagnostics if item.get("severity") == "error"]
    warnings = [item for item in diagnostics if item.get("severity") != "error"]
    return {
        "status": health.get("status", "unknown"),
        "summary": health.get("summary", {}),
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "diagnostics": [
            {
                "code": item.get("code"),
                "severity": item.get("severity", "warning"),
                "message": item.get("message"),
                "feature_key": item.get("feature_key"),
                "operator": item.get("operator"),
                "target_value": item.get("target_value"),
                "provider_count": item.get("provider_count"),
                "op_rule_id": item.get("op_rule_id"),
                "activity_node_id": item.get("activity_node_id"),
                "state_node_id": item.get("state_node_id"),
                "source_type": item.get("source_type"),
            }
            for item in diagnostics
        ],
    }


async def solve_layered(
    request: LayeredSolveRequest,
    session: AsyncSession,
) -> dict[str, Any]:
    """Run a layered initial solve while preserving existing solve persistence."""

    machine = await session.get(Machine, request.machine_id)
    if machine is None:
        return _error_payload(None, "MACHINE_NOT_FOUND", f"Machine {request.machine_id} not found")

    current_state_obj = await session.get(MachineState, request.current_state_id)
    if current_state_obj is None or current_state_obj.machine_id != request.machine_id:
        return _error_payload(
            None,
            "CURRENT_STATE_INVALID",
            f"Current state {request.current_state_id} does not belong to machine {request.machine_id}",
        )

    expansion_payload = _expanded_payload(request)
    effective_activity_scope_node_ids = expansion_payload.activity_scope_node_ids
    expansion = await expand_layered_context(session, machine.machine_type_id, expansion_payload)
    direct_goal_facts = _direct_goal_fact_dicts(request)
    if direct_goal_facts:
        expansion = {
            **expansion,
            "goal_facts": [*expansion["goal_facts"], *direct_goal_facts],
        }
    health = await check_layered_health(session, machine.machine_type_id, expansion_payload)

    current_state = await load_state(request.current_state_id, session)
    if current_state is None:
        return _error_payload(None, "CURRENT_STATE_NOT_FOUND", "Current state not found")
    blockage_constraints = request.blockage_constraints or None
    strategy: str | None = blockage_constraints.get("strategy") if blockage_constraints else None
    strategy_b_reason: str | None = (
        blockage_constraints.get("strategy_b", {}).get("blockage_reason")
        if blockage_constraints else None
    )
    strategy_a_offset: int | None = (
        blockage_constraints.get("strategy_a", {}).get("not_before_offset")
        if blockage_constraints else None
    )
    blocked_step_id: int | None = (
        blockage_constraints.get("blocked_step_id")
        if blockage_constraints else None
    )
    blocked_op_rule_id: int | None = (
        blockage_constraints.get("blocked_op_rule_id")
        if blockage_constraints else None
    )
    parent_plan_id = request.parent_plan_id
    replan_reason_map = {
        "A": "blockage_strategy_a",
        "B": "blockage_strategy_b",
        "AB": "blockage_strategy_ab",
    }
    replan_reason = replan_reason_map.get(strategy) if strategy else "layered_initial"

    current_state_overrides = dict(request.current_state_overrides or {})
    if strategy in ("B", "AB") and strategy_b_reason:
        current_state_overrides["blockage_reason"] = strategy_b_reason
    if current_state_overrides:
        current_state = {**current_state, **current_state_overrides}

    target_state, goal_conflicts = _build_layered_target_state(current_state, expansion["goal_facts"])
    if goal_conflicts:
        return _error_payload(
            None,
            "INVALID_LAYERED_GOAL",
            "Layered target goals cannot be converted into an exact target state",
            {"goal_conflicts": goal_conflicts, "layered_health": health},
        )

    target_state_id = await _create_synthetic_target_state(
        session,
        request.machine_id,
        target_state,
    )

    objectives = request.objectives or [{"type": request.objective, "weight": 1.0}]
    solve_req = SolveRequest(
        machine_id=request.machine_id,
        current_state_id=request.current_state_id,
        target_state_id=target_state_id,
        objective=request.objective,
        objectives=objectives,
        constraints=request.constraints,
        parent_plan_id=parent_plan_id,
        blockage_constraints=blockage_constraints,
        overrides={
            "mode": request.context.get("mode", "layered") if request.context else "layered",
            "target_state_node_ids": request.target_state_node_ids,
            "activity_scope_node_ids": effective_activity_scope_node_ids,
            "requested_activity_scope_node_ids": request.activity_scope_node_ids,
            "activity_scope_defaulted": not bool(request.activity_scope_node_ids),
            "current_state_overrides": current_state_overrides,
            "direct_goal_facts": [
                fact.model_dump(mode="json") for fact in request.direct_goal_facts
            ],
            "context": request.context,
        },
        status="running",
    )

    try:
        session.add(solve_req)
        await session.flush()

        if not expansion["goal_facts"]:
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await session.commit()
            return _error_payload(
                solve_req.id,
                "NO_LAYERED_GOALS",
                "Layered solve requires at least one expanded goal fact",
                {"layered_expansion": expansion, "layered_health": health},
            )

        state_by_id, state_children = await _load_state_nodes(machine.machine_type_id, session)
        effective_rules, _ = _build_effective_rules(
            expansion,
            state_by_id,
            state_children,
            include_inactive=request.include_inactive,
        )
        if not effective_rules and current_state != target_state:
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await session.commit()
            return _error_payload(
                solve_req.id,
                "NO_LAYERED_CANDIDATE_RULES",
                "Layered solve has no candidate activity rules",
                {"layered_expansion": expansion, "layered_health": health},
            )

        feature_defs = await _load_feature_defs(machine.machine_type_id, session)
        pop_result = partial_order_plan(
            current_state=current_state,
            target_state=target_state,
            rules=effective_rules,  # type: ignore[arg-type]
            feature_defs=feature_defs,
        )
        if pop_result.status != "success":
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await session.commit()
            return _error_payload(
                solve_req.id,
                "NO_SOLUTION" if pop_result.status == "no_solution" else "INTERNAL_ERROR",
                pop_result.error_message or "Layered planner failed",
                {
                    "planner": pop_result.diagnostics,
                    "layered_expansion": expansion,
                    "layered_health": health,
                },
            )

        rag = RAG(
            nodes=[
                RAGNode(
                    id=node.id,
                    op_rule_id=node.op_rule_id,
                    op_rule_code=node.op_rule_code,
                    predecessors=node.predecessors,
                )
                for node in pop_result.nodes
            ],
            edges=list(pop_result.edges),
        )
        if has_cycle(rag.nodes, rag.edges):
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await session.commit()
            return _error_payload(
                solve_req.id,
                "CIRCULAR_DEPENDENCY",
                "Circular dependency detected in layered RAG",
                {"planner": pop_result.diagnostics},
            )

        version = 1
        if parent_plan_id is not None:
            parent_plan = await session.get(CandidatePlan, parent_plan_id)
            if parent_plan is not None:
                version = (parent_plan.version or 1) + 1

        plan_id = await save_candidate_plan(
            rag,
            solve_req.id,
            session,
            version=version,
            parent_plan_id=parent_plan_id,
            replan_reason=replan_reason,
        )
        await session.flush()

        new_blocked_step_id = None
        if strategy in ("A", "AB") and strategy_a_offset is not None:
            try:
                blocked_step = await _resolve_blocked_step_for_new_plan(
                    session=session,
                    plan_id=plan_id,
                    blocked_step_id=blocked_step_id,
                    blocked_op_rule_id=blocked_op_rule_id,
                )
            except _AmbiguousBlockedStepError as exc:
                solve_req.status = "failed"
                solve_req.solved_at = datetime.now(timezone.utc)
                await session.commit()
                return _error_payload(
                    solve_req.id,
                    "AMBIGUOUS_BLOCKED_STEP",
                    str(exc),
                    {"layered_expansion": expansion, "layered_health": health},
                )
            if blocked_step is not None:
                blocked_step.not_before = strategy_a_offset
                new_blocked_step_id = blocked_step.id

        if strategy in ("A", "B", "AB"):
            session.add(BlockageEvent(
                plan_id=plan_id,
                blocked_step_id=new_blocked_step_id,
                strategy=strategy or "A",
                not_before_offset=strategy_a_offset,
                blockage_reason=strategy_b_reason,
                note=blockage_constraints.get("note") if blockage_constraints else None,
                created_by=blockage_constraints.get("created_by") if blockage_constraints else None,
            ))

        await session.flush()

        state_continuity_groups_by_step = _state_continuity_groups_by_step(
            pop_result.nodes,
            effective_rules,
            expansion,
        )
        sched_result = await solve_schedule(
            plan_id,
            session,
            objectives=objectives,
            state_continuity_groups_by_step=state_continuity_groups_by_step,
        )
        if sched_result.status not in ("optimal", "feasible"):
            solve_req.status = "failed"
            solve_req.solved_at = datetime.now(timezone.utc)
            await session.commit()
            return _error_payload(
                solve_req.id,
                "INFEASIBLE" if sched_result.status == "infeasible" else "SOLVER_TIMEOUT",
                sched_result.error_message or "Layered schedule failed",
                {
                    "planner": pop_result.diagnostics,
                    "schedule": sched_result.diagnostics,
                    "layered_health": health,
                },
            )

        await save_schedule_result(sched_result, solve_req.id, plan_id, session)
        await compute_step_role_diff(plan_id, parent_plan_id, session)

        steps_result = await session.execute(
            select(CandidatePlanStep).where(CandidatePlanStep.candidate_plan_id == plan_id)
        )
        plan_steps = {
            step.step_order: {
                "step_id": step.id,
                "not_before": step.not_before,
                "step_role": step.step_role or "normal",
            }
            for step in steps_result.scalars().all()
        }

        tasks_response = []
        for task in sched_result.tasks or []:
            step_meta = plan_steps.get(task.step_order)
            tasks_response.append({
                "step_order": task.step_order,
                "step_id": step_meta["step_id"] if step_meta else None,
                "op_rule_id": task.op_rule_id,
                "op_rule_code": task.op_rule_code,
                "op_rule_name": task.op_rule_name,
                "start_min": task.start_min,
                "end_min": task.end_min,
                "duration_min": task.duration_min,
                "resources": task.resources,
                "resource_type": task.resource_type,
                "resource_reqs": task.resource_reqs,
                "activity_node_id": task.activity_node_id,
                "activity_node_code": task.activity_node_code,
                "activity_node_level": task.activity_node_level,
                "activity_group_id": task.activity_group_id,
                "activity_group_code": task.activity_group_code,
                "activity_group_name": task.activity_group_name,
                "state_continuity_groups": task.state_continuity_groups,
                "predecessors": task.predecessors,
                "not_before": step_meta["not_before"] if step_meta else None,
                "step_role": step_meta["step_role"] if step_meta else "normal",
            })

        rule_by_id = {rule.id: rule for rule in effective_rules}
        replay = _replay_schedule(current_state, tasks_response, rule_by_id, expansion)
        scheduled_op_rule_ids = {task["op_rule_id"] for task in tasks_response}

        state_delta = [
            {"feature_key": key, "from_value": values[0], "to_value": values[1]}
            for key, values in sorted(compute_state_delta(current_state, target_state).items())
        ]

        solve_req.status = "done"
        solve_req.solved_at = datetime.now(timezone.utc)
        await session.commit()

        return {
            "solve_request_id": solve_req.id,
            "status": "done",
            "candidate_plan_id": plan_id,
            "synthetic_target_state_id": target_state_id,
            "diagnostics": {
                "planner": pop_result.diagnostics,
                "schedule": sched_result.diagnostics,
                "layered_health": health,
            },
            "state_delta": state_delta,
            "critical_path": sched_result.critical_path or [],
            "schedule": {
                "makespan": sched_result.makespan,
                "tasks": tasks_response,
                "parallel_groups": sched_result.parallel_groups,
            },
            "layered": {
                "preflight_health": _preflight_health_summary(health),
                "goal_facts": expansion["goal_facts"],
                "candidate_activities": expansion["candidate_activities"],
                "effective_preconditions": _effective_precondition_explanations(
                    expansion,
                    scheduled_op_rule_ids,
                ),
                "activity_summary": _activity_summary(tasks_response, expansion),
                "activity_tree": _activity_tree(tasks_response, expansion),
                "activity_selection": _activity_selection_explanations(
                    current_state,
                    tasks_response,
                    effective_rules,
                    expansion,
                ),
                "state_summary": _state_summary(
                    replay["final_state"],
                    expansion,
                    replay["goal_results"],
                ),
                "state_tree": _state_tree(
                    replay["final_state"],
                    expansion,
                    replay["goal_results"],
                ),
                "state_replay": replay,
                "current_state_overrides": current_state_overrides,
                "context": request.context,
                "requested_activity_scope_node_ids": request.activity_scope_node_ids,
                "activity_scope_node_ids": effective_activity_scope_node_ids,
                "activity_scope_defaulted": not bool(request.activity_scope_node_ids),
            },
        }
    except Exception as exc:
        await session.rollback()
        return _error_payload(
            getattr(solve_req, "id", None),
            "INTERNAL_ERROR",
            str(exc),
        )

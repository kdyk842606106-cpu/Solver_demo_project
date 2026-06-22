"""Diagnostics for schedule infeasibility and suspicious RAG inputs."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.core.scheduler.loader import RagData, ResourceData
from app.core.scheduler.model import step_resource_requirements


def diagnose_schedule_inputs(
    rag_data: RagData,
    resources: list[ResourceData],
) -> dict[str, Any]:
    """Return human-readable diagnostics for the Scheduler input surface."""
    step_orders = [step.step_order for step in rag_data.steps]
    duplicate_step_orders = sorted({
        step_order for step_order in step_orders if step_orders.count(step_order) > 1
    })
    step_order_set = set(step_orders)

    horizon = sum(max(int(step.duration_min), 0) for step in rag_data.steps)
    max_not_before = max(
        (step.not_before for step in rag_data.steps if step.not_before is not None),
        default=0,
    )
    if max_not_before > 0:
        horizon += max_not_before

    capacities: dict[str, int] = defaultdict(int)
    instance_counts: dict[str, int] = defaultdict(int)
    resource_instances: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        capacity = int(resource.capacity or 0)
        capacities[resource.resource_type] += capacity
        instance_counts[resource.resource_type] += 1
        resource_instances[resource.resource_type].append({
            "resource_id": resource.id,
            "code": resource.code,
            "capacity": capacity,
        })

    requirements_by_step: dict[int, dict[str, int]] = {
        step.step_order: step_resource_requirements(step)
        for step in rag_data.steps
    }

    resource_pressure: dict[str, dict[str, Any]] = {}
    over_capacity_steps: list[dict[str, Any]] = []
    missing_resource_types: set[str] = set()
    for step in rag_data.steps:
        requirements = requirements_by_step[step.step_order]
        for resource_type, demand in requirements.items():
            capacity = capacities.get(resource_type, 0)
            pressure = resource_pressure.setdefault(
                resource_type,
                {
                    "available_capacity": capacity,
                    "available_instances": instance_counts.get(resource_type, 0),
                    "max_single_step_demand": 0,
                    "required_step_count": 0,
                    "total_demand_minutes": 0,
                },
            )
            pressure["max_single_step_demand"] = max(
                pressure["max_single_step_demand"],
                demand,
            )
            pressure["required_step_count"] += 1
            pressure["total_demand_minutes"] += demand * max(int(step.duration_min), 0)

            if capacity <= 0:
                missing_resource_types.add(resource_type)
            if demand > capacity:
                over_capacity_steps.append({
                    "step_order": step.step_order,
                    "op_rule_id": step.op_rule_id,
                    "op_rule_code": step.op_rule_code,
                    "resource_type": resource_type,
                    "demand": demand,
                    "available_capacity": capacity,
                })

    missing_edge_refs = [
        {"predecessor": pred, "successor": succ}
        for pred, succ in rag_data.edges
        if pred not in step_order_set or succ not in step_order_set
    ]

    invalid_durations = [
        {
            "step_order": step.step_order,
            "op_rule_id": step.op_rule_id,
            "op_rule_code": step.op_rule_code,
            "duration_min": step.duration_min,
        }
        for step in rag_data.steps
        if int(step.duration_min) <= 0
    ]

    not_before_issues = [
        {
            "step_order": step.step_order,
            "op_rule_id": step.op_rule_id,
            "op_rule_code": step.op_rule_code,
            "not_before": step.not_before,
            "horizon": horizon,
        }
        for step in rag_data.steps
        if step.not_before is not None and step.not_before < 0
    ]

    cycle_path = _find_cycle(step_order_set, rag_data.edges)

    likely_causes: list[str] = []
    if duplicate_step_orders:
        likely_causes.append("duplicate_step_order")
    if cycle_path:
        likely_causes.append("rag_cycle")
    if missing_edge_refs:
        likely_causes.append("edge_references_missing_step")
    if over_capacity_steps:
        likely_causes.append("resource_demand_exceeds_capacity")
    if missing_resource_types:
        likely_causes.append("resource_type_has_no_available_capacity")
    if invalid_durations:
        likely_causes.append("non_positive_duration")
    if not_before_issues:
        likely_causes.append("invalid_not_before")

    return {
        "step_count": len(rag_data.steps),
        "edge_count": len(rag_data.edges),
        "horizon": horizon,
        "duplicate_step_orders": duplicate_step_orders,
        "cycle_path": cycle_path,
        "missing_edge_refs": missing_edge_refs,
        "invalid_durations": invalid_durations,
        "not_before_issues": not_before_issues,
        "resource_capacities": dict(sorted(capacities.items())),
        "resource_instances": {
            key: value for key, value in sorted(resource_instances.items())
        },
        "resource_pressure": {
            key: value for key, value in sorted(resource_pressure.items())
        },
        "missing_resource_types": sorted(missing_resource_types),
        "over_capacity_steps": over_capacity_steps,
        "likely_causes": likely_causes,
    }


def _find_cycle(
    nodes: set[int],
    edges: list[tuple[int, int]],
) -> list[int]:
    """Return one cycle path from the ordering graph, or an empty list."""
    adjacency: dict[int, list[int]] = {node: [] for node in nodes}
    for pred, succ in edges:
        if pred in nodes and succ in nodes:
            adjacency[pred].append(succ)

    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def dfs(node: int) -> list[int]:
        visiting.add(node)
        stack.append(node)
        for succ in adjacency[node]:
            if succ in visiting:
                idx = stack.index(succ)
                return stack[idx:] + [succ]
            if succ not in visited:
                found = dfs(succ)
                if found:
                    return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in sorted(nodes):
        if node not in visited:
            found = dfs(node)
            if found:
                return found
    return []


def topological_blockers(
    rag_data: RagData,
) -> dict[str, Any]:
    """Return topological progress details for manually inspecting a RAG."""
    nodes = {step.step_order for step in rag_data.steps}
    adjacency: dict[int, list[int]] = {node: [] for node in nodes}
    indegree: dict[int, int] = {node: 0 for node in nodes}

    for pred, succ in rag_data.edges:
        if pred not in nodes or succ not in nodes:
            continue
        adjacency[pred].append(succ)
        indegree[succ] += 1

    ready = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    ordered: list[int] = []
    while ready:
        node = ready.popleft()
        ordered.append(node)
        for succ in sorted(adjacency[node]):
            indegree[succ] -= 1
            if indegree[succ] == 0:
                ready.append(succ)

    blocked = sorted(node for node, degree in indegree.items() if degree > 0)
    return {
        "topological_order_prefix": ordered,
        "blocked_step_orders": blocked,
        "blocked_count": len(blocked),
    }

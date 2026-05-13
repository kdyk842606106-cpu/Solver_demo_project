"""
Schedule Graph module.

Explicitly models the dependency graph from scheduling results,
including both logical edges (from Planner/RAG) and resource edges
(from Scheduler resource allocation).

Used for:
- Critical path computation
- Schedule visualization
- What-if analysis
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScheduleGraph:
    """Explicit dependency graph from scheduling result.

    Contains both logical edges (from Planner/RAG) and resource edges
    (from Scheduler resource allocation). Used for critical path analysis,
    visualization, and what-if simulation.
    """

    tasks: list[dict[str, Any]] = field(default_factory=list)
    logic_edges: list[tuple[int, int]] = field(default_factory=list)
    resource_edges: list[tuple[int, int]] = field(default_factory=list)
    makespan: int = 0

    def all_edges(self) -> list[tuple[int, int]]:
        """Combined logical + resource edges for path traversal."""
        return self.logic_edges + self.resource_edges

    def get_edge_type(self, from_step: int, to_step: int) -> str:
        """Classify edge as 'logic' or 'resource'."""
        if (from_step, to_step) in self.logic_edges:
            return "logic"
        return "resource"


def build_schedule_graph(
    tasks: list[Any],
    rag_edges: list[tuple[int, int]],
    makespan: int,
) -> ScheduleGraph:
    """Build ScheduleGraph from scheduler output.

    Args:
        tasks: Solved tasks with timing and assigned resources
        rag_edges: Logical edges from Planner RAG
        makespan: Total makespan from CP-SAT
    """
    # Logic edges: directly from RAG
    logic_edges = list(rag_edges)

    # Resource edges: from assigned resources
    # Group by resource_id, sort by start time, link adjacent pairs
    resource_usage: dict[int, list[tuple[int, int, int]]] = {}
    for t in tasks:
        for r in t.resources:
            rid = r["resource_id"]
            resource_usage.setdefault(rid, []).append(
                (t.start_min, t.end_min, t.step_order)
            )

    resource_edges: list[tuple[int, int]] = []
    for rid, usages in resource_usage.items():
        usages_sorted = sorted(usages, key=lambda x: x[0])
        for i in range(len(usages_sorted) - 1):
            _, end_i, order_i = usages_sorted[i]
            start_j, _, order_j = usages_sorted[i + 1]
            if start_j == end_i:  # Tight resource edge
                resource_edges.append((order_i, order_j))

    # Flatten tasks for serialization
    task_dicts: list[dict[str, Any]] = []
    for t in tasks:
        task_dicts.append(
            {
                "step_order": t.step_order,
                "op_rule_code": t.op_rule_code,
                "op_rule_name": t.op_rule_name,
                "start_min": t.start_min,
                "end_min": t.end_min,
                "duration_min": t.duration_min,
                "predecessors": t.predecessors,
                "resources": t.resources,
                "resource_type": t.resource_type,
            }
        )

    return ScheduleGraph(
        tasks=task_dicts,
        logic_edges=logic_edges,
        resource_edges=resource_edges,
        makespan=makespan,
    )


def compute_critical_path(graph: ScheduleGraph) -> list[str]:
    """Compute critical path from ScheduleGraph.

    Backward-trace from tasks ending at makespan through all tight edges
    (logical + resource) where predecessor.end == successor.start.
    """
    if not graph.tasks:
        return []

    by_order: dict[int, dict[str, Any]] = {t["step_order"]: t for t in graph.tasks}
    makespan = graph.makespan

    # Build adjacency: child -> list of parents
    parents: dict[int, list[int]] = {t["step_order"]: [] for t in graph.tasks}
    for from_step, to_step in graph.all_edges():
        parents.setdefault(to_step, []).append(from_step)

    # Backward trace from makespan tasks
    on_path: set[int] = set()
    stack = [t["step_order"] for t in graph.tasks if t["end_min"] == makespan]

    while stack:
        order = stack.pop()
        if order in on_path:
            continue
        task = by_order.get(order)
        if task is None:
            continue
        on_path.add(order)

        for pred_order in parents.get(order, []):
            pred = by_order.get(pred_order)
            if pred is not None and pred["end_min"] == task["start_min"]:
                stack.append(pred_order)

    path_tasks = sorted(
        [by_order[o] for o in on_path],
        key=lambda t: t["start_min"],
    )
    return [t["op_rule_code"] for t in path_tasks]

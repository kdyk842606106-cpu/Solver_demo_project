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
    resource_usage: dict[int, dict[int, list[tuple[int, int]]]] = {}
    for t in tasks:
        segments = getattr(t, "segments", []) or [{
            "start_min": t.start_min,
            "end_min": t.end_min,
            "resources": t.resources,
        }]
        for segment in segments:
            for resource in segment.get("resources", []):
                rid = resource["resource_id"]
                resource_usage.setdefault(rid, {}).setdefault(t.step_order, []).append(
                    (segment["start_min"], segment["end_min"])
                )

    resource_edges: list[tuple[int, int]] = []
    for usages_by_step in resource_usage.values():
        ranges = sorted(
            (
                min(start for start, _ in usages),
                max(end for _, end in usages),
                step_order,
            )
            for step_order, usages in usages_by_step.items()
        )
        for left, right in zip(ranges, ranges[1:]):
            if left[1] <= right[0] and left[2] != right[2]:
                resource_edges.append((left[2], right[2]))

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
                "resource_reqs": getattr(t, "resource_reqs", []),
                "segments": getattr(t, "segments", []),
                "elapsed_min": getattr(t, "elapsed_min", None),
            }
        )

    return ScheduleGraph(
        tasks=task_dicts,
        logic_edges=logic_edges,
        resource_edges=resource_edges,
        makespan=makespan,
    )


def compute_critical_path(graph: ScheduleGraph) -> list[str]:
    """Compute critical path from ScheduleGraph using standard CPM.

    Performs a backward pass over the full dependency graph (logical +
    resource edges) to compute Latest Start (LS) / Latest Finish (LF).
    A task is critical when its Total Float (LF - EF or LS - ES) is
    zero — i.e. any delay would increase the makespan.

    This correctly handles gaps caused by not_before constraints or
    resource waits, unlike the previous tight-edge backtrace.
    """
    if not graph.tasks:
        return []

    by_order: dict[int, dict[str, Any]] = {t["step_order"]: t for t in graph.tasks}
    makespan = graph.makespan

    # Build adjacency tables
    children: dict[int, list[int]] = {t["step_order"]: [] for t in graph.tasks}
    for from_step, to_step in graph.all_edges():
        children[from_step].append(to_step)

    # Backward pass: LS / LF in reverse end_min order (topological for backward)
    ls: dict[int, int] = {}
    lf: dict[int, int] = {}
    for t in sorted(graph.tasks, key=lambda x: -x["end_min"]):
        so = t["step_order"]
        dur = t.get("elapsed_min") or t["duration_min"]
        if not children[so]:
            lf[so] = makespan
        else:
            lf[so] = min(ls[c] for c in children[so])
        ls[so] = lf[so] - dur

    # Critical if ES == LS (equivalently EF == LF or slack == 0)
    critical_orders = [
        t["step_order"]
        for t in graph.tasks
        if t["start_min"] == ls[t["step_order"]]
    ]

    path_tasks = sorted(
        [by_order[o] for o in critical_orders],
        key=lambda t: t["start_min"],
    )
    return [t["op_rule_code"] for t in path_tasks]

"""Tests for ScheduleGraph and resource-aware critical path computation."""

import pytest
from app.core.scheduler.schedule_graph import (
    ScheduleGraph,
    build_schedule_graph,
    compute_critical_path,
)


class MockTaskResult:
    """Minimal mock of TaskResult for testing."""

    def __init__(
        self,
        step_order,
        start_min,
        end_min,
        duration_min,
        op_rule_code,
        resources=None,
        predecessors=None,
    ):
        self.step_order = step_order
        self.start_min = start_min
        self.end_min = end_min
        self.duration_min = duration_min
        self.op_rule_code = op_rule_code
        self.op_rule_name = op_rule_code
        self.op_rule_id = step_order
        self.resources = resources or []
        self.predecessors = predecessors or []
        self.resource_type = "NONE"


def test_empty_graph():
    """Empty graph should return empty critical path."""
    graph = ScheduleGraph()
    assert compute_critical_path(graph) == []


def test_simple_logic_only():
    """Simple chain with only logical edges."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [], []),
        MockTaskResult(2, 10, 25, 15, "B", [], [1]),
        MockTaskResult(3, 25, 30, 5, "C", [], [2]),
    ]
    graph = build_schedule_graph(tasks, [(1, 2), (2, 3)], 30)
    cp = compute_critical_path(graph)

    assert cp == ["A", "B", "C"]
    assert graph.logic_edges == [(1, 2), (2, 3)]
    assert graph.resource_edges == []


def test_resource_edge_detection():
    """Tasks sharing a resource with tight timing create resource edges."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [{"resource_id": 1, "resource_code": "R1"}], []),
        MockTaskResult(2, 10, 20, 10, "B", [{"resource_id": 1, "resource_code": "R1"}], []),
    ]
    graph = build_schedule_graph(tasks, [], 20)

    # B starts at 10 == A ends at 10 -> resource edge A->B
    assert (1, 2) in graph.resource_edges
    assert graph.resource_edges == [(1, 2)]

    cp = compute_critical_path(graph)
    assert cp == ["A", "B"]


def test_no_loose_resource_edge():
    """Tasks sharing a resource with gap do NOT create resource edge."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [{"resource_id": 1, "resource_code": "R1"}], []),
        MockTaskResult(2, 15, 25, 10, "B", [{"resource_id": 1, "resource_code": "R1"}], []),
    ]
    graph = build_schedule_graph(tasks, [], 25)

    # B starts at 15 != A ends at 10 -> no resource edge
    assert graph.resource_edges == []


def test_critical_path_with_resource_edges():
    """Critical path includes resource-induced waits."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [], []),
        MockTaskResult(2, 10, 20, 10, "B", [{"resource_id": 1, "resource_code": "R1"}], [1]),
        MockTaskResult(3, 20, 30, 10, "C", [{"resource_id": 1, "resource_code": "R1"}], []),
    ]
    # Logical: A -> B
    # Resource: B -> C (both use R1, tight)
    graph = build_schedule_graph(tasks, [(1, 2)], 30)
    cp = compute_critical_path(graph)

    assert "A" in cp
    assert "B" in cp
    assert "C" in cp
    assert len(cp) == 3


def test_multiple_makespan_tasks():
    """Multiple tasks ending at makespan - all traced back."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [], []),
        MockTaskResult(2, 10, 20, 10, "B", [], [1]),
        MockTaskResult(3, 0, 20, 20, "C", [], []),  # Also ends at 20
    ]
    graph = build_schedule_graph(tasks, [(1, 2)], 20)
    cp = compute_critical_path(graph)

    # Both B and C end at makespan=20
    assert "A" in cp
    assert "B" in cp
    assert "C" in cp


def test_non_critical_branch():
    """Branch that is not on critical path should not be included."""
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [], []),
        MockTaskResult(2, 10, 20, 10, "B", [], [1]),  # critical
        MockTaskResult(3, 10, 15, 5, "C", [], [1]),   # non-critical, ends early
    ]
    graph = build_schedule_graph(tasks, [(1, 2), (1, 3)], 20)
    cp = compute_critical_path(graph)

    assert "A" in cp
    assert "B" in cp
    assert "C" not in cp  # C ends at 15, not on path to makespan


def test_ms010_scenario_simplified():
    """Simplified MS010-like scenario with resource bottleneck."""
    # A -> B(logic) -> C(resource R1) -> D(resource R1)
    # E(logic from B, non-critical, ends early)
    tasks = [
        MockTaskResult(1, 0, 5, 5, "OPS001", [], []),
        MockTaskResult(2, 5, 15, 10, "OPS002", [], [1]),
        MockTaskResult(3, 15, 25, 10, "OPS003", [{"resource_id": 1, "resource_code": "R1"}], [2]),
        MockTaskResult(4, 25, 30, 5, "OPS004", [{"resource_id": 1, "resource_code": "R1"}], [3]),
        MockTaskResult(5, 5, 10, 5, "OPS005", [], [1]),  # non-critical branch
    ]
    graph = build_schedule_graph(
        tasks,
        [(1, 2), (2, 3), (3, 4), (1, 5)],
        30,
    )
    cp = compute_critical_path(graph)

    assert "OPS001" in cp
    assert "OPS002" in cp
    assert "OPS003" in cp
    assert "OPS004" in cp
    assert "OPS005" not in cp
    assert len(cp) == 4


def test_schedule_graph_edge_classification():
    """ScheduleGraph correctly classifies edge types."""
    graph = ScheduleGraph(
        logic_edges=[(1, 2)],
        resource_edges=[(2, 3)],
    )

    assert graph.get_edge_type(1, 2) == "logic"
    assert graph.get_edge_type(2, 3) == "resource"
    assert graph.all_edges() == [(1, 2), (2, 3)]

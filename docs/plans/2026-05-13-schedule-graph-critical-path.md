# Schedule Graph + Resource-Aware Critical Path — Implementation Plan
> **For agent:** REQUIRED SUB-SKILL: Use Section 5 (Subagent-Driven Development) to implement this plan.

**Goal:** Introduce a `ScheduleGraph` abstraction in the Scheduler layer to explicitly model both logical and resource-induced dependencies, enabling correct critical path computation that respects both Planner semantics and Scheduler resource constraints.

**Architecture:** New module `app/core/scheduler/schedule_graph.py` defines `ScheduleGraph` dataclass with logic_edges + resource_edges. `solve_schedule()` builds this graph after resource assignment. Critical path algorithm traverses the combined edge set. API layer consumes `critical_path` directly from scheduler result.

**Tech Stack:** Python 3.12, dataclasses, existing TaskResult/ScheduleResultData types.

---

## Context

Current architecture:
- Planner builds RAG with `predecessor_ids` (logical dependencies)
- Scheduler runs CP-SAT + assigns resources
- API layer (`solve.py`) computes critical path using ONLY logical edges
- Result: incorrect critical path because resource-induced waits are invisible

New architecture after this plan:
- Scheduler outputs `ScheduleGraph` containing BOTH edge types
- Critical path computed in Scheduler, not API layer
- API layer is a thin adapter, no algorithm logic

---

## Task 1: Create ScheduleGraph Module

**Files:**
- Create: `app/core/scheduler/schedule_graph.py`

**Step 1:** Define `ScheduleGraph` dataclass

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ScheduleGraph:
    """Explicit dependency graph from scheduling result.
    
    Contains both logical edges (from Planner/RAG) and resource edges
    (from Scheduler resource allocation). Used for critical path analysis,
    visualization, and what-if simulation.
    """
    tasks: list[dict[str, Any]]  # Flattened task dicts for serialization
    logic_edges: list[tuple[int, int]]      # (from_step_order, to_step_order)
    resource_edges: list[tuple[int, int]]   # (from_step_order, to_step_order)
    makespan: int
    
    def all_edges(self) -> list[tuple[int, int]]:
        """Combined logical + resource edges for path traversal."""
        return self.logic_edges + self.resource_edges
    
    def get_edge_type(self, from_step: int, to_step: int) -> str:
        """Classify edge as 'logic' or 'resource'."""
        if (from_step, to_step) in self.logic_edges:
            return "logic"
        return "resource"
```

**Step 2:** Define critical path function

```python
def compute_critical_path(graph: ScheduleGraph) -> list[str]:
    """Compute critical path from ScheduleGraph.
    
    Backward-trace from tasks ending at makespan through all tight edges
    (logical + resource) where predecessor.end == successor.start.
    """
    if not graph.tasks:
        return []
    
    by_order = {t["step_order"]: t for t in graph.tasks}
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
```

**Step 3:** Define graph builder function

```python
def build_schedule_graph(
    tasks: list[TaskResult],
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
    
    resource_edges = []
    for rid, usages in resource_usage.items():
        usages_sorted = sorted(usages, key=lambda x: x[0])
        for i in range(len(usages_sorted) - 1):
            _, end_i, order_i = usages_sorted[i]
            start_j, _, order_j = usages_sorted[i + 1]
            if start_j == end_i:  # Tight resource edge
                resource_edges.append((order_i, order_j))
    
    # Flatten tasks for serialization
    task_dicts = []
    for t in tasks:
        task_dicts.append({
            "step_order": t.step_order,
            "op_rule_code": t.op_rule_code,
            "op_rule_name": t.op_rule_name,
            "start_min": t.start_min,
            "end_min": t.end_min,
            "duration_min": t.duration_min,
            "predecessors": t.predecessors,
            "resources": t.resources,
            "resource_type": t.resource_type,
        })
    
    return ScheduleGraph(
        tasks=task_dicts,
        logic_edges=logic_edges,
        resource_edges=resource_edges,
        makespan=makespan,
    )
```

**Step 4:** Verify module imports
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.core.scheduler.schedule_graph import ScheduleGraph, build_schedule_graph, compute_critical_path
print('✅ schedule_graph module imports OK')
"
```

---

## Task 2: Integrate ScheduleGraph into solve_schedule()

**Files:**
- Modify: `app/core/scheduler/solver.py`
- Modify: `app/core/scheduler/__init__.py` (if needed for exports)

**Step 1:** Import ScheduleGraph in solver.py
```python
from app.core.scheduler.schedule_graph import ScheduleGraph, build_schedule_graph, compute_critical_path
```

**Step 2:** Update `ScheduleResultData` to include graph
```python
@dataclass
class ScheduleResultData:
    status: str
    makespan: Optional[int] = None
    tasks: Optional[list[TaskResult]] = None
    parallel_groups: Optional[list[list[int]]] = None
    solver_stats: Optional[SolverStats] = None
    error_message: Optional[str] = None
    schedule_graph: Optional[ScheduleGraph] = None  # NEW
    critical_path: Optional[list[str]] = None        # NEW
```

**Step 3:** After resource assignment in `solve_schedule()`, build graph and compute CP
```python
# After: _assign_resources(tasks, resources)
# After: parallel_groups = _detect_actual_parallel(tasks)

# Build schedule graph (NEW)
schedule_graph = build_schedule_graph(tasks, rag_data.edges, makespan_val)
critical_path = compute_critical_path(schedule_graph)

return ScheduleResultData(
    status=result_status,
    makespan=makespan_val,
    tasks=tasks,
    parallel_groups=parallel_groups,
    solver_stats=stats,
    schedule_graph=schedule_graph,   # NEW
    critical_path=critical_path,      # NEW
)
```

**Step 4:** Verify import test
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.core.scheduler.solver import ScheduleResultData
print('✅ ScheduleResultData with new fields OK')
"
```

---

## Task 3: Update API Layer to Consume Scheduler Critical Path

**Files:**
- Modify: `app/api/v1/solve.py`

**Step 1:** Remove old `_compute_critical_path` function (lines 92-127)

**Step 2:** Replace critical_path computation with scheduler output
```python
# OLD:
# critical_path = _compute_critical_path(sched_result.tasks or [])

# NEW:
critical_path = sched_result.critical_path or []
```

**Step 3:** Import `ScheduleGraph` if needed for type hints (optional)
```python
from app.core.scheduler.schedule_graph import ScheduleGraph
```

**Step 4:** Save `schedule_graph` to DB if desired (optional, for audit)
```python
# In save_schedule_result() or new function
# Could serialize schedule_graph.tasks/edges as JSON
```

**Step 5:** Verify API imports
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.api.v1.solve import router
print('✅ solve.py imports OK after changes')
"
```

---

## Task 4: Add Unit Tests for ScheduleGraph

**Files:**
- Create: `tests/unit/test_schedule_graph.py`

**Step 1:** Test `build_schedule_graph` with simple case
```python
import pytest
from app.core.scheduler.schedule_graph import ScheduleGraph, build_schedule_graph, compute_critical_path

class MockTaskResult:
    def __init__(self, step_order, start, end, duration, code, resources=None, predecessors=None):
        self.step_order = step_order
        self.start_min = start
        self.end_min = end
        self.duration_min = duration
        self.op_rule_code = code
        self.resources = resources or []
        self.predecessors = predecessors or []
        self.op_rule_name = code
        self.op_rule_id = step_order
        self.resource_type = "NONE"

def test_critical_path_with_resource_edges():
    tasks = [
        MockTaskResult(1, 0, 10, 10, "A", [], []),
        MockTaskResult(2, 10, 20, 10, "B", [{"resource_id": 1, "resource_code": "R1"}], [1]),
        MockTaskResult(3, 20, 30, 10, "C", [{"resource_id": 1, "resource_code": "R1"}], []),  # waits for B's resource
    ]
    rag_edges = [(1, 2)]
    graph = build_schedule_graph(tasks, rag_edges, 30)
    cp = compute_critical_path(graph)
    
    assert "A" in cp
    assert "B" in cp
    assert "C" in cp
    assert len(cp) == 3
```

**Step 2:** Test with MS010-like scenario
```python
def test_critical_path_ms010_scenario():
    # OPS001->OPS002->OPS003->OPS004->OPS017->OPS018->OPS019->OPS020->OPS021->OPS026->OPS027->OPS024
    tasks = [
        MockTaskResult(1, 0, 450, 450, "OPS001", [], []),
        MockTaskResult(2, 450, 2880, 2430, "OPS002", [], [1]),
        MockTaskResult(3, 2880, 4860, 1980, "OPS003", [{"resource_id": 1, "resource_code": "SPACE_R"}], [2]),
        MockTaskResult(4, 4860, 8220, 3360, "OPS004", [{"resource_id": 1, "resource_code": "SPACE_R"}], [3]),
        MockTaskResult(17, 8220, 9360, 1140, "OPS017", [{"resource_id": 2, "resource_code": "SPACE_UP"}], [4]),
        MockTaskResult(18, 9360, 14880, 5520, "OPS018", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [17]),
        MockTaskResult(19, 14880, 16847, 1967, "OPS019", [{"resource_id": 4, "resource_code": "SPACE_FRONT"}], [18]),
        MockTaskResult(20, 16847, 20105, 3258, "OPS020", [{"resource_id": 4, "resource_code": "SPACE_FRONT"}], [19]),
        MockTaskResult(21, 20105, 21185, 1080, "OPS021", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [20]),
        MockTaskResult(26, 21185, 22865, 1680, "OPS026", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [21, 16]),
        MockTaskResult(27, 22865, 28835, 5760, "OPS027", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [26]),
        MockTaskResult(24, 28835, 29045, 210, "OPS024", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [23]),
        MockTaskResult(11, 24155, 28835, 4680, "OPS011", [], [10]),  # non-critical, ends at makespan too
        MockTaskResult(10, 17040, 19560, 2520, "OPS010", [{"resource_id": 5, "resource_code": "SPACE_LIGHT"}], [9]),
        MockTaskResult(9, 10152, 13272, 3120, "OPS009", [{"resource_id": 5, "resource_code": "SPACE_LIGHT"}], [8]),
        MockTaskResult(8, 9120, 10152, 1032, "OPS008", [{"resource_id": 5, "resource_code": "SPACE_LIGHT"}], [4, 5]),
        MockTaskResult(5, 8220, 9120, 900, "OPS005", [{"resource_id": 5, "resource_code": "SPACE_LIGHT"}], [4]),
        MockTaskResult(12, 13272, 15372, 2100, "OPS012", [{"resource_id": 6, "resource_code": "SPACE_DOWN"}], [9, 4]),
        MockTaskResult(13, 15372, 16332, 960, "OPS013", [{"resource_id": 6, "resource_code": "SPACE_DOWN"}], [12]),
        MockTaskResult(14, 16332, 17712, 1380, "OPS014", [{"resource_id": 6, "resource_code": "SPACE_DOWN"}], [13]),
        MockTaskResult(25, 17712, 20934, 3222, "OPS025", [{"resource_id": 6, "resource_code": "SPACE_DOWN"}], [14]),
        MockTaskResult(16, 9102, 9282, 180, "OPS016", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [15, 4]),
        MockTaskResult(15, 8220, 9030, 810, "OPS015", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [4]),
        MockTaskResult(7, 16620, 17040, 420, "OPS007", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [6]),
        MockTaskResult(6, 14880, 16620, 1740, "OPS006", [{"resource_id": 3, "resource_code": "SPACE_OUT"}], [5]),
        MockTaskResult(23, 22080, 23700, 1800, "OPS023", [{"resource_id": 5, "resource_code": "SPACE_LIGHT"}], [22]),
        MockTaskResult(22, 21185, 21905, 720, "OPS022", [{"resource_id": 2, "resource_code": "SPACE_UP"}], [21]),
    ]
    
    rag_edges = [(1,2),(2,3),(3,4),(4,5),(4,15),(4,17),(15,16),(4,16),(4,8),(5,8),(17,18),(8,9),(9,12),(4,12),(5,6),(18,19),(12,13),(13,14),(6,7),(19,20),(9,10),(7,10),(14,25),(20,21),(21,22),(25,26),(16,26),(22,23),(26,27),(10,11),(23,24)]
    
    graph = build_schedule_graph(tasks, rag_edges, 29045)
    cp = compute_critical_path(graph)
    
    assert "OPS001" in cp
    assert "OPS004" in cp
    assert "OPS018" in cp
    assert "OPS027" in cp
    assert "OPS024" in cp
    assert "OPS011" not in cp  # Not on critical path despite ending at makespan
    assert len(cp) == 12
```

**Step 3:** Run tests
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/unit/test_schedule_graph.py -v
```

---

## Task 5: End-to-End Integration Test

**Files:**
- None (uses existing backend)

**Step 1:** Start backend
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

**Step 2:** Send solve request
```bash
curl -s -X POST http://localhost:8000/api/v1/solve \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": 9001,
    "current_state_id": 9001,
    "target_state_id": 9002,
    "objective": "minimize_makespan"
  }' > /tmp/solve_result_graph.json
```

**Step 3:** Verify critical path
```bash
cat /tmp/solve_result_graph.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
cp = d.get('critical_path', [])
print('critical_path:', cp)
print('len:', len(cp))
assert len(cp) > 2, f'Only {len(cp)} activities!'
assert 'MS010-OPS004' in cp, 'Missing OPS004'
assert 'MS010-OPS018' in cp, 'Missing OPS018'
assert 'MS010-OPS027' in cp, 'Missing OPS027'
assert 'MS010-OPS011' not in cp, 'OPS011 should NOT be critical'
print('✅ Integration test passed!')
"
```

---

## Task 6: Update ScheduleResult Persistence

**Files:**
- Modify: `app/core/scheduler/solver.py` — `save_schedule_result()`

**Step 1:** Optionally save schedule_graph to DB for audit
```python
# In save_schedule_result(), add:
if result.schedule_graph:
    record.tasks = result.schedule_graph.tasks  # or merge into existing tasks_json
```

**Step 2:** Verify DB write doesn't break
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/integration/test_planner_integration.py -v
```

---

## Task 7: Commit

**Files:**
- `app/core/scheduler/schedule_graph.py` (new)
- `app/core/scheduler/solver.py`
- `app/core/scheduler/__init__.py`
- `app/api/v1/solve.py`
- `tests/unit/test_schedule_graph.py` (new)
- `docs/plans/2026-05-13-schedule-graph-critical-path.md`

**Step 1:** Stage and commit
```bash
cd /mnt/e/Solver_demo_project && \
git add app/core/scheduler/schedule_graph.py \
        app/core/scheduler/solver.py \
        app/core/scheduler/__init__.py \
        app/api/v1/solve.py \
        tests/unit/test_schedule_graph.py \
        docs/plans/2026-05-13-schedule-graph-critical-path.md && \
git commit -m "feat(scheduler): introduce ScheduleGraph for resource-aware critical path

- Add app/core/scheduler/schedule_graph.py with ScheduleGraph dataclass
- ScheduleGraph explicitly models logic_edges + resource_edges
- Critical path computed in Scheduler, not API layer
- API layer removed _compute_critical_path, consumes scheduler output
- Added comprehensive unit tests for graph building and CP computation
- Fixes incorrect critical path that only considered logical dependencies

BREAKING: ScheduleResultData gains schedule_graph and critical_path fields"
```

---

## Verification Checklist

- [ ] `schedule_graph.py` created with ScheduleGraph, build_schedule_graph, compute_critical_path
- [ ] `ScheduleResultData` has `schedule_graph` and `critical_path` fields
- [ ] `solve_schedule()` builds graph and computes CP after resource assignment
- [ ] API layer `_compute_critical_path` removed
- [ ] Unit tests pass (`test_schedule_graph.py`)
- [ ] Integration test: solve API returns `len(critical_path) > 2`
- [ ] Integration test: OPS004, OPS018, OPS027 in critical_path
- [ ] Integration test: OPS011 NOT in critical_path
- [ ] Existing tests don't regress
- [ ] All changes committed

---

## Future Enhancements (out of scope)

1. **What-if analysis:** Use ScheduleGraph to simulate "如果 OPS018 提前 1 天，总工期缩短多少？"
2. **Resource bottleneck heatmap:** Visualize resource_edges density
3. **Multi-resource support:** Current resource_edges handles single resource per task; extend for multiple
4. **ScheduleGraph persistence:** Save to DB for historical plan comparison
5. **Interactive network diagram:** Frontend renders ScheduleGraph directly (vis-network already supports multiple edge types)

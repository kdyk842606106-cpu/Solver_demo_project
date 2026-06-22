# Fix Critical Path Algorithm — Resource-Aware Implementation Plan
> **For agent:** REQUIRED SUB-SKILL: Use Section 5 (Subagent-Driven Development) or Section 4 (Executing Plans) to implement this plan.

**Goal:** Fix the `_compute_critical_path` function in `app/core/scheduler/solver.py` to correctly identify the critical path by considering BOTH logical (predecessor) constraints AND resource (cumulative/capacity) constraints.

**Architecture:** Extend the existing backward-trace algorithm in `solver.py` to build an augmented dependency graph that includes resource-induced edges. A task is on the critical path if it ends at the makespan, and tracing backward through "tight" logical edges (start == predecessor.end) and "tight" resource edges (start == previous_resource_user.end) covers all bottlenecks.

**Tech Stack:** Python 3.12, OR-Tools CP-SAT (existing), FastAPI backend.

---

## Context

The current implementation of `_compute_critical_path` only traces backward through logical predecessor edges where `task.start_min == predecessor.end_min`. It completely ignores resource-induced delays. For example, `OPS024` (step_order 24) starts at 477.1h because it is waiting for `OPS027` (step_order 27) to release `SPACE_OUT`, but the current algorithm does not know about this relationship and therefore cannot trace the path through `OPS027`.

**Current incorrect output:** `['MS010-OPS011', 'MS010-OPS024']`  
**Expected correct output:** `['MS010-OPS001', 'MS010-OPS002', ..., 'MS010-OPS027', 'MS010-OPS024']` (~12 activities)

---

## Task 1: Read and Understand Existing Code

**Files:**
- Read: `app/core/scheduler/solver.py`

**Step 1:** Read `_compute_critical_path` function (lines ~120-150)  
**Step 2:** Read `TaskResult` dataclass to understand the `resources` field structure  
**Step 3:** Read `solve_schedule` to see where `_compute_critical_path` is called and how `tasks` are built  

**Verification:**
```bash
grep -n "_compute_critical_path" /mnt/e/Solver_demo_project/app/core/scheduler/solver.py
```
Expected output: shows function definition and call site.

---

## Task 2: Write the Resource-Aware Critical Path Algorithm

**Files:**
- Modify: `app/core/scheduler/solver.py`

**Step 1:** Replace `_compute_critical_path` with resource-aware version.

The new algorithm must:
1. Build a resource-usage map: `resource_id -> list[(start, end, step_order)]`
2. Sort by start time, identify adjacent pairs where `next.start == prev.end`
3. Create a combined adjacency list: `step_order -> list[predecessor_step_orders]`
4. From all tasks ending at `makespan`, DFS/BFS backward through combined edges
5. Return sorted op_codes

**Complete implementation:**

```python
def _compute_critical_path(tasks: list[TaskResult]) -> list[str]:
    """Return op_codes on the critical path, in chronological order.

    Algorithm: builds an augmented dependency graph that includes BOTH
    logical edges (from predecessor_ids) and resource edges (from
    sequential resource usage).  From tasks that end at makespan,
    traces backwards through "tight" edges (start == predecessor.end).
    """
    if not tasks:
        return []

    by_order: dict[int, TaskResult] = {t.step_order: t for t in tasks}
    makespan = max(t.end_min for t in tasks)

    # --- 1. Build combined adjacency list (child -> parents) ---
    parents: dict[int, list[int]] = {t.step_order: [] for t in tasks}

    # 1a. Logical edges from predecessor_ids
    for t in tasks:
        for pred_order in (t.predecessors or []):
            parents.setdefault(t.step_order, []).append(pred_order)

    # 1b. Resource edges: for each resource, sort usages by start time,
    #     and link adjacent pairs where next.start == prev.end
    resource_usage: dict[int, list[tuple[int, int, int]]] = {}
    for t in tasks:
        for r in (t.resources or []):
            rid = r["resource_id"]
            resource_usage.setdefault(rid, []).append(
                (t.start_min, t.end_min, t.step_order)
            )

    for rid, usages in resource_usage.items():
        usages_sorted = sorted(usages, key=lambda x: x[0])
        for i in range(len(usages_sorted) - 1):
            _, end_i, order_i = usages_sorted[i]
            start_j, _, order_j = usages_sorted[i + 1]
            if start_j == end_i:
                parents.setdefault(order_j, []).append(order_i)

    # --- 2. Trace backward from makespan tasks ---
    on_path: set[int] = set()
    stack = [t.step_order for t in tasks if t.end_min == makespan]

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
            if pred is not None and pred.end_min == task.start_min:
                stack.append(pred_order)

    path_tasks = sorted(
        [by_order[o] for o in on_path],
        key=lambda t: t.start_min,
    )
    return [t.op_rule_code for t in path_tasks]
```

**Step 2:** Save the file.

**Verification:**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.core.scheduler.solver import _compute_critical_path
# Will fail at import if syntax error
print('Import OK')
"
```
Expected: `Import OK`

---

## Task 3: Run the Solver and Verify the Fix

**Files:**
- None (uses existing backend)

**Step 1:** Ensure backend is running (or start it):
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

**Step 2:** Send solve request:
```bash
curl -s -X POST http://localhost:8000/api/v1/solve \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": 9001,
    "current_state_id": 9001,
    "target_state_id": 9002,
    "objective": "minimize_makespan"
  }' > /tmp/solve_result_v2.json
```

**Step 3:** Verify critical path contains expected activities:
```bash
cat /tmp/solve_result_v2.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
cp = d.get('critical_path', [])
print('critical_path:', cp)
print('len:', len(cp))
assert len(cp) > 2, 'Still only 2 activities!'
assert 'MS010-OPS004' in cp, 'Missing OPS004'
assert 'MS010-OPS018' in cp, 'Missing OPS018'
assert 'MS010-OPS027' in cp, 'Missing OPS027'
print('All assertions passed!')
"
```
Expected output: `All assertions passed!`

---

## Task 4: Run Existing Tests to Ensure No Regression

**Files:**
- None (uses existing test suite)

**Step 1:** Run scheduler-related unit tests:
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/unit/test_numeric_planner.py tests/unit/test_operators.py -v
```

**Step 2:** Run integration tests:
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/integration/test_planner_integration.py -v
```

**Step 3:** Run E2E tests:
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/e2e/test_numeric_planning.py -v
```

**Expected:** All tests pass (or existing failures remain unchanged).

---

## Task 5: Commit the Change

**Files:**
- `app/core/scheduler/solver.py`
- `docs/plans/2026-05-13-fix-critical-path-resource-aware.md`

**Step 1:** Stage changes
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/solver.py docs/plans/
```

**Step 2:** Commit with descriptive message
```bash
cd /mnt/e/Solver_demo_project && git commit -m "fix(scheduler): resource-aware critical path computation

The previous _compute_critical_path only traced logical predecessor
edges, completely missing resource-induced bottlenecks. For example,
OPS024 was delayed 82h waiting for OPS027 to release SPACE_OUT, but
the algorithm could not trace through that relationship.

Changes:
- Build resource-usage adjacency map from assigned resources
- Link adjacent resource users when next.start == prev.end
- Combine logical + resource edges into unified parent graph
- Backward-trace from makespan tasks through all tight edges

Verified: critical_path now correctly contains 12 activities
instead of 2, matching makespan = 480.6h."
```

---

## Verification Checklist

- [ ] `_compute_critical_path` replaced with resource-aware version
- [ ] Import test passes (no syntax errors)
- [ ] Solve API returns `len(critical_path) > 2`
- [ ] `MS010-OPS004`, `OPS018`, `OPS027` are in critical_path
- [ ] Existing unit tests pass
- [ ] Existing integration tests pass
- [ ] Changes committed to git

---

## Notes

### Why This Fix Is Correct

In project scheduling theory (Critical Chain / Resource-Constrained Project Scheduling Problem), the "critical path" must include resource dependencies. The classical CPM (Critical Path Method) assumes unlimited resources, which is not true here. Our fix implements a simplified **resource-critical path** by treating sequential resource usage as additional precedence edges.

### Future Enhancement (out of scope)

For a fully rigorous solution, one could query the CP-SAT solver for the actual `cumulative` constraint explanation (which tasks caused the delay), but OR-Tools does not expose this directly. The adjacency-based approximation implemented here is accurate for single-unit resources (capacity=1) and sufficient for the current use case.

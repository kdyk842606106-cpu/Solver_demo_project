# MS010 关键路径修复 — 资源边建模与 CP 算法重构

> **For agent:** REQUIRED SUB-SKILL: Use Section 4 or Section 5 to implement this plan.
> **Goal:** 修复 ScheduleGraph 资源边建模缺失 + compute_critical_path 伪路径拼接问题，返回真正的最长关键路径。
> **Architecture:** 扩展 StepData/TaskResult 支持多资源需求 → CP-SAT 为每个资源类型独立建 cumulative → 完整资源分配 → 从资源分配推导全部 resource_edges → compute_critical_path 改为反向紧边回溯。
> **Tech Stack:** Python 3.11, OR-Tools CP-SAT, FastAPI, SQLAlchemy 2.0 (async)

---

## 约束

- **接口兼容性优先**：所有 tools 之间的函数签名、调用方式、API 响应格式不变。
- **直接替换文件**：实现完成后，新旧文件可直接 swap，无需适配层。
- **CP-SAT 多资源建模**：同一 task interval 可出现在多个 cumulative 中（OR-Tools 原生支持）。
- **返回格式**：`critical_path: list[str]` 保持单一列表，返回最长关键路径（多条并行时选最长）。

---

## Phase 1: 数据流修复（loader → model → solver）

### Task 1: 扩展 StepData 支持多资源需求
**Files:**
- Modify: `app/core/scheduler/loader.py`

**Step 1:** 修改 `StepData` dataclass，将 `resource_type: str` + `resource_qty: int` 替换为 `resource_reqs: list[dict]`

```python
@dataclass
class StepData:
    """A single step in the RAG with all data needed for scheduling."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    duration_min: int
    resource_reqs: list[dict[str, Any]] = field(default_factory=list)
    # 保留 resource_type / resource_qty 用于向后兼容（取主资源）
    resource_type: str = "NONE"
    resource_qty: int = 0
    not_before: int | None = None
```

**Step 2:** 修改 `load_rag()` 加载全部 required resource_reqs 到 `resource_reqs` 列表，同时保留 `resource_type` / `resource_qty` 作为第一个 required req

关键代码：
```python
# 收集全部 required resource_reqs
resource_reqs = []
resource_type = "NONE"
resource_qty = 0
for req in rule.resource_reqs:
    if req.is_required:
        resource_reqs.append({
            "resource_type": req.resource_type,
            "quantity": req.quantity,
        })
        if resource_type == "NONE":
            resource_type = req.resource_type
            resource_qty = req.quantity
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.core.scheduler.loader import StepData
sd = StepData(step_order=1, op_rule_id=1, op_rule_code='TEST', duration_min=10,
                resource_reqs=[{'resource_type': 'WORKER', 'quantity': 3}, {'resource_type': 'CRANE', 'quantity': 1}],
                resource_type='WORKER', resource_qty=3)
print(sd)
print('resource_reqs:', sd.resource_reqs)
"
```
**期望输出：**`StepData(...)` + `resource_reqs: [{'resource_type': 'WORKER', 'quantity': 3}, {'resource_type': 'CRANE', 'quantity': 1}]`

**Step 3:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/loader.py && git commit -m "feat(scheduler): StepData multi-resource reqs support"
```

---

### Task 2: 扩展 TaskResult 支持多资源分配
**Files:**
- Modify: `app/core/scheduler/solver.py`

**Step 1:** 修改 `TaskResult` dataclass

```python
@dataclass
class TaskResult:
    """Solved task with timing and resource assignment."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    start_min: int
    end_min: int
    duration_min: int
    predecessors: list[int]
    resources: list[dict[str, Any]]  # 现在包含多个资源
    resource_type: str = "NONE"       # 向后兼容：主资源类型
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
from app.core.scheduler.solver import TaskResult
t = TaskResult(step_order=1, op_rule_id=1, op_rule_code='TEST', start_min=0, end_min=10,
               duration_min=10, predecessors=[], resources=[{'resource_id': 1}, {'resource_id': 2}])
print('resources:', t.resources)
"
```
**期望输出：**`resources: [{'resource_id': 1}, {'resource_id': 2}]`

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/solver.py && git commit -m "feat(scheduler): TaskResult multi-resource assignment"
```

---

### Task 3: CP-SAT 模型支持多资源 cumulative
**Files:**
- Modify: `app/core/scheduler/model.py`

**Step 1:** 修改 `build_model()` 中的资源约束部分

当前代码（只建模主资源）：
```python
for res_type in resource_type_set:
    # ... 每个 task 只出现一次
```

改为按 `StepData.resource_reqs` 中每个 req 独立建 cumulative：

```python
# 按资源类型聚合：res_type -> [(step_order, interval, demand)]
resource_intervals: dict[str, list[tuple[int, Any, int]]] = {}
for step in rag_data.steps:
    tv = task_vars[step.step_order]
    for req in step.resource_reqs:
        rt = req["resource_type"]
        demand = req["quantity"] if req["quantity"] > 0 else 1
        resource_intervals.setdefault(rt, []).append((step.step_order, tv.interval, demand))

for res_type, entries in resource_intervals.items():
    capacity = get_resource_capacity(resources, res_type)
    if capacity <= 0:
        capacity = 1

    intervals = [e[1] for e in entries]
    demands = [e[2] for e in entries]

    if intervals:
        model.add_cumulative(intervals, demands, capacity)
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
import asyncio
from app.core.scheduler.loader import load_rag, load_resources
from app.core.scheduler.model import build_model
from app.db.session import get_async_session

async def test():
    async with get_async_session() as session:
        rag = await load_rag(322, session)
        res_types = list({req['resource_type'] for s in rag.steps for req in s.resource_reqs})
        resources = await load_resources(res_types, session)
        model = build_model(rag, resources)
        print('Model built successfully')
        print('Tasks:', len(model.task_vars))
        print('Horizon:', model.horizon)

asyncio.run(test())
" 2>&1 | head -20
```
**期望输出：**`Model built successfully` + tasks/horizon 数值

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/model.py && git commit -m "feat(scheduler): multi-resource cumulative constraints"
```

---

### Task 4: 资源分配支持多资源
**Files:**
- Modify: `app/core/scheduler/solver.py`

**Step 1:** 重写 `_assign_resources()`，为每个 `resource_req` 独立分配资源

```python
def _assign_resources(
    tasks: list[TaskResult],
    resources: list[ResourceData],
) -> None:
    """
    Assign concrete resource instances for ALL resource_reqs on each task.

    For each task, iterate resource_reqs and assign one available resource
    per req. Mutates tasks in place.
    """
    pools: dict[str, list[ResourceData]] = {}
    for r in resources:
        pools.setdefault(r.resource_type, []).append(r)

    busy: dict[int, list[tuple[int, int]]] = {r.id: [] for r in resources}

    for task in tasks:
        # 从 step_map 中获取原始 resource_reqs（通过 loader 传入）
        # 但 TaskResult 目前没有 resource_reqs 字段...
        # 方案：通过 resource_type 作为向后兼容，但在 solve_schedule 中
        # 我们已有 rag_data.steps，可以按需扩展
        pass
```

> ⚠️ **接口决策**：`_assign_resources` 当前不接收 `rag_data`，只接收 `tasks` 和 `resources`。为了保持接口不变，需要扩展 `TaskResult` 增加 `resource_reqs` 字段，或者从 `solver.solve_schedule` 直接传入。

**推荐做法**：扩展 `TaskResult` 增加 `resource_reqs: list[dict]` 字段，`_assign_resources` 遍历 `task.resource_reqs` 分配。

修改后的 `_assign_resources`：

```python
def _assign_resources(
    tasks: list[TaskResult],
    resources: list[ResourceData],
) -> None:
    pools: dict[str, list[ResourceData]] = {}
    for r in resources:
        pools.setdefault(r.resource_type, []).append(r)

    busy: dict[int, list[tuple[int, int]]] = {r.id: [] for r in resources}

    for task in tasks:
        task.resources = []  # 清空，重新分配
        if not getattr(task, 'resource_reqs', []):
            # 向后兼容：空 req 列表则跳过
            continue

        for req in task.resource_reqs:
            rt = req["resource_type"]
            qty = req["quantity"] if req["quantity"] > 0 else 1
            pool = pools.get(rt, [])

            assigned = 0
            for res in pool:
                if _is_resource_free(busy[res.id], task.start_min, task.end_min):
                    task.resources.append({
                        "resource_id": res.id,
                        "resource_code": res.code,
                        "resource_type": rt,
                    })
                    busy[res.id].append((task.start_min, task.end_min))
                    assigned += 1
                    if assigned >= qty:
                        break
```

同时修改 `solve_schedule` 中 TaskResult 构造，传入 `resource_reqs`：

```python
TaskResult(
    ...,
    resources=[],
    resource_type=sd.resource_type,
    resource_reqs=sd.resource_reqs,  # 新增
)
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
import asyncio
from app.core.scheduler.solver import solve_schedule
from app.db.session import get_async_session

async def test():
    async with get_async_session() as session:
        result = await solve_schedule(322, session, max_time_seconds=30)
        if result.tasks:
            t = result.tasks[0]
            print(f'Task {t.op_rule_code}: resources={t.resources}')
            print(f'resource_reqs={getattr(t, \"resource_reqs\", [])}')

asyncio.run(test())
" 2>&1 | head -10
```
**期望输出：**`Task MS010-OPS001: resources=[...]`，且资源数量与 DB 中 `op_rule_resource_req` 记录匹配。

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/solver.py && git commit -m "feat(scheduler): multi-resource assignment for all reqs"
```

---

## Phase 2: ScheduleGraph + 关键路径算法重构

### Task 5: build_schedule_graph 支持完整 resource_edges
**Files:**
- Modify: `app/core/scheduler/schedule_graph.py`

**Step 1:** 修改 `build_schedule_graph()` 资源边推导逻辑

当前代码只基于 `task.resources`（单一资源）推导。改为按 `resource_id` 分组，对所有已分配资源生成相邻等待边：

```python
def build_schedule_graph(
    tasks: list[Any],  # TaskResult list
    rag_edges: list[tuple[int, int]],
    makespan: int,
) -> ScheduleGraph:
    logic_edges = list(rag_edges)

    # 按 resource_id 分组，生成 resource_edges
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
            _, _end_i, order_i = usages_sorted[i]
            _start_j, _, order_j = usages_sorted[i + 1]
            resource_edges.append((order_i, order_j))

    # task_dicts 序列化保持不变
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
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
import asyncio
from app.core.scheduler.solver import solve_schedule
from app.core.scheduler.schedule_graph import build_schedule_graph
from app.db.session import get_async_session

async def test():
    async with get_async_session() as session:
        result = await solve_schedule(322, session, max_time_seconds=30)
        if result.tasks:
            graph = build_schedule_graph(result.tasks, result.schedule_graph.logic_edges if result.schedule_graph else [], result.makespan)
            print(f'Logic edges: {len(graph.logic_edges)}')
            print(f'Resource edges: {len(graph.resource_edges)}')
            # 验证 resource_edges 数量 > logic_edges（MS010 有 74 个 resource_reqs）
            print(f'Total edges: {len(graph.all_edges())}')

asyncio.run(test())
" 2>&1 | head -10
```
**期望输出：**`Resource edges` 远大于之前的数量（之前约 27，现在应有 50+）。

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/schedule_graph.py && git commit -m "feat(scheduler): derive all resource_edges from multi-resource assignments"
```

---

### Task 6: compute_critical_path 反向紧边回溯
**Files:**
- Modify: `app/core/scheduler/schedule_graph.py`

**Step 1:** 重写 `compute_critical_path()`

核心思路：
1. 先用标准 CPM backward pass 计算 LS/LF（不变）
2. 找出所有 `slack=0` 的任务
3. 从终点（makespan 任务）反向回溯，只走紧边：`pred.end == curr.start` 且 `pred.slack=0`
4. 如果多条路径到达终点，选择最长的（step count 最多）
5. 返回路径的 `op_rule_code` 列表

```python
def compute_critical_path(graph: ScheduleGraph) -> list[str]:
    """Compute critical path from ScheduleGraph.

    Uses standard CPM backward pass for slack, then traces back from
    makespan tasks through tight zero-slack edges to find the actual
    critical path chain(s). Returns the longest path if multiple exist.
    """
    if not graph.tasks:
        return []

    by_order: dict[int, dict[str, Any]] = {t["step_order"]: t for t in graph.tasks}
    makespan = graph.makespan

    # Build adjacency: children (forward) and parents (backward)
    children: dict[int, list[int]] = {t["step_order"]: [] for t in graph.tasks}
    parents: dict[int, list[int]] = {t["step_order"]: [] for t in graph.tasks}
    for from_step, to_step in graph.all_edges():
        children[from_step].append(to_step)
        parents[to_step].append(from_step)

    # CPM backward pass: LS / LF
    ls: dict[int, int] = {}
    lf: dict[int, int] = {}
    for t in sorted(graph.tasks, key=lambda x: -x["end_min"]):
        so = t["step_order"]
        dur = t["duration_min"]
        if not children[so]:
            lf[so] = makespan
        else:
            lf[so] = min(ls[c] for c in children[so])
        ls[so] = lf[so] - dur

    # Zero-slack task set
    zero_slack = {
        t["step_order"]
        for t in graph.tasks
        if t["start_min"] == ls[t["step_order"]]
    }

    # Find all end tasks (zero-slack tasks ending at makespan)
    end_tasks = [so for so in zero_slack if by_order[so]["end_min"] == makespan]

    if not end_tasks:
        # Fallback: return all zero-slack sorted by time (旧行为，兼容)
        return [by_order[so]["op_rule_code"] for so in sorted(zero_slack, key=lambda s: by_order[s]["start_min"])]

    # Trace back from each end task through tight zero-slack edges
    def trace_back(start_step: int) -> list[int]:
        """Trace a single continuous path from end task back to start."""
        path = [start_step]
        current = start_step
        while True:
            # Find predecessors that are zero-slack AND end exactly when current starts
            candidates = [
                p for p in parents[current]
                if p in zero_slack and by_order[p]["end_min"] == by_order[current]["start_min"]
            ]
            if not candidates:
                break
            # If multiple, pick the one with the latest start (最靠近 current)
            # 这样保证走最长的链
            prev = max(candidates, key=lambda p: by_order[p]["start_min"])
            path.append(prev)
            current = prev
        path.reverse()
        return path

    # Try all end tasks, pick the longest path
    best_path: list[int] = []
    for et in end_tasks:
        path = trace_back(et)
        if len(path) > len(best_path):
            best_path = path

    return [by_order[so]["op_rule_code"] for so in best_path]
```

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -c "
import asyncio
from app.core.scheduler.solver import solve_schedule
from app.core.scheduler.schedule_graph import build_schedule_graph, compute_critical_path
from app.db.session import get_async_session

async def test():
    async with get_async_session() as session:
        result = await solve_schedule(322, session, max_time_seconds=30)
        if result.tasks and result.schedule_graph:
            cp = compute_critical_path(result.schedule_graph)
            print(f'Critical path ({len(cp)} steps):')
            print(' → '.join(cp))
            # 验证连续性
            task_by_code = {t.op_rule_code: t for t in result.tasks}
            for i in range(len(cp) - 1):
                a = task_by_code[cp[i]]
                b = task_by_code[cp[i+1]]
                tight = (a.end_min == b.start_min)
                pred_edge = (a.step_order in b.predecessors)
                status = '✓' if tight else '✗'
                print(f'  {cp[i]}→{cp[i+1]}: {a.end_min}→{b.start_min} {status}')

asyncio.run(test())
" 2>&1 | head -40
```
**期望输出：**CP 路径连续无断裂，所有 `→` 都是 `✓`（时间紧接）。

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add app/core/scheduler/schedule_graph.py && git commit -m "feat(scheduler): compute_critical_path tight-edge backtrace with longest path selection"
```

---

## Phase 3: API 层兼容 + 集成验证

### Task 7: solve.py API 响应兼容
**Files:**
- Modify: `app/api/v1/solve.py`

**Step 1:** 检查 `solve.py` 中 `critical_path` 的使用

当前代码（约第 322 行）：
```python
critical_path = sched_result.critical_path or []
```

`ScheduleResultData.critical_path` 类型已经是 `Optional[list[str]]`，`solve.py` 直接读取，**无需修改**。

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && grep -n "critical_path" app/api/v1/solve.py | head -10
```
**期望输出：**显示 `critical_path` 读取位置，确认格式未变。

---

### Task 8: 集成测试验证 MS010
**Files:**
- 无文件修改，纯验证

**Step 1:** 运行后端，调用 API 测试

```bash
cd /mnt/e/Solver_demo_project
# 确保 PostgreSQL 运行
# 启动后端（Windows 侧或 WSL 侧）
```

或者直接调用 solver-agent MCP 工具：
```bash
# 已验证的调用链路
solver-agent__schedule(322, objectives=[{"type": "minimize_makespan"}], max_time_seconds=30)
```

**Step 2:** 验证 critical_path 连续性

使用之前的验证脚本，确保所有 CP 链节 `end == next.start`。

**期望结果：**
- `critical_path` 长度 < 24（因为排除了伪并行任务）
- 所有链节时间紧接
- makespan 不变（28374 min 或相近）

**Step 3:** 如果验证失败 → 返回 Task 6 调试

---

### Task 9: 单元测试更新
**Files:**
- Modify: `tests/unit/test_schedule_graph.py`
- Modify: 相关测试文件

**Step 1:** 更新 `test_schedule_graph.py` 中的测试用例，反映新的 `compute_critical_path` 行为

关键检查点：
- 多资源场景下 resource_edges 数量增加
- critical_path 返回的是连续路径，不是零 slack 任务集合
- 最长路径选择逻辑正确

**验证命令：**
```bash
cd /mnt/e/Solver_demo_project && .venv-wsl2/bin/python -m pytest tests/unit/test_schedule_graph.py -v
```
**期望输出：**全部通过。

**Step 2:** Commit
```bash
cd /mnt/e/Solver_demo_project && git add tests/ && git commit -m "test(scheduler): update schedule_graph tests for tight-edge CP"
```

---

## Phase 4: 收尾

### Task 10: 端到端验证 + HTML 报告
**Files:**
- 无修改

**Step 1:** 运行完整 solve → schedule → report 链路

```bash
cd /mnt/e/Solver_demo_project
# 1. Solve
# 2. 生成报告输入 JSON
# 3. 生成 HTML 报告
.venv-wsl2/bin/python scripts/report_generator.py <input> <output>
```

**验证点：**
- HTML 报告中 critical_path 链显示为连续路径
- 甘特图中 CP 标记（红色左边框）只在真正关键的任务上
- 无断裂链节

**Step 2:** Commit 最终版本
```bash
cd /mnt/e/Solver_demo_project && git tag -a v0.2.1-cp-fix -m "Fix critical path: multi-resource edges + tight-edge backtrace"
```

---

## 回滚预案

如果任何阶段验证失败：
1. `git reset --hard HEAD~N` 回滚到阶段起点
2. 更新计划，重新执行
3. 旧文件（`schedule_graph.py.bak` 等）保留在 git history 中

---

## 接口变更摘要

| 文件 | 变更 | 兼容性 |
|------|------|--------|
| `loader.py` | `StepData` 增加 `resource_reqs` | ✅ 向后兼容，保留 `resource_type` |
| `model.py` | `build_model` 内部逻辑 | ✅ 输入/输出不变 |
| `solver.py` | `TaskResult` 增加 `resource_reqs` | ✅ 序列化 JSON 新增字段，消费者忽略 |
| `solver.py` | `_assign_resources` 内部逻辑 | ✅ 输入/输出不变 |
| `schedule_graph.py` | `build_schedule_graph` 内部逻辑 | ✅ 输入/输出不变 |
| `schedule_graph.py` | `compute_critical_path` 算法 | ✅ 返回值格式不变 |
| `solve.py` | 无变更 | ✅ |
| API Response | `critical_path: list[str]` | ✅ 格式不变 |

**所有 tools 调用方式不变，可直接替换文件。**

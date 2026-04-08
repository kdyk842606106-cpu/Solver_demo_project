# Scheduler 模块协议

路径：`app/core/scheduler/`

Scheduler 基于 Planner 生成的 RAG 和资源容量约束，使用 OR-Tools CP-SAT 求解最短工期排程。

## 核心入口

### `solve_schedule(candidate_plan_id, session, max_time_seconds=30.0) -> ScheduleResultData`

返回结构：

```python
ScheduleResultData(
    status="optimal" | "feasible" | "infeasible" | "error",
    makespan=int | None,
    tasks=list[TaskResult] | None,
    parallel_groups=list[list[int]] | None,
    solver_stats=SolverStats | None,
    error_message=str | None,
)
```

其中任务结构为：

```python
TaskResult(
    step_order=1,
    op_rule_id=3,
    op_rule_code="OP_WARMUP",
    start_min=0,
    end_min=30,
    duration_min=30,
    predecessors=[],
    resources=[{"resource_id": 1, "resource_code": "TECH-01"}],
    resource_type="TECHNICIAN",
)
```

## 当前执行流程

### 1. 加载 RAG

通过 `loader.load_rag(...)` 从数据库读取：

- `candidate_plan`
- `candidate_plan_step`
- `op_rule`
- `op_rule_resource_req`

并组装：

```python
RagData(
    candidate_plan_id=1,
    steps=[...],
    edges=[(1, 2), (1, 3)],
)
```

### 2. 加载资源

通过 `load_resources(resource_types, session)` 按资源类型查询 `resource` 表，仅加载 `is_available=True` 资源。

### 3. 构建 CP-SAT 模型

`model.build_model(...)` 当前包含：

- 每个任务的 `start / end / interval`
- 所有依赖边的 precedence 约束
- 按资源类型分组的 cumulative 容量约束
- `minimize(makespan)` 目标

### 4. 求解

使用：

```python
solver.parameters.max_time_in_seconds = 30.0
```

状态映射：

| CP-SAT 状态 | Scheduler 返回 |
|------------|----------------|
| `OPTIMAL` | `optimal` |
| `FEASIBLE` | `feasible` |
| `INFEASIBLE` | `infeasible` |
| 其他 | `error` |

注意：

- 当前实现没有单独的 `timeout` 状态
- 若超时但求解器没有产出可行解，通常会落到 `error`
- API 层再把这类 `error` 映射为 `SOLVER_TIMEOUT`

### 5. 分配具体资源

`_assign_resources(...)` 的当前策略：

- 按 `resource_type` 建立资源池
- 对每个任务按时间顺序尝试分配第一个空闲资源
- 只分配一个具体资源实例
- 如果找不到空闲资源，则保留空列表，作为降级行为

重要限制：

- 建模时只读取每个工序“第一个 `is_required=True` 的资源需求”
- `resource_qty > 1` 会进入 cumulative 约束，但资源实例分配阶段仍只写入一个具体资源
- 因此当前“容量建模”与“实例回填”并不完全等价

### 6. 检测并行组

`_detect_actual_parallel(tasks)` 以任务时间区间重叠为准：

```python
if t1.start_min < t2.end_min and t2.start_min < t1.end_min:
    # 视为并行
```

所以 `parallel_groups` 表示“实际同时执行”的步骤对，而不是理论可并行集合。

## 持久化契约

### `save_schedule_result(result, solve_request_id, candidate_plan_id, session) -> int`

落库到 `schedule_result`：

| 字段 | 说明 |
|------|------|
| `solve_request_id` | 所属求解请求 |
| `candidate_plan_id` | 所属候选计划 |
| `makespan` | 总工期 |
| `solver_status` | 如 `OPTIMAL` / `FEASIBLE` |
| `tasks` | 完整任务 JSON 数组 |

持久化的 `tasks` 结构包含：

- `step_order`
- `op_rule_id`
- `op_rule_code`
- `start_min`
- `end_min`
- `duration_min`
- `predecessors`
- `resources`

## 输入契约

Scheduler 对 Planner/DB 的假设：

- `candidate_plan_id` 必须存在
- `candidate_plan_step.predecessor_ids` 中的步骤号有效
- `op_rule.duration_min` 有效
- 对应规则若没有可用资源，模型会把容量回退到 `1`

这个“回退到 1”是当前实现的容错策略，不代表真实业务语义。

## 失败语义

| 场景 | 返回 |
|------|------|
| `candidate_plan` 不存在 | `status="error"` |
| `candidate_plan.steps` 为空 | `status="error"` |
| 资源约束不可满足 | `status="infeasible"` |
| 求解器返回其他状态 | `status="error"` |

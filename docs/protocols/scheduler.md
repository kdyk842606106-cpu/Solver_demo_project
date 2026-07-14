# Scheduler 模块协议

路径：`app/core/scheduler/`

Scheduler 基于 Planner 生成的 RAG 和资源容量约束，使用 OR-Tools CP-SAT 求解最短工期排程。

## 可选工作日历（TICKET-087）

- `solve_request.calendar_enabled=false` 时继续使用原有连续分钟轴和单 interval 建模。
- 启用时，步骤通过 `OpRule.effect.feature_key -> StateFeatureDef.dimension_template_id` 解析状态维度日历；未映射维度回退机器默认日历，多日历取 UTC 工作窗口交集。
- 每个任务由连续工作窗口中的 `segments` 表达；工作窗口内不可主动暂停，日历关闭后释放资源并在下一个开放窗口恢复。
- cumulative 资源约束和具体资源分配均作用于 segment；恢复片段允许使用不同的同类型资源。
- 机器未显式配置默认日历时继承唯一启用的系统默认日历，并返回 `CALENDAR_SYSTEM_DEFAULT_FALLBACK`；显式机器默认和状态维度映射优先。
- 日历窗口可携带 `shift_code/shift_name`。不同班次首尾相接时保留分片边界但不计暂停，同一班次的相邻窗口仍可合并；资源可在班次交接点重新分配。
- `start_min/end_min` 仍是相对计划起点的实际分钟偏移，`duration_min` 仍是工作量；`elapsed_min` 包含日历暂停。
- 日历定义和机器映射在首次求解时写入 `solve_request.calendar_snapshot`；重排默认继承父计划快照。

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
    op_rule_name="Warm up",
    start_min=0,
    end_min=30,
    duration_min=30,
    predecessors=[],
    resources=[
        {
            "resource_id": 1,
            "resource_code": "TECH-01",
            "resource_type": "TECHNICIAN",
            "quantity": 1,
        }
    ],
    resource_type="TECHNICIAN",
    resource_reqs=[
        {"resource_type": "TECHNICIAN", "quantity": 1},
        {"resource_type": "TOOLING", "quantity": 1},
    ],
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

每个 `StepData` 会保留：

- `resource_reqs`：canonical 多资源需求列表，来自所有 `is_required=True` 的 `op_rule_resource_req`。
- `resource_type/resource_qty`：兼容旧数据与旧测试的主资源 fallback。
- `not_before`：阻塞策略 A/AB 注入的最早开始时间约束。
- `activity_node_id/activity_node_code/activity_node_name`：任务展示用活动元数据；原子活动路径会使用合成的负数 `activity_node_id` 兼容旧展示字段。
- `atomic_activity_id`：TICKET-036 后原子活动规则的真实执行能力身份。
- `activity_group_id/activity_group_code/activity_group_name`：二级活动包/活动组元数据，用于 Gantt 分组和连续性软目标诊断。

### 2. 加载资源

通过 `load_resources(resource_types, session)` 按资源类型查询 `resource` 表，仅加载 `is_available=True` 资源。

### 3. 构建 CP-SAT 模型

`model.build_model(...)` 当前包含：

- 每个任务的 `start / end / interval`
- 所有依赖边的 precedence 约束
- 按资源类型分组的 cumulative 容量约束；同一个任务可同时出现在多个资源类型的 cumulative 中
- `not_before` 约束：`start >= not_before`
- `minimize(makespan)` 目标

资源需求归一化规则：

1. 优先读取 `StepData.resource_reqs`。
2. 对相同 `resource_type` 的需求数量求和。
3. 若 `resource_reqs` 为空，再使用旧字段 `resource_type/resource_qty` 作为兼容 fallback。
4. 如果某类资源当前没有可用实例，建模容量回退为 `1`，作为开发期容错；这不代表真实业务语义。

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

- 按 `resource_type` 建立资源池。
- 对每个任务读取完整 `resource_reqs`，为每个资源类型分别分配实例。
- 资源实例可以有 `capacity > 1`；占用表按 `(start, end, quantity)` 记录，而不是二元 busy/free。
- 分配结果写入 `task.resources`，每条包含 `resource_id`、`resource_code`、`resource_type`、`quantity`。
- 如果某个需求未能完整回填，保留未分配部分作为降级行为；正常情况下 CP-SAT 的 cumulative 约束应避免这种情况。

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
- `op_rule_name`
- `start_min`
- `end_min`
- `duration_min`
- `predecessors`
- `resources`
- `resource_type`
- `resource_reqs`
- `activity_node_id`
- `activity_node_code`
- `activity_node_name`
- `atomic_activity_id`
- `activity_group_id`
- `activity_group_code`
- `activity_group_name`

## 输入契约

Scheduler 对 Planner/DB 的假设：

- `candidate_plan_id` 必须存在
- `candidate_plan_step.predecessor_ids` 中的步骤号有效
- `op_rule.duration_min` 有效
- `resource_reqs` 是 Scheduler 的主资源契约
- `resource_type/resource_qty` 只用于兼容旧数据与旧测试
- 对应资源类型若没有可用资源，模型会把容量回退到 `1`
- 原子活动任务应携带原子活动和二级活动包元数据；共享原子活动归属到哪个二级包用于连续性目标仍是遗留策略问题。

这个“回退到 1”是当前实现的容错策略，不代表真实业务语义。

## 失败语义

| 场景 | 返回 |
|------|------|
| `candidate_plan` 不存在 | `status="error"` |
| `candidate_plan.steps` 为空 | `status="error"` |
| 资源约束不可满足 | `status="infeasible"` |
| 求解器返回其他状态 | `status="error"` |

## 关键路径与调度图

求解成功后会构建 `ScheduleGraph`：

- `logic_edges` 来自 Planner/RAG 的 precedence。
- `resource_edges` 来自资源实例分配后的相邻使用顺序。
- `compute_critical_path()` 使用逻辑边 + 资源边做 CPM backward pass，返回关键路径上的 `op_rule_code` 列表。

该逻辑已适配多资源：一个任务分配到多个资源时，每个资源实例都会参与 `resource_edges` 推导。

## 注册式排期规则（TICKET-089）

Scheduler 在建模前从 `solve_request.constraints.scheduling_rules.snapshot` 解析本次实际规则，缺省时才读取 `machine_type.scheduling_config.rules`。当前注册类型为：

- `group_continuity`：按原子活动 `metadata_json.responsible_subsystem` 建组，软成本统一计算 span、gap、interruption。
- `state_package_continuity`：按分层/维护求解附着到任务的 `state_continuity_groups` 建组，并通过同一注册式软成本计算 span、gap、interruption；不重复推导状态包归属。
- `scope_exclusivity`：命中任务与同一机器计划内其他任务建立硬不重叠约束，或按重叠任务对计算软成本。无工艺先后关系时由 CP-SAT 自主选择前后顺序。
- `shift_restriction`：按资源需求、效果状态维度或责任子系统选择任务，再以 `allowed_shift_codes` 过滤工作日历窗口。

原子活动的责任子系统只从原子活动读取，活动包和引用实例不参与覆盖。功能调测等业务识别只使用 OpRule effect 对应的状态维度模板键，行吊识别只使用 required resource type。

启用工作日历后，单个任务必须满足：

```text
sum(segment.duration_min) == duration_min
end_min - start_min == duration_min
calendar_pause_min == 0
```

因此任务可以连续跨越 UTC 时间首尾相接、且全部允许的多个 shift；任意中间 shift 被日历关闭或规则过滤，都会形成空档，任务不能在空档后恢复。预检找不到足够长的连续允许区间时返回 `CALENDAR_CONTIGUOUS_WINDOW_TOO_SHORT`，诊断包括任务、所需时长、最长连续允许时长、允许 shift 和过滤规则。

持久化任务 JSON 还包含 `responsible_subsystem`、`effect_dimension_keys`、`matched_scheduling_rules` 和 `scheduling_rule_violations`。

规则可选携带 `presentation.gantt_marker`。该字段随规则快照和活动规则诊断返回，但 Compiler 不读取它，因而不会改变约束、目标函数或排程结果。甘特图以任务的 `matched_scheduling_rules` 关联标识，并直接使用既有 `segments` 班次元数据绘制班次色条；相同文本与颜色的标识在单个任务内去重。

`STATE_PACKAGE_CONTINUITY` 是注册表提供的内置可选规则，仅支持 `layered/maintenance`。初始求解会将适用的内置规则并入实际规则快照；同类型机器配置规则优先于内置默认值。历史请求仍可直接提交 `minimize_state_group_span/gaps/interruptions` 三个 Objective，二者共用既有状态包归属和成本公式。

## 计划调整上下文（TICKET-095）

`solve_schedule(..., adjustment_context=...)` 只接收服务层已归一为 `step_order` 的范围、基线开始时间和约束，不接收 UI 框选几何。普通调整克隆现有 RAG，因此 Scheduler 不负责增删活动、改工期或替换系统依赖。

硬约束以 CP-SAT assumption literal 编译；无解时 `sufficient_assumptions_for_infeasibility()` 被映射回稳定的约束 ID、类型和活动，用于候选预览冲突定位。人工 `precedence` 在服务层先与系统依赖合并做环检测，成功候选再把该人工边持久化到候选步骤。

可行解按以下词典顺序逐阶段锁定最优值：

1. 范围外移动活动数；
2. 范围外开始时间总位移；
3. 全部移动活动数；
4. 全部开始时间总位移；
5. `high=4 / normal=2 / low=1` 加权开始时间；
6. 既有 makespan、连续性和注册排期规则目标。

开始时间相差至少 1 分钟才计为移动。范围外活动不是硬冻结；当硬约束或系统依赖要求时可以移动，但稳定性目标优先减少这种影响。

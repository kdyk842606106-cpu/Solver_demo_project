# Planner 模块协议

路径：`app/core/planner/`

Planner 的职责是从当前状态与目标状态的差异出发，自动选择工序，并根据 precondition/effect 链推导依赖关系，最终生成 RAG（Resource-Aware Graph）。

## 核心入口

### `build_rag(current_state_id, target_state_id, session) -> PlanResult`

返回值结构：

```python
PlanResult(
    status="success" | "no_solution" | "error",
    rag=RAG(...) | None,
    error_message=str | None,
)
```

其中 `RAG` 结构为：

```python
RAG(
    nodes=[
        RAGNode(
            id=1,
            op_rule_id=3,
            op_rule_code="OP_WARMUP",
            predecessors=[]
        )
    ],
    edges=[(1, 2)]
)
```

### `save_candidate_plan(rag, solve_request_id, session) -> int`

将 RAG 落库到：

- `candidate_plan`
- `candidate_plan_step`

`search_method` 当前固定写入 `state_inference`。

## 当前实现算法

### 1. 加载状态

- 通过 `load_state(...)` 读取 `machine_state_feature`
- 生成 `dict[str, str]` 形式状态快照

### 2. 计算状态差异

- 通过 `compute_state_delta(current, target)` 得到需要修复的 feature 集合
- 若当前状态已满足目标状态，则返回：
  - `status="no_solution"`
  - `error_message="Already at target state, no operations needed"`

### 3. 加载规则

- 根据 `current_state_id` 反查机台，再读取该机型所有 `is_active=True` 的 `OpRule`
- 规则包含：
  - `preconditions`
  - `effects`
  - `resource_reqs`

### 4. 为每个 delta 选择工序

- 通过 `find_ops_for_delta(feature_key, target_value, rules)` 找出所有可产生目标 effect 的工序
- 优先选择“当前状态已满足其 preconditions”的候选
- 若都不直接满足，则选择耗时最短者
- 同一工序可同时修复多个 delta，不重复加入

### 5. 递归补齐前置依赖

对于已选工序的每个 precondition：

- 若当前状态已满足，则不建依赖
- 否则在已选工序中查找 provider
- 若未找到，则在全量规则中查找能提供该条件的中间工序
- 找到后加入 RAG，并继续分析其中间工序自己的 preconditions

### 6. 环检测

- 使用 DFS 做 cycle detection
- 若出现环，返回：
  - `status="error"`
  - `error_message="Circular dependency detected in RAG"`

## 与文档契约相关的真实行为

- 当前实现不是 BFS 状态空间搜索，而是“delta 匹配 + 依赖补齐”
- 当前实现确实会自动引入中间工序，不要求所有目标工序都能直接执行
- `max_ops = 50` 是一个硬编码安全上限，用于避免异常规则导致无限扩张

## 关键辅助函数

| 文件 | 函数 | 作用 |
|------|------|------|
| `state.py` | `load_state` | 从数据库加载状态特征 |
| `state.py` | `compute_state_delta` | 比较当前与目标状态 |
| `state.py` | `is_goal` | 判断是否已达到目标 |
| `matcher.py` | `load_rules` | 加载工序规则 |
| `matcher.py` | `check_preconditions` | 校验某状态是否满足前提 |
| `matcher.py` | `find_ops_for_delta` | 查找可产生目标 effect 的工序 |
| `matcher.py` | `find_provider` | 查找满足某 precondition 的提供者工序 |
| `executor.py` | `effects_satisfy_precondition` | 用于 effect/precondition 匹配辅助判断 |

## 输出契约

Planner 对 Scheduler 的共享数据契约是 `candidate_plan_step`：

| 字段 | 说明 |
|------|------|
| `step_order` | 当前直接使用 `RAGNode.id`，从 1 开始 |
| `op_rule_id` | 关联工序规则 |
| `predecessor_ids` | 本步骤的前驱步骤 `step_order` 列表 |

注意：

- 当前 `step_order` 并不是重新拓扑排序后的结果，而是节点创建顺序
- 只要图无环，Scheduler 仍可根据 `predecessor_ids` 正确建 precedence 约束

## 失败语义

| 场景 | 返回 |
|------|------|
| 当前状态已等于目标状态 | `status="no_solution"` |
| 没有任何规则可产生所需 effect | `status="no_solution"` |
| 查不到当前/目标状态 | `status="error"` |
| 找不到机台或规则集为空 | `status="error"` 或 `status="no_solution"`，取决于具体分支 |
| 依赖图成环 | `status="error"` |

## 并行相关说明

Planner 内部保留了 `find_parallel_groups(rag)` 这样的分析函数，但 API 返回的 `parallel_groups` 并不来自这里。当前对外暴露的并行组以 Scheduler 根据任务时间重叠检测出的结果为准。

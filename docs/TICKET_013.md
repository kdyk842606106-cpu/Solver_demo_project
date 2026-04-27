# TICKET-013: V0.3 紧急专项 — 数值型状态规划能力设计冻结

> 对应版本：V0.3
> 对应阶段：V0.3 紧急架构专项（高于 TICKET-012）
> 背景来源：现有 Planner 无法正确处理数值型特征的多步推进与重复执行实例化
> 预估工作量：1 次对话完成设计冻结，后续按 Phase 分票实现
> 当前状态：设计已冻结，等待 Phase 1 实现票拆分

---

## 本次任务范围（只做这些）

围绕数值型状态规划的原始痛点，冻结最小正确设计方案，明确后续实现边界，覆盖：

1. 重复执行实例化（同一 `OpRule` 多次执行的 Planner 表达）
2. 多步数值推进（如 `0 -> 80`、步长 `20`）
3. 数值型隐式子目标递归（前置条件驱动的数值补齐）
4. 副作用弯路控制的第一阶段策略

并满足：

- 不破坏现有枚举型规划链路
- 不先改 Scheduler 主体语义
- 文档中明确阶段性取舍，避免过度设计

---

## 子任务清单

```text
[✅] A  重新定义根因：为什么当前 Planner 会在数值型场景失败
[✅] B  冻结最小架构：Planner 内部步骤实例化 + NumericFeaturePlanner
[✅] C  冻结阶段边界：Phase 1 / 2 / 3 范围与非目标
[✅] D  明确副作用策略：第一阶段不把 primary_feature 作为主方案
[✅] E  完整测试链路设计（unit / integration / e2e）
[✅] F  回写 STATE/TICKET 状态同步
```

---

## 当前问题重述

### 1. 原始痛点

当前规划器的核心假设是：

- 一个 `delta` 找一个 `OpRule`
- 一次执行就把特征推进到目标值

这在枚举型特征上成立，但在数值型特征上失效。

典型失败场景：

- 当前：`water_level = 0`
- 目标：`water_level = 80`
- 可用规则：`OP_FILL_WATER`，effect 为 `water_level +20`

当前 `find_ops_for_delta()` 只能找“单步命中 80”的 rule，结果直接返回 `no_solution`。

### 2. 当前架构中的真实根因

根因不是单一的“缺少主副作用标注”，而是以下三个假设同时成立：

1. **单步命中假设**
   - `find_ops_for_delta()` 按“一次应用 effect 后是否恰好等于目标值”选 rule。
2. **单 rule 单节点假设**
   - 当前 `build_rag()` 会按 `op_rule_id` 去重建节点，无法自然表达同一 rule 的多次执行。
3. **静态 current_state 假设**
   - precondition 补齐仍以初始 `current_state` 为主，而非链式推进后的中间状态。

副作用弯路问题存在，但它是“候选规则选择不够好”的第二层问题，不是第一层主根因。

---

## 设计结论（本票冻结）

### A：先把 Planner 从“rule 选取器”升级为“步骤实例生成器”

冻结结论：

- Planner 内部引入“步骤实例（step instance）”概念。
- 同一 `OpRule` 可在同一个 plan 中生成多个步骤实例。
- RAG 节点按步骤实例唯一，而不是按 `op_rule_id` 唯一。

这样最终仍可落库为多条 `CandidatePlanStep`：

- `step_order=1, op_rule_id=OP_FILL_WATER`
- `step_order=2, op_rule_id=OP_FILL_WATER`
- `step_order=3, op_rule_id=OP_FILL_WATER`
- `step_order=4, op_rule_id=OP_FILL_WATER`

结论：**第一阶段不要求先改 Scheduler，也不要求先改 CandidatePlanStep 表结构。**

### B：新增 NumericFeaturePlanner，而不是硬扩现有 matcher

冻结结论：

- 现有枚举型规划链路尽量保持不动。
- 新增 `NumericFeaturePlanner`，负责单个数值特征的链式推进。
- 顶层 `build_rag()` 继续做编排，按特征类型分流并最终合并为统一 RAG。

原因：

- 现有 `matcher.find_ops_for_delta()` 适合“单步 effect 命中”，不适合承担多步数值状态链求解。
- 把数值型规划独立出来，更符合“最小侵入式扩展”。

### C：第一阶段只冻结精确数值目标（eq）

冻结结论：

- 第一阶段先支持精确数值目标（`eq`）。
- 阈值目标（`gte/lte`）不复用现有 `target_state` 的 equality 语义。
- `gte/lte` 作为后续阶段，通过显式 goal predicate 单独扩展。

原因：

- 当前 `target_state_id` 表达的是“目标状态快照”，天然是 equality 语义。
- 若强行复用，会让 `target_state` 从“状态快照”变成“目标谓词容器”，语义变脏。

### D：副作用弯路控制第一阶段不以 primary_feature 为主方案

冻结结论：

- 第一阶段先解决“不会规划”的主问题：重复执行实例化 + 多步推进。
- 副作用弯路先通过候选规则过滤与排序做第一层控制。
- `primary_feature` 若引入，应放在第二阶段作为歧义消解元数据，而不是第一阶段主前提。

原因：

- `primary_feature` 解决的是“会规划但可能选错 rule”。
- 当前更大的主问题是“根本不会生成数值型链条”。

---

## 分阶段边界（冻结）

### Phase 1：数值型精确目标跑通

目标：

- 支持数值型 `eq` 目标
- 支持同一 rule 重复执行实例化
- 支持数值型隐式子目标递归补齐
- 不改 Scheduler 主体语义

本阶段不做：

- 不做 `gte/lte` 目标 API 扩展
- 不强依赖 `primary_feature`
- 不先加 occurrence 运维字段

### Phase 2：副作用歧义控制增强

目标：

- 控制“有进展但走弯路”的候选 rule 误选
- 若结构性过滤不足，再评估 `primary_feature`

本阶段不做：

- 不把 effect-level 主副作用标注作为默认方案
- 不允许多 primary 语义提前进入系统

### Phase 3：阈值目标与显式 goal predicate

目标：

- 为 `gte/lte` 等阈值目标补显式目标表达
- 不污染 `target_state` 的 equality 语义

---

## Phase 1 可实施设计

### 1. 目标边界

Phase 1 只解决一个闭环：

```text
当前状态 + 目标状态(eq) + 数值型 increment/decrement 规则
  -> Planner 生成重复执行实例 DAG
  -> CandidatePlanStep 可保存多个相同 op_rule_id 的步骤
  -> Scheduler 按现有 precedence + resource 逻辑排程
```

Phase 1 不改变 `/api/v1/solve` 请求结构，不引入新的目标谓词结构。目标状态仍来自 `target_state_id`，其含义仍为 exact target。

### 2. 新增模块

建议新增：

```text
app/core/planner/numeric.py
```

职责：

- 识别数值型 feature 的可用推进规则
- 为单个数值 feature 生成一组有序 step instances
- 使用 `RuleEvaluator.apply_effects()` 推进局部状态副本
- 识别并返回无法精确到达目标的配置错误或无解错误

不负责：

- 不直接保存数据库
- 不直接调用 Scheduler
- 不处理 `gte/lte` 外部目标语义
- 不做完整全局最优搜索

### 3. 内部数据结构

建议在 `numeric.py` 或 `search.py` 中定义轻量 dataclass。

```python
@dataclass
class PlannedStep:
    instance_id: str
    op_rule: OpRule
    target_feature: str
    before_state: StateDict
    after_state: StateDict
    predecessor_instance_ids: list[str]
```

说明：

- `instance_id` 是 Planner 内部临时 ID，例如 `water_level:OP_FILL_WATER:1`。
- `op_rule` 仍是原有规则模板。
- 同一个 `op_rule.id` 可以出现在多个 `PlannedStep` 中。
- `before_state/after_state` 用于数值链条验证与后续 explain，不在 Phase 1 落库。

RAG 落地前转换为现有 `RAGNode`：

```python
RAGNode(
    id=<sequential node id>,
    op_rule_id=planned_step.op_rule.id,
    op_rule_code=planned_step.op_rule.code,
    predecessors=[...node ids...],
)
```

### 4. 顶层编排改造

`build_rag()` 保持主入口，但内部拆为三段：

```text
1. 加载 current_state / target_state / rules / feature_defs
2. 对 delta 按 feature value_type 分流
3. 合并 enum steps 与 numeric step instances，生成统一 RAG
```

推荐编排：

```text
for each delta feature:
  if feature_def.value_type == "number":
    NumericFeaturePlanner.plan_exact(...)
  else:
    走现有枚举型 delta matching
```

注意：

- 枚举型旧链路必须保留，避免破坏现有 V0.1/V0.2 场景。
- 数值型链条必须按实例保留，不允许按 `op_rule_id` 去重。
- 合并 RAG 时只按 `instance_id` 去重；枚举型可以继续按 `op_rule_id` 去重。

### 5. NumericFeaturePlanner 输入输出

建议函数签名：

```python
def plan_exact_numeric_feature(
    feature_key: str,
    current_state: StateDict,
    target_value: str,
    rules: list[OpRule],
    max_steps: int = 50,
) -> NumericPlanResult:
    ...
```

返回结构：

```python
@dataclass
class NumericPlanResult:
    status: str  # success | no_solution | error
    steps: list[PlannedStep]
    final_state: StateDict | None = None
    error_code: str | None = None
    error_message: str | None = None
```

`error_code` 建议预留：

- `NUMERIC_NO_PROVIDER`
- `NUMERIC_EXACT_TARGET_UNREACHABLE`
- `NUMERIC_MAX_STEPS_EXCEEDED`
- `NUMERIC_INVALID_VALUE`

API 层可先继续映射为现有 `NO_SOLUTION` / `INTERNAL_ERROR`，但 Domain 层错误需要先结构化，后续再统一错误码协议。

### 6. 数值候选规则筛选

Phase 1 候选规则必须满足：

1. effect 中包含目标 `feature_key`
2. effect_type 是 `increment` 或 `decrement`
3. `delta_value` 非空且可转为数值
4. 推进方向朝向目标：
   - target > current 时，只允许正向推进 effect
   - target < current 时，只允许反向推进 effect
5. 应用该 effect 后不能离目标更远

排序规则：

1. 优先副作用更少的 rule
2. 再优先步长更大的 rule
3. 再优先 `duration_min` 更短的 rule

说明：

- 这只是 Phase 1 的结构性过滤，不替代 Phase 2 的业务主副作用标注。
- 若规则含多个 effects，必须通过 `RuleEvaluator.apply_effects()` 统一应用，不能手写 effect 分发。

### 7. 精确目标求解策略

Phase 1 建议使用“有界最短步数搜索”，而不是单纯贪心。

原因：

- `0 -> 30`，规则 `+20` 与 `+10`，贪心需要回退才能成功。
- 后续加入 precondition 后，纯 coin-change DP 也不足以表达可执行性。

最小策略：

```text
BFS over numeric value
  state: 当前 feature 数值 + 当前完整局部 state 快照
  edge: 应用一个候选 rule
  goal: feature_value == target_value
  cap: max_steps
```

Phase 1 可以先只在单 feature 数值空间内做 BFS，并通过 `RuleEvaluator.evaluate_preconditions()` 判断当前局部状态是否可执行。若 precondition 不满足，交给隐式子目标补齐逻辑处理。

### 8. 隐式子目标处理

数值链条中的每个候选 rule 执行前，都必须检查 preconditions。

若 precondition 不满足：

```text
precond(feature="pressure", operator="gte", value="2")
  -> 生成内部 GoalPredicate(feature="pressure", operator="gte", value="2")
  -> 调用子目标规划
  -> 子目标 steps 成为当前 step 的 predecessors
```

Phase 1 对外目标只支持 eq，但内部隐式子目标可以理解 `eq/gte/lte`，因为这些已经是 `op_rule_precond.operator` 的现有语义。

防循环规则：

- 使用 `visited_goals`，key 为 `(feature_key, operator, feature_value)`。
- 如果递归中再次遇到同一 key，返回 `error`，错误码建议 `NUMERIC_IMPLICIT_GOAL_CYCLE`。

### 9. RAG 合并规则

合并时遵守：

1. 数值同一 feature 的链式步骤必须串行。
2. 不同 feature 之间默认不建立边，除非存在 precondition 依赖。
3. 隐式子目标步骤必须作为依赖边连到消费它的 step。
4. enum 步骤与 numeric 步骤之间也只通过 precondition/effect 语义建边。
5. 资源冲突仍由 Scheduler 处理，Planner 不提前串行化资源冲突。

### 10. 持久化规则

Phase 1 不新增数据库字段。

落库仍使用现有：

- `candidate_plan`
- `candidate_plan_step.step_order`
- `candidate_plan_step.op_rule_id`
- `candidate_plan_step.predecessor_ids`

允许同一 `op_rule_id` 出现在多条 `candidate_plan_step` 中。

后续如 UI/运维需要显示“第 n 次 / 共 m 次”，再评估新增：

- `occurrence_index`
- `total_occurrences`
- `is_recurring`

但这些不是 Phase 1 必需条件。

---

## 完整测试链路

### 1. 测试分层

Phase 1 必须覆盖四层：

1. Unit：纯函数与 planner 子模块
2. Integration：真实数据库 + `build_rag()` + `save_candidate_plan()`
3. API：`POST /api/v1/solve` 同步求解响应
4. E2E：前端选择状态并提交求解，确认重复步骤显示与排程结果

### 2. Unit 测试

建议新增文件：

```text
tests/unit/test_numeric_planner.py
```

用例：

| 编号 | 场景 | 输入 | 期望 |
|------|------|------|------|
| U1 | 单规则重复执行 | `0 -> 80`, `+20` | 4 个 `PlannedStep`，同一 `op_rule_id` 可重复 |
| U2 | 多步长精确组合 | `0 -> 30`, `+20`, `+10` | 2 步成功，不返回 no_solution |
| U3 | 无法精确到达 | `0 -> 25`, `+20`, `+10` | `NUMERIC_EXACT_TARGET_UNREACHABLE` |
| U4 | 反向目标 | `80 -> 20`, `-20` | 3 步成功 |
| U5 | 方向过滤 | `0 -> 40`, `-20` | 不作为候选，返回无 provider |
| U6 | max_steps 防护 | `0 -> 1000`, `+1`, `max_steps=10` | `NUMERIC_MAX_STEPS_EXCEEDED` |
| U7 | 非数值输入 | current 或 target 为非数字 | `NUMERIC_INVALID_VALUE` |
| U8 | 副作用更少优先 | 纯 `+20` 与带副作用 `+20` 并存 | 优先纯规则 |
| U9 | 状态不可变 | 输入 state 在规划后不变 | 原 state 未被修改 |

必须断言：

- effect 应用通过 `RuleEvaluator`，结果值格式与 `EffectRegistry` 一致。
- 每个 step 的 `before_state` 与 `after_state` 连续一致。
- 同一 rule 重复执行时不会被去重。

### 3. Integration 测试

建议新增文件：

```text
tests/integration/test_numeric_planner_integration.py
```

用例：

| 编号 | 场景 | 验证点 |
|------|------|--------|
| I1 | 真实 DB 构建 `water_level 0 -> 80` | `build_rag()` 成功，RAG 有 4 个相同 `op_rule_code` 节点 |
| I2 | 保存 candidate plan | `candidate_plan_step` 有 4 行相同 `op_rule_id`，`step_order` 不同 |
| I3 | 数值链条串行依赖 | 第 2/3/4 步 predecessor 分别指向前一步 |
| I4 | 枚举 + 数值混合目标 | 枚举旧逻辑仍成功，数值步骤同时存在 |
| I5 | 隐式数值子目标 | 主规则需要 `pressure >= 2`，自动生成增压步骤并连边 |
| I6 | 循环隐式子目标 | A 需要 B，B 需要 A，返回结构化 error |
| I7 | Scheduler 兼容 | `solve_schedule()` 能调度重复 `op_rule_id` 的步骤 |

必须断言：

- `candidate_plan_step.predecessor_ids` 使用 step_order，不使用 op_rule_id。
- Scheduler 输出的 `tasks` 长度与 RAG 节点数一致。
- 重复 `op_rule_id` 不导致资源建模或任务提取丢失。

### 4. API 测试

建议新增或扩展：

```text
tests/integration/test_numeric_solve_api.py
```

用例：

| 编号 | 场景 | 请求 | 期望 |
|------|------|------|------|
| A1 | 数值目标成功 | `POST /api/v1/solve` | `status=done`，tasks 包含 4 个注水步骤 |
| A2 | 无法精确到达 | `target=25`，规则 `+20/+10` | `status=failed`，错误可诊断 |
| A3 | 旧枚举场景回归 | V0.1/V0.2 典型状态 | 响应与原测试一致 |
| A4 | 混合目标 | `water_level` + `calibration` | 两类步骤都存在，依赖正确 |

API 响应断言：

- HTTP 仍可按现有业务失败语义返回 200 + `status=failed`。
- 成功时 `schedule.tasks[*].step_order` 连续。
- 重复 rule 的 `op_rule_code` 在 `tasks` 中出现多次。

### 5. E2E 测试

建议新增文件：

```text
tests/e2e/test_numeric_planning.py
```

场景 E1：纯数值重复执行

```text
前置数据：
  feature_def: water_level number
  current_state: water_level=0
  target_state: water_level=80
  op_rule: OP_FILL_WATER, effect water_level increment 20

操作：
  通过前端选择 current/target，点击求解

期望：
  页面显示求解成功
  任务表出现 4 行 OP_FILL_WATER
  Gantt 图出现 4 个对应 bar
  4 个 bar 按 predecessor 串行或在调度结果中不违反前后依赖
```

场景 E2：混合枚举 + 数值目标

```text
前置数据：
  water_level: 0 -> 40
  calibration: off -> on
  OP_FILL_WATER: +20
  OP_CALIBRATE: calibration set on

期望：
  页面显示 2 个注水步骤 + 1 个校准步骤
  若 calibration 无依赖，可与注水链并行或由 Scheduler 按资源决定
```

场景 E3：隐式数值子目标

```text
前置数据：
  target: water_level=40
  OP_FILL_WATER precondition: pressure >= 2
  OP_PRESSURIZE effect: pressure +1

期望：
  结果中先出现 2 个 OP_PRESSURIZE
  OP_FILL_WATER 的第一步 predecessor 包含增压链最后一步
```

场景 E4：无解错误可诊断

```text
前置数据：
  target: water_level=25
  rules: +20, +10

期望：
  页面显示求解失败
  错误文案能区分为数值目标不可精确到达，而不是泛化系统错误
```

### 6. 回归测试要求

必须继续通过：

- `tests/unit/test_planner.py`
- `tests/unit/test_rule_evaluator.py`
- `tests/unit/test_effects.py`
- `tests/integration/test_planner_integration.py`
- `tests/integration/test_blockage_strategies.py`
- `tests/e2e/test_serial.py`
- `tests/e2e/test_parallel.py`

回归重点：

- 枚举型 `set` 规则仍走旧逻辑。
- 阻塞策略 B 仍通过状态注入与规则匹配触发，不因 numeric 分流而失效。
- Scheduler 不因重复 `op_rule_id` 丢失步骤。

---

## 实施顺序建议

### TICKET-014：Phase 1 设计落地准备

范围：

- 新增 `numeric.py` 空模块与 dataclass
- 增加 unit 测试骨架
- 不接入 `build_rag()`

验收：

- `NumericFeaturePlanner` 可纯内存生成 `0 -> 80` 的 4 个 step instances。

### TICKET-015：Phase 1 接入 build_rag

范围：

- `build_rag()` 按 feature type 分流
- 数值 steps 合并 RAG
- 保存 candidate plan 时支持重复 `op_rule_id`

验收：

- integration 测试 I1-I4 通过。

### TICKET-016：隐式子目标与 Scheduler/API/E2E 验证

范围：

- 数值 precondition 隐式子目标
- Scheduler/API/E2E 完整链路

验收：

- I5-I7、A1-A4、E1-E4 通过。

### TICKET-017：Phase 2 副作用歧义控制评估

范围：

- 基于真实测试数据评估结构性过滤是否足够
- 决定是否引入 `primary_feature_key`

验收：

- 有明确引入或暂缓依据。

---

## 本次不做（明确排除）

- 不直接开始代码实现，本票只冻结可实施设计
- 不先修改 Scheduler 核心建模
- 不先加数据库 occurrence 字段
- 不把 `primary_feature` 直接定为第一阶段主方案
- 不把 `gte/lte` 目标强塞进现有 `target_state` 语义

---

## 验收标准

```text
✅ 文档明确指出当前数值型规划失败的主根因
✅ 文档冻结“步骤实例化 + NumericFeaturePlanner”为第一阶段主方案
✅ 文档明确 `primary_feature` 不是第一阶段主方案
✅ 文档明确 `gte/lte` 目标作为后续显式 goal predicate 扩展
✅ 文档包含 unit / integration / API / e2e 完整测试链路
✅ STATE/TICKET 状态同步回写
```

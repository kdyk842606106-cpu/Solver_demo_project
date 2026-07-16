# 分层活动与分层状态需求文档

> 日期：2026-06-16
> 同步：2026-06-23，TICKET-036 后更新为当前模型口径
> 状态：当前需求基线 v2
> 适用范围：在现有 Integration Planning Solver 基础上，扩展分层分级活动管理、分层状态目标、维修维护自发式规划、活动连续性优化和规则健康诊断能力。

> 实现状态（2026-07-16）：本文核心能力已进入 V0.3 Beta，包括活动包 + 原子活动、任意深度状态目标、维护联合求解、Scope Guard、健康检查和状态包连续性。本文用于解释需求语义；当前接口以 `docs/protocols/` 为准。

---

## 1. 背景

当前系统已经具备以下底座：

- Planner / Scheduler / API / UI 闭环；
- 基于 precondition / effect 的规则驱动求解；
- 实例级 Partial Order Planner；
- 多资源 Scheduler；
- 数值型重复活动与 re-provider 能力；
- 阻塞重排、版本链和计划 diff；
- Excel 场景导入。

V0.3 已解决的核心问题是：真实业务活动和状态不是平铺结构，而是天然存在分层分级关系。系统支持计划员按业务层级管理活动、定义目标、组织维修维护能力，并让 Planner / Scheduler 自发生成必要活动集合、合并公共准备、跳过不必要步骤、形成紧凑排程。

本需求文档定义分层活动、分层状态、规则作用域、状态聚合、维修维护联合求解和活动连续性优化的目标语义。

---

## 2. 总体目标

系统需要从“平铺活动规则求解器”升级为：

> 支持活动能力包、可复用原子活动与任意深度状态目标树的计划求解系统。用户可以按活动范围、状态范围或维修维护意图提出目标；系统将目标展开为事实集合，将可用活动展开为能力集合，并由 Planner / Scheduler 自发生成满足目标的最小必要活动偏序和小时级排程。

目标结构：

```text
一级活动
  -> 二级活动
    -> 引用原子活动

状态目标树
  -> 聚合状态
    -> 原子状态（活跃无子节点）
```

核心方向：

- 原子活动是推荐的可复用执行能力；
- 一级、二级活动用于业务组织、作用域约束、目标范围、维修维护能力包、连续性分组和展示；
- legacy 三级 `activity_node` 保留为旧数据和导入兼容路径；
- 有子节点的状态是聚合状态；
- 活跃无子节点状态是原子状态，由当前状态、外部状态或原子活动 effect 判定；
- 上层状态完成由子状态全部达成自动聚合，不由活动直接写入；
- 维修维护不是固定序列，而是由目标事实和活动能力驱动的自发式规划；
- 活动连续性不是硬规则，而是 Scheduler 的软优化偏好。

---

## 3. 第一性原则

### 3.1 依赖来自状态事实，不来自手工 DAG

活动之间的必要先后关系应尽量由以下机制自然产生：

```text
activity A effects fact X
activity B requires fact X
=> A must precede B
```

不应默认把活动层级、维修包、人工序列或展示顺序转成硬依赖。

### 3.2 维修维护是能力集合，不是固定流程

维修维护二级活动不表示“必须执行整段序列”，而表示一个维修维护能力包：

```text
维修维护能力包 =
  候选原子活动集合
  默认维修目标事实
  公共作用域约束
  业务展示分组
```

用户标记“需要维修维护”时，系统注入的是维修意图和目标事实，而不是固定活动清单。

### 3.3 多个维修维护意图必须联合求解

多个维修维护意图不应分别求解后再合并，而应转成一个联合目标集合，由 Planner 一次性选择最小必要活动实例集合。

```text
maintenance intent A
maintenance intent B
=> joint goal facts
=> one Planner run
=> one partial-order plan
```

这样公共准备、公共恢复、公共测试等事实只需要被达成一次。

### 3.4 连续性来自优化代价，不来自硬编码规则

同一二级活动包下的原子活动应尽量连续，是因为现实中存在切换成本、准备复用成本和现场上下文成本。

因此连续性应作为 Scheduler 软优化目标，而不是硬性 precedence 或硬性连续窗口。

### 3.5 所有目标范围内状态默认必须完成

不引入 `required` 字段。用户选中了某个状态子树作为目标，该子树下所有状态默认都必须完成。

可选、暂不适用、删除、停用等语义应通过目标范围选择、数据生命周期或后续版本的适用性规则处理，不在本阶段引入 `required`。

---

## 4. 核心概念

### 4.1 活动能力

活动能力由活动包和原子活动共同表达：

| 对象 | 语义 | 是否可执行 | 主要用途 |
| --- | --- | --- | --- |
| 一级活动 | 系统、模块、大类或顶层业务范围 | 否 | 组织、目标范围、高层约束、展示 |
| 二级活动包 | 活动块、作业包、维修维护能力包 | 否 | 组织、公共约束、连续性亲和、维修目标入口 |
| 原子活动 | 可复用具体执行能力 / SOP 原子步骤 | 是 | Planner 选择、Scheduler 排程、资源占用 |
| legacy 三级活动节点 | 旧模型可执行活动节点 | 是 | 兼容既有数据、旧导入和旧测试 |

新数据优先通过 `atomic_activity` 成为 Scheduler task；legacy 三级活动节点仍可展开并调度。

### 4.2 状态目标树

状态支持任意深度树：

| 对象 | 语义 | 完成方式 |
| --- | --- | --- |
| 聚合状态 | 顶层或中层业务目标状态 | 其下所有活跃子状态完成 |
| 原子状态 | 活跃无子节点的可判定状态 | 当前状态、外部状态或活动 effect 满足 |

聚合状态不绑定事实；原子状态绑定 `feature_key/operator/target_value`。当前普通维护流只支持原子状态 `operator=eq` 的自动特征定义补齐。

### 4.3 状态维度

状态以 `feature_key` 作为状态维度锚点：

```text
feature_key = power_state
value = on / off
```

同一个 `feature_key` 的不同取值天然互斥。首期不单独建设状态互斥组。

治理要求：

```text
不要把同一状态维度拆成多个布尔 feature。
例如不要建 power_on / power_off，
应建 power_state = on / off。
```

---

## 5. 规则语义

系统不应把所有规则都建成同一种 `rule`。建议区分三类语义。

### 5.1 Activity Rule

Activity Rule 是原子活动的可执行规则。

归属：

```text
推荐挂在 `atomic_activity` 上；旧 `activity_node_id` 仅用于 legacy 三级活动节点兼容
```

包含：

- preconditions；
- effects；
- duration_min；
- resource_reqs；
- activity category；
- activity metadata。

Planner 使用 Activity Rule 决定某个原子活动能否执行，以及执行后产生哪些状态变化。

### 5.2 Scope Guard

Scope Guard 是挂在一级或二级活动上的作用域公共约束。

归属：

```text
一级活动或二级活动
```

包含：

- preconditions；
- constraint metadata；
- source activity scope。

不允许包含：

- effects；
- duration；
- resource_reqs。

语义：

```text
Scope Guard 不是可执行活动，也不会产生状态。
它只是在求解前动态追加到作用域内原子活动或 legacy 活动节点的有效前置条件中。
```

### 5.3 Aggregation Rule

Aggregation Rule 是系统内置的状态聚合规则，不要求用户逐条维护。

语义：

```text
聚合状态完成 = 其下所有活跃子状态完成
原子状态完成 = 自身条件达成
```

活动不允许直接写入一级、二级状态完成。

---

## 6. 状态引用约束

活动规则引用状态时，需遵守以下约束：

| 规则归属 | 可引用状态层级 |
| --- | --- |
| 一级活动 Scope Guard | 应引用高层业务状态 |
| 二级活动 Scope Guard | 可引用高层或下层状态 |
| 原子活动 Activity Rule | 可引用任意层级状态 |

解释：

- 一级活动只表达高层语义，避免直接绑定过细状态；
- 二级活动可承接跨层公共约束；
- 原子活动作为最终执行能力，可引用实际执行需要的任意层级状态；
- 若一级活动 Scope Guard 继承到原子活动，其来源仍必须保留为一级活动，不视为原子活动直接绑定高层状态。

---

## 7. 状态完成语义

### 7.1 目标展开

当用户选择上层状态作为目标时，系统应递归展开为活跃无子节点的原子状态目标。

示例：

```text
目标：一级状态 A 完成
=> A 下所有二级状态完成
=> 所有子树叶子原子状态完成
=> Planner 追踪这些原子目标事实
```

### 7.2 上层状态不可直接写入

禁止：

```text
原子活动 effect -> 聚合状态 = completed
```

允许：

```text
原子活动 effect -> 原子状态满足
聚合状态由子状态聚合
```

### 7.3 完成度展示

系统应支持按状态树展示完成度：

```text
一级状态 A：8/10 个原子状态已满足
二级状态 B：3/3 已完成
二级状态 C：5/7 未完成
原子状态 D：由活动 OPS012 达成
```

---

## 8. 求解前展开

Planner 不直接处理上层活动和上层状态。求解前应先进行展开。

流程：

```text
1. 用户选择目标状态范围、活动范围或维修维护意图
2. 展开目标状态树，得到原子目标事实集合
3. 展开活动范围，得到候选原子活动或 legacy 活动集合
4. 为每个候选执行能力计算 effective preconditions：
   自身 Activity Rule preconditions
   + 所属二级活动 Scope Guard
   + 所属一级活动 Scope Guard
5. effects 只来自候选执行能力自身 Activity Rule
6. 将展开后的活动能力集合和目标事实集合交给 Planner
```

展开时必须保留来源：

```text
precondition source =
  self_activity_rule
  parent_level_2_scope_guard
  parent_level_1_scope_guard
```

这些来源用于解释和诊断。

---

## 9. 维修维护需求

### 9.1 维修维护同样使用活动包和原子活动

维修维护活动不单独建立平铺结构，而是纳入统一活动树。

示例：

```text
一级活动：真空系统
  二级活动：真空阀组维修维护能力包
    原子活动：停机隔离
    原子活动：释放真空
    原子活动：拆卸阀组
    原子活动：更换密封件
    原子活动：复装阀组
    原子活动：泄漏测试
    原子活动：恢复真空
```

### 9.2 维修维护请求不是执行固定序列

用户标记某模块需要维修维护时，系统不应直接把该二级活动包下所有原子活动加入计划。

正确语义：

```text
维修维护请求
=> 注入当前异常事实或维修意图
=> 生成 desired goal facts
=> Planner 在候选能力集合中选择最小必要活动实例
```

示例：

```text
用户标记：真空阀组需要维修
系统注入：
  valve_status = leaking
目标事实：
  valve_status = ok
  leak_test = passed
```

Planner 自己判断：

- 哪些前置状态当前已满足；
- 哪些准备活动必须补齐；
- 哪些维修步骤可跳过；
- 哪些步骤可与其他维修目标共享；
- 是否需要恢复被破坏的目标状态。

### 9.3 顺序由 precondition / effect 自然涌现

维修维护原子活动不应通过固定序列强制全部执行。

推荐表达：

```text
拆卸阀组 requires vacuum_released = true
释放真空 effects vacuum_released = true

复装阀组 requires valve_removed = true
拆卸阀组 effects valve_removed = true

泄漏测试 requires valve_installed = true
复装阀组 effects valve_installed = true
```

因此如果当前状态已经满足 `vacuum_released = true`，Planner 可以跳过释放真空。

### 9.4 多个维修维护意图联合求解

多个维修维护意图必须转成联合目标事实，一次性求解。

禁止流程：

```text
维修 A 求一段序列
维修 B 求一段序列
最后尝试合并
```

目标流程：

```text
维修 A 意图
维修 B 意图
=> joint_goal_facts
=> one Planner run
=> one minimum necessary activity set
```

这样公共准备和公共恢复可以自然只出现一次。

### 9.5 公共事实只需达成一次

默认事实是持续有效的 persistent fact。

示例公共事实：

```text
equipment_stopped = true
vacuum_released = true
safety_locked = true
work_area_clean = true
```

如果两个维修目标都需要这些事实，Planner 应只生成一次 provider 活动，并用同一个 provider 支持多个后续分支。

目标计划形态：

```text
公共准备
  -> 维修 A 独有步骤
  -> 维修 B 独有步骤
公共恢复 / 公共验证
```

未来如需表达一次性消耗、时效性或排他性，可扩展 fact lifetime；本阶段默认不引入复杂 lifetime 模型。

---

## 10. Planner 能力需求

Planner 需要支持以下能力。

### 10.1 联合目标求解

输入应是一个目标事实集合，而不是单个目标或单段活动序列。

```text
current_state
joint_goal_facts
candidate_activity_rules
scope_guards
=> partial-order plan
```

### 10.2 最小必要活动集

Planner 应优先选择满足全部目标的最小活动实例集合。

推荐优化优先级：

```text
1. 满足所有目标事实
2. 活动实例数量最少
3. 总 duration_min 最短
4. 状态破坏更少
5. 后续 Scheduler 更容易形成紧凑排程
```

### 10.3 Multi-goal Provider

Planner 选择 provider 时，不应只局部满足一个 open precondition。

应评估：

```text
一个候选活动能覆盖多少当前未满足事实
一个候选活动能否同时服务多个维修维护分支
一个候选活动是否减少后续 re-provider 需求
```

这使 Planner 更接近集合覆盖式选择：

```text
候选活动 = 一个事实覆盖集合
选择更少活动覆盖更多目标和前置事实
```

### 10.4 Re-provider

如果某活动破坏了后续仍需要的事实，Planner 应尝试插入重新提供该事实的活动。

若无法恢复，应返回结构化诊断：

```text
STATE_INVALIDATED_NO_REPROVIDER
```

---

## 11. Scheduler 能力需求

### 11.1 Scheduler 只排执行能力实例

Scheduler task 来自 Planner 选中的 Activity Rule 实例。新模型下推荐规则绑定到 `atomic_activity_id`；legacy 规则仍可通过三级 `activity_node_id` 进入排程。

一级、二级活动不进入 Scheduler task 列表，不直接占用资源。

### 11.2 连续性作为软优化目标

同一二级活动包下的原子活动应尽量紧凑，但不能强制连续。

连续性优化不得破坏：

```text
1. 状态依赖
2. 资源可行性
3. 最小必要活动集
4. not_before / blockage 等硬约束
```

### 11.3 自发式连续性代价

Scheduler 可引入以下软成本项：

```text
group_span_cost:
  同一二级活动内，最晚结束时间 - 最早开始时间 越小越好

group_gap_cost:
  同一二级活动包内，相邻原子活动之间空档越小越好

group_interruption_cost:
  同一二级活动执行窗口中插入其他二级活动，惩罚越高

setup_reuse_cost:
  共享准备状态、工装、区域或维修上下文的活动越靠近越好
```

这些成本应作为软目标，不应让可行排程变成无解。

### 11.4 连续性解释

系统应能解释：

- 哪些活动因同属二级活动被排得更紧凑；
- 哪些活动因为资源冲突或前置条件被合理打散；
- 同一维修维护能力包是否形成连续窗口；
- 公共准备是否被多个分支复用。

---

## 12. 可达性与规则健康检查

因为目标范围内所有原子状态默认必须完成，系统必须在求解前做规则健康检查。

### 12.1 Provider / Consumer 图

系统应建立以下关系：

```text
状态事实 -> 被哪些活动需要
活动 -> 会产生哪些状态事实
活动 -> 会改变哪些 feature_key
```

### 12.2 目标可达性检查

对每个原子目标状态检查：

| 诊断码 | 含义 |
| --- | --- |
| OK | 当前已满足或存在 provider |
| NO_PROVIDER | 没有任何活动能产生该状态 |
| AMBIGUOUS_PROVIDER | 多个 provider，需要排序、代价选择或业务确认 |
| BROKEN_CHAIN | provider 的前置条件没有 provider |
| SELF_DEPENDENCY | 父级公共约束依赖自身子树完成后才成立 |
| CONFLICTING_GOAL | 同一 feature_key 上存在互斥目标值 |

### 12.3 Scope Guard 检查

需要检查 Scope Guard 是否导致子树不可执行。

示例：

```text
二级活动公共前置 requires clean_area = true
但 clean_area = true 只能由该二级活动包下的某个原子活动产生
=> SELF_DEPENDENCY
```

### 12.4 状态回放校验

求解后应按计划偏序的一种合法拓扑序或 Scheduler 结果回放状态变化：

```text
start_state
-> activity_1 effects
-> activity_2 effects
-> ...
-> final_state
```

校验：

- 每个活动执行时 precondition 是否成立；
- 所有目标原子状态最终是否仍成立；
- 聚合状态是否可由下级状态重新聚合为完成；
- 被破坏的目标事实是否有 re-provider 修复。

---

## 13. 目标输入方式

系统应逐步支持三类目标入口。

### 13.1 状态范围目标

用户选择状态树节点：

```text
一级状态
二级状态
多个原子状态
```

系统展开为原子目标事实集合。

### 13.2 活动范围目标

用户选择活动树节点：

```text
一级活动
二级活动
多个原子活动或 legacy 活动节点
```

系统展开为候选执行能力集合。

若候选范围内活动的前置条件需要范围外 provider，系统可提供两种策略：

```text
strict mode:
  不允许补入范围外活动，返回缺失 provider 诊断

completion mode:
  允许补入必要范围外 provider，并标记 external_dependency
```

首期建议默认 strict mode。

### 13.3 维修维护意图

用户标记一个或多个维修维护意图：

```text
scope_node_id
issue_type
observed_facts
desired_goal_facts
```

系统将多个意图合并为联合目标事实集合后一次性求解。

---

## 14. 展示与解释需求

### 14.1 活动层级展示

计划结果应按活动树展示：

```text
一级活动
  二级活动
    原子活动任务 1
    原子活动任务 2
```

Gantt 和任务表应支持按一级、二级活动折叠。

### 14.2 状态层级展示

计划结果应按状态树展示目标完成情况：

```text
一级状态完成度
二级状态完成度
原子状态来源活动
不可达状态诊断
```

### 14.3 规则来源解释

每个原子活动的有效前置条件应展示来源：

```text
self activity rule
level 2 scope guard
level 1 scope guard
```

### 14.4 维修维护解释

维修维护计划需要解释：

- 哪些维修意图被合并；
- 哪些公共准备活动被复用；
- 哪些原子活动被跳过，原因是当前状态已满足或目标不需要；
- 哪些恢复 / 测试活动被共享；
- 哪些状态被维修活动破坏并重新提供。

### 14.5 连续性解释

排程结果需要解释：

- 同一二级活动下的任务是否形成紧凑窗口；
- 若没有连续，原因是资源冲突、前置条件还是更优全局工期；
- 软连续性成本是否影响了排序。

---

## 15. 数据模型建议

以下为概念模型，具体字段名应在技术设计阶段与现有 ORM / schema 对齐。

### 15.1 activity_node

```text
id
parent_id
level: 1 / 2; legacy 3 仅用于兼容旧数据
code
name
activity_category: normal / repair / maintenance
sort_order
active
metadata_json
```

### 15.2 atomic_activity

```text
id
machine_type_id
code
name
activity_category: normal / repair / maintenance
sort_order
active
metadata_json
```

### 15.3 activity_package_atomic_ref

```text
id
activity_node_id      # level 2 package
atomic_activity_id
sort_order
active
metadata_json
```

### 15.4 state_node

```text
id
parent_id
level >= 1
code
name
feature_key          # atomic leaf only
operator             # atomic leaf only
target_value         # atomic leaf only
state_kind: atomic / aggregate / external / manual
active
metadata_json
```

### 15.5 activity_rule

```text
id
atomic_activity_id   # preferred executable binding
activity_node_id     # legacy level-3 binding
op_rule_id            # 可复用现有 op_rule
preconditions
effects
duration_min
resource_reqs
active
```

### 15.6 scope_guard

```text
id
activity_node_id      # level 1 or level 2
preconditions
active
metadata_json
```

### 15.7 maintenance_intent_template

```text
id
scope_activity_node_id
issue_type
observed_fact_templates
desired_goal_fact_templates
candidate_activity_scope
active
```

---

## 16. 分期计划

说明：本节记录分层能力从 TICKET-024 到 TICKET-036 的现行基线。早期票据中的双三层设计已被 TICKET-036 扩展为状态任意深度树和原子活动模型。

### Phase 1：分层数据底座

目标：建立活动包、状态树和兼容旧三层数据的底座。

范围：

- 新增活动树管理；
- 新增状态树管理；
- legacy 三级活动可关联现有 `op_rule`；
- 一级、二级活动支持 Scope Guard；
- Excel 导入支持活动层级和状态层级列；
- 前端增加活动树、状态树管理入口。

不做：

- 不改变 Planner 主流程；
- 不做维修维护联合求解；
- 不做连续性优化。

### Phase 2：目标展开与 Effective Rule 展开

目标：让分层结构能进入求解前处理。

范围：

- 状态目标树展开为原子目标事实；
- 活动范围展开为候选执行能力集合；
- Scope Guard 动态注入为原子活动或 legacy 活动有效前置条件；
- 保留前置条件来源；
- effects 仍只来自候选执行能力自身 Activity Rule；
- 基础解释字段返回。

### Phase 3：可达性和健康检查

目标：在真实数据进入求解前发现规则缺口。

范围：

- Provider / Consumer 图；
- `NO_PROVIDER`；
- `BROKEN_CHAIN`；
- `SELF_DEPENDENCY`；
- `CONFLICTING_GOAL`；
- Scope Guard 导致子树不可执行诊断；
- 导入后诊断和求解前诊断。

### Phase 4：Planner / Scheduler 接入

目标：Planner 和 Scheduler 正式消费展开后的分层规则。

范围：

- Planner 接收联合目标事实集合；
- Planner 接收候选执行能力集合；
- Scheduler 只排执行能力实例；
- 计划结果按活动树和状态树汇总；
- 求解后状态回放校验；
- 解释每条有效前置条件和目标事实来源。

### Phase 5：维修维护自发式规划与连续性优化

目标：让维修维护和同组连续性通过 Planner / Scheduler 的能力自然实现。

范围：

- 维修维护活动纳入统一活动包和原子活动结构；
- 二级维修维护活动作为能力包，而非固定序列；
- 维修维护意图转 observed facts 和 desired goal facts；
- 多个维修维护意图联合求解；
- Planner 支持 multi-goal provider 选择；
- 公共准备、公共恢复、公共测试只生成一次；
- 不必要维修步骤可被自然跳过；
- Scheduler 引入 group span / gap / interruption / setup reuse 软成本；
- 计划结果解释维修融合和连续性结果。

暂不纳入：

- 历史人工计划顺序；
- 推荐顺序；
- 活动块连续性硬约束；
- 跨块切换成本的复杂业务建模；
- 人员班组和班次排程。

---

## 17. 非目标

本阶段不做：

- 把一级、二级活动作为可执行 Scheduler task；
- 把上层活动 rule 的 effect 复制到子活动；
- 让活动直接 set 一级、二级状态完成；
- 将维修维护能力包固定展开为完整序列；
- 维修 A、维修 B 分别求解后再事后合并；
- 强制同一二级活动包下所有原子活动硬连续；
- 单独建设状态互斥组；
- 引入 `required` 字段控制目标子状态是否必须完成；
- 引入历史人工计划顺序和推荐顺序软约束。

---

## 18. 验收标准

### 18.1 分层结构

- 可以创建一级、二级活动包；
- 可以创建原子活动，并把原子活动引用到二级活动包；
- 可以创建任意深度状态目标树；
- 活跃无子节点状态作为原子状态；
- 原子活动可以关联可执行规则；
- legacy 三级活动节点仍可被读取和导入；
- 一级、二级活动可以配置 Scope Guard；
- 一级活动 Scope Guard 只能引用一级状态。

### 18.2 状态聚合

- 选择聚合状态作为目标时，会展开为所有活跃叶子原子目标；
- 聚合状态完成度由下级状态自动汇总；
- 活动 effect 不能直接写入聚合状态完成。

### 18.3 Effective Rule

- 原子活动求解前置条件 = 自身前置 + 二级 Scope Guard + 一级 Scope Guard；
- 每条前置条件保留来源；
- effects 只来自原子活动或 legacy 活动自身 Activity Rule。

### 18.4 可达性诊断

- 无 provider 的原子目标状态能被识别；
- provider 前置断链能被识别；
- Scope Guard 自依赖能被识别；
- 同一 `feature_key` 的互斥目标值能被识别。

### 18.5 维修维护

- 标记一个维修维护意图后，系统不是固定展开整段维修包，而是按目标事实求解；
- 当前状态已满足的准备步骤可被跳过；
- 多个维修维护意图能联合求解；
- 公共准备活动不会重复生成；
- 公共恢复 / 测试活动可被多个维修分支共享；
- 无法恢复的被破坏状态返回结构化错误。

### 18.6 连续性

- 同一二级活动包下的原子活动在资源允许时更紧凑；
- 资源冲突或前置条件导致打散时，系统仍能给出可行排程；
- 连续性不作为硬约束导致无解；
- 排程结果能解释同组活动为何连续或为何被打散。

---

## 19. 关键风险

1. 如果把二级维修维护活动误建成固定序列，会破坏自发式规划。
2. 如果 Scope Guard 包含 effect，会导致上层状态被错误复制到子活动。
3. 如果一级、二级状态允许被活动直接 set，会破坏状态聚合语义。
4. 如果多个维修意图分别求解后再合并，公共准备会重复，无法满足最短必要活动集原则。
5. 如果连续性做成硬约束，可能把原本可行的排程变成无解。
6. 如果同一状态维度被拆成多个布尔 feature，会削弱天然互斥和状态覆盖语义。
7. 如果缺少 Provider / Consumer 健康检查，真实数据导入后会表现为 Planner 无解，而不是可修复的数据诊断。

---

## 20. 下一步建议

建议先创建第一张实现票，范围控制在 Phase 1 + Phase 2：

```text
活动 / 状态双三层结构
Scope Guard 数据模型
目标状态展开
effective rule 展开
基础解释字段
```

原因：

- 这是后续维修维护自发式规划和连续性优化的前置底座；
- 不需要立即重写 Planner / Scheduler；
- 可以先通过导入和管理页面验证数据结构是否符合业务认知；
- 能逐步把系统入口从 `target_state_id` 过渡到状态树 / 活动树目标。

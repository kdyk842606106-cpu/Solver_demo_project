# 分层活动与分层状态需求文档

> 日期：2026-06-16
> 状态：需求草案 v1
> 适用范围：在现有 Integration Planning Solver 基础上，扩展分层分级活动管理、分层状态目标、维修维护自发式规划、活动连续性优化和规则健康诊断能力。

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

下一阶段需要解决的问题是：真实业务活动和状态不是平铺结构，而是天然存在分层分级关系。系统需要支持计划员按业务层级管理活动、定义目标、组织维修维护能力，并让 Planner / Scheduler 尽量自发地生成必要活动集合、合并公共准备、跳过不必要步骤、形成紧凑排程。

本需求文档定义分层活动、分层状态、规则作用域、状态聚合、维修维护联合求解和活动连续性优化的目标语义。

---

## 2. 总体目标

系统需要从“平铺活动规则求解器”升级为：

> 支持活动与状态双三层结构的计划求解系统。用户可以按活动范围、状态范围或维修维护意图提出目标；系统将目标展开为事实集合，将可用活动展开为能力集合，并由 Planner / Scheduler 自发生成满足目标的最小必要活动偏序和小时级排程。

目标结构：

```text
一级活动
  -> 二级活动
    -> 三级活动

一级状态
  -> 二级状态
    -> 三级状态
```

核心方向：

- 三级活动是最终可执行单元；
- 一级、二级活动用于业务组织、作用域约束、目标范围、维修维护能力包和展示；
- 一级、二级状态是聚合状态；
- 三级状态是原子状态，由当前状态、外部状态或三级活动 effect 判定；
- 上层状态完成由下一层状态全部达成自动聚合，不由活动直接写入；
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
  候选三级活动集合
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

同一二级活动下的三级活动应尽量连续，是因为现实中存在切换成本、准备复用成本和现场上下文成本。

因此连续性应作为 Scheduler 软优化目标，而不是硬性 precedence 或硬性连续窗口。

### 3.5 所有目标范围内状态默认必须完成

不引入 `required` 字段。用户选中了某个状态子树作为目标，该子树下所有状态默认都必须完成。

可选、暂不适用、删除、停用等语义应通过目标范围选择、数据生命周期或后续版本的适用性规则处理，不在本阶段引入 `required`。

---

## 4. 核心概念

### 4.1 活动层级

活动分为三层：

| 层级 | 语义 | 是否可执行 | 主要用途 |
| --- | --- | --- | --- |
| 一级活动 | 系统、模块、大类或顶层业务范围 | 否 | 组织、目标范围、高层约束、展示 |
| 二级活动 | 活动块、作业包、维修维护能力包 | 否 | 组织、公共约束、连续性亲和、维修目标入口 |
| 三级活动 | 具体执行活动 / SOP 原子步骤 | 是 | Planner 选择、Scheduler 排程、资源占用 |

只有三级活动可以成为 Scheduler task。

### 4.2 状态层级

状态分为三层：

| 层级 | 语义 | 完成方式 |
| --- | --- | --- |
| 一级状态 | 顶层业务目标状态 | 其下所有二级状态完成 |
| 二级状态 | 中层业务目标状态 | 其下所有三级状态完成 |
| 三级状态 | 原子可判定状态 | 当前状态、外部状态或活动 effect 满足 |

一级、二级状态是聚合状态；三级状态是原子状态。

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

Activity Rule 是三级活动的可执行规则。

归属：

```text
只允许挂在三级活动上
```

包含：

- preconditions；
- effects；
- duration_min；
- resource_reqs；
- activity category；
- activity metadata。

Planner 使用 Activity Rule 决定某个三级活动能否执行，以及执行后产生哪些状态变化。

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
它只是在求解前动态追加到作用域内三级活动的有效前置条件中。
```

### 5.3 Aggregation Rule

Aggregation Rule 是系统内置的状态聚合规则，不要求用户逐条维护。

语义：

```text
一级状态完成 = 其下所有二级状态完成
二级状态完成 = 其下所有三级状态完成
三级状态完成 = 自身条件达成
```

活动不允许直接写入一级、二级状态完成。

---

## 6. 状态引用约束

活动规则引用状态时，需遵守以下约束：

| 规则归属 | 可引用状态层级 |
| --- | --- |
| 一级活动 Scope Guard | 只能引用一级状态 |
| 二级活动 Scope Guard | 可引用一级、二级、三级状态 |
| 三级活动 Activity Rule | 可引用一级、二级、三级状态 |

解释：

- 一级活动只表达一级语义，不能直接绑定二级、三级细节状态；
- 二级活动可承接跨层公共约束；
- 三级活动作为最终执行单元，可引用实际执行需要的任意层级状态；
- 若一级活动 Scope Guard 继承到三级活动，其来源仍必须保留为一级活动，不视为三级活动直接绑定一级状态。

---

## 7. 状态完成语义

### 7.1 目标展开

当用户选择上层状态作为目标时，系统应递归展开为三级叶子状态目标。

示例：

```text
目标：一级状态 A 完成
=> A 下所有二级状态完成
=> 所有二级状态下的所有三级状态完成
=> Planner 追踪这些三级目标事实
```

### 7.2 上层状态不可直接写入

禁止：

```text
三级活动 effect -> 一级状态 = completed
三级活动 effect -> 二级状态 = completed
```

允许：

```text
三级活动 effect -> 三级状态满足
二级状态由三级状态聚合
一级状态由二级状态聚合
```

### 7.3 完成度展示

系统应支持按状态树展示完成度：

```text
一级状态 A：8/10 个三级叶子状态已满足
二级状态 B：3/3 已完成
二级状态 C：5/7 未完成
三级状态 D：由活动 OPS012 达成
```

---

## 8. 求解前展开

Planner 不直接处理上层活动和上层状态。求解前应先进行展开。

流程：

```text
1. 用户选择目标状态范围、活动范围或维修维护意图
2. 展开目标状态树，得到三级目标事实集合
3. 展开活动树，得到候选三级活动集合
4. 为每个三级活动计算 effective preconditions：
   自身 Activity Rule preconditions
   + 所属二级活动 Scope Guard
   + 所属一级活动 Scope Guard
5. effects 只来自三级活动自身 Activity Rule
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

### 9.1 维修维护同样使用三层活动结构

维修维护活动不单独建立平铺结构，而是纳入统一活动树。

示例：

```text
一级活动：真空系统
  二级活动：真空阀组维修维护能力包
    三级活动：停机隔离
    三级活动：释放真空
    三级活动：拆卸阀组
    三级活动：更换密封件
    三级活动：复装阀组
    三级活动：泄漏测试
    三级活动：恢复真空
```

### 9.2 维修维护请求不是执行固定序列

用户标记某模块需要维修维护时，系统不应直接把该二级活动下所有三级活动加入计划。

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

维修维护三级活动不应通过固定序列强制全部执行。

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

### 11.1 Scheduler 只排三级活动

Scheduler task 只能来自三级 Activity Rule 实例。

一级、二级活动不进入 Scheduler task 列表，不直接占用资源。

### 11.2 连续性作为软优化目标

同一二级活动下的三级活动应尽量紧凑，但不能强制连续。

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
  同一二级活动内，相邻三级活动之间空档越小越好

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

因为目标范围内所有三级状态默认必须完成，系统必须在求解前做规则健康检查。

### 12.1 Provider / Consumer 图

系统应建立以下关系：

```text
状态事实 -> 被哪些活动需要
活动 -> 会产生哪些状态事实
活动 -> 会改变哪些 feature_key
```

### 12.2 目标可达性检查

对每个三级目标状态检查：

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
但 clean_area = true 只能由该二级活动下的某个三级活动产生
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
- 所有目标三级状态最终是否仍成立；
- 一级、二级状态是否可由下级状态重新聚合为完成；
- 被破坏的目标事实是否有 re-provider 修复。

---

## 13. 目标输入方式

系统应逐步支持三类目标入口。

### 13.1 状态范围目标

用户选择状态树节点：

```text
一级状态
二级状态
多个三级状态
```

系统展开为三级目标事实集合。

### 13.2 活动范围目标

用户选择活动树节点：

```text
一级活动
二级活动
多个三级活动
```

系统展开为候选三级活动集合。

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
    三级活动任务 1
    三级活动任务 2
```

Gantt 和任务表应支持按一级、二级活动折叠。

### 14.2 状态层级展示

计划结果应按状态树展示目标完成情况：

```text
一级状态完成度
二级状态完成度
三级状态来源活动
不可达状态诊断
```

### 14.3 规则来源解释

每个三级活动的有效前置条件应展示来源：

```text
self activity rule
level 2 scope guard
level 1 scope guard
```

### 14.4 维修维护解释

维修维护计划需要解释：

- 哪些维修意图被合并；
- 哪些公共准备活动被复用；
- 哪些三级活动被跳过，原因是当前状态已满足或目标不需要；
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
level: 1 / 2 / 3
code
name
activity_category: normal / repair / maintenance
sort_order
active
metadata_json
```

### 15.2 state_node

```text
id
parent_id
level: 1 / 2 / 3
feature_key
name
value_type: bool / enum / number / string
state_kind: atomic / aggregate / external / manual
active
metadata_json
```

### 15.3 activity_rule

```text
id
activity_node_id      # only level 3
op_rule_id            # 可复用现有 op_rule
preconditions
effects
duration_min
resource_reqs
active
```

### 15.4 scope_guard

```text
id
activity_node_id      # level 1 or level 2
preconditions
active
metadata_json
```

### 15.5 maintenance_intent_template

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

### Phase 1：分层数据底座

目标：建立活动和状态双三层结构。

范围：

- 新增活动树管理；
- 新增状态树管理；
- 三级活动关联现有 `op_rule`；
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

- 状态目标树展开为三级目标事实；
- 活动范围展开为候选三级活动集合；
- Scope Guard 动态注入为三级活动有效前置条件；
- 保留前置条件来源；
- effects 仍只来自三级 Activity Rule；
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
- Planner 接收候选三级活动集合；
- Scheduler 只排三级活动；
- 计划结果按活动树和状态树汇总；
- 求解后状态回放校验；
- 解释每条有效前置条件和目标事实来源。

### Phase 5：维修维护自发式规划与连续性优化

目标：让维修维护和同组连续性通过 Planner / Scheduler 的能力自然实现。

范围：

- 维修维护活动纳入统一活动三层结构；
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
- 强制同一二级活动下所有三级活动硬连续；
- 单独建设状态互斥组；
- 引入 `required` 字段控制目标子状态是否必须完成；
- 引入历史人工计划顺序和推荐顺序软约束。

---

## 18. 验收标准

### 18.1 分层结构

- 可以创建一级、二级、三级活动；
- 可以创建一级、二级、三级状态；
- 三级活动可以关联可执行规则；
- 一级、二级活动可以配置 Scope Guard；
- 一级活动 Scope Guard 只能引用一级状态。

### 18.2 状态聚合

- 选择一级状态作为目标时，会展开为所有三级叶子目标；
- 一级、二级状态完成度由下级状态自动汇总；
- 活动 effect 不能直接写入一级、二级状态完成。

### 18.3 Effective Rule

- 三级活动求解前置条件 = 自身前置 + 二级 Scope Guard + 一级 Scope Guard；
- 每条前置条件保留来源；
- effects 只来自三级 Activity Rule。

### 18.4 可达性诊断

- 无 provider 的三级目标状态能被识别；
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

- 同一二级活动下的三级活动在资源允许时更紧凑；
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


# 多阻塞场景下维修序列与活动恢复设计文档

> 文档类型：正式设计文档
> 适用版本：V0.2 现状分析 / V0.3 候选设计
> 相关文档：`docs/ANCHOR.md`、`docs/STATE_V0.3.md`、`docs/v0.2-spec.md`

---

## 1. 背景与问题定义

当前系统在策略 B（插入维修序列）下，支持通过向当前状态注入 `blockage_reason` 来触发维修规则，再由 RAGBuilder 基于通用 `precondition/effect` 规则推导维修工序并生成排程。

现有实现可正确做到：

- 根据 `blockage_reason` 自动匹配维修活动
- 将维修活动纳入 RAG
- 由 Scheduler 基于依赖边和资源约束完成排程

但在部分场景下，会出现以下问题：

- 某被阻塞活动 `OP_X` 已插入对应维修活动 `OP_REPAIR_X`
- 业务语义要求：`OP_REPAIR_X` 必须先完成，`OP_X` 才能恢复执行
- 实际结果中，`OP_REPAIR_X` 与 `OP_X` 有时会被并行安排

该问题在单阻塞场景下已经存在，而在多阻塞场景下会进一步放大。

---

## 2. 根因分析

### 2.1 当前依赖推导机制

系统当前的依赖边来自 `precondition/effect` 自动推导，符合 `ANCHOR.md` 中的架构原则：

- `RAGBuilder` 仅负责通用规则匹配和依赖推导
- `Scheduler` 仅消费 RAG 中已有的 precedence 关系与资源约束
- 阻塞语义不应通过 Scheduler 特判或 API 补丁来表达

因此，只有在以下条件成立时，系统才会自然生成 `repair -> blocked_op` 依赖边：

- 维修工序的 effect 改变了某个状态
- 被阻塞活动的 precondition 明确依赖该状态

### 2.2 并行问题的直接原因

当被阻塞活动本身没有显式声明“维修完成后才能执行”的前置状态时：

- 维修活动虽被插入到 RAG 中
- 但原活动没有任何 precondition 指向维修工序的 effect
- 系统无法推出两者之间的 predecessor 关系
- 最终排程允许它们并行

例如：

- 维修活动 effect：`blockage_reason = none`
- 原活动没有 precondition：`blockage_reason = none`

则维修活动与原活动之间不存在显式状态依赖。

---

## 3. 设计目标

本设计文档关注以下目标：

1. 保证维修活动完成后，相关业务活动才能恢复执行
2. 支持多阻塞同时存在，而不会出现错误放行
3. 不违反 `ANCHOR.md` 中的架构原则
4. 尽量保持规则驱动，避免在调度层引入业务特判
5. 为 V0.3 及后续扩展保留可演进空间

本设计文档不直接包含代码实现与迁移脚本，只给出建模与架构建议。

---

## 4. 约束条件

根据 `docs/ANCHOR.md`，本问题的设计必须满足以下约束：

- 所有 precondition 匹配和 effect 应用必须经过 `RuleEvaluator`
- 不能在 `RAGBuilder` / `Scheduler` / `API` 层直接写业务型 precondition 比较逻辑
- 阻塞语义不应侵入 `RAGBuilder`
- 新能力应尽量遵循零侵入扩展原则
- 依赖关系应优先通过规则库数据表达，而不是代码硬编码

这意味着以下做法原则上不推荐作为主方案：

- 在 Scheduler 中识别 repair step 后强制追加 precedence
- 在 API / Service 层直接修改 `predecessor_ids`
- 在 RAGBuilder 中增加“repair 一定先于 blocked op”的业务特判

---

## 5. 单阻塞场景的最小修复方案

### 5.1 基本思路

单阻塞场景下，最小修复方案是把“维修完成后才可执行”直接建模为状态依赖。

示例：

- 维修活动 effect：`blockage_reason = none`
- 被阻塞活动 precondition：`blockage_reason = none`

这样系统会自然推导：

- `OP_REPAIR_X` 先把状态恢复为 `none`
- `OP_X` 只有在该状态满足后才可执行
- `RAGBuilder` 自动生成 `OP_REPAIR_X -> OP_X`

### 5.2 优点

- 改动最小
- 完全符合当前架构原则
- 不需要修改 Scheduler 或 RAGBuilder 核心语义
- 后续新增维修规则时仍然走数据驱动

### 5.3 局限

该方案只适合单阻塞或单一全局阻塞语义。

一旦进入多阻塞场景，会遇到两个问题：

1. 一个全局 `blockage_reason = none` 难以准确表达“哪一个阻塞已解除”
2. 某一个维修完成后，可能错误放开其他本不应恢复的活动

因此，该方案只能作为单阻塞阶段的最小补丁，不应直接作为多阻塞长期方案。

---

## 6. 多阻塞场景的建模挑战

多阻塞场景的典型特征如下：

- 同一计划中，多个活动可能同时受阻
- 每个阻塞可能有不同原因
- 不同阻塞可能需要不同维修序列或恢复动作
- 某一维修的完成，不应自动放开所有阻塞活动

示例场景：

1. `OP_CALIBRATE` 因 `hardware_fault` 阻塞
2. `OP_RELEASE` 因 `pending_approval` 阻塞

如果继续使用单一全局状态：

- `blockage_reason = hardware_fault`
- 维修后统一写回 `blockage_reason = none`

则系统无法明确区分：

- 是哪个阻塞已解除
- 哪个活动应被恢复执行
- 哪些活动仍应保持阻塞

因此，多阻塞场景必须从“单值全局阻塞”向“可区分的恢复门禁”演进。

---

## 7. 方案一：全局阻塞集合建模

### 7.1 设计思路

将当前单值：

- `blockage_reason = "hardware_fault"`

升级为集合型特征，例如：

- `blockage_reasons = ["hardware_fault", "pending_approval"]`

对应规则设计：

- `OP_REPAIR_HW`
  - precondition：`blockage_reasons contains hardware_fault`
  - effect：从集合中移除 `hardware_fault`

- `OP_REPAIR_APPROVAL`
  - precondition：`blockage_reasons contains pending_approval`
  - effect：从集合中移除 `pending_approval`

被阻塞活动的 precondition 可设计为：

- `blockage_reasons not_contains hardware_fault`
- 或依赖更细粒度的恢复标识

### 7.2 优点

- 能表达多个阻塞同时存在
- 每个维修工序只处理自己负责的阻塞原因
- 从概念上保持“阻塞原因”是系统状态的一部分

### 7.3 缺点

当前系统需要显著扩展：

- `OperatorRegistry` 需支持集合型操作符，如 `contains` / `not_contains`
- `EffectRegistry` 需支持集合增删 effect
- `feature_definition` 与规则值类型需要进一步明确集合语义

该方案适合作为通用能力演进方向，但不属于最小改动方案。

---

## 8. 方案二：活动级 readiness 门禁建模

### 8.1 设计思路

将“阻塞原因”与“活动能否恢复执行”拆分为两类不同职责的状态特征。

#### 一类：阻塞原因

用于描述当前发生了什么阻塞，并触发相应维修规则，例如：

- `blockage_reason = hardware_fault`
- `blockage_reason = pending_approval`
- `blockage_reason = fixture_missing`

#### 二类：活动恢复门禁（readiness）

用于描述某类活动是否具备执行条件，例如：

- `calibration_ready = yes/no`
- `approval_ready = yes/no`
- `fixture_ready = yes/no`

### 8.2 规则建模方式

维修活动同时承担两个职责：

1. 清理或更新对应 `blockage_reason`
2. 恢复对应活动的 readiness 状态

例如：

- `OP_REPAIR_HW`
  - precondition：`blockage_reason = hardware_fault`
  - effect：
    - `blockage_reason = none`
    - `calibration_ready = yes`

- `OP_GET_APPROVAL`
  - precondition：`blockage_reason = pending_approval`
  - effect：
    - `approval_ready = yes`

业务活动不再依赖全局 `blockage_reason = none`，而改为依赖自身门禁：

- `OP_CALIBRATE`
  - precondition：`calibration_ready = yes`

- `OP_RELEASE`
  - precondition：`approval_ready = yes`

### 8.3 优点

- 能稳定支持多个阻塞同时存在
- 一个维修活动只会解锁对应活动，不会误放行其他活动
- 依赖关系仍然通过 `precondition/effect` 自动推导
- 与当前规则驱动架构高度一致
- 语义上更符合制造/集成类场景的真实业务关系

### 8.4 成本与限制

- 需要新增 readiness 类特征定义
- 需要为关键活动补充对应 precondition
- 需要在规则库设计阶段明确“哪个维修恢复哪个门禁”

与方案一相比，该方案对求解器底层能力扩展要求更低，但会增加规则库建模工作量。

---

## 9. 方案对比

| 维度 | 方案一：全局阻塞集合 | 方案二：活动级 readiness |
|------|----------------------|--------------------------|
| 单阻塞修复 | 可行 | 可行 |
| 多阻塞支持 | 强 | 强 |
| 误放行风险 | 中 | 低 |
| 与当前能力兼容性 | 低 | 高 |
| 对 RuleEvaluator 扩展要求 | 高 | 低 |
| 规则库建模清晰度 | 中 | 高 |
| 适合作为近期落地方案 | 否 | 是 |

---

## 10. 推荐方案

推荐采用：**方案二：活动级 readiness 门禁建模**。

### 推荐原因

1. 与当前架构约束最一致
2. 不需要在 Scheduler / API / RAGBuilder 引入业务特判
3. 不要求短期内扩展集合型 operator 与 effect
4. 可以准确表达“哪个维修恢复哪个活动”
5. 能避免全局 `blockage_reason = none` 带来的误解锁问题

换言之：

- `blockage_reason` 负责解释“为什么阻塞”
- readiness 负责表达“是否允许恢复执行”

两者职责分离后，多阻塞语义才具备稳定扩展性。

---

## 11. 与当前实现的关系

### 11.1 当前实现本质上仍是单阻塞模型

从现有代码与 API 结构看，当前系统一次求解只消费一组阻塞输入：

- 一个 `blockage_constraints`
- 一个 `strategy`
- 一个 `blocked_step_id` / `blocked_op_rule_id`
- 一个 `strategy_b.blockage_reason`

同时，当前状态覆盖也是单值写入：

- `current_state_override["blockage_reason"] = xxx`

因此，即使规则库升级为多阻塞思路，当前 API 入口仍然无法完整表达“多个阻塞同时求解”。

### 11.2 API 层的后续演进方向

若后续要真正支持多阻塞统一求解，建议将当前结构：

```json
"blockage_constraints": {
  "strategy": "B",
  "blocked_op_rule_id": 123,
  "strategy_b": {"blockage_reason": "hardware_fault"}
}
```

演进为列表结构，例如：

```json
"blockage_constraints": [
  {
    "strategy": "B",
    "blocked_op_rule_id": 123,
    "strategy_b": {"blockage_reason": "hardware_fault"}
  },
  {
    "strategy": "AB",
    "blocked_op_rule_id": 456,
    "strategy_a": {"not_before_offset": 120},
    "strategy_b": {"blockage_reason": "pending_approval"}
  }
]
```

但这是下一阶段能力扩展，不属于本文推荐方案的第一落地步。

---

## 12. 分阶段实施建议

### 12.1 阶段一：修复单阻塞并行问题

目标：先解决“维修活动与原活动并行”的现有问题。

建议：

1. 识别当前发生并行问题的业务活动规则
2. 为这些活动补充明确的恢复型 precondition
3. 在单阻塞场景下，允许短期使用 `blockage_reason = none` 或直接引入 readiness 特征
4. 补充测试，确保 repair step 成为 blocked op 的 predecessor

### 12.2 阶段二：引入活动级 readiness 特征

目标：建立面向多阻塞的稳定语义模型。

建议：

1. 为关键活动定义 readiness 特征
2. 将业务活动 precondition 从全局阻塞清除条件迁移为 readiness 条件
3. 让维修活动在 effect 中恢复 readiness
4. 保留 `blockage_reason` 作为维修匹配触发入口

### 12.3 阶段三：扩展多阻塞 API 输入

目标：支持一次 solve 请求内表达多个阻塞事件。

建议：

1. 将 `blockage_constraints` 从单对象扩展为列表
2. 明确单次请求中多阻塞事件的校验规则
3. 定义策略 A / B / AB 在多阻塞混合场景下的合并语义
4. 补充版本 diff、step_role、blockage_event 记录策略

---

## 13. 不推荐方案说明

以下方案不建议作为主设计方向：

### 13.1 在 Scheduler 中强制追加 repair precedence

问题：

- 将业务语义侵入调度层
- 会破坏 RAG 与 Scheduler 的职责边界
- 后续扩展时维护复杂度高

### 13.2 在 API / Service 层手工补 `predecessor_ids`

问题：

- 属于补丁式依赖
- 依赖关系不再来自规则推导
- 与系统“规则驱动”原则冲突

### 13.3 用字符串拼接表达多个阻塞

例如：

- `blockage_reason = "hardware_fault,pending_approval"`

问题：

- 匹配逻辑脆弱
- 局部清除困难
- 组合数快速膨胀
- 不利于后续类型系统扩展

---

## 14. 结论

针对“维修活动插入后必须完成，原活动才能恢复执行”的问题，正确方向应当是：

- 在规则层建立明确的状态依赖
- 而不是在调度层或服务层用代码特判强制串行

针对“多个阻塞”的长期演进，推荐采用以下职责划分：

- `blockage_reason`：描述阻塞原因，触发维修规则
- readiness 特征：描述活动是否恢复可执行

在该模型下：

- repair 活动通过 effect 恢复 readiness
- blocked 活动通过 precondition 依赖 readiness
- 多个阻塞可同时存在且互不误伤
- 系统仍保持 `precondition/effect` 自动推导依赖的核心架构

因此，正式建议为：

1. 短期修复现有并行问题时，优先通过规则补齐恢复型 precondition
2. 中期演进时，引入活动级 readiness 特征作为多阻塞正式建模方式
3. 长期再扩展 API，使一次 solve 能表达多个阻塞事件

---

## 15. 后续落地清单

建议后续实现工作按如下顺序推进：

1. 盘点当前会与维修并行的业务活动规则
2. 为这些活动定义对应 readiness 特征
3. 为维修规则补齐 readiness effect
4. 为业务活动补齐 readiness precondition
5. 补充测试：
   - 维修必须先于对应 blocked op
   - 多个阻塞不会相互误解锁
   - AB 策略下 readiness 与 `not_before` 可同时生效
6. 评估是否进入多阻塞 API 能力扩展

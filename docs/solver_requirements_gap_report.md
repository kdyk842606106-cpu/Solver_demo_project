# Solver Requirements Gap Report

> 创建时间：2026-04-25
> 评估基线：`docs/solver_requirements_summary.md`
> 对照版本：`docs/STATE_V0.3.md`
> 评估范围：Planner / Scheduler / API / Frontend / Tests

---

## 1. 目的

本文档用于评估当前已开发系统与 `docs/solver_requirements_summary.md` 中“泵体机械集成场景最终需求定义”之间的差距。

重点回答三个问题：

- 当前系统已经具备了哪些与需求一致的能力
- 当前系统距离系统化需求还差哪些关键能力
- 如果要逐步收敛到该需求基线，优先级应该如何划分

本报告基于代码与现有测试的只读调查整理，不代表需求已被项目正式采纳为当前开发主线。当前项目账本仍以 `docs/STATE_V0.3.md` 为准。

---

## 2. 执行摘要

总体判断：当前系统已经具备一个可运行的 `Planner -> Scheduler -> API -> UI` 闭环，并且已经完成 V0.2 阻塞处理、V0.3 Numeric Phase 1 等工程化扩展；但它与 `solver_requirements_summary.md` 中定义的“面向泵体机械集成场景的系统化 Planner 架构”仍存在明显差距。

当前系统更准确的定位是：

- 一个以 `delta 匹配 + precondition/provider 递归补齐` 为核心的工程型求解器
- 已具备基础排程、阻塞重排、重复 numeric step 实例化等能力
- 尚未达到需求文档中定义的“最小代价路径搜索 + 条件集合目标 + 数值事件触发 + 双层并行判定 + What-if + 规则健康检查”的完整能力面

最关键的差距集中在以下五个方面：

- Planner 求解范式仍不是完整的最小代价路径搜索
- 顶层目标模型仍基于 `target_state_id`，不是条件集合 `G`
- 数值规则仍是 `increment/decrement` 风格，不是需求中的 `sub/reset` 触发式语义
- 并行判定缺少“效果可交换性”这一层业务规则过滤
- What-if 与规则库健康检查两类系统化能力基本未落地

---

## 3. 调查范围与证据来源

本次调查重点阅读了以下文件：

### 3.1 文档

- `docs/solver_requirements_summary.md`
- `docs/STATE_V0.3.md`
- `docs/ANCHOR.md`
- `docs/protocols/planner.md`

### 3.2 后端核心

- `app/core/planner/search.py`
- `app/core/planner/numeric.py`
- `app/core/planner/matcher.py`
- `app/core/solver/operators.py`
- `app/core/solver/effects.py`
- `app/core/scheduler/loader.py`
- `app/core/scheduler/model.py`
- `app/core/scheduler/solver.py`
- `app/api/v1/solve.py`
- `app/db/schemas.py`

### 3.3 前端与测试

- `frontend/src/views/SolvePage/index.vue`
- `tests/integration/test_planner_integration.py`
- `tests/e2e/test_numeric_planning.py`
- 以及若干 `tests/unit/`、`tests/integration/` 中与 explainability / blockage / parallel groups 相关测试

---

## 4. 当前已实现且与需求基本对齐的能力

### 4.1 已有清晰的分层闭环

当前系统已具备较清晰的分层：

- Planner 负责从状态差异推导候选步骤与依赖
- Scheduler 负责基于 precedence 与资源约束做 CP-SAT 排程
- API 负责拼装结果并返回前端
- 前端可展示 Gantt、任务明细、并行组、版本差异等信息

相关文件：

- `app/core/planner/search.py`
- `app/core/scheduler/loader.py`
- `app/core/scheduler/model.py`
- `app/core/scheduler/solver.py`
- `app/api/v1/solve.py`
- `frontend/src/views/SolvePage/index.vue`

这与需求文档第 5 节定义的 Planner / Scheduler 边界在大方向上是对齐的。

### 4.2 状态模型已经采用 key-value 形式

当前 Planner 使用 `dict[str, str]` 作为状态快照，并通过数据库中的状态记录装载当前状态与目标状态。

相关文件：

- `app/core/planner/state.py`
- `app/core/planner/search.py:108`

这与需求文档中“状态结构为 key-value 映射”的基本表达方式一致。

### 4.3 前置条件操作符支持已经较丰富

当前实现已支持：

- `eq`
- `neq`
- `gt`
- `gte`
- `lt`
- `lte`
- `in`

相关文件：

- `app/core/solver/operators.py:79`

这意味着当前系统在 precondition 表达能力上，并不弱于需求文档中描述的“基于 key 的逻辑表达式，纯 AND 逻辑”。

### 4.4 Numeric Phase 1 已具备多步数值推进与重复步骤实例化

这是当前系统相对成熟的一块能力。已经实现：

- exact numeric target 的多步推进
- 重复 op rule 实例化为多个 planner step
- numeric precondition 驱动的隐式子目标规划
- 循环检测与结构化错误

相关文件：

- `app/core/planner/numeric.py:56`
- `app/core/planner/search.py:176`
- `tests/unit/test_numeric_planner.py`
- `tests/e2e/test_numeric_planning.py:13`

这部分能力已经覆盖需求文档中“多步数值推进”“重复执行实例化”的一部分技术前提。

### 4.5 不可达判定和结构化错误已有基础闭环

`POST /api/v1/solve` 已能返回稳定结构的失败信息：

- `status=failed`
- `error_code`
- `error_message`

当前已出现的错误码包括：

- `NO_SOLUTION`
- `CIRCULAR_DEPENDENCY`
- `INFEASIBLE`
- `SOLVER_TIMEOUT`
- `AMBIGUOUS_BLOCKED_STEP`
- `INTERNAL_ERROR`

相关文件：

- `app/api/v1/solve.py:231`
- `app/api/v1/solve.py:315`
- `app/api/v1/solve.py:398`

这与需求文档中“不可达时明确返回，不陷入无限搜索”的要求基本一致。

### 4.6 API/UI 已提供基础可解释信息

当前 `solve` 返回中已包含：

- `state_delta`
- `critical_path`
- `schedule.tasks`
- `parallel_groups`
- 阻塞重排相关的 `step_role` / `not_before`

相关文件：

- `app/api/v1/solve.py:349`
- `frontend/src/views/SolvePage/index.vue:79`

虽然还达不到“完整解释性”，但已经不是纯黑盒输出。

---

## 5. 当前系统与需求之间的关键差距

以下差距按“是否影响核心需求定义”排序。

### 5.1 Planner 不是完整的最小代价路径搜索

需求文档第 2 节将问题定义为：

- 从初始状态 `s0` 到目标条件集合 `G`
- 搜索最小代价可达路径

而当前 Planner 的核心实现仍是：

- 先计算 `current_state` 与 `target_state` 的 delta
- 为每个 delta 选一个可产生目标 effect 的 rule
- 再递归补齐 preconditions 所需 provider

相关证据：

- `app/core/planner/search.py:131`
- `docs/protocols/planner.md:46`
- `docs/protocols/planner.md:93`

`docs/protocols/planner.md:93` 已明确写出：

- 当前实现不是 BFS 状态空间搜索
- 而是“delta 匹配 + 依赖补齐”

影响：

- 当前系统不能严格保证“全局最小代价路径”
- 更接近启发式拼装计划，而不是需求文档定义的标准路径搜索器

### 5.2 顶层目标模型仍是 `target_state_id`，不是条件集合 `G`

需求文档中目标 `G` 的定义是：

- 基于 key 的逻辑表达式集合
- 纯 AND 逻辑
- 不要求必须命中某个预定义终态记录

但当前 API 仍要求：

- `current_state_id`
- `target_state_id`

相关文件：

- `app/db/schemas.py:343`
- `app/api/v1/solve.py:145`
- `app/api/v1/solve.py:157`

当前 `state_delta`、`is_goal`、`build_rag()` 的上层语义，本质上仍围绕“当前状态快照 vs 目标状态快照”展开。

影响：

- 无法直接表达需求文档中的条件型目标，例如 `洁净状态 > 100`
- 目标输入仍被数据库中的预定义状态对象绑定

### 5.3 效果操作符集合与需求文档不一致

需求文档定义的最小效果集为：

- `set`
- `sub`
- `reset`

当前实际实现的效果类型为：

- `set`
- `increment`
- `decrement`

相关文件：

- `app/core/solver/effects.py:4`
- `app/db/schemas.py:182`

其中最关键的缺口是：

- 当前没有 `reset`
- 当前 numeric 语义也不是面向“归零后触发某活动并恢复阈值”的事件驱动模型

影响：

- 需求文档中“安装缺口归零自动触发清洁，再 reset 回阈值”的核心机制尚未被原生建模

### 5.4 数值触发规则尚未形成需求中的事件驱动闭环

需求文档对 numeric 的关键要求并不是“仅能多步到达 exact target”，而是：

- `sub` 使数值逐步下降
- 某数值归零时自动触发关联活动
- 该活动执行 `reset`
- 形成可重复出现的维护/清洁循环

当前系统虽然已经支持：

- numeric exact target
- repeated step instantiation
- numeric precondition chaining

但尚未看到以下通用机制：

- “数值归零事件 -> 自动触发某条 reset rule”
- “由触发规则自涌现出的重复维护活动插入点”

相关文件：

- `app/core/planner/numeric.py:56`
- `app/core/planner/search.py:176`

影响：

- 当前 numeric 功能更像“数值步进规划”
- 与需求文档中的“触发式重复活动”不是同一层能力

### 5.5 并行判定逻辑与需求文档明显不一致

需求文档要求并行判定有两层：

1. 偏序图无路径
2. 效果可交换性检查

尤其强调共享 key 上的效果组合语义，例如：

- `set + set` 不可并行
- `set + sub` 不可并行
- `sub + sub` 可并行

当前系统中有两类并行信息：

- Planner 的 `find_parallel_groups(rag)`：按“前驱集合相同”分组
- Scheduler 的 `parallel_groups`：按时间区间重叠检测

相关文件：

- `app/core/planner/search.py:486`
- `app/core/scheduler/solver.py:248`
- `frontend/src/views/SolvePage/index.vue:198`

但当前没有看到对“共享 key 的效果可交换性”的系统建模和验证。

影响：

- 需求文档里最典型的冲突场景，当前无法被严格过滤
- 当前对外展示的并行组更偏向结果展示，而不是严格业务可并行语义

### 5.6 代价模型尚未达到需求中的统一权重求解

需求文档强调：

- Planner 目标是最小代价路径
- 代价单位统一，用于反映复杂度、风险、优先级
- 不等同于工时

当前系统的实际选择逻辑主要是：

- 优先 precondition 已满足的 candidate
- 否则选 `duration_min` 最短的 rule

相关文件：

- `app/core/planner/search.py:210`
- `app/core/planner/matcher.py:185`

同时，`STATE` 中也明确记录：

- 当前只有 `minimize_makespan` 完整实现
- `weight` 尚未参与真实加权求解

相关文件：

- `docs/STATE_V0.3.md:38`
- `app/core/scheduler/model.py:121`

影响：

- 当前系统不能代表需求文档中的“统一代价路径最优”能力

### 5.7 What-if 参数预演能力基本未落地

需求文档场景 2 要求支持：

- 修改阈值
- 修改权重
- 新增模板
- 然后快速比较新旧方案差异

当前系统已有：

- 版本链
- diff 展示
- blockage replan

相关文件：

- `frontend/src/views/SolvePage/index.vue:119`
- `app/api/v1/plans.py`

但这些能力仍主要服务于“版本对比”和“阻塞重排”，并不是通用的 what-if 参数实验框架。

当前缺少：

- 临时参数注入并求解的通用入口
- what-if 对比的专门语义
- 参数敏感性输出

### 5.8 工艺规则校验 / 模板库健康检查能力基本空缺

需求文档场景 3 明确要求：

- 死锁检测
- 冗余活动检测
- 循环风险报告
- 前置条件一致性检查
- 效果可交换性冲突检查

当前调查中未发现对应的：

- API 入口
- 服务层分析模块
- 离线校验工具链

这部分目前基本属于未开始状态。

### 5.9 当前 explainability 仍停留在轻量展示层

需求文档强调的解释能力包括：

- 每一步状态变化
- 前置条件判定
- 效果执行说明
- 为什么先做这个
- 为什么没选另一个候选活动

当前系统返回的解释信息主要是：

- `state_delta`
- `critical_path`
- task 基本元数据

相关文件：

- `app/api/v1/solve.py:349`
- `frontend/src/views/SolvePage/index.vue:89`

而 `STATE` 也显示：

- V0.3 的“求解可解释性深化”尚未开始

相关文件：

- `docs/STATE_V0.3.md:155`

影响：

- 当前系统可以说“不是完全黑盒”
- 但还达不到需求文档中的“工程师可完整追溯决策原因”的深度

### 5.10 Scheduler 资源建模仍是 MVP 级别

当前 Scheduler 只取每个 rule 的“首个 required resource”参与建模：

- `resource_type = first required req`

相关文件：

- `app/core/scheduler/loader.py:105`

这与旧版上下文中提到的已知限制一致。虽然不直接违反 `solver_requirements_summary.md` 的当前文字，但说明资源建模仍偏 MVP，不适合直接承接更复杂的资源组合场景。

---

## 6. 部分对齐但仍存在边界风险的能力

### 6.1 状态可回退：框架允许，但未形成系统化场景闭环

需求文档强调：

- `set` 可覆盖旧值
- 系统需支持拆卸、返工、上下电切换等回退行为

当前框架层面，`set` 的确是覆盖式效果，理论上支持回退。

相关文件：

- `app/core/solver/effects.py:87`

但调查中尚未看到面向“返工路径选择”这一业务语义的系统性验证，因此更准确的表述应是：

- 当前框架允许状态回退
- 但尚不能证明已经系统满足需求文档中的返工规划能力

### 6.2 结果确定性：大体可重复，但未形成明确制度化约束

需求文档要求相同输入应给出相同输出。

当前系统大概率是稳定的，因为：

- 规则选择多数基于固定字段比较
- 列表处理通常保持固定顺序

但仍存在边界风险：

- 当多个候选 `duration_min` 相同时，tie-break 规则未显式制度化
- 某些查询稳定性依赖数据库返回顺序

相关文件：

- `app/core/planner/search.py:217`
- `app/core/planner/matcher.py:185`

### 6.3 条件型目标：底层局部支持，顶层输入尚未对齐

当前 numeric precondition 已可使用 `gte/lte` 等操作符，但这只出现在：

- 规则前置条件匹配
- numeric implicit goal planning 的局部场景

相关文件：

- `app/core/solver/operators.py:109`
- `app/core/planner/numeric.py:183`

它还没有扩展为顶层 solve API 的完整目标表达体系。

---

## 7. 测试覆盖现状与需求覆盖差距

### 7.1 当前已有测试覆盖的能力

已看到较明确测试覆盖的方向包括：

- 基础 Planner 集成链路
- numeric repeated steps
- numeric implicit preconditions
- numeric unreachable / cycle diagnostics
- blockage A/B/AB 与 repeated step 兼容
- solve enriched response 中的 `critical_path`、`step_role` 等字段

相关文件：

- `tests/integration/test_planner_integration.py`
- `tests/unit/test_numeric_planner.py`
- `tests/e2e/test_numeric_planning.py`
- `tests/integration/test_step3_api.py`
- `tests/integration/test_blockage_strategies.py`

### 7.2 当前未见系统覆盖的需求能力

以下需求方向，当前未见明确测试闭环：

- 条件集合目标 `G`
- `set/sub/reset` 触发式 numeric 规则
- 效果可交换性并行验证
- What-if 参数对比
- 模板库健康检查 / 规则校验工具
- “为什么选这个 rule / 为什么没选那个 rule”的 explainability 断言

这意味着：

- 当前测试可以证明现有实现是稳定的
- 但还不能证明系统满足 `solver_requirements_summary.md` 中的大部分高阶能力

---

## 8. 差距分级

### 8.1 P0 级差距：直接影响是否满足核心需求定义

以下差距若不补，系统不能声称满足该需求文档的核心定义：

1. Planner 不是完整的最小代价路径搜索
2. 顶层目标仍基于 `target_state_id`，不是条件集合 `G`
3. 效果模型缺少 `reset`，numeric 仍不是触发式语义
4. 并行判定缺少“效果可交换性”过滤层

### 8.2 P1 级差距：影响系统化可用性，但不阻断现有闭环

1. What-if 参数预演能力缺失
2. Explainability 深度不足
3. 多目标与统一权重代价尚未落地

### 8.3 P2 级差距：影响平台化治理与长期可维护性

1. 模板库健康检查能力缺失
2. 资源建模仍是 MVP 级别
3. tie-break / 确定性规则未制度化

---

## 9. 建议的收敛顺序

如果未来决定以 `solver_requirements_summary.md` 作为正式需求基线，建议按以下顺序推进。

### 9.1 第一阶段：先对齐 Planner 核心语义

优先解决：

1. 顶层目标表达升级为条件集合 `G`
2. 效果系统补齐 `set/sub/reset`
3. 将 numeric 规则升级为事件驱动语义，而不只是 exact target chaining
4. 并行判定补上效果可交换性层

原因：

- 这四项直接定义了“问题是什么”和“Planner 在求什么”
- 如果它们不先冻结，后续 What-if、规则校验、解释性都缺乏稳定语义基础

### 9.2 第二阶段：补齐求解策略与 explainability

优先解决：

1. 从现有 delta/provider 范式演进到可控的最小代价搜索策略
2. 建立 rule candidate comparison / reject reason / precondition trace 等解释结构
3. 将 explainability 暴露到 API 与前端

### 9.3 第三阶段：补平台化能力

优先解决：

1. What-if 参数注入与方案对比
2. 模板库健康检查工具链
3. 更细的资源建模和调度验证

---

## 10. 结论

当前系统已经不是一个简单原型，而是一个有实际闭环能力的工程系统，尤其在以下方向已经具备较好基础：

- Planner / Scheduler 分层
- 阻塞重排
- Numeric Phase 1
- API 结构化错误
- 基础结果展示

但如果以 `docs/solver_requirements_summary.md` 作为目标蓝图，当前系统仍不能认为“已基本实现需求”，更准确的判断应是：

- 已具备约 40% 到 50% 的基础能力框架
- 已完成部分关键底座
- 但距离需求文档描述的系统化 Planner 能力仍有实质性架构差距

最关键的三条结论如下：

1. 当前 Planner 仍是“工程化规则拼装器”，不是“完整最小代价路径搜索器”
2. 当前 numeric 能力已解决“重复步骤实例化”，但尚未解决“触发式维护循环”
3. 当前并行组输出更偏结果展示，尚不是需求文档定义的严格业务并行判定

因此，后续如果要正式切换到该需求基线，不建议直接在现有行为上继续局部打补丁，而应先冻结：

- 目标表达语义
- 效果操作符语义
- 并行判定语义
- Planner 搜索语义

在这四项冻结之后，再展开 What-if、规则校验、解释性深化，会更稳妥。

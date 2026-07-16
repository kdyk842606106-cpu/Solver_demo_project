# PROJECT ANCHOR

> **本文档定义系统的永久性约定，不随版本迭代更新。**
> 开发时所有决策必须符合本文档定义的原则。
> 修改本文档需标注原因和日期。

---

## 系统定位

集成计划求解引擎（Integration Planning Solver）。
规则驱动的状态空间求解引擎 + 计划师操作界面。

给定机台的起点状态、目标状态、工序规则库和资源约束，
自动推导合法工序路径（RAG）并生成最优排程（CP-SAT），
支持计划师对阻塞情况进行动态重排。

核心创新：依赖关系从 precondition/effect 链自动推导，并行分支自然涌现。

---

## 技术栈（锁定）

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy 2.0 (async) |
| 求解 | Google OR-Tools CP-SAT |
| 数据库 | PostgreSQL 15 / Alembic 迁移 |
| 前端 | Vue 3 + Element Plus + ECharts |
| 容器 | Docker + Docker Compose |

---

## 分层架构（锁定）

```
UI (Vue 3) → API (FastAPI) → Service → Domain (solver/) → Persistence (SQLAlchemy)
```

跨层调用规则：只能调用相邻下层，不可跨层。

```
┌─────────────────────────────────────────┐
│  表示层 — Vue 3 + Element Plus          │
├─────────────────────────────────────────┤
│  应用层 — FastAPI 路由                   │
├─────────────────────────────────────────┤
│  服务层 — 业务编排                       │
├─────────────────────────────────────────┤
│  领域层 — 求解核心 (solver/)             │
│  RuleEvaluator / StateDelta /           │
│  RAGBuilder / Scheduler                 │
├─────────────────────────────────────────┤
│  持久层 — PostgreSQL / SQLAlchemy ORM    │
└─────────────────────────────────────────┘
```

---

## 领域层四个核心模块（锁定）

| 模块 | 职责 |
|------|------|
| **RuleEvaluator** | 所有 precond 匹配和 effect 应用的唯一入口，策略模式 |
| **StateDelta** | 计算起点与目标的状态差 |
| **RAGBuilder** | 状态差 → 工序 DAG（正向搜索 + 依赖补齐） |
| **Scheduler** | 工序 DAG → 排程（CP-SAT，precedence + 资源约束） |

四个模块只通过数据结构通信，任一模块可独立替换。

---

## 五条设计原则（锁定）

```
原则 1：规则内置，数据驱动
  所有业务知识在规则库（数据库），引擎不含业务逻辑。
  新增工序类型 = 往数据库加数据，不改代码。

原则 2：模块解耦，接口稳定
  核心模块只通过数据结构通信，内部实现可替换。

原则 3：策略模式，注册优于修改
  新增 Operator / Effect / Objective → 注册新类。
  主流程代码不因扩展而修改。

原则 4：零侵入扩展
  新参数必须有默认值，不传时行为与上版本完全一致。

原则 5：阻塞语义不侵入 RAGBuilder
  阻塞 = 往 current_state 注入 blockage_reason 特征。
  RAGBuilder 只做通用规则匹配，维修序列是推导的自然结果。
```

---

## 硬性禁止（锁定）

```
❌ 禁止在 RAGBuilder/Scheduler/API 层直接写 precond 比较逻辑
❌ 禁止 ORM Model 与 Pydantic Schema 混用
❌ 禁止组件内直接调用 axios（必须经过 src/api/ 封装）
❌ 禁止 Domain 层导入 FastAPI 模块
❌ 禁止 feature_key 在前端硬编码（必须从数据库动态读取）
❌ 禁止时间单位混用（统一分钟，字段名以 _min 结尾）
❌ 禁止注册表内部用 if/elif 分支做类型分发（必须装饰器注册）
```

---

## AI 编程硬性约束（锁定）

### 架构约束

```
约束 1：规则评估必须经过 RuleEvaluator
  所有 precond 匹配和 effect 应用通过 RuleEvaluator 统一调用。

约束 2：零侵入扩展
  blockage_constraints=None 时，求解流程与上一版本完全相同。

约束 3：状态不可变
  apply_effect() 返回新状态副本，不修改传入的 state 对象。
  RAGBuilder 每次展开操作状态副本。

约束 4：阻塞语义不侵入 RAGBuilder
  RAGBuilder 不感知"阻塞"概念，只做通用规则匹配。
```

### 数据约束

```
约束 5：feature_key 是系统外键锚点
  新增特征必须先在 feature_definition 中定义。
  删除前检查 op_rule_precond / op_rule_effect / machine_state_feature 引用。

约束 6：blockage_reason 合法值来自数据库
  前端下拉列表动态读取 feature_definition，不硬编码。

约束 7：时间单位统一
  所有时间偏移量统一分钟，字段名以 _min 结尾。

约束 8：step_role 标注时机
  在 CP-SAT 求解完成后通过新旧计划 diff 计算，
  不在 RAGBuilder 或 Scheduler 内部标注。
  repair 判断依据：op_rule.is_repair = TRUE。
```

### 错误处理约束

```
约束 9：求解失败必须可诊断
  求解失败必须返回稳定的结构化 error_code。
  至少覆盖：无解、循环依赖、资源不可行、求解超时。

约束 10：前端错误展示
  统一 ElMessage.error()，error_code → 中文映射表。
```

### 代码风格约束

```
约束 11：后端
  数据库查询通过 SQLAlchemy ORM（迁移脚本除外）。
  Pydantic Schema 与 SQLAlchemy Model 严格分离。
  API → Service → Domain，不可跨层。
  Domain 层不导入 FastAPI 模块。
  类型注解完整。

约束 12：前端
  API 调用统一通过 src/api/ 封装（包括健康检查等基础接口）。
  GanttChart / BlockageDialog 是纯组件，数据由父页面传入，事件通过 emit 传递。

约束 13：注册表模式
  OperatorRegistry / EffectRegistry / ObjectiveRegistry
  统一装饰器注册。禁止 if/elif 分支分发。
```

### 测试约束

```
约束 14：领域层必须有单元测试
  每个 Operator / Effect 独立测试。
  RAGBuilder 循环检测 + 深度限制测试。
  策略A / 策略B / AB 三个场景集成测试。
  测试数据使用 pytest fixture。

约束 15：验收测试
  对应 STATE 文档中定义的验收场景。
  断言：version/parent_plan_id, step_role, start_min, blockage_event。
```

---

## 明确不在范围内（锁定）

```
❌ 多项目隔离
❌ 角色权限管理
❌ 跨机台资源调配
❌ 实时执行状态追踪（步骤级别）
❌ 外部系统推送阻塞信号
❌ 执行中阻塞（进行中被中断）
❌ 工序时长不确定性建模（鲁棒排程）
❌ 技能匹配约束
```

---

## 核心业务词汇表（锁定）

| 术语 | 含义 |
|------|------|
| 机台 | 被集成的目标设备 |
| 起点状态 | 集成开始时机台的实际状态（特征键值对集合） |
| 目标状态 | 集成完成后机台应达到的状态 |
| 状态差(delta) | 起点与目标之间需要改变的特征集合 |
| 工序规则(op_rule) | 使机台从一种状态变迁到另一种状态的操作单元 |
| 前置条件(precondition) | 执行工序需满足的当前状态条件 |
| 执行效果(effect) | 执行工序后对机台状态的变更 |
| RAG | 有向无环图，节点为工序，边为执行依赖 |
| 关键路径 | RAG 中决定总工期的最长路径 |
| 排程(schedule) | 为 RAG 中每个工序分配开始时间和资源 |
| 阻塞(blockage) | 计划步骤因外部原因无法在预定时间执行 |
| 策略A(活动提拉) | 阻塞步骤延后，无关步骤提前 |
| 策略B(维修序列) | 匹配 is_repair=TRUE 规则插入 RAG |
| 维修工序(repair op) | is_repair=TRUE，通过 blockage_reason 匹配触发 |
| 版本链 | candidate_plan 通过 parent_plan_id 的父子关系 |
| step_role | 版本对比中步骤的变化标注 (normal/repair/pulled_forward/delayed) |

### V0.3 术语分层补充（锁定）

V0.3 引入 Network Editor 后，“状态”需要区分求解器状态快照、业务状态定义和画布引用实例。后续文档、UI 文案和代码注释必须按下表使用规范业务名；技术名保持现状，通过映射表解释，不把历史字段名直接暴露为新业务概念。

| 规范业务名 | 技术名 / 表 | 含义与边界 |
|------|------|------|
| 状态快照 | `MachineState` / `machine_state` | 机台某一时刻的特征键值集合，用于起点状态、目标状态或历史快照。 |
| 状态维度 | `feature_key`；`StateFeatureDef` / `FeatureDefinition` | 描述状态事实的维度键。用户侧统一称“状态维度”；`StateFeatureDef` 表示机台类型内定义，`FeatureDefinition` 表示全局特征定义。 |
| 状态本体 | `StateNode` / `state_node` | 全局唯一的业务状态定义，不直接携带层级所有权。 |
| 原子状态 | `StateNode` 且非 `aggregate`，并具备可转换为事实的 `feature_key/operator/target_value` | 可判定的叶子状态事实；后续实现应统一原子状态判定口径，避免按 `feature_key`、`is_leaf`、`state_kind` 分散判断。 |
| 状态包 | 聚合型 `StateNode` | 命名状态集合，按当前成员 AND 达成，可作为前置、上下文、声明输出或目标状态。 |
| 状态包成员引用 | `StateNodeReference` / `state_node_reference` | 表示同一状态本体出现在某个状态包中；删除引用不删除状态本体。 |
| 引用实例 | `state_node_reference` 的图投影 / `reference_id` 图节点 | 状态包容器或画布中的一次显示实例，布局信息归实例所有，不污染状态本体。 |

活动类术语同样按业务层级区分：

| 规范业务名 | 技术名 / 表 | 含义与边界 |
|------|------|------|
| 虚拟活动 | `ActivityNode(level 1/2)` / `activity_node` | 组织、分解和声明上下文/输出的活动包，不直接参与求解器执行。 |
| 原子活动 | `AtomicActivity` / `atomic_activity` | 当前推荐的可复用可执行能力定义，通过规则和绑定进入求解。 |
| 旧执行活动 | `ActivityNode(level 3)` | 历史兼容的可执行活动节点，仅用于旧数据兼容，不作为新增建模首选。 |
| 工序规则 / 执行定义 | `OpRule` / `op_rule` | 求解器实际读取的可执行规则，包含 precondition、effect、duration 和资源需求。 |
| 活动包原子活动引用 | `ActivityPackageAtomicRef` / `activity_package_atomic_ref` | 表示某个二级活动包复用一个原子活动；移除引用不删除原子活动定义。 |

---

## 版本路线图（方向性，可调整）

> 修改记录（2026-07-16）：V0.3 已进入 RC，修正原先仍标记 V0.2 为当前版本的过时路线图；架构原则和锁定约束未变。

```
V0.1 ✅ 基础求解链路（状态推导 RAG + CP-SAT 排程 + CRUD + 前端）
V0.2 ✅ 阻塞处理 + 架构升级（RuleEvaluator/类型系统/objectives数组化）
V0.3 RC ← 当前：实例级 POP + 分层状态/活动 + 工作日历 + 统一计划调整
V1.0    规则库规模化 + Deadline约束 + 历史阻塞模式库 + 外部集成接口
```

---

## 文档体系说明

本项目采用三层文档体系管理 AI 上下文：

```
ANCHOR.md       = 系统"宪法"     — 不可违反的原则，极少修改
STATE_Vx.x.md   = 系统"当前账本" — 现在是什么样子，每版本替换
TICKET_xxx.md   = 系统"工作令"   — 每次对话只做一件事

三者关系：
  宪法 约束 账本的变更方向
  账本 为 工作令 提供背景
  工作令 驱动 账本的更新
```

深入参考文档（按需查阅，不作为每次会话必读）：
- `docs/v0.2-spec.md` — V0.2 完整规格书（业务语义 + 数据模型 + 前端设计）
- `docs/protocols/` — 各模块实现协议（api.md / db.md / planner.md / scheduler.md）
- `docs/archive/` — 已完成版本的历史归档

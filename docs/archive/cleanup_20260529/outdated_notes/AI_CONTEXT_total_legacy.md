# ~~Demo 项目 AI Coding Context 总文档~~ (已归档)

> **本文档已归档** (2026-04-10)
>
> 本文档的内容已重构为三层文档体系：
> - **`docs/ANCHOR.md`** — 系统宪法（Ch1 设计原则 + Ch2 架构 + Ch9 约束 + 词汇表）
> - **`docs/STATE_V0.2.md`** — 当前版本快照（Ch4-8 已完成基线 + Ch7 任务清单 + 数据模型变更）
> - **`docs/TICKET_*.md`** — 任务工单（从 Ch7 任务清单细化而来）
>
> **请使用 `/session-start` 命令自动加载上下文。**
> 本文件保留仅作历史参考和详细 SQL/场景示例查阅。不再作为开发时的主参考文档。
>
> **原文档版本**：涵盖 V0.1（已完成）、V0.2（当前）、远景架构（V0.3 ~ V1.0）

---

## 第零章：阅读指引

```
章节结构：
  第一章：系统定位与设计原则       ← 所有决策的出发点，必读
  第二章：整体架构                ← 分层设计与模块边界
  第三章：领域层详细设计           ← 求解核心，最关键
  第四章：数据模型                ← 完整表结构定义
  第五章：API 接口设计            ← 前后端契约
  第六章：前端设计约定            ← Vue 组件与交互
  第七章：V0.2 开发任务清单       ← 当前版本实施指导
  第八章：版本路线图              ← 远景规划
  第九章：AI 编程助手注意事项     ← 开发时的硬性约束
```

---

## 第一章：系统定位与设计原则

### 1.1 系统定位

```
系统名称：集成计划求解引擎（Integration Planning Solver）

一句话定义：
  给定机台的起点状态、目标状态、工序规则库和资源约束，
  自动推导合法工序路径并生成最优排程，
  并在执行过程中支持计划师对阻塞情况进行动态重排。

本质：规则驱动的状态空间求解引擎 + 计划师操作界面

定位类型：可配置求解平台（单项目、单起终点）
  ✅ 规则库通过界面维护，新规则加入无需改代码
  ✅ 状态特征类型系统支持界面校验
  ✅ 优化目标内置预设，对外暴露权重参数
  ✅ 约束开关可配置控制
  ✅ 阻塞处理策略由计划师在界面选择

探索目标：验证"状态空间 + 规则推导 + CP-SAT 排程"架构的
          数学可行性，建立可扩展的 Solver 架构基础
```

### 1.2 核心设计原则

```
原则 1：规则内置，数据驱动
  所有业务知识存在规则库（数据库）中
  求解引擎本身是通用的，不硬编码任何业务逻辑
  新增工序类型、新增阻塞处理模式 = 往数据库加数据，不改代码

原则 2：模块解耦，接口稳定
  RuleEvaluator / StateDelta / RAGBuilder / Scheduler 四个核心模块
  模块之间只通过明确定义的数据结构通信
  任一模块的内部实现可以替换，不影响其他模块

原则 3：策略模式，注册优于修改
  新增 precondition operator → 注册新 Operator 类
  新增 effect type → 注册新 Effect 类
  新增优化目标 → 注册新 Objective 类
  主流程代码不因扩展而修改

原则 4：零侵入扩展
  每个新版本的功能通过新增字段/表/参数实现
  不修改已有接口的默认行为
  新参数缺省时行为与上一版本完全一致

原则 5：可解释性优先于精度
  这是数学可行性探索工具
  求解结果必须能说明"为什么是这个顺序"
  可解释性输出为结构化数据，不是自然语言
```

### 1.3 明确不在 Demo 范围内

```
❌ 多项目隔离
❌ 角色权限管理
❌ 跨机台资源调配
❌ 实时执行状态追踪（步骤级别）
❌ 外部系统推送阻塞信号
❌ 执行中阻塞（进行中被中断的步骤）
❌ 工序时长的不确定性建模（鲁棒排程）
❌ 技能匹配约束
```

---

## 第二章：整体架构

### 2.1 技术栈

```
后端：Python 3.11 + FastAPI + SQLAlchemy 2.0
求解：Google OR-Tools（CP-SAT Solver）
数据库：PostgreSQL 15
前端：Vue 3 + Element Plus + ECharts（甘特图）
容器：Docker + Docker Compose
```

### 2.2 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      表示层 (UI Layer)                       │
│                   Vue 3 + Element Plus                       │
│                                                             │
│  FeatureDefinitionPage  RulePage  StatePage  SolvePage       │
│  （特征管理）           （规则管理）（状态管理） （求解 + 计划）  │
└──────────────────────────┬──────────────────────────────────┘
                            │ REST API (JSON)
┌──────────────────────────▼──────────────────────────────────┐
│                     应用层 (API Layer)                        │
│                        FastAPI                               │
│                                                             │
│  /api/v1/features   /api/v1/rules     /api/v1/states        │
│  /api/v1/resources  /api/v1/solve     /api/v1/plans         │
└──────┬──────────┬──────────┬──────────┬───────────┬─────────┘
       │          │          │          │           │
┌──────▼──┐ ┌────▼─────┐ ┌──▼──────┐ ┌─▼───────────▼───────┐
│  规则   │ │  特征    │ │  状态   │ │    求解核心 (Solver)   │
│  管理   │ │  管理    │ │  管理   │ │                        │
│ service │ │ service  │ │ service │ │                        │
└──────┬──┘ └────┬─────┘ └──┬──────┘ └──────────┬───────────┘
       │         │           │                   │
┌──────▼─────────▼───────────▼───────────────────▼───────────┐
│                      领域层 (Domain Layer)                   │
│                                                             │
│  RuleEvaluator    StateDelta    RAGBuilder    Scheduler      │
│  （规则评估器）   （状态差分析） （路径搜索）  （CP-SAT排程）  │
└──────────────────────────────┬──────────────────────────────┘
                                │ SQLAlchemy ORM
┌──────────────────────────────▼──────────────────────────────┐
│                    持久层 (Persistence Layer)                 │
│                  PostgreSQL / SQLAlchemy Models               │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 后端目录结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── database.py                # DB 连接配置
│   ├── models/                    # SQLAlchemy ORM 模型
│   │   ├── rule.py                # op_rule 相关
│   │   ├── feature.py             # feature_definition
│   │   ├── state.py               # machine_state 相关
│   │   ├── resource.py            # resource
│   │   ├── plan.py                # candidate_plan 相关
│   │   └── blockage.py            # blockage_event
│   ├── schemas/                   # Pydantic 请求/响应模型
│   │   ├── rule.py
│   │   ├── feature.py
│   │   ├── state.py
│   │   ├── solve.py
│   │   └── plan.py
│   ├── api/                       # FastAPI 路由
│   │   ├── features.py
│   │   ├── rules.py
│   │   ├── states.py
│   │   ├── solve.py
│   │   └── plans.py
│   ├── services/                  # 应用服务层
│   │   ├── rule_service.py
│   │   ├── feature_service.py
│   │   ├── state_service.py
│   │   └── plan_service.py
│   └── solver/                    # 求解核心（领域层）
│       ├── rule_evaluator.py      # RuleEvaluator（策略模式）
│       ├── operators.py           # Operator 注册表
│       ├── effects.py             # Effect 注册表
│       ├── state_delta.py         # StateDelta
│       ├── rag_builder.py         # RAGBuilder
│       ├── scheduler.py           # Scheduler（CP-SAT）
│       ├── objectives.py          # Objective 注册表
│       └── solver.py              # 主流程编排
├── migrations/                    # Alembic 数据库迁移
└── tests/
```

### 2.4 前端目录结构

```
frontend/
├── src/
│   ├── api/                       # Axios 接口封装
│   │   ├── features.js
│   │   ├── rules.js
│   │   ├── states.js
│   │   ├── solve.js
│   │   └── plans.js
│   ├── components/
│   │   ├── GanttChart.vue         # 甘特图组件（ECharts）
│   │   ├── BlockageDialog.vue     # 阻塞处理对话框
│   │   └── PlanVersionPanel.vue   # 计划版本管理面板
│   ├── pages/
│   │   ├── FeatureDefinitionPage.vue
│   │   ├── RulePage.vue
│   │   ├── StatePage.vue
│   │   └── SolvePage.vue
│   └── router/index.js
```

---

## 第三章：领域层详细设计

这是整个系统最核心的部分，所有设计决策在此定义。

### 3.1 RuleEvaluator（规则评估器）

```python
# solver/rule_evaluator.py

"""
职责：所有 precondition 匹配和 effect 应用的统一入口
设计模式：策略模式（Strategy Pattern）
核心价值：新增规则类型只需注册，不修改主流程
"""

class RuleEvaluator:
    def evaluate_precond(
        self,
        current_state: dict[str, Any],
        precond_list: list[PrecondSchema]
    ) -> bool:
        """
        检查当前状态是否满足所有 precondition（AND 逻辑）
        每条 precond 调用 OperatorRegistry 分发到对应 Operator
        """

    def apply_effect(
        self,
        current_state: dict[str, Any],
        effect_list: list[EffectSchema]
    ) -> dict[str, Any]:
        """
        将 effect_list 应用到 current_state，返回新状态（不可变，返回副本）
        每条 effect 调用 EffectRegistry 分发到对应 Effect 处理器
        """
```

**OperatorRegistry（可注册的 precondition 比较算子）**：

```python
# solver/operators.py

# V0.2 实现的算子
class EqualOperator:        # operator = 'eq'
class NotEqualOperator:     # operator = 'neq'
class GreaterThanOperator:  # operator = 'gt'
class GteOperator:          # operator = 'gte'
class LessThanOperator:     # operator = 'lt'
class LteOperator:          # operator = 'lte'
class InSetOperator:        # operator = 'in'，value_list 字段

# 预留注册接口，未来直接注册不改主流程：
# OperatorRegistry.register('regex', RegexOperator)
# OperatorRegistry.register('contains', ContainsOperator)
```

**EffectRegistry（可注册的 effect 变更类型）**：

```python
# solver/effects.py

# V0.2 实现的 effect 类型
class SetEffect:        # effect_type = 'set'，直接赋新值
class IncrementEffect:  # effect_type = 'increment'，数值 + delta_value
class DecrementEffect:  # effect_type = 'decrement'，数值 - delta_value

# 预留注册接口：
# EffectRegistry.register('append', AppendEffect)
# EffectRegistry.register('toggle', ToggleEffect)
```

**类型安全约定**：

```
RuleEvaluator 在执行比较前，必须查询 feature_definition 表获取
feature 的 value_type，并转换为对应 Python 类型再比较：
  value_type = 'number'  → float(feature_value)
  value_type = 'boolean' → feature_value.lower() == 'true'
  value_type = 'string'  → str(feature_value)
  value_type = 'enum'    → str，并校验是否在 allowed_values 中
```

### 3.2 StateDelta（状态差分析器）

```python
# solver/state_delta.py

"""
职责：计算起点状态与目标状态之间的差异
输出：结构化差异列表，作为 RAGBuilder 搜索的起点
     同时作为求解可解释性数据的来源
"""

class StateDelta:
    def compute(
        self,
        start_state: dict[str, Any],
        goal_state: dict[str, Any]
    ) -> StateDeltaResult:
        """
        返回：
          delta:              需要改变的特征列表（from / to / value_type）
          already_satisfied:  start 已满足 goal 的特征列表
          unknown_features:   goal 中存在但 feature_definition 中不存在的特征
                              （用于校验，未知特征应报警告）
        """
```

### 3.3 RAGBuilder（路径搜索器）

```python
# solver/rag_builder.py

"""
职责：基于状态差，在规则库中搜索能连接起点到终点的工序 DAG
搜索算法：正向链接 BFS（V0.2）
防护机制：循环检测 + 深度限制（V0.2 必须实现）
"""

class RAGBuilder:
    MAX_SEARCH_DEPTH = 20        # 可配置，防止规则爆炸

    def build(
        self,
        current_state: dict[str, Any],
        goal_state: dict[str, Any],
        blockage_constraints: BlockageConstraints | None = None
    ) -> RAG:
        """
        搜索流程：
          1. StateDelta.compute() 获取需要改变的特征集合
          2. BFS 展开：
             a. 找所有 precondition 当前满足的 op_rule
                （若 blockage_constraints.strategy_b：
                   current_state 已含 blockage_reason 特征
                   is_repair=True 的规则自动匹配）
             b. 用 RuleEvaluator.apply_effect() 得到新状态
             c. 检查新状态是否是 visited_states 中已有状态（防循环）
             d. 检查搜索深度是否超过 MAX_SEARCH_DEPTH
          3. 剪枝：优先展开 duration_min 更短的 op_rule
          4. 到达目标状态后停止搜索
          5. 返回 RAG（有向无环图）

        RAG 节点：op_rule 实例 + 在图中的角色标注
        RAG 边：依赖关系（precond/effect 决定的执行顺序）
        并行关系：两个节点之间无依赖路径则可并行（显式标注）
        """
```

**策略 B 的 RAGBuilder 处理约定**：

```
当 blockage_constraints.strategy_b.blockage_reason 存在时：
  1. 在调用 RAGBuilder.build() 之前，将 blockage_reason 写入 current_state：
     current_state['blockage_reason'] = 'hardware_fault'（示例）
  2. RAGBuilder 正常执行 BFS，is_repair=TRUE 的规则会因为
     precondition 匹配 blockage_reason 而被自动选入路径
  3. 维修序列的 effect 清除 blockage_reason，恢复阻塞步骤 precondition
  4. 阻塞步骤在维修序列之后重新出现在 RAG 中

关键约定：RAGBuilder 不感知"阻塞"的业务语义
          阻塞只是当前状态的一个特征，规则匹配过程完全通用
```

### 3.4 Scheduler（排程器）

```python
# solver/scheduler.py

"""
职责：将 RAG 转化为具体排程（每个工序的开始时间和资源分配）
引擎：Google OR-Tools CP-SAT
"""

class Scheduler:
    def schedule(
        self,
        rag: RAG,
        resources: list[Resource],
        objectives: list[ObjectiveConfig],
        constraints: ConstraintConfig
    ) -> ScheduleResult:
        """
        CP-SAT 建模流程：
          1. 为每个 RAG 节点创建 interval_var（start, duration, end）
          2. 添加硬约束（不可关闭）：
             a. 依赖顺序约束：edge(A→B) → end[A] <= start[B]
             b. 资源互斥约束：同一资源同一时间只能分配给一个工序
          3. 添加软约束（根据 ConstraintConfig 开关）：
             a. not_before 约束：start[OPx] >= not_before_offset
                （策略A阻塞处理时注入）
             b. deadline 约束：end[最后节点] <= deadline_offset
                （预留，V0.2 暂不实现）
          4. 设置优化目标：
             ObjectiveRegistry 根据 objectives 列表构建加权目标函数
          5. 调用 solver.Solve()
          6. 返回排程结果（每个步骤的 start_min / resource_id）
        """
```

**ObjectiveRegistry（可注册的优化目标）**：

```python
# solver/objectives.py

# V0.2 实现
class MinimizeMakespanObjective:     # type = 'minimize_makespan'

# 预留（V0.3+）
# class MinimizeResourceUsageObjective  # type = 'minimize_resource_usage'
# class MinimizeCriticalPathObjective   # type = 'minimize_critical_path'

# 调用方传入格式：
objectives = [
    {"type": "minimize_makespan", "weight": 1.0}
]
# 未来多目标：
objectives = [
    {"type": "minimize_makespan", "weight": 0.7},
    {"type": "minimize_resource_usage", "weight": 0.3}
]
```

**ConstraintConfig（约束开关配置）**：

```python
@dataclass
class ConstraintConfig:
    enable_not_before: bool = False   # 策略A阻塞：not_before 约束
    enable_deadline:   bool = False   # 项目截止时间约束（预留）
    # 未来扩展：enable_resource_smoothing / enable_soft_precedence 等
```

### 3.5 Solver 主流程（编排层）

```python
# solver/solver.py

"""
职责：编排 StateDelta → RAGBuilder → Scheduler 的完整求解流程
      持久化求解结果到数据库
"""

class Solver:
    def solve(self, request: SolveRequest) -> SolveResult:
        """
        完整求解流程：
          1. 加载起点状态和目标状态
          2. 加载 feature_definition（供 RuleEvaluator 类型安全使用）
          3. 若有阻塞约束（blockage_constraints）：
             a. 策略B：将 blockage_reason 注入 current_state
          4. StateDelta.compute() → state_delta
          5. RAGBuilder.build(current_state, goal_state, blockage_constraints) → rag
          6. Scheduler.schedule(rag, resources, objectives, constraints) → schedule
          7. 持久化：
             a. 创建 candidate_plan（version 递增，parent_plan_id 指向上一版本）
             b. 创建 candidate_plan_step（含 step_role 标注）
             c. 若有阻塞：创建 blockage_event
          8. 若 request.parent_plan_id 存在：
             对新旧计划步骤做 diff，标注 step_role
             （unchanged / repair / pulled_forward / delayed）
          9. 返回 SolveResult
        """
```

---

## 第四章：数据模型

### 4.1 完整表结构

#### 配置表（规则库）

```sql
-- ━━━━━━ 特征类型定义表（V0.2 新增）━━━━━━
CREATE TABLE feature_definition (
    feature_key    VARCHAR(128) PRIMARY KEY,
    value_type     VARCHAR(32)  NOT NULL,
    -- 枚举值：'string' / 'number' / 'boolean' / 'enum'
    allowed_values JSONB,
    -- value_type='enum' 时定义合法值列表，例如：["hot", "cold", "warm"]
    unit           VARCHAR(32),
    -- 可选单位，例如：'bar' / 'celsius' / 'count'
    description    TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ━━━━━━ 工序规则表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE op_rule (
    id             SERIAL PRIMARY KEY,
    code           VARCHAR(64)  NOT NULL UNIQUE,
    -- 命名约定：维修类型工序统一用 'OP_REPAIR_' 前缀
    name           VARCHAR(128) NOT NULL,
    duration_min   INTEGER      NOT NULL,
    -- 单位：分钟
    is_repair      BOOLEAN      NOT NULL DEFAULT FALSE,
    -- TRUE 表示维修维护类工序，参与策略B的自动匹配
    valid_from     TIMESTAMP,
    valid_to       TIMESTAMP,
    -- 规则有效期，NULL 表示无限制
    description    TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ━━━━━━ 前置条件表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE op_rule_precond (
    id             SERIAL PRIMARY KEY,
    op_rule_id     INTEGER     NOT NULL REFERENCES op_rule(id) ON DELETE CASCADE,
    feature_key    VARCHAR(128) NOT NULL REFERENCES feature_definition(feature_key),
    operator       VARCHAR(16)  NOT NULL DEFAULT 'eq',
    -- 枚举值：'eq' / 'neq' / 'gt' / 'gte' / 'lt' / 'lte' / 'in'
    feature_value  VARCHAR(256),
    -- operator 为 'eq'/'neq'/'gt'/'gte'/'lt'/'lte' 时使用
    value_list     JSONB
    -- operator 为 'in' 时使用，例如：["hot", "warm"]
);

-- ━━━━━━ 执行效果表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE op_rule_effect (
    id             SERIAL PRIMARY KEY,
    op_rule_id     INTEGER      NOT NULL REFERENCES op_rule(id) ON DELETE CASCADE,
    feature_key    VARCHAR(128) NOT NULL REFERENCES feature_definition(feature_key),
    effect_type    VARCHAR(32)  NOT NULL DEFAULT 'set',
    -- 枚举值：'set' / 'increment' / 'decrement'
    new_value      VARCHAR(256),
    -- effect_type='set' 时使用
    delta_value    NUMERIC
    -- effect_type='increment'/'decrement' 时使用
);

-- ━━━━━━ 资源表（V0.1 已有）━━━━━━
CREATE TABLE resource (
    id             SERIAL PRIMARY KEY,
    code           VARCHAR(64)  NOT NULL UNIQUE,
    name           VARCHAR(128) NOT NULL,
    resource_type  VARCHAR(64)  NOT NULL,
    -- 枚举值：'person' / 'crane' / 'assembly_space' 等
    description    TEXT
);

-- ━━━━━━ 工序规则与资源的关联表（V0.1 已有）━━━━━━
CREATE TABLE op_rule_resource (
    op_rule_id     INTEGER NOT NULL REFERENCES op_rule(id) ON DELETE CASCADE,
    resource_id    INTEGER NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    quantity       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (op_rule_id, resource_id)
);
```

#### 运行时表（求解与计划）

```sql
-- ━━━━━━ 机台状态快照表（V0.1 已有）━━━━━━
CREATE TABLE machine_state (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(128) NOT NULL,
    -- 例如：'起点状态_2026-04-10' / '目标状态'
    state_type     VARCHAR(32)  NOT NULL,
    -- 枚举值：'start' / 'goal'
    description    TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE machine_state_feature (
    id             SERIAL PRIMARY KEY,
    state_id       INTEGER      NOT NULL REFERENCES machine_state(id) ON DELETE CASCADE,
    feature_key    VARCHAR(128) NOT NULL REFERENCES feature_definition(feature_key),
    feature_value  VARCHAR(256) NOT NULL
);

-- ━━━━━━ 求解请求表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE solve_request (
    id               SERIAL PRIMARY KEY,
    start_state_id   INTEGER NOT NULL REFERENCES machine_state(id),
    goal_state_id    INTEGER NOT NULL REFERENCES machine_state(id),
    objectives       JSONB   NOT NULL DEFAULT '[{"type": "minimize_makespan", "weight": 1.0}]',
    -- V0.2：数组格式，支持未来多目标
    -- 示例：[{"type": "minimize_makespan", "weight": 1.0}]
    constraints      JSONB   NOT NULL DEFAULT '{}',
    -- 约束开关配置
    -- 示例：{"enable_not_before": true, "enable_deadline": false}
    parent_plan_id   INTEGER REFERENCES candidate_plan(id),
    -- 重排时指向被重排的计划版本，初次求解时为 NULL
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ━━━━━━ 计划版本表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE candidate_plan (
    id               SERIAL PRIMARY KEY,
    solve_request_id INTEGER     NOT NULL REFERENCES solve_request(id),
    version          INTEGER     NOT NULL DEFAULT 1,
    parent_plan_id   INTEGER     REFERENCES candidate_plan(id),
    -- 版本链，初始计划为 NULL
    replan_reason    VARCHAR(64),
    -- 枚举值：'initial' / 'blockage_strategy_a' /
    --         'blockage_strategy_b' / 'blockage_strategy_ab'
    total_duration_min INTEGER,
    -- 求解结果：总工期（分钟）
    status           VARCHAR(32) NOT NULL DEFAULT 'draft',
    -- 枚举值：'draft' / 'confirmed' / 'superseded'
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ━━━━━━ 计划步骤表（V0.1 已有，V0.2 扩展）━━━━━━
CREATE TABLE candidate_plan_step (
    id               SERIAL PRIMARY KEY,
    plan_id          INTEGER     NOT NULL REFERENCES candidate_plan(id) ON DELETE CASCADE,
    op_rule_id       INTEGER     NOT NULL REFERENCES op_rule(id),
    step_order       INTEGER     NOT NULL,
    start_min        INTEGER     NOT NULL,
    -- 相对计划起点的开始时间（分钟）
    duration_min     INTEGER     NOT NULL,
    end_min          INTEGER     NOT NULL GENERATED ALWAYS AS (start_min + duration_min) STORED,
    resource_id      INTEGER     REFERENCES resource(id),
    not_before       INTEGER,
    -- 策略A时由计划师指定，单位同 start_min（分钟），NULL 表示无约束
    step_role        VARCHAR(32) NOT NULL DEFAULT 'normal'
    -- 枚举值：
    --   'normal'         正常步骤，未发生变化
    --   'repair'         维修序列（策略B新插入）
    --   'pulled_forward' 被提拉提前执行（策略A/AB）
    --   'delayed'        被延后执行
);

-- ━━━━━━ 阻塞事件表（V0.2 新增）━━━━━━
CREATE TABLE blockage_event (
    id                SERIAL PRIMARY KEY,
    plan_id           INTEGER     NOT NULL REFERENCES candidate_plan(id),
    blocked_step_id   INTEGER     NOT NULL REFERENCES candidate_plan_step(id),
    strategy          VARCHAR(8)  NOT NULL,
    -- 枚举值：'A' / 'B' / 'AB'
    not_before_offset INTEGER,
    -- 策略A：计划师指定的"不早于"时间，单位：分钟（相对计划起点）
    blockage_reason   VARCHAR(64),
    -- 策略B：写入机台状态特征的 blockage_reason 值
    --        同时作为维修序列 op_rule_precond 的匹配键
    note              TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by        VARCHAR(64)
);
```

### 4.2 数据模型关系图

```
feature_definition (1) ──────────────────────── (N) op_rule_precond
feature_definition (1) ──────────────────────── (N) op_rule_effect
feature_definition (1) ──────────────────────── (N) machine_state_feature

op_rule (1) ─────────────────────────────────── (N) op_rule_precond
op_rule (1) ─────────────────────────────────── (N) op_rule_effect
op_rule (1) ─────────────────────────────────── (N) op_rule_resource
op_rule (1) ─────────────────────────────────── (N) candidate_plan_step

resource (1) ────────────────────────────────── (N) op_rule_resource
resource (1) ────────────────────────────────── (N) candidate_plan_step

machine_state (1) ───────────────────────────── (N) machine_state_feature
machine_state (start) ───── solve_request ────── machine_state (goal)

solve_request (1) ───────────────────────────── (N) candidate_plan
candidate_plan (parent 1) ───────────────────── (N) candidate_plan (child)
candidate_plan (1) ──────────────────────────── (N) candidate_plan_step
candidate_plan (1) ──────────────────────────── (N) blockage_event

blockage_event (N) ──────────────────────────── (1) candidate_plan_step
```

### 4.3 种子数据约定

```sql
-- 维修序列规则示例（策略B 至少需要这两条）
INSERT INTO feature_definition (feature_key, value_type, allowed_values) VALUES
```sql
  ('blockage_reason', 'enum',
   '["none", "hardware_fault", "pending_approval", "material_missing"]'),
  ('temperature_level', 'enum',
   '["cold", "warm", "hot"]'),
  ('calibration_status', 'enum',
   '["uncalibrated", "calibrated"]'),
  ('cleanliness', 'enum',
   '["dirty", "clean"]'),
  ('integration_status', 'enum',
   '["blocked", "ready", "completed"]');

-- 维修序列工序规则（is_repair = TRUE）
INSERT INTO op_rule (code, name, duration_min, is_repair) VALUES
  ('OP_REPAIR_HARDWARE', '硬件故障攻关修复', 120, TRUE),
  ('OP_REPAIR_APPROVAL', '审批等待处理',      60, TRUE);

-- OP_REPAIR_HARDWARE precondition：匹配 blockage_reason = hardware_fault
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
  SELECT id, 'blockage_reason', 'eq', 'hardware_fault'
  FROM op_rule WHERE code = 'OP_REPAIR_HARDWARE';

-- OP_REPAIR_HARDWARE effect：清除 blockage_reason，恢复 integration_status
INSERT INTO op_rule_effect (op_rule_id, feature_key, effect_type, new_value)
  SELECT id, 'blockage_reason',   'set', 'none'
  FROM op_rule WHERE code = 'OP_REPAIR_HARDWARE'
UNION ALL
  SELECT id, 'integration_status', 'set', 'ready'
  FROM op_rule WHERE code = 'OP_REPAIR_HARDWARE';

-- OP_REPAIR_APPROVAL precondition：匹配 blockage_reason = pending_approval
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
  SELECT id, 'blockage_reason', 'eq', 'pending_approval'
  FROM op_rule WHERE code = 'OP_REPAIR_APPROVAL';

-- OP_REPAIR_APPROVAL effect：清除 blockage_reason
INSERT INTO op_rule_effect (op_rule_id, feature_key, effect_type, new_value)
  SELECT id, 'blockage_reason', 'set', 'none'
  FROM op_rule WHERE code = 'OP_REPAIR_APPROVAL';
```

---

## 第五章：API 接口设计

### 5.1 接口总览

```
GET    /api/v1/features                    获取所有特征定义
POST   /api/v1/features                    新增特征定义
PUT    /api/v1/features/{feature_key}      更新特征定义
DELETE /api/v1/features/{feature_key}      删除特征定义

GET    /api/v1/rules                       获取所有工序规则（含 precond / effect）
POST   /api/v1/rules                       新增工序规则
PUT    /api/v1/rules/{id}                  更新工序规则
DELETE /api/v1/rules/{id}                  删除工序规则

GET    /api/v1/resources                   获取所有资源
POST   /api/v1/resources                   新增资源
PUT    /api/v1/resources/{id}              更新资源
DELETE /api/v1/resources/{id}              删除资源

GET    /api/v1/states                      获取所有状态快照
POST   /api/v1/states                      新增状态快照
PUT    /api/v1/states/{id}                 更新状态快照
DELETE /api/v1/states/{id}                 删除状态快照

POST   /api/v1/solve                       触发求解（初次 + 重排）
GET    /api/v1/plans                       获取所有计划版本列表
GET    /api/v1/plans/{id}                  获取单个计划详情（含步骤）
GET    /api/v1/plans/{id}/versions         获取某计划的完整版本链
GET    /api/v1/plans/{id}/diff/{other_id}  获取两个版本的 diff 结果
```

### 5.2 核心接口详细定义

#### POST /api/v1/solve

```json
// 请求体
{
  "start_state_id": 1,
  "goal_state_id": 2,

  "objectives": [
    {"type": "minimize_makespan", "weight": 1.0}
  ],

  "constraints": {
    "enable_not_before": false,
    "enable_deadline": false
  },

  "blockage_constraints": null,
  // 无阻塞时为 null，有阻塞时见下方结构

  "parent_plan_id": null
  // 初次求解为 null，重排时填写被重排的 plan_id
}

// 阻塞约束结构（blockage_constraints 非 null 时）
{
  "blocked_step_id": 5,
  // candidate_plan_step.id，被标记阻塞的步骤

  "strategy": "AB",
  // 枚举值：'A' / 'B' / 'AB'

  "strategy_a": {
    "not_before_offset": 120
    // 单位：分钟，相对计划起点
  },

  "strategy_b": {
    "blockage_reason": "hardware_fault"
    // 必须是 feature_definition 中 blockage_reason 的合法 enum 值
  },

  "note": "主轴传感器异常，攻关预计2小时",
  "created_by": "张工"
}
```

```json
// 响应体（HTTP 200）
{
  "plan_id": 3,
  "version": 2,
  "parent_plan_id": 1,
  "replan_reason": "blockage_strategy_ab",
  "total_duration_min": 180,
  "status": "draft",

  "state_delta": [
    {
      "feature_key": "temperature_level",
      "from": "cold",
      "to": "hot",
      "value_type": "enum"
    }
  ],
  // StateDelta 结构化输出，可解释性数据

  "steps": [
    {
      "id": 12,
      "op_rule_code": "OP_WARMUP",
      "op_rule_name": "设备暖机",
      "step_order": 1,
      "start_min": 0,
      "duration_min": 30,
      "end_min": 30,
      "resource_id": 1,
      "resource_code": "TECH-01",
      "not_before": null,
      "step_role": "normal"
    },
    {
      "id": 13,
      "op_rule_code": "OP_REPAIR_HARDWARE",
      "op_rule_name": "硬件故障攻关修复",
      "step_order": 2,
      "start_min": 30,
      "duration_min": 120,
      "end_min": 150,
      "resource_id": 1,
      "resource_code": "TECH-01",
      "not_before": null,
      "step_role": "repair"
    },
    {
      "id": 14,
      "op_rule_code": "OP_CLEANING",
      "op_rule_name": "设备清洁",
      "step_order": 3,
      "start_min": 30,
      "duration_min": 30,
      "end_min": 60,
      "resource_id": 2,
      "resource_code": "TECH-02",
      "not_before": null,
      "step_role": "pulled_forward"
    },
    {
      "id": 15,
      "op_rule_code": "OP_CALIBRATE",
      "op_rule_name": "设备校准",
      "step_order": 4,
      "start_min": 150,
      "duration_min": 30,
      "end_min": 180,
      "resource_id": 1,
      "resource_code": "TECH-01",
      "not_before": 120,
      "step_role": "delayed"
    }
  ],

  "critical_path": ["OP_WARMUP", "OP_REPAIR_HARDWARE", "OP_CALIBRATE"],
  // 可解释性：关键路径

  "parallel_groups": [
    ["OP_REPAIR_HARDWARE", "OP_CLEANING"]
  ]
  // 可解释性：并行执行的工序组
}
```

#### GET /api/v1/plans/{id}/diff/{other_id}

```json
// 响应体（HTTP 200）
// 对比 plan_id=1（原始）与 plan_id=3（重排后）
{
  "base_plan_id": 1,
  "compare_plan_id": 3,
  "summary": {
    "inserted": 1,
    "delayed": 1,
    "pulled_forward": 1,
    "unchanged": 1
  },
  "steps": [
    {
      "op_rule_code": "OP_WARMUP",
      "change_type": "unchanged",
      "base_start_min": 0,
      "compare_start_min": 0,
      "delta_min": 0
    },
    {
      "op_rule_code": "OP_REPAIR_HARDWARE",
      "change_type": "inserted",
      "base_start_min": null,
      "compare_start_min": 30,
      "delta_min": null
    },
    {
      "op_rule_code": "OP_CLEANING",
      "change_type": "pulled_forward",
      "base_start_min": 90,
      "compare_start_min": 30,
      "delta_min": -60
    },
    {
      "op_rule_code": "OP_CALIBRATE",
      "change_type": "delayed",
      "base_start_min": 60,
      "compare_start_min": 150,
      "delta_min": 90
    }
  ]
}
```

### 5.3 通用错误响应格式

```json
// HTTP 4xx / 5xx
{
  "error_code": "RULE_PRECOND_UNKNOWN_FEATURE",
  "message": "precondition 引用了未定义的特征：temperature_level_x",
  "detail": {
    "op_rule_code": "OP_WARMUP",
    "feature_key": "temperature_level_x"
  }
}
```

**错误码约定**：

```
FEATURE_NOT_FOUND          特征定义不存在
FEATURE_VALUE_INVALID      特征值不在 allowed_values 范围内
RULE_NOT_FOUND             工序规则不存在
RULE_PRECOND_UNKNOWN_FEATURE  precondition 引用未定义特征
STATE_NOT_FOUND            状态快照不存在
SOLVE_NO_SOLUTION          求解无解（状态差无法被规则库覆盖）
SOLVE_DEPTH_EXCEEDED       搜索深度超过 MAX_SEARCH_DEPTH
SOLVE_CYCLE_DETECTED       规则库中存在循环依赖
BLOCKAGE_REASON_INVALID    blockage_reason 不在合法枚举值中
PLAN_NOT_FOUND             计划版本不存在
```

---

## 第六章：前端设计约定

### 6.1 页面路由

```
/features          特征定义管理页（FeatureDefinitionPage）
/rules             工序规则管理页（RulePage）
/resources         资源管理页（ResourcePage）
/states            状态快照管理页（StatePage）
/solve             求解操作页（SolvePage）
```

### 6.2 各页面职责

**FeatureDefinitionPage**：
```
功能：CRUD 特征定义
特殊逻辑：
  value_type 选择 'enum' 时，展示 allowed_values 多值输入
  value_type 选择 'number' 时，可选填 unit 字段
  feature_key 不允许修改（作为外键被其他表引用）
  删除前检查是否有 op_rule_precond / op_rule_effect 引用，有则阻止并提示
```

**RulePage**：
```
功能：CRUD 工序规则（含 precondition / effect / resource 关联）
特殊逻辑：
  precondition 的 feature_key 下拉列表从 feature_definition 表动态加载
  operator 选择 'in' 时，feature_value 输入框替换为多值 Tag 输入
  effect 的 effect_type 选择 'increment'/'decrement' 时：
    new_value 输入框隐藏，显示 delta_value 数字输入框
  is_repair = TRUE 的规则在列表中用橙色标签标识
  valid_from / valid_to 字段用日期选择器展示
```

**StatePage**：
```
功能：CRUD 状态快照（起点状态 / 目标状态）
特殊逻辑：
  state_type 区分 'start' / 'goal'，用颜色标签区分
  每个特征键值对的输入根据 feature_definition.value_type 渲染不同控件：
    'enum'    → Select 下拉（选项来自 allowed_values）
    'number'  → InputNumber（附带 unit 显示）
    'boolean' → Switch 开关
    'string'  → Input 文本框
```

**SolvePage**：
```
功能：触发求解 + 查看结果 + 阻塞处理 + 版本对比

布局：
┌─────────────────────────────────────────────────────────┐
│  求解配置区                                              │
│  起点状态: [下拉选择]  目标状态: [下拉选择]               │
│  优化目标: [minimize_makespan ▾]  权重: [1.0]            │
│  [触发求解]                                             │
├─────────────────────────────────────────────────────────┤
│  版本历史区                                              │
│  v1 初始计划  2026-04-10 14:00  [查看][设为当前]         │
│  v2 阻塞重排  2026-04-10 15:00  [查看][设为当前][对比▾]  │ ← 当前
├─────────────────────────────────────────────────────────┤
│  甘特图区（当前版本 / 对比模式）                          │
│  [甘特图组件 GanttChart]                                 │
├─────────────────────────────────────────────────────────┤
│  可解释性区                                              │
│  状态差：需改变 N 个特征  关键路径：OP_A → OP_B → OP_C   │
│  并行组：[OP_X, OP_Y]                                   │
└─────────────────────────────────────────────────────────┘
```

### 6.3 GanttChart 组件约定

```
技术：ECharts（自定义系列实现甘特图）
数据驱动：直接消费 /api/v1/solve 或 /api/v1/plans/{id} 返回的 steps 数组

step_role 颜色约定：
  'normal'         → #5470C6（蓝色，默认）
  'repair'         → #FAC858（橙色，维修序列）
  'pulled_forward' → #91CC75（绿色，被提拉）
  'delayed'        → #EE6666（红色，被延后）

对比模式：
  左右两个甘特图并排展示
  消费 /api/v1/plans/{id}/diff/{other_id} 数据
  change_type 对应上述颜色，'unchanged' 用灰色

Tooltip：
  悬浮显示：工序名称 / 开始时间 / 结束时间 /
            资源 / step_role / not_before（若存在）
```

### 6.4 BlockageDialog 组件约定

```
触发方式：在 GanttChart 中点击某个步骤 → "标记阻塞" 按钮

┌─────────────────────────────────────────────────────┐
│  标记阻塞：OP_CALIBRATE（设备校准）                   │
├─────────────────────────────────────────────────────┤
│  处理策略                                            │
│  ┌─────────────────────────────────────────────┐   │
│  │  ☑ 策略 A：离线修复（活动提拉）               │   │
│  │     阻塞步骤不早于：[+120] 分钟后开始          │   │
│  ├─────────────────────────────────────────────┤   │
│  │  ☑ 策略 B：攻关修复（插入维修序列）            │   │
│  │     阻塞原因：[hardware_fault ▾]              │   │
│  │     （下拉列表动态读取 blockage_reason        │   │
│  │       的 allowed_values，排除 'none'）        │   │
│  └─────────────────────────────────────────────┘   │
│  备注：[___________________________________]        │
│  操作人：[___________________________________]      │
│                                                     │
│               [取消]  [确认并重新求解]               │
└─────────────────────────────────────────────────────┘

表单校验：
  至少勾选一种策略
  策略A勾选时：not_before_offset 必填且 > 0
  策略B勾选时：blockage_reason 必选
```

---

## 第七章：V0.2 开发任务清单

### 7.1 任务分类

V0.2 包含两类任务，必须同步完成：

```
类型 1：主线功能（阻塞处理与动态重排）
类型 2：架构升级（为远景打基础，不可推后）
```

### 7.2 完整任务列表（按建议开发顺序）

```
━━━━━━ STEP 1：数据模型扩展 ━━━━━━

□ 1-1  新增 feature_definition 表（架构升级）
□ 1-2  op_rule_precond 新增 operator / value_list 字段（架构升级）
□ 1-3  op_rule_effect 新增 effect_type / delta_value 字段（架构升级）
□ 1-4  op_rule 新增 is_repair / valid_from / valid_to 字段（主线依赖）
□ 1-5  solve_request 新增 objectives(JSONB) / constraints(JSONB) /
        parent_plan_id 字段（主线依赖 + 架构升级）
□ 1-6  candidate_plan 新增 version / parent_plan_id /
        replan_reason / status 字段（主线依赖）
□ 1-7  candidate_plan_step 新增 not_before / step_role 字段（主线依赖）
□ 1-8  新增 blockage_event 表（主线依赖）
□ 1-9  写入种子数据（feature_definition 基础特征 +
        OP_REPAIR_HARDWARE / OP_REPAIR_APPROVAL 规则）

━━━━━━ STEP 2：领域层架构升级 ━━━━━━

□ 2-1  实现 OperatorRegistry + 7 个 Operator 类（架构升级）
        eq / neq / gt / gte / lt / lte / in
□ 2-2  实现 EffectRegistry + 3 个 Effect 类（架构升级）
        set / increment / decrement
□ 2-3  实现 RuleEvaluator（架构升级）
        evaluate_precond() + apply_effect()
        含 feature_definition 类型安全转换
□ 2-4  升级 RAGBuilder（架构升级 + 主线依赖）
        将 precond 匹配逻辑替换为 RuleEvaluator 调用
        新增 visited_states 循环检测
        新增 MAX_SEARCH_DEPTH 深度限制
□ 2-5  实现 ObjectiveRegistry + MinimizeMakespanObjective（架构升级）
□ 2-6  升级 Scheduler（架构升级 + 主线依赖）
        objectives 改为数组处理
        新增 ConstraintConfig 约束开关
        新增 not_before 约束注入逻辑（策略A）
□ 2-7  升级 Solver 主流程（主线依赖）
        处理 blockage_constraints 参数
        策略B：blockage_reason 注入 current_state
        版本链写入：candidate_plan version / parent_plan_id
        步骤 diff 计算：step_role 标注
        blockage_event 持久化

━━━━━━ STEP 3：API 层扩展 ━━━━━━

□ 3-1  新增 /api/v1/features CRUD 接口
□ 3-2  升级 /api/v1/rules CRUD 接口
        支持 precond 的 operator / value_list
        支持 effect 的 effect_type / delta_value
        支持 op_rule 的 is_repair / valid_from / valid_to
□ 3-3  升级 POST /api/v1/solve 接口
        接受 objectives / constraints / blockage_constraints / parent_plan_id
        返回 state_delta / critical_path / parallel_groups
□ 3-4  新增 GET /api/v1/plans/{id}/versions 接口
□ 3-5  新增 GET /api/v1/plans/{id}/diff/{other_id} 接口

━━━━━━ STEP 4：前端新增组件 ━━━━━━

□ 4-1  新增 FeatureDefinitionPage
        CRUD + value_type 联动控件 + 引用保护删除
□ 4-2  升级 RulePage
        precond 支持 operator 选择 + 'in' 时多值输入
        effect 支持 effect_type 联动控件
        is_repair 橙色标签
□ 4-3  升级 StatePage
        特征输入根据 value_type 渲染对应控件
□ 4-4  新增 BlockageDialog 组件
        策略选择 + 参数填写 + 表单校验 + 触发重排
□ 4-5  升级 GanttChart 组件
        step_role 颜色区分
        对比模式（左右并排）
□ 4-6  升级 SolvePage
        版本历史面板
        可解释性展示区（state_delta / critical_path / parallel_groups）
        BlockageDialog 集成
```

### 7.3 验收标准

```
STEP 2 验收（领域层）：

□ 场景1（策略A）：
  给定计划版本 v1，标记 OP_CALIBRATE 阻塞，策略A，not_before=120min
  → 新计划 v2 中 OP_CALIBRATE.start_min >= 120
  → RAG 中不依赖 OP_CALIBRATE 的步骤被提拉至 120min 前
  → v2.parent_plan_id = v1.id，v2.replan_reason = 'blockage_strategy_a'

□ 场景2（策略B）：
  给定计划版本 v1，标记 OP_CALIBRATE 阻塞，策略B，blockage_reason=hardware_fault
  → 新计划 v2 的步骤列表中出现 OP_REPAIR_HARDWARE
  → OP_REPAIR_HARDWARE 位于 OP_CALIBRATE 之前
  → OP_REPAIR_HARDWARE.step_role = 'repair'
  → blockage_event 表写入一条记录

□ 场景3（策略AB）：
  策略A + 策略B 同时使用
  → 新计划中同时出现 OP_REPAIR_HARDWARE（repair）
     和被提拉步骤（pulled_forward）
  → OP_CALIBRATE.start_min >= not_before_offset
  → CP-SAT 正确仲裁 OP_REPAIR_HARDWARE 与提拉步骤的资源竞争

□ 场景4（循环检测）：
  规则库中故意写入循环依赖规则（A的effect满足B的precond，B的effect满足A的precond）
  → RAGBuilder 抛出 SOLVE_CYCLE_DETECTED 错误，不死循环

□ 场景5（类型安全）：
  feature_definition 中 pressure_bar 的 value_type = 'number'
  precondition operator = 'gte'，feature_value = '3.5'
  current_state 中 pressure_bar = '3.8'
  → RuleEvaluator 正确将两者转为 float 比较，返回 True
```

---

## 第八章：版本路线图

```
┌─────────────────────────────────────────────────────────┐
│  V0.1（已完成）                                          │
│                                                         │
│  ✅ 基础求解链路：                                        │
│     状态推导 RAG + CP-SAT 排程                           │
│  ✅ 核心数据模型：                                        │
│     op_rule / machine_state / resource                   │
│  ✅ 基础 FastAPI 接口                                    │
│  ✅ 基础前端界面                                         │
└─────────────────────────────────────────────────────────┘
                          ↓ 当前
┌─────────────────────────────────────────────────────────┐
│  V0.2（当前版本）                                        │
│                                                         │
│  🎯 主线：阻塞处理与动态重排                             │
│     策略A（活动提拉）/ 策略B（维修序列）/ A+B 并用        │
│     计划版本链 / 版本对比甘特图                          │
│                                                         │
│  🏗️ 架构升级（为远景打基础）                             │
│     feature_definition 类型系统                         │
│     precondition operator 扩展                          │
│     effect effect_type 扩展                             │
│     RuleEvaluator 策略模式抽象层                         │
│     RAGBuilder 循环检测 + 深度限制                       │
│     objectives 接口数组化                               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  V0.3（计划）                                            │
│                                                         │
│  □ 求解可解释性深化                                      │
│     precond/effect 推导链完整记录（why_this_order）       │
│     关键路径高亮展示                                     │
│  □ 多目标优化                                           │
│     ObjectiveRegistry 扩展 minimize_resource_usage 等   │
│     前端权重配置界面                                     │
│  □ 工序组（Composite Operation）                        │
│     op_rule 支持 is_composite + sub_op_rules            │
│  □ 搜索策略可插拔                                        │
│     RAGBuilder 支持 A* 启发式搜索                        │
│     启发函数可配置（最短工期 / 最少资源）                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  V1.0（远景）                                            │
│                                                         │
│  □ 规则库规模：支持几千条规则                            │
│     规则 CRUD 界面完整支持批量导入（CSV/JSON）            │
│     规则冲突检测（同一 precond 对应多条 effect 冲突）     │
│  □ 项目 Deadline 约束                                   │
│     enable_deadline 开关实现                            │
│     deadline 违约量报告                                 │
│  □ 历史阻塞模式库                                        │
│     blockage_event 积累后的相似阻塞推荐                  │
│  □ 外部系统集成接口预留                                  │
│     Webhook 接收外部执行状态推送                         │
│     与项目管理系统的双向数据同步接口                     │
└─────────────────────────────────────────────────────────┘
```

---

## 第九章：AI 编程助手注意事项

> 以下约定为硬性规则，开发时必须遵守。

### 9.1 架构约束

```
约束 1：规则评估必须经过 RuleEvaluator
  ❌ 禁止在 RAGBuilder / Scheduler / API 层直接写 precondition 比较逻辑
  ✅ 所有 precond 匹配和 effect 应用通过 RuleEvaluator 统一调用

约束 2：零侵入扩展原则
  新增参数必须有合理的默认值，确保不传该参数时行为与上一版本完全一致
  示例：blockage_constraints=None 时，求解流程与 V0.1 完全相同

约束 3：状态不可变原则
  RuleEvaluator.apply_effect() 必须返回新状态副本，不修改传入的 state 对象
  RAGBuilder 中每次 BFS 展开都操作状态副本，防止状态污染

约束 4：阻塞语义不侵入 RAGBuilder
  RAGBuilder 不感知"阻塞"的业务概念
  阻塞处理通过"在 current_state 中注入 blockage_reason 特征"实现
  RAGBuilder 只做通用的规则匹配，维修序列的插入是规则推导的自然结果
```

### 9.2 数据约束

```
约束 5：feature_key 是系统的外键锚点
  feature_definition.feature_key 被 op_rule_precond / op_rule_effect /
  machine_state_feature 三张表引用
  任何新增特征必须先在 feature_definition 中定义
  删除 feature_definition 记录前必须检查三张表的引用

约束 6：blockage_reason 的合法值来自数据库
  前端 BlockageDialog 的阻塞原因下拉列表必须动态读取：
  SELECT allowed_values FROM feature_definition
  WHERE feature_key = 'blockage_reason'
  不可硬编码枚举值在前端

约束 7：时间单位统一
  系统中所有时间偏移量（start_min / duration_min / not_before_offset）
  统一使用"分钟"作为单位，字段名以 _min 结尾
  不允许混用秒、小时等单位

约束 8：step_role 标注时机
  step_role 在 Solver 主流程中、CP-SAT 求解完成后
  通过新旧计划 diff 计算得出
  不在 RAGBuilder 或 Scheduler 内部标注
  'repair' 步骤的判断依据是 op_rule.is_repair = TRUE
```

### 9.3 错误处理约定

```
约束 9：求解失败必须给出可诊断的错误
  SOLVE_NO_SOLUTION 时，响应体必须包含 unresolved_delta：
  {
    "error_code": "SOLVE_NO_SOLUTION",
    "detail": {
      "unresolved_delta": [
        {"feature_key": "pressure_bar", "from": "2.0", "to": "5.0"}
      ],
      "message": "规则库中没有能将 pressure_bar 从 2.0 变更为 5.0 的工序规则"
    }
  }

  SOLVE_CYCLE_DETECTED 时，必须包含检测到的循环路径：
  {
    "error_code": "SOLVE_CYCLE_DETECTED",
    "detail": {
      "cycle_path": ["OP_A", "OP_B", "OP_A"]
    }
  }

约束 10：前端错误展示
  所有 API 错误统一通过 Element Plus 的 ElMessage.error() 展示
  错误信息使用 error_code 对应的中文描述（维护一份 error_code → 中文 的映射表）
```

### 9.4 代码风格约定

```
```
约束 11：后端
  所有数据库查询통过 SQLAlchemy ORM，禁止裸 SQL（迁移脚本除外）
  Pydantic Schema 与 SQLAlchemy Model 严格分离，不混用
  API 层只调用 Service 层，Service 层只调用 Domain 层
  Domain 层（solver/）不直接导入 FastAPI 相关模块
  类型注解必须完整（函数参数和返回值都需要）

约束 12：前端
  所有 API 调用统一通过 src/api/ 下的封装函数，不在组件内直接使用 axios
  组件 Props 必须定义类型和默认值
  GanttChart / BlockageDialog 作为纯组件，不直接调用 API，
  数据由父页面传入，事件通过 emit 向上传递

约束 13：注册表模式实现规范
  OperatorRegistry / EffectRegistry / ObjectiveRegistry
  统一使用装饰器注册方式：

  @OperatorRegistry.register('eq')
  class EqualOperator(BaseOperator):
      def evaluate(self, current_value: Any, target_value: Any) -> bool:
          ...

  禁止在注册表类内部硬编码 if/elif 分支做类型分发
```

### 9.5 测试约定

```
约束 14：领域层必须有单元测试
  RuleEvaluator 的每个 Operator 和 Effect 都需要独立测试
  RAGBuilder 必须有循环检测和深度限制的测试用例
  Solver 主流程必须有策略A / 策略B / AB 三个场景的集成测试
  测试数据使用 pytest fixture，不依赖真实数据库（使用 SQLite in-memory）

约束 15：验收测试用例对应第七章 7.3 的五个场景
  tests/test_solver_blockage.py 文件覆盖所有五个验收场景
  每个场景必须断言：
    - 新计划的 version 和 parent_plan_id
    - 每个步骤的 step_role
    - 阻塞步骤的 start_min 满足约束
    - blockage_event 表的写入
```

---

## 附录 A：关键业务语义词汇表

```
术语                    含义
─────────────────────────────────────────────────────────────
机台                   被集成的目标设备（含硬件+软件+接口）
起点状态               集成开始时机台的实际状态（特征键值对集合）
目标状态               集成完成后机台应达到的状态（特征键值对集合）
状态差（delta）         起点状态与目标状态之间需要改变的特征集合
工序规则（op_rule）     能使机台从一种状态变迁到另一种状态的操作单元
前置条件（precondition）执行该工序所需满足的当前状态条件
执行效果（effect）      执行该工序后对机台状态产生的变更
RAG                   有向无环图，节点为工序，边为执行依赖关系
关键路径               RAG 中决定总工期的最长路径
排程（schedule）       为 RAG 中每个工序分配具体开始时间和资源
阻塞（blockage）       某个计划步骤因外部原因无法在预定时间开始执行
策略A（活动提拉）       阻塞步骤延后执行，不依赖阻塞步骤的其他步骤提前执行
策略B（维修序列）       在规则库中匹配对应的维修工序，插入 RAG 中
维修工序（repair op）   is_repair=TRUE 的工序，通过 blockage_reason 特征匹配触发
版本链                 同一求解请求下，多次重排产生的 candidate_plan 父子关系
step_role             标注步骤在版本对比中的变化类型
                       normal/repair/pulled_forward/delayed
```

---

## 附录 B：典型求解场景示例

### B.1 初次求解（无阻塞）

```
起点状态：
  temperature_level   = cold
  calibration_status  = uncalibrated
  cleanliness         = dirty
  integration_status  = ready

目标状态：
  temperature_level   = hot
  calibration_status  = calibrated
  cleanliness         = clean
  integration_status  = completed

状态差：
  temperature_level:   cold → hot
  calibration_status:  uncalibrated → calibrated
  cleanliness:         dirty → clean
  integration_status:  ready → completed

规则库匹配结果（RAG）：
  OP_WARMUP    precond: temperature_level=cold
               effect:  temperature_level=hot

  OP_CALIBRATE precond: temperature_level=hot,
                        calibration_status=uncalibrated
               effect:  calibration_status=calibrated

  OP_CLEANING  precond: cleanliness=dirty
               effect:  cleanliness=clean

  OP_FINAL     precond: calibration_status=calibrated,
                        cleanliness=clean
               effect:  integration_status=completed

依赖关系推导：
  OP_WARMUP → OP_CALIBRATE（OP_CALIBRATE 需要 temperature_level=hot）
  OP_CALIBRATE → OP_FINAL（OP_FINAL 需要 calibration_status=calibrated）
  OP_CLEANING → OP_FINAL（OP_FINAL 需要 cleanliness=clean）
  OP_CLEANING ∥ OP_WARMUP（无依赖，可并行）
  OP_CLEANING ∥ OP_CALIBRATE（无依赖，可并行）

排程结果（minimize_makespan）：
  t=0:   OP_WARMUP   (30min, TECH-01)  ← 开始
         OP_CLEANING (20min, TECH-02)  ← 并行
  t=30:  OP_CALIBRATE(30min, TECH-01)
  t=60:  OP_FINAL    (15min, TECH-01)

总工期：75 分钟
关键路径：OP_WARMUP → OP_CALIBRATE → OP_FINAL
```

### B.2 策略 B 阻塞处理（维修序列插入）

```
原始计划 v1（总工期 75min）：
  t=0:  OP_WARMUP    (30min, TECH-01)
        OP_CLEANING  (20min, TECH-02)
  t=30: OP_CALIBRATE (30min, TECH-01)
  t=60: OP_FINAL     (15min, TECH-01)

阻塞发生：
  阻塞步骤：OP_CALIBRATE
  策略：B
  blockage_reason：hardware_fault

处理流程：
  1. 将 blockage_reason=hardware_fault 注入当前状态
  2. RAGBuilder 重新搜索：
     OP_REPAIR_HARDWARE 的 precond 匹配 blockage_reason=hardware_fault ✓
     OP_REPAIR_HARDWARE 的 effect 清除 blockage_reason = none
     OP_REPAIR_HARDWARE 插入 OP_CALIBRATE 之前
  3. CP-SAT 重新排程

重排结果 v2（总工期 165min）：
  t=0:   OP_WARMUP          (30min,  TECH-01)   step_role: normal
         OP_CLEANING        (20min,  TECH-02)   step_role: pulled_forward
  t=30:  OP_REPAIR_HARDWARE (120min, TECH-01)   step_role: repair
  t=150: OP_CALIBRATE       (30min,  TECH-01)   step_role: delayed
  t=180: OP_FINAL           (15min,  TECH-01)   step_role: delayed

版本链：
  v2.parent_plan_id = v1.id
  v2.replan_reason  = 'blockage_strategy_b'

blockage_event 记录：
  plan_id         = v1.id
  blocked_step_id = OP_CALIBRATE 的 step id
  strategy        = 'B'
  blockage_reason = 'hardware_fault'
```

### B.3 策略 AB 阻塞处理（提拉 + 维修序列并用）

```
原始计划 v1（与 B.1 相同）

阻塞发生：
  阻塞步骤：OP_CALIBRATE
  策略：AB
  not_before_offset：120（min）
  blockage_reason：hardware_fault

处理流程：
  1. 注入 blockage_reason=hardware_fault 到当前状态
  2. RAGBuilder 重新搜索（与策略B相同，OP_REPAIR_HARDWARE 被匹配插入）
  3. CP-SAT 建模时同时施加约束：
     a. not_before 约束：start[OP_CALIBRATE] >= 120（策略A）
     b. OP_REPAIR_HARDWARE 位于 OP_CALIBRATE 之前（策略B，RAG 边）
     c. 资源互斥：TECH-01 同一时间只能做一件事
  4. CP-SAT 自动求解资源竞争下的最优方案

重排结果 v2：
  t=0:   OP_WARMUP          (30min,  TECH-01)   step_role: normal
         OP_CLEANING        (20min,  TECH-02)   step_role: pulled_forward
  t=30:  OP_REPAIR_HARDWARE (120min, TECH-01)   step_role: repair
  t=120: ← not_before 下界
  t=150: OP_CALIBRATE       (30min,  TECH-01)   step_role: delayed
  t=180: OP_FINAL           (15min,  TECH-01)   step_role: delayed

说明：
  OP_CLEANING 在 t=0 被提拉（TECH-02 空闲，无依赖阻塞步骤）
  OP_REPAIR_HARDWARE 与 OP_CLEANING 并行（不同资源）
  OP_CALIBRATE 受 not_before=120 和 OP_REPAIR_HARDWARE 结束时间双重约束
  CP-SAT 自动取两者中的较大值（150 > 120，故 start=150）
```

---

## 附录 C：V0.1 → V0.2 数据库迁移清单

```sql
-- migration_v0.2.sql
-- 按顺序执行

-- ① 新增 feature_definition 表
CREATE TABLE feature_definition (
    feature_key    VARCHAR(128) PRIMARY KEY,
    value_type     VARCHAR(32)  NOT NULL,
    allowed_values JSONB,
    unit           VARCHAR(32),
    description    TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ② op_rule_precond 扩展
ALTER TABLE op_rule_precond
    ADD COLUMN operator    VARCHAR(16) NOT NULL DEFAULT 'eq',
    ADD COLUMN value_list  JSONB;

-- ③ op_rule_effect 扩展
ALTER TABLE op_rule_effect
    ADD COLUMN effect_type  VARCHAR(32) NOT NULL DEFAULT 'set',
    ADD COLUMN delta_value  NUMERIC;

-- ④ op_rule 扩展
ALTER TABLE op_rule
    ADD COLUMN is_repair   BOOLEAN   NOT NULL DEFAULT FALSE,
    ADD COLUMN valid_from  TIMESTAMP,
    ADD COLUMN valid_to    TIMESTAMP;

-- ⑤ solve_request 扩展
ALTER TABLE solve_request
    ADD COLUMN objectives      JSONB NOT NULL
        DEFAULT '[{"type": "minimize_makespan", "weight": 1.0}]',
    ADD COLUMN constraints     JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN parent_plan_id  INTEGER REFERENCES candidate_plan(id);

-- ⑥ candidate_plan 扩展
ALTER TABLE candidate_plan
    ADD COLUMN version         INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN parent_plan_id  INTEGER     REFERENCES candidate_plan(id),
    ADD COLUMN replan_reason   VARCHAR(64),
    ADD COLUMN status          VARCHAR(32) NOT NULL DEFAULT 'draft';

-- ⑦ candidate_plan_step 扩展
ALTER TABLE candidate_plan_step
    ADD COLUMN not_before  INTEGER,
    ADD COLUMN step_role   VARCHAR(32) NOT NULL DEFAULT 'normal';

-- ⑧ 新增 blockage_event 表
CREATE TABLE blockage_event (
    id                SERIAL PRIMARY KEY,
    plan_id           INTEGER      NOT NULL REFERENCES candidate_plan(id),
    blocked_step_id   INTEGER      NOT NULL REFERENCES candidate_plan_step(id),
    strategy          VARCHAR(8)   NOT NULL,
    not_before_offset INTEGER,
    blockage_reason   VARCHAR(64),
    note              TEXT,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by        VARCHAR(64)
);

-- ⑨ 为 op_rule_precond 和 op_rule_effect 添加 feature_key 外键
--    （迁移前需确保现有数据的 feature_key 已在 feature_definition 中存在）
ALTER TABLE op_rule_precond
    ADD CONSTRAINT fk_precond_feature
    FOREIGN KEY (feature_key) REFERENCES feature_definition(feature_key);

ALTER TABLE op_rule_effect
    ADD CONSTRAINT fk_effect_feature
    FOREIGN KEY (feature_key) REFERENCES feature_definition(feature_key);

ALTER TABLE machine_state_feature
    ADD CONSTRAINT fk_state_feature
    FOREIGN KEY (feature_key) REFERENCES feature_definition(feature_key);

-- ⑩ 写入基础种子数据（已在第四章 4.3 节定义，此处执行）
-- （见第四章 4.3 节的 INSERT 语句）
```

---

## 附录 D：环境配置与启动

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: solver_db
      POSTGRES_USER: solver
      POSTGRES_PASSWORD: solver123
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://solver:solver123@db:5432/solver_db
    depends_on:
      - db
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app

volumes:
  pgdata:
```

```
# 本地开发启动顺序
1. docker-compose up db              # 启动数据库
2. cd backend && alembic upgrade head # 执行迁移
3. cd backend && python seed.py      # 写入种子数据
4. cd backend && uvicorn app.main:app --reload --port 8000
5. cd frontend && npm run dev
```

---

> **文档维护约定**：
> 每次版本迭代开始前，先更新本文档的对应章节，
> 再开始编写代码。代码与文档不一致时，
> 以本文档为准并提示人工确认后再修改文档。
>
> **当前状态**：V0.2 开发中
> **下一步行动**：按第七章 7.2 任务清单，从 STEP 1 数据模型扩展开始

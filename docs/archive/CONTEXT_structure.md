# AI Context 管理方案：专业开发者视角

---

## 首先说清楚一个根本问题

当前这份总文档有一个**结构性缺陷**：

```
它是"写给人看的设计文档"
不是"写给 AI 用的上下文"

两者的核心区别：

写给人看的文档：
  追求完整性、可读性、叙述逻辑
  人会选择性阅读，跳过已知部分

写给 AI 用的上下文：
  追求信息密度、无歧义、状态明确
  AI 每次都全量读取，重复信息是噪声
  AI 需要知道"当前状态是什么"而不只是"历史上发生了什么"
```

---

## 核心方案：三层文档体系

```
┌─────────────────────────────────────────────────────┐
│  Layer 1：项目锚点文档（Project Anchor）              │
│  不随版本变化，描述系统永恒不变的部分                  │
│  文件名：ANCHOR.md                                   │
│  大小上限：≤ 500 行                                  │
├─────────────────────────────────────────────────────┤
│  Layer 2：当前状态文档（Current State）               │
│  描述"现在是什么样子"，每个版本迭代时整体替换           │
│  文件名：STATE_V0.2.md                               │
│  大小上限：≤ 800 行                                  │
├─────────────────────────────────────────────────────┤
│  Layer 3：任务工单（Task Ticket）                     │
│  描述"这次对话要做的具体一件事"                        │
│  文件名：TICKET_xxx.md                               │
│  大小上限：≤ 200 行                                  │
└─────────────────────────────────────────────────────┘

使用方式：
  每次开启新对话时，粘贴：
    ANCHOR.md + STATE_Vx.x.md + TICKET_xxx.md
  
  三份文档总量控制在 1500 行以内
  确保任何主流大模型都能完整处理
```

---

## Layer 1：ANCHOR.md 内容结构

这份文档**一旦写定几乎不改**，描述系统的骨架：

```markdown
# PROJECT ANCHOR
> 本文档描述系统的永久性约定，不随版本迭代更新。
> 开发时所有决策必须符合本文档定义的原则。

## 系统一句话定义
规则驱动的状态空间求解引擎 + 计划师操作界面。
给定起点状态、目标状态、规则库，自动推导工序路径并生成最优排程，
支持阻塞时的动态重排。

## 技术栈（锁定）
- 后端：Python 3.11 + FastAPI + SQLAlchemy 2.0
- 求解：Google OR-Tools CP-SAT
- 数据库：PostgreSQL 15
- 前端：Vue 3 + Element Plus + ECharts

## 分层架构（锁定）
UI → API(FastAPI) → Service → Domain(solver/) → Persistence(SQLAlchemy)
跨层调用规则：只能调用相邻下层，不可跨层

## 领域层四个核心模块（锁定）
RuleEvaluator  → 所有 precond 匹配和 effect 应用的唯一入口
StateDelta     → 计算起点与目标的状态差
RAGBuilder     → 状态差 → 工序 DAG（正向 BFS）
Scheduler      → 工序 DAG → 排程（CP-SAT）

## 五条设计原则（锁定）
1. 规则内置数据驱动：业务知识在数据库，引擎不含业务逻辑
2. 模块解耦接口稳定：四个核心模块只通过数据结构通信
3. 策略模式注册优于修改：新增类型只注册不改主流程
4. 零侵入扩展：新参数有默认值，不传时行为与上版本完全一致
5. 阻塞语义不侵入 RAGBuilder：阻塞 = 往 current_state 注入特征

## 硬性禁止（锁定）
- 禁止在 RAGBuilder/Scheduler/API 层直接写 precond 比较逻辑
- 禁止 ORM Model 与 Pydantic Schema 混用
- 禁止组件内直接调用 axios（必须经过 src/api/ 封装）
- 禁止 Domain 层导入 FastAPI 模块
- 禁止 feature_key 在前端硬编码（必须从数据库动态读取）
- 禁止时间单位混用（统一分钟，字段名以 _min 结尾）

## 明确不在范围内（锁定）
多项目隔离 / 角色权限 / 跨机台调配 / 实时执行追踪 /
外部系统推送阻塞 / 执行中步骤被中断的处理 / 鲁棒排程

## 核心业务词汇表（锁定）
| 术语 | 含义 |
|------|------|
| 机台 | 被集成的目标设备 |
| 工序规则(op_rule) | 使机台从一种状态变迁到另一种状态的操作单元 |
| 阻塞(blockage) | 某计划步骤因外部原因无法在预定时间执行 |
| 策略A | 活动提拉：阻塞步骤延后，无关步骤提前 |
| 策略B | 维修序列：匹配 is_repair=TRUE 规则插入 RAG |
| step_role | 版本对比中步骤的变化标注(normal/repair/pulled_forward/delayed) |
| 版本链 | candidate_plan 通过 parent_plan_id 形成的父子关系 |
```

---

## Layer 2：STATE_Vx.x.md 内容结构

这份文档描述**当前版本的完整快照**，版本切换时整体替换，不是追加：

```markdown
# CURRENT STATE: V0.2
> 生成时间：2026-04-10
> 前置阅读：必须先读 ANCHOR.md

## 本版本目标（一句话）
实现阻塞处理与动态重排，同时完成架构升级为远景打基础。

## 当前已完成（V0.1 遗产，可直接使用）
### 数据库表（已存在，可能需要迁移扩展）
- op_rule (id, code, name, duration_min, description)
- op_rule_precond (id, op_rule_id, feature_key, feature_value)
- op_rule_effect (id, op_rule_id, feature_key, new_value)
- resource (id, code, name, resource_type)
- op_rule_resource (op_rule_id, resource_id, quantity)
- machine_state (id, name, state_type, description)
- machine_state_feature (id, state_id, feature_key, feature_value)
- solve_request (id, start_state_id, goal_state_id)
- candidate_plan (id, solve_request_id, total_duration_min)
- candidate_plan_step (id, plan_id, op_rule_id, step_order,
                       start_min, duration_min, resource_id)

### 后端文件（已存在）
- app/main.py, app/database.py
- app/models/{rule,state,resource,plan}.py
- app/solver/state_delta.py  ← V0.1 版本，precond 匹配是简单等值比较
- app/solver/rag_builder.py  ← V0.1 版本，无循环检测
- app/solver/scheduler.py    ← V0.1 版本，objectives 是单值

### 已知 V0.1 的技术债（本版本必须还清）
- op_rule_precond 只支持等值匹配，没有 operator 字段
- op_rule_effect 只支持 set，没有 effect_type 字段
- RAGBuilder 没有循环检测和深度限制
- Scheduler objectives 是单个枚举值，不是数组

## 本版本数据模型变更（V0.1 → V0.2）
### 新增表
- feature_definition (feature_key PK, value_type, allowed_values JSONB,
                      unit, description)
- blockage_event (id, plan_id, blocked_step_id, strategy,
                  not_before_offset, blockage_reason, note, created_by)

### 扩展字段
- op_rule_precond: + operator VARCHAR(16) DEFAULT 'eq'
                   + value_list JSONB
- op_rule_effect:  + effect_type VARCHAR(32) DEFAULT 'set'
                   + delta_value NUMERIC
- op_rule:         + is_repair BOOLEAN DEFAULT FALSE
                   + valid_from TIMESTAMP, valid_to TIMESTAMP
- solve_request:   + objectives JSONB DEFAULT '[{"type":"minimize_makespan","weight":1.0}]'
                   + constraints JSONB DEFAULT '{}'
                   + parent_plan_id INTEGER
- candidate_plan:  + version INTEGER DEFAULT 1
                   + parent_plan_id INTEGER
                   + replan_reason VARCHAR(64)
                   + status VARCHAR(32) DEFAULT 'draft'
- candidate_plan_step: + not_before INTEGER
                       + step_role VARCHAR(32) DEFAULT 'normal'

## 本版本新增领域层文件
- solver/operators.py    ← OperatorRegistry + 7 个 Operator 类
- solver/effects.py      ← EffectRegistry + 3 个 Effect 类
- solver/rule_evaluator.py ← RuleEvaluator（策略模式）
- solver/objectives.py   ← ObjectiveRegistry + MinimizeMakespanObjective

## 本版本关键接口约定
### POST /api/v1/solve 请求体新增字段
{
  "objectives": [{"type": "minimize_makespan", "weight": 1.0}],
  "constraints": {"enable_not_before": false},
  "blockage_constraints": {
    "blocked_step_id": int,
    "strategy": "A"|"B"|"AB",
    "strategy_a": {"not_before_offset": int},   // strategy含A时必填
    "strategy_b": {"blockage_reason": string},  // strategy含B时必填
    "note": string,
    "created_by": string
  },
  "parent_plan_id": int | null
}

### POST /api/v1/solve 响应体新增字段
{
  "state_delta": [...],
  "critical_path": [...],
  "parallel_groups": [...],
  "steps": [{ ..., "not_before": int|null, "step_role": string }]
}

## 当前任务完成状态
□ STEP1 数据模型扩展        [ ] 未开始 / [ ] 进行中 / [ ] 已完成
□ STEP2 领域层架构升级      [ ] 未开始 / [ ] 进行中 / [ ] 已完成
□ STEP3 API 层扩展          [ ] 未开始 / [ ] 进行中 / [ ] 已完成
□ STEP4 前端新增组件        [ ] 未开始 / [ ] 进行中 / [ ] 已完成

## 当前已知问题 / 决策悬挂
（开发过程中遇到未解决的问题记录在此，供下次对话继续）
- 暂无
```

**关键设计点**：STATE 文档里不写"为什么这么设计"，只写"现在是什么样"。"为什么"在 ANCHOR.md 里。

---

## Layer 3：TICKET_xxx.md 内容结构

每次开启对话时，明确**这次只做一件事**：

```markdown
# TICKET-008: 实现 RuleEvaluator 策略模式抽象层

## 本次任务范围（只做这些，不做其他）
实现 solver/operators.py、solver/effects.py、solver/rule_evaluator.py
完成后更新 STATE_V0.2.md 中的任务完成状态

## 输入（已知信息）
- V0.1 中 rag_builder.py 的 precond 匹配逻辑是：
  直接 feature_value == current_state.get(feature_key)
  需要替换为 RuleEvaluator 调用
- feature_definition 表已建（STEP1 已完成）

## 输出要求
1. solver/operators.py
   - OperatorRegistry 使用装饰器注册
   - 实现 eq/neq/gt/gte/lt/lte/in 共 7 个 Operator
   - 类型安全：查询 feature_definition.value_type 做类型转换后再比较

2. solver/effects.py
   - EffectRegistry 使用装饰器注册
   - 实现 set/increment/decrement 共 3 个 Effect
   - apply 方法返回新状态副本（不可变原则）

3. solver/rule_evaluator.py
   - evaluate_precond(state, precond_list) → bool（AND 逻辑）
   - apply_effect(state, effect_list) → dict（返回副本）

4. tests/test_rule_evaluator.py
   - 每个 Operator 至少一个测试
   - 类型安全测试（number 类型的 gt 比较）
   - 枚举类型的 in 操作测试

## 本次不做（明确排除）
- RAGBuilder 的改造（TICKET-009 做）
- Scheduler 的改造（TICKET-010 做）

## 完成标准
tests/test_rule_evaluator.py 全部通过
solver/rag_builder.py 中旧的 precond 匹配逻辑被注释标记为 DEPRECATED
```

---

## 版本切换时如何操作

```
V0.2 完成后，进入 V0.3 开发前的操作：

STEP 1：归档
  将 STATE_V0.2.md 重命名为 ARCHIVE_V0.2.md
  存入 /docs/archive/ 目录
  正式开发时不再使用，只作历史参考

STEP 2：生成新状态文档
  基于 STATE_V0.2.md 生成 STATE_V0.3.md
  核心操作：
  ① "当前已完成"区块：将 V0.2 所有内容移入，描述为已有基础
  ② "已知的技术债"：将 V0.2 遗留问题写入
  ③ "本版本变更"：只写 V0.3 新增内容
  ④ "任务完成状态"：全部重置为未开始

STEP 3：ANCHOR.md 是否需要更新
  99% 的情况不需要更新
  只有当核心设计原则或技术栈发生根本性变化时才修改
  修改时必须标注原因和日期

文件目录结构：
  /docs/
  ├── ANCHOR.md              ← 永久不变
  ├── STATE_V0.2.md          ← 当前版本（开发中）
  ├── TICKET_001.md          ← 已完成的工单（可保留参考）
  ├── TICKET_008.md          ← 当前工单
  └── archive/
      ├── ARCHIVE_V0.1.md
      └── TICKET_001~007.md
```

---

## 跨大模型使用时的注意事项

不同模型的上下文窗口和指令遵循能力不同，需要差异化处理：

```
┌──────────────┬──────────────────────────────────────────┐
│ 模型能力级别 │ 对应策略                                  │
├──────────────┼──────────────────────────────────────────┤
│ 强（如       │ 三份文档全量输入                          │
│ Claude/GPT4o)│ 可以在一次对话内完成较复杂任务            │
│              │ 可以在对话末要求模型"更新 STATE 文档"     │
├──────────────┼──────────────────────────────────────────┤
│ 中（如       │ ANCHOR + TICKET 输入                     │
│ Gemini Flash)│ STATE 文档只输入与本次任务相关的章节       │
│              │ 单次对话任务粒度要更小                    │
├──────────────┼──────────────────────────────────────────┤
│ 弱/本地模型  │ 只输入 TICKET                            │
│              │ ANCHOR 中的关键约束手动提炼成几行         │
│              │ 只做代码生成，不做架构决策               │
└──────────────┴──────────────────────────────────────────┘

通用原则：
  无论用什么模型，对话开头第一句话永远是：
  "请先阅读以下上下文文档，阅读完毕后回复'已就绪'，
   不要提前开始任何任务"
  等模型确认后再开始工作
```

---

## 保证一致性的关键习惯

这是最容易被忽略但最重要的部分：

```
习惯 1：每次对话结束时，要求模型输出"状态更新"
  提示词：
  "本次对话结束，请根据我们完成的工作，
   输出需要更新到 STATE_V0.2.md 的内容（diff 格式）"
  
  将模型输出的变更手动合入 STATE_V0.2.md
  这是维持跨对话连续性的核心动作

习惯 2：代码实现与文档同步更新
  不允许"先写代码后补文档"
  正确顺序：
    ① 更新 STATE 文档（描述将要做的变更）
    ② 生成 TICKET
    ③ 开发
    ④ 开发完成后确认 STATE 文档与实现一致

习惯 3：决策悬挂必须记录
  对话中遇到需要人工判断的问题，
  不要在对话中随意拍板
  记录在 STATE 文档的"当前已知问题"区块
  下次对话开始时先处理悬挂问题

习惯 4：TICKET 粒度控制
  单个 TICKET 对应的工作量 ≤ 一次对话能完成的量
  经验值：一个文件的实现 / 一组相关 API / 一个组件
  粒度太大导致对话中途断掉，状态难以恢复

习惯 5：不要在对话中做架构决策
  对话中临时产生的架构想法，
  不要直接让模型实现
  先结束对话，更新 ANCHOR.md 或 STATE 文档，
  再开新对话执行
  防止"架构漂移"（实际代码与文档记录不一致）
```

---

## 实际操作模板

每次开启新对话时，粘贴以下内容：

```
===== AI CONTEXT START =====

[ANCHOR.md 全文]

---

[STATE_V0.2.md 全文]

---

[TICKET_当前工单.md 全文]

===== AI CONTEXT END =====

请先阅读以上上下文，阅读完毕后回复"已就绪：[用一句话说明你理解的本次任务]"，
不要提前开始任何工作。
```

---

## 总结：文档体系的本质

```
ANCHOR.md    = 系统的"宪法"
               定义不可违反的原则，极少修改

STATE_Vx.x.md = 系统的"当前账本"
               记录现在是什么样子，每个版本替换

TICKET_xxx.md = 系统的"工作令"
               每次对话只做一件事，做完即归档

三者关系：
  宪法 约束 账本的变更方向
  账本 为 工作令 提供背景
  工作令 驱动 账本的更新
  账本的版本累积 形成 版本路线图
```

这套体系的核心价值不在于文档本身，而在于**它强迫你在每次开发前明确"现在在哪，要去哪，这次做什么"**，这个思考过程本身就是防止混乱的最有效手段。
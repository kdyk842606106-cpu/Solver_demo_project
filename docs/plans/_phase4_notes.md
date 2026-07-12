# Phase 4: 差距分析笔记

> 整理时间：2026-04-25
> 基于：STATE_V0.3.md、STATE_V0.2.md、_phase1_notes.md、_phase2_notes.md、_phase3_notes.md、solver_requirements_gap_report.md
> 评估基线：solver_requirements_summary.md

---

## 一、现状盘点（V0.1 → V0.3）

### V0.1 基线（已完成，2026-04-10 前）

| 类别 | 已交付能力 |
|------|-----------|
| **两阶段求解链路** | Planner（状态推导 RAG）+ Scheduler（CP-SAT 排程） |
| **数据库** | 14 张核心表 + Alembic 迁移 + 种子数据 |
| **主数据 API** | CRUD API（machine、state、op-rule、resource 等） |
| **前端基础页面** | Vite + Vue 3 初始工程，基础页面结构 |
| **API 端点** | POST /solve、GET /machines/{id}/state、GET /health 等 |

**V0.1 已知实现特征（Gotchas）：**
- solve_request 创建时直接写 status=running，不经过 pending
- POST /solve 业务失败仍返回 HTTP 200，通过 status=failed + error_code 区分
- parallel_groups 来自 Scheduler 求解后时间重叠检测，非 Planner 预标记
- Planner 含 max_ops=50 硬编码安全上限

### V0.2 交付（已完成，2026-04-19）

| 类别 | 已交付能力 | 证据来源 |
|------|-----------|---------|
| **阻塞处理 A/B/AB 闭环** | 策略 A（延时）、策略 B（维修）、策略 AB 同时生效 | STATE_V0.3.md §V0.2 |
| **数据模型升级** | feature_definition、blockage_event、not_before、step_role、版本链字段 | STATE_V0.2.md §数据模型变更 |
| **领域层注册表化** | OperatorRegistry（7个）、EffectRegistry（3个）、ObjectiveRegistry、RuleEvaluator | STATE_V0.2.md §STEP 2 |
| **版本链** | parent_plan_id、replan_reason、version，支持版本历史查询与对比 | API 扩展 |
| **前端重构** | Vue 3 + Element Plus + ECharts，Gantt 图、对比模式、step_role 颜色标注 | STATE_V0.2.md §STEP 4 |
| **展示增强** | Gantt/任务表统一显示「步骤编号 + 活动编码 + 活动名称」 | TICKET-010 |

**V0.2 验收结果：** 190 测试全通过（STEP 2 准出修复）+ 211 测试全通过（STEP 3 API 扩展）

### V0.3 交付（当前版本，已完成）

| 类别 | 已交付能力 | Ticket |
|------|-----------|--------|
| **数值型状态规划 Phase 1** | NumericFeaturePlanner 骨架、精确目标 BFS/有界搜索、重复步骤实例化、隐式子目标、循环检测 | TICKET-013/014/015/016 |
| **重复步骤持久化** | CandidatePlanStep 支持重复 op_rule_id，通过 instance 区分 | TICKET-015 |
| **数值+阻塞兼容性** | 实例级 blocked_step_id 路由、step_role diff 修复、A/B/AB 交叉回归 | TICKET-017 |
| **内网开发机一键启动** | bootstrap/launch 两阶段脚本、start.intranet.bat、npm registry 配置 | TICKET-018/019/020 |

**V0.3 未开始项：**
- TICKET-012：主数据 Excel 单文件导入
- STEP 1：求解可解释性深化
- STEP 2：多目标优化能力
- STEP 3：工序组能力（Operation Group）
- STEP 4：A* 搜索策略

---

## 二、核心差距矩阵

基于 solver_requirements_gap_report.md §8 差距分级整理：

### P0 级差距：直接影响核心需求定义

| 需求能力 | 当前状态 | 差距等级 | 证据来源 |
|---------|---------|---------|---------|
| **最小代价路径搜索** | 启发式拼装（delta 匹配 + 递归补齐） | 🔴 高 | gap_report §5.1：当前是"工程化规则拼装器"而非"完整最小代价路径搜索器" |
| **条件表达式目标（G）** | 仅支持 target_state_id（数据库预定义快照） | 🔴 高 | gap_report §5.2：无法表达 `洁净状态 > 100` 这类条件型目标 |
| **效果操作符集合** | set / increment / decrement | 🔴 高 | gap_report §5.3：需求定义最小集为 set/sub/reset，当前缺少 reset |
| **数值触发语义** | 步进规划（exact target 多步推进） | 🔴 高 | gap_report §5.4：需求是"sub归零→触发→reset"事件驱动，当前是"数值步进"而非"触发式维护循环" |
| **效果可交换性并行** | 完全缺失（仅基于前驱集合相同分组） | 🔴 高 | Phase2 发现3 + gap_report §5.5：典型冲突场景（如 set+set 写同一 key）无法被过滤 |

### P1 级差距：影响系统化可用性

| 需求能力 | 当前状态 | 差距等级 | 证据来源 |
|---------|---------|---------|---------|
| **求解可解释性** | 轻量展示（state_delta、critical_path） | 🟡 中 | gap_report §5.9：V0.3 STEP 1（求解可解释性深化）未开始 |
| **多目标优化权重** | 框架有，weight 字段未参与加权求解 | 🟡 中 | STATE_V0.3.md 技术债第2条 + Phase3 发现1 |
| **What-if 参数对比** | 部分支持（版本链 + diff 展示） | 🟡 中 | gap_report §5.7：无通用参数注入入口，非系统化 what-if 框架 |
| **代价模型统一** | 依赖 duration_min 最短规则选择 | 🟡 中 | gap_report §5.6：代价非统一权重，无法反映复杂度/风险/优先级 |

### P2 级差距：影响平台化治理

| 需求能力 | 当前状态 | 差距等级 | 证据来源 |
|---------|---------|---------|---------|
| **工艺规则离线校验** | 完全未开始 | 🟢 低 | gap_report §5.8：死锁/冗余/循环/效果冲突检测均无对应模块 |
| **模板库健康检查** | 完全未开始 | 🟢 低 | gap_report §5.8：诊断级输出能力缺失 |
| **异常恢复重规划** | 完全未开始（P3 需求） | 🟢 低 | Phase1 §场景4：状态回退规则、新旧路径差异分析均未实现 |
| **资源建模精细化** | MVP 级别（仅取首个 required resource） | 🟢 低 | gap_report §5.10：资源建模偏 MVP，不适合复杂资源组合场景 |

---

## 三、技术债务清单

### 已知技术债（来自 STATE_V0.3.md）

| # | 债务项 | 现状 | 影响 | 优先级 |
|---|-------|------|------|--------|
| 1 | 测试基础设施重复 | tests/e2e/conftest.py 与 tests/conftest.py 双引擎 + 重复 fixture | 维护成本高，测试执行不一致 | 中 |
| 2 | 多目标 weight 未生效 | ObjectiveRegistry 已建立，但 weight 字段被忽略 | V0.3 STEP 2（多目标优化）被阻塞 | 高 |
| 3 | 旧错误码命名残留 | 不同文件中 error_code 命名不一致（NO_SOLUTION vs no_solution） | API 错误码不稳定，前端映射表可能失效 | 低 |

### 新增技术债（来自 Phase 2-3 发现）

| # | 债务项 | 证据 | 影响 | 优先级 |
|---|-------|------|------|--------|
| 4 | solve.py 单一职责违反（185行） | Phase3 发现2：混合验证/编排/持久化/响应组装7类职责 | 单元测试难以编写，是 API 层主要技术债 | 高 |
| 5 | Planner 并行分析理论缺陷 | Phase2 发现3：find_parallel_groups 仅基于前驱集合相同，未检查 effect 冲突 | 可能误判并行安全性 | 高 |
| 6 | 效果可交换性过滤层缺失 | Phase1 发现4 + gap_report §5.5 | 共享 key 的冲突场景无法被严格过滤 | 高 |
| 7 | max_ops=50 硬编码 | Phase2 发现6 + Phase3 发现3 | 复杂场景隐性瓶颈，规则库规模化受限 | 中 |
| 8 | 测试覆盖率无报告 | Phase3 §测试覆盖：requirements.txt 无 pytest-cov | 无法量化测试充分性 | 中 |
| 9 | 前端无生产优化配置 | Phase3 发现6：vite build 无 manualChunks | 主包体积随功能增加而膨胀 | 低 |
| 10 | 资源分配贪心策略 | Phase2 发现2：首个空闲资源实例分配 | 全局最优无保证，资源不足时降级处理 | 中 |
| 11 | step_order 语义不精确 | Phase2 发现1：RAGNode.id 作为 step_order，是创建顺序非拓扑排序 | Scheduler 正确性依赖 predecessor_ids 而非 step_order | 低 |
| 12 | 同步阻塞 API | Phase3 发现4：POST /solve 同步等待完整求解 | V1.0 外部集成需大规模重构（需异步架构） | 高 |

### 架构风险

| 风险项 | 描述 | 后果 |
|-------|------|------|
| **求解范式差距** | 当前是 delta/provider 启发式拼装，不是状态空间最小代价搜索 | 后续 What-if、规则校验、解释性扩展缺乏稳定语义基础 |
| **目标语义未对齐** | 顶层目标仍是 target_state_id，不是条件集合 G | 条件目标无法实现，需在 API 层重构目标输入模型 |
| **同步阻塞 API** | 求解放入同步 HTTP 响应 | V1.0 外部集成（MES/ERP）需引入异步任务架构（Celery/ARQ + Redis） |
| **FeatureDefinition 职责重叠** | 全局特征定义表与 StateFeatureDef 部分重叠 | 数据一致性风险，blockage_reason 取值来源分散（Phase2 发现7/9） |
| **Numeric 与 enum 节点 ID 分配机制差异** | enum 用 op.id 做 key，numeric 用 instance_id 做 key | 长期扩展可能出现 ID 冲突（Phase3 发现5，但当前无冲突） |

---

## 四、人工替代率量化

基于 Phase1 §五业务场景到系统能力映射，以及 gap_report §2 执行摘要：

### 业务场景与人工替代率映射

| 业务场景 | 当前人工替代率 | 目标 | 差距 | 关键缺口 |
|---------|--------------|------|------|---------|
| **常规排程（场景1）** | ~60% | 90% | 30% | ① 目标需预定义快照（非条件表达式）② 数值触发需人工确认插入点 ③ 并行安全性需人工复核 |
| **What-if 预演（场景2）** | ~20% | 80% | 60% | ① 无通用参数注入入口 ② 敏感性结论需人工推导 |
| **工艺规则校验（场景3）** | 0% | 70% | 70% | 死锁/冗余/循环/效果冲突全靠人工审查 |
| **异常恢复（场景4）** | 0% | 60% | 60% | 状态回退后需人工重规划，返工范围需人工判断 |

### 综合人工替代率

**当前综合人工替代率：约 35%-45%**

计算依据：
- 常规排程占比最高（场景1是核心场景），但仍有 30% 差距
- What-if 和工艺校验基本未覆盖（场景2/3）
- 异常恢复 P3 需求未开始（场景4）

**目标综合人工替代率：约 75%-80%**

收敛路径（按 gap_report §9 建议）：
1. 第一阶段：冻结目标表达/效果操作符/并行判定/Planner 搜索四项语义
2. 第二阶段：补齐求解策略与 explainability
3. 第三阶段：补 What-if、规则校验、资源建模

---

## 五、关键发现

### 发现1：当前能力覆盖约 40%-50%，但架构差距是实质性的

> 来源：gap_report §2 执行摘要 + Phase1 发现7

当前系统已具备"较清晰的分层闭环"和"部分关键底座"，但与需求文档描述的系统化 Planner 能力仍有实质性架构差距。最准确的定位是：
- ✅ 工程型求解器（delta 匹配 + 依赖补齐）
- ✅ 基础排程、阻塞重排、numeric 重复步骤实例化
- ❌ 不是"最小代价路径搜索 + 条件集合目标 + 数值事件触发 + 双层并行判定"

**不能声称"已基本实现需求"，只能说"具备约 40%-50% 基础能力框架"。**

### 发现2：四层语义必须先冻结，才能稳妥扩展

> 来源：gap_report §9 建议 + Phase1 发现8

不建议直接在现有行为上继续局部打补丁，而应先冻结：
1. **目标表达语义**：从 target_state_id 升级为条件集合 G
2. **效果操作符语义**：补齐 set/sub/reset，numeric 从步进升级为事件驱动
3. **并行判定语义**：补齐效果可交换性过滤层
4. **Planner 搜索语义**：从启发式拼装演进为可控的最小代价搜索

这四项冻结之后，再展开 What-if、规则校验、解释性深化，会更稳妥。

### 发现3：多目标优化是架构性缺口，非简单的功能未实现

> 来源：Phase3 发现1

OR-Tools CP-SAT 原生支持多目标加权，但当前 `ObjectiveRegistry.apply_all()` 对每个 objective 独立调用 `apply_to_model()`，且完全忽略 `weight` 字段。这是**架构设计问题**，不是"待实现功能"：
- CP-SAT 模型每次只能有一个优化目标
- 加权多目标需要线性组合（`model.minimize(Σ weight_i * target_i)`）或分层优化
- 当前注册表架构已预留，但 apply_all() 逻辑未实现

### 发现4：solve.py 是 API 层主要技术债，违反单一职责

> 来源：Phase3 发现2

`solve()` 函数约 185 行，承担了 7 类职责：
- 输入验证（machine/state/objective）
- 阻塞策略解析（5 个字段提取）
- Planner/Scheduler 调用编排
- 多次持久化（flush/commit/rollback）
- 响应组装（state_delta/critical_path/tasks_response）
- 异常处理（4 类分支 + 嵌套 try/except）

按 ANCHOR.md 四层架构，这些逻辑应下沉到 Service 层，API 层只做参数解析和响应封装。

### 发现5：效果可交换性并行过滤层缺失是 P0 级差距

> 来源：Phase2 发现3 + gap_report §5.5

**需求定义的并行判定有两层：**
1. 偏序图无路径（当前已有）
2. **共享 key 上效果可交换性检查**（当前缺失）

典型冲突场景：
- `set + set` 写同一 key → 不可并行（当前会误判为可并行）
- `set + sub` 写同一 key → 不可并行（当前会误判）
- `sub + sub` 写同一 key → 可并行（当前按前驱集合分组可能不一致）

当前对外暴露的 `parallel_groups` 来自 Scheduler 的时间重叠检测（`_detect_actual_parallel`），是正确的。但 Planner 阶段的并行机会分析存在理论缺陷。

### 发现6：V1.0 外部集成需重大架构增补

> 来源：Phase3 发现4

当前架构与 V1.0 目标（外部集成接口）存在以下缺口：
- API 为同步阻塞式（POST /solve 等待完整求解）
- 无 webhook、无回调机制、无事件总线
- docker-compose 仅含数据库，无 Redis/RabbitMQ 预留
- 无异步任务提交/轮询获取结果机制

**若 V1.0 需要对接 MES/ERP，必须引入异步任务架构（Celery/ARQ + Redis）和 webhook 推送能力。**

---

## 附录：文件读取清单

| 文件 | 行数 | 用途 |
|------|------|------|
| docs/STATE_V0.3.md | ~350 | V0.3 完整状态盘点 |
| docs/archive/STATE_V0.2.md | ~300 | V0.2 基线对比 |
| docs/plans/_phase1_notes.md | ~300 | 需求与愿景梳理 |
| docs/plans/_phase2_notes.md | ~400 | 模块交互与数据流 |
| docs/plans/_phase3_notes.md | ~350 | 技术选型评估 |
| docs/solver_requirements_gap_report.md | ~400 | 需求差距分析 |

---

## 自审查清单

- [x] V0.1/V0.2/V0.3 已交付能力完整列出
- [x] 10 项需求能力差距矩阵已建立（P0 5项 + P1 4项 + P2 4项）
- [x] 技术债务已分类（已知 3 项 + 新增 9 项 + 架构风险 5 项）
- [x] 人工替代率已量化（综合 35%-45%）
- [x] 关键发现已记录（6 条）

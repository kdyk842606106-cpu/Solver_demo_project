# CURRENT STATE: V0.3

> Update 2026-06-22: TICKET-036 implemented. State targets now support arbitrary-depth trees where active childless nodes expand as atomic states and aggregate nodes do not bind facts; atomic state writes auto-ensure global and per-machine-type feature definitions. Activity capability modeling now has reusable `atomic_activity` definitions, level-2 package references, `op_rule.atomic_activity_id`, migration `007_atomic_activity_refactor.py`, atomic activity/ref CRUD APIs, and compatibility for legacy level-3 activity nodes. Layered expansion, health checks, layered/maintenance solve, Scheduler metadata loading, and scenario import now understand atomic activity refs while preserving legacy paths. Data Management now uses a unified state target workspace and a package/ref/atomic-library activity capability workspace. Deferred: shared atomic activity ownership under Scheduler continuity objectives and full rule editing inside the new activity workspace. Verification: full backend `python -m pytest` 313 passed; frontend `npm run build` passed.

> Update 2026-06-17: TICKET-035 completed. Layered and maintenance solve responses now include hierarchical `layered.activity_tree` and `layered.state_tree` fields while preserving the existing flat summaries. State replay goal results and level-3 state tree rows now expose the source activity or current-state source for satisfied target facts. Solve page now renders activity/state result trees, task details as an activity hierarchy, Gantt level-2 activity grouping/collapse controls, maintenance reuse/skip explanations, target-state source rows, and continuity explanation rows. Existing solve/blockage e2e specs were updated to target the visible task-detail tab so hidden explanation tables do not break old flows. Verification: focused layered/maintenance source tests 2 passed; layered API integration 6 passed; frontend e2e 7 passed after escalated rerun; full backend regression 309 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-17: TICKET-034 completed. Scenario Excel import now supports optional `layered_health_checks` sheets for declared post-import diagnostics. Dry-run validates check scopes by code; successful import executes the declared checks after layered nodes, Scope Guards, maintenance intents, and rules are flushed, returning compact `post_import_health_checks` results. Failed and dry-run responses return an empty checks list. Data Management import dialog now shows declared diagnostic counts and post-import result rows. Verification: focused post-import diagnostic test 1 passed; scenario import integration 8 passed; layered API integration 6 passed; full backend regression 309 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-17: TICKET-033 completed. Layered and maintenance solve success responses now expose `layered.preflight_health`, a compact solve-preflight view of the existing layered health check. The full payload remains available under `diagnostics.layered_health`. Solve page now shows preflight health status, goal/candidate/effective-rule/diagnostic counts, and diagnostic rows in the layered/maintenance explanation tab. Planner/Scheduler behavior and solve status semantics are unchanged. Verification: focused layered/maintenance preflight tests 2 passed; layered API integration 6 passed; full backend regression 309 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-17: TICKET-032 completed. Scenario Excel import now supports optional `maintenance_intents` sheets for importing/upserting maintenance intent templates by `(machine_type_code, issue_type)`. Validation enforces level-2 maintenance scopes, same-machine-type target state and candidate activity node codes, known `eq` maintenance facts, and at least one goal. Imported templates are immediately available through the existing maintenance intent API and `/solve/maintenance`. Data Management import summary now shows maintenance intent counts. Verification: maintenance import/solve focused test 1 passed; scenario import integration 8 passed; layered API integration 6 passed; full backend regression 309 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-17: TICKET-031 completed. Layered and maintenance solve responses now include `layered.activity_selection`, explaining every candidate effective rule as selected or skipped, including skip reasons for already-satisfied effects and non-demanded candidates. Selected providers now expose goal/downstream precondition consumers and mark `is_shared_provider=true` when one provider supports multiple consumers. Solve page now shows an `活动选择解释` table in the layered/maintenance explanation tab. Verification: focused maintenance selection test 1 passed; layered API integration 6 passed; full backend regression 308 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-17: TICKET-030 completed. Layered scenario Excel import now supports optional `activity_nodes`, `state_nodes`, and `scope_guards` sheets, optional `rules.activity_node_code`, dry-run preview counts, strict layered validation, upsert of layered nodes/Scope Guards, and rule binding to level-3 activity nodes. Added integration coverage proving layered workbook import and `/solve/layered` use. Data Management import summary now shows layered counts. Verification: scenario import tests 7 passed; focused layered/import tests 13 passed; full backend regression 308 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-16: TICKET-029 completed. Phase 5B Scheduler continuity soft costs are implemented. Scheduler now carries level-3 activity metadata and parent level-2 activity group metadata from `StepData` through task output and persisted schedule JSON. `ObjectiveRegistry` now builds one weighted CP-SAT objective expression and supports `minimize_makespan`, `minimize_activity_group_span`, `minimize_activity_group_gaps`, and `minimize_activity_group_interruptions`. Continuity remains soft only: no hard sequence, adjacency, or contiguous-window constraints. Solve diagnostics now expose objective terms and per-group span/gap/interruption summaries. Solve page exposes an optional continuity preference and weight for snapshot, layered, and maintenance modes. Verification: focused TICKET-029 tests 22 passed; full backend regression 306 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-16: TICKET-028 completed. Phase 5A maintenance intent templates and joint maintenance solve are implemented. Added `maintenance_intent_template`, migration `005_maintenance_intent_template.py`, CRUD APIs under machine types, `POST /api/v1/solve/maintenance`, and `app/services/maintenance_solve.py`. `LayeredSolveRequest` now supports solve-only current-state overrides and direct goal facts, so maintenance intent templates merge into one layered Planner/Scheduler run instead of fixed sequences. Data Management now includes maintenance intent management, and Solve page includes maintenance mode. Deferred at that point: Scheduler continuity soft costs, setup reuse, hard maintenance sequences, history/manual/recommended ordering, shifts, and fact lifetime. Verification: layered/maintenance API test 6 passed; full backend regression 301 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-16: TICKET-027 completed. Phase 4 layered Planner/Scheduler integration is implemented. Added `POST /api/v1/solve/layered`, `app/services/layered_solve.py`, `LayeredSolveRequest`, synthetic target-state persistence, POP consumption of effective Scope Guard preconditions, existing Scheduler persistence, layered activity/state summaries, effective-precondition explanations, and post-solve replay validation. Solve page now has `快照 / 分层` mode and a `分层解释` tab. Existing `/solve`, blockage, import, Planner, and Scheduler contracts remain compatible. Verification: focused layered API test 5 passed; focused regression 67 passed; full backend regression 300 passed; frontend `npm run build` passed after escalated rerun.

> Update 2026-06-16: TICKET-026 completed. Phase 3 of layered activity/state reachability diagnostics is implemented as a side-effect-free health-check layer. Added `POST /api/v1/machine-types/{machine_type_id}/layered-health-check`, Provider/Consumer graph summaries, and structured diagnostics for `NO_PROVIDER`, `AMBIGUOUS_PROVIDER`, `BROKEN_CHAIN`, `SELF_DEPENDENCY`, and `CONFLICTING_GOAL`. Added Data Management `健康检查` tab. Existing `/solve`, Planner, Scheduler, blockage, and import contracts remain unchanged. Verification: full backend regression 299 passed; frontend `npm run build` passed.

> Update 2026-06-16: TICKET-025 completed. Phase 2 of layered activity/state expansion is implemented as a preview layer. Added a side-effect-free expansion service and `POST /api/v1/machine-types/{machine_type_id}/layered-expansion`, expanding selected state nodes into level-3 goal facts, selected activity scopes into level-3 candidate activities, and Scope Guard inheritance into source-aware effective rule previews. Added Data Management `展开预览` tab. Existing `/solve`, Planner, Scheduler, blockage, and import contracts remain unchanged. Verification: full backend regression 298 passed; frontend `npm run build` passed.

> Update 2026-06-16: TICKET-024 completed. Phase 1 of layered activity/state management is implemented. The system now has `activity_node`, `state_node`, `scope_guard`, and `scope_guard_precond` data foundations, nullable `op_rule.activity_node_id` binding for level-3 activities, master-data APIs with hierarchy validation, and Data Management UI tabs for 活动层级 / 状态层级 / 作用域约束. Existing `/solve`, Planner, Scheduler, blockage, and import contracts remain unchanged. Verification: full backend regression 297 passed; frontend `npm run build` passed.

> Update 2026-06-01: TICKET-023 completed. Planner main strategy has been replaced by an instance-level Partial Order Planner in `app/core/planner/partial_order.py`; `build_rag()` now delegates to POP and `candidate_plan.search_method` is `partial_order`. The existing `/solve`, RAG, `candidate_plan_step.predecessor_ids`, Scheduler, blockage, and multi-resource contracts remain unchanged. Focused regression: 104 passed.

> Update 2026-06-02: Effect-driven repeated activity re-provider has been implemented on top of POP. Registered effects now include `sub` and `reset`; POP performs state/effect replay and inserts re-provider instances for unmet downstream preconditions and repairable final goal drift, including numeric and non-numeric facts with direct providers. Excel import, RulePage configuration, planner helper semantics, and planner protocol docs have been synchronized. No database migration or bootstrap script change is required.

> 本轮复核（2026-05-29）：文档入口与协议文档已系统性校准。当前主干能力已包含 Planner 正向 BFS、实例级阻塞定位、Scheduler 多资源约束/分配、关键路径图、内网/本地/Docker 启动入口。旧 `CONTEXT` 文档已归档到 `docs/archive/cleanup_20260529/outdated_notes/`；AI 上下文入口为 `ANCHOR + STATE + 最新 TICKET`。

> 本轮新增（2026-05-27）：TICKET-022 已完成 Scheduler 多资源排程。`resource_reqs` 作为 canonical 资源需求输入，贯穿 CP-SAT cumulative 约束、具体资源分配、任务 JSON 持久化与 API 响应；`resource_type/resource_qty` 仅作为兼容 fallback。新增 `tests/unit/test_scheduler_multi_resource.py` 与 Pump Body 多资源集成断言。

> 本轮新增（2026-05-26）：TICKET-021 已完成 Planner 正向 BFS 主策略改造。新增 `app/core/planner/bfs.py`；`build_rag()` 主流程已切换为 forward BFS；`numeric.py` 不再作为主流程分流；`search_method` 写入 `forward_bfs`；已通过 planner/API/blockage/numeric 相关 97 项回归。

> 生成时间：2026-04-19
> 前置阅读：必须先读 ANCHOR.md

---

## 本版本目标

在 V0.2 稳定能力基础上，推进 V0.3 主线：求解可解释性深化、多目标优化、工序组能力、搜索策略演进。

当前已完成两项原先阻断后续深化的底座改造：

- Planner 已从旧的 delta-provider / 逆向依赖补齐，切换为正向 BFS 主策略。
- Scheduler 已从单主资源建模，升级为 `resource_reqs` 驱动的多资源约束与分配。

业务场景 Excel 导入包（TICKET-012）已完成；求解解释性（TICKET-011 / STEP 1）仍是下一阶段最自然的业务增强入口。

---

## 当前已完成（继承自历史版本）

### V0.1 基础能力（已完成）

- 完整两阶段求解链路：Planner（状态推导 RAG）+ Scheduler（CP-SAT 排程）
- 主数据 CRUD、求解接口、健康检查与基础前端
- 14 张核心表、Alembic 迁移与种子数据

### V0.2 架构升级与阻塞重排（已完成）

- 数据模型升级：`feature_definition`、`blockage_event`、`not_before`、`step_role`、版本链字段等落地
- 领域层注册表化：`OperatorRegistry`、`EffectRegistry`、`ObjectiveRegistry`、`RuleEvaluator`
- 策略 A/B/AB 阻塞处理闭环：状态注入 + 约束仲裁 + 事件记录
- API 扩展：`/features`、`/plans/{id}/versions`、`/plans/{id}/diff/{other_id}`
- 前端重构：Vue 3 + Element Plus + ECharts（含对比模式）
- 展示增强：Gantt/任务表统一显示“步骤编号 + 活动编码 + 活动名称”

---

## 已知技术债（延续）

1. 测试基础设施：`tests/e2e/conftest.py` 与 `tests/conftest.py` 双引擎 + 重复 fixture，需统一。
2. 多目标能力边界：TICKET-029 已完成 Scheduler 首个加权多目标切片；更通用的成本函数、setup reuse、事实生命周期和班次/人员目标仍需后续票据设计。
3. 历史文档中仍有旧错误码命名残留，需逐步清理并与 API 协议统一。
4. `solve.py` 仍承担输入校验、阻塞编排、Planner/Scheduler 编排、响应组装等多类职责，后续建议下沉到 Service 层。
5. 旧需求差距报告和历史计划文档中保留了“Planner 非 BFS / Scheduler 单资源”的旧结论，已在 2026-05-29 复核中标注修正。

---

## 本版本变更（V0.3）

### 专项：主数据 Excel 导入（优先前置）

- 目标：通过上传一个 `.xlsx` 文件，完成 `StateFeatureDef`、`Resource`、`OpRule` 的批量导入。
- 约束：严格 Upsert（已存在更新，不存在创建）；任一错误整批失败并回滚。
- 文件结构：`meta` + `feature_defs` + `resources` + `rules` + `instructions`（中文说明 sheet）。
- 规则表达：`rules` 中 `preconditions/effects/resource_reqs` 采用单元格 DSL。

> 说明：该专项作为 V0.3 前置可用性任务执行，不替代四项主线目标。

### 专项：数值型状态规划能力（最高优先级）

- 目标：在不破坏现有枚举型规划与 Scheduler 链路前提下，为数值型特征规划冻结最小正确架构。
- 聚焦问题：
  - 同一 `OpRule` 需要重复执行多次时，当前 RAG 无法表达实例化步骤。
  - 当前 `find_ops_for_delta()` 仅支持“单步精确命中”，无法处理 `0 -> 80`、步长 `20` 这类多步推进。
  - 当前 precondition 分析依赖静态 `current_state`，无法正确表达数值链条中的逐步状态演进。
  - 含副作用的规则可能被误选为目标特征的 provider，形成“有进展但走弯路”的错误规划。
- 约束：
  - 保持 `RuleEvaluator` 为 precondition/effect 唯一入口。
  - 保持 `CandidatePlanStep + predecessor_ids` 与 Scheduler 兼容，不先扩大调度层改动。
  - 第一阶段聚焦精确数值目标（`eq`），阈值目标（`gte/lte`）作为后续扩展单独建模。

### STEP 1：求解可解释性深化

- 目标：让 Planner/Scheduler 输出可追踪“为什么选这个工序、为什么这样排程”的解释信息。
- 产物：解释数据结构、响应字段、最小可视化承载方案。

### STEP 2：多目标优化能力

- 目标：让 `objectives` 从“可扩展框架”升级为“可用多目标能力”。
- 产物：至少支持 2 类目标组合与明确权重生效逻辑。

### STEP 3：工序组能力（Operation Group）

- 目标：支持按工序组进行组织与展示，为复杂工艺建模做准备。
- 产物：分组数据结构、求解链路兼容、前端展示入口。

### STEP 4：A* 搜索策略

- 目标：在保留现有策略前提下，引入 A* 搜索作为可选 Planner 策略。
- 产物：策略选择开关、启发函数基线实现、回归验证。

---

## 任务完成状态

```text
━━━━━━ TICKET-013：数值型状态规划能力设计冻结 ━━━━━━ [✅] 已完成
  [✅] T13-1  重新定义痛点与根因（动作实例化 / 单步命中 / 静态状态假设）
  [✅] T13-2  冻结最小架构方案（Planner 内部实例化步骤 + NumericFeaturePlanner）
  [✅] T13-3  明确阶段边界（Phase 1 精确数值目标 / Phase 2 副作用控制 / Phase 3 阈值目标）
  [✅] T13-4  补齐完整测试链路（unit / integration / API / e2e）
  [✅] T13-5  文档回写：STATE/TICKET 同步

━━━━━━ TICKET-014：Phase 1 准备层 — NumericFeaturePlanner 骨架与纯内存验证 ━━━━━━ [✅] 已完成
  [✅] T14-1  新增 numeric.py 与 PlannedStep / NumericPlanResult 数据结构
  [✅] T14-2  实现数值候选规则筛选与排序
  [✅] T14-3  实现精确目标 BFS / 有界搜索
  [✅] T14-4  验证状态不可变与重复 op_rule 不去重
  [✅] T14-5  补充 unit 测试并通过相关回归

━━━━━━ TICKET-015：Phase 1 接入层 — build_rag 分流与重复步骤持久化 ━━━━━━ [✅] 已完成
  [✅] T15-1  加载 StateFeatureDef 并按 value_type 对 delta 分流
  [✅] T15-2  接入 NumericFeaturePlanner，number exact 目标生成实例化步骤
  [✅] T15-3  数值步骤合并为统一 RAG，按实例 predecessor 串行建边
  [✅] T15-4  CandidatePlanStep 支持重复 op_rule_id 持久化
  [✅] T15-5  集成回归验证：numeric 重复步骤与 mixed enum/numeric 场景通过

━━━━━━ TICKET-016：Phase 1 闭环层 — 隐式子目标 + Scheduler/API/E2E 验证 ━━━━━━ [✅] 已完成
  [✅] T16-1  支持数值 precondition 驱动的隐式子目标规划
  [✅] T16-2  增加 visited_goals 循环检测与结构化错误
  [✅] T16-3  Scheduler/API 对重复 op_rule_id 步骤完整兼容
  [✅] T16-4  补充 API 测试 A1-A4 与 E2E 测试 E1-E4
  [✅] T16-5  全量测试通过

━━━━━━ TICKET-017：数值型重复步骤与阻塞重排兼容性修复 ━━━━━━ [✅] 已完成
  [✅] T17-1  实例级 blocked_step_id 路由与 step_id 回传
  [✅] T17-2  修复重复 op_rule_id 的 step_role diff 错配
  [✅] T17-3  numeric + blockage A/B/AB 交叉回归
  [✅] T17-4  运行相关测试并修复问题
  [✅] T17-5  文档回写：STATE/TICKET 同步

━━━━━━ TICKET-018：内网开发机一键启动架构 ━━━━━━ [✅] 已完成
  [✅] T18-1  bootstrap / launch 两阶段脚本落地
  [✅] T18-2  start.intranet.bat 一键入口
  [✅] T18-3  固定项目级 npm registry 使用方式
  [✅] T18-4  复用既有 PostgreSQL 与迁移/seed 流程
  [✅] T18-5  README 使用说明更新

━━━━━━ TICKET-019：启动脚本统一收敛与模式分流 ━━━━━━ [✅] 已完成
  [✅] T19-1  launcher 支持 mode 参数与分支
  [✅] T19-2  start.bat / start.local.bat 统一调用 launcher
  [✅] T19-3  保持 intranet / local / docker 三种入口兼容
  [✅] T19-4  启动脚本检查与修复
  [✅] T19-5  文档回写：STATE/TICKET 同步

━━━━━━ TICKET-020：内网开发机配置教程补充 ━━━━━━ [✅] 已完成
  [✅] T20-1  编写详细配置教程
  [✅] T20-2  覆盖可能需要修改的配置项
  [✅] T20-3  覆盖常见问题与排查
  [✅] T20-4  补充 README 快速入口
  [✅] T20-5  文档回写：STATE/TICKET 状态同步

━━━━━━ TICKET-021：Planner 正向 BFS 搜索主策略改造 ━━━━━━ [✅] 已完成
  [✅] T21-1  主策略切换为 forward BFS，保留 build_rag 对外契约
  [✅] T21-2  数值 repeated step 能力迁入统一 BFS
  [✅] T21-3  repair/blockage 语义通过状态注入继续兼容
  [✅] T21-4  BFS path 转 RAG，支持重复 op_rule 实例与依赖压缩
  [✅] T21-5  unit/integration/e2e 回归覆盖

━━━━━━ TICKET-022：Scheduler 多资源排程 ━━━━━━ [✅] 已完成
  [✅] T22-1  `StepData.resource_reqs` 作为 canonical 多资源输入
  [✅] T22-2  CP-SAT 对每个资源类型建立 cumulative 约束
  [✅] T22-3  资源实例分配支持每个需求类型与资源 capacity
  [✅] T22-4  schedule task JSON 持久化 `resource_reqs` / `resources`
  [✅] T22-5  单元测试与 Pump Body 集成断言补齐

━━━━━━ TICKET-012：业务场景 Excel 导入包与端到端数据装载 ━━━━━━  [✅] 已完成
  [✅] T12-1  业务场景导入规范冻结（模板、DSL、校验规则、响应结构）
  [✅] T12-2  后端导入 API（dry-run + scenario_upsert）
  [✅] T12-3  前端导入入口与校验结果展示
  [✅] T12-4  模板文件与中文 instructions sheet 交付
  [✅] T12-5  集成验证（成功导入 + 整批回滚 + 100+ rules dry-run）

━━━━━━ TICKET-024：分层活动/状态 Phase 1 数据底座 ━━━━━━ [✅] 已完成
  [✅] T24-1  新增 activity_node / state_node / scope_guard / scope_guard_precond 数据模型
  [✅] T24-2  op_rule 可选绑定三级 activity_node，旧规则保持兼容
  [✅] T24-3  后端 master-data CRUD 与层级 / Scope Guard 校验
  [✅] T24-4  前端数据管理页新增活动层级 / 状态层级 / 作用域约束入口
  [✅] T24-5  集成测试、全量 pytest 与前端 build 验证

━━━━━━ TICKET-025：分层活动/状态 Phase 2 展开预览 ━━━━━━ [✅] 已完成
  [✅] T25-1  目标状态树展开为 level-3 goal facts
  [✅] T25-2  活动范围展开为 level-3 candidate activities
  [✅] T25-3  Scope Guard 动态合并为 source-aware effective preconditions
  [✅] T25-4  前端数据管理页新增展开预览入口
  [✅] T25-5  集成测试、全量 pytest 与前端 build 验证

━━━━━━ TICKET-026：分层活动/状态 Phase 3 可达性和健康检查 ━━━━━━ [✅] 已完成
  [✅] T26-1  Provider / Consumer 图摘要
  [✅] T26-2  NO_PROVIDER / AMBIGUOUS_PROVIDER 目标可达性诊断
  [✅] T26-3  BROKEN_CHAIN 前置断链诊断
  [✅] T26-4  SELF_DEPENDENCY Scope Guard 自依赖诊断
  [✅] T26-5  CONFLICTING_GOAL 互斥目标诊断
  [✅] T26-6  前端数据管理页新增健康检查入口
  [✅] T26-7  集成测试、全量 pytest 与前端 build 验证

━━━━━━ TICKET-027：分层活动/状态 Phase 4 Planner/Scheduler 接入 ━━━━━━ [✅] 已完成
  [✅] T27-1  新增 `/api/v1/solve/layered` 分层求解入口
  [✅] T27-2  分层目标状态展开为联合目标事实并合成 target snapshot
  [✅] T27-3  Planner 消费候选三级活动和 Scope Guard effective preconditions
  [✅] T27-4  Scheduler 复用既有 CandidatePlan / CandidatePlanStep 排程链路
  [✅] T27-5  返回活动树 / 状态树汇总、有效前置解释和状态回放校验
  [✅] T27-6  前端 Solve 页新增快照 / 分层模式和分层解释页签
  [✅] T27-7  集成测试、全量 pytest 与前端 build 验证

━━━━━━ TICKET-028：分层活动/状态 Phase 5A 维护意图模板与联合求解 ━━━━━━ [✅] 已完成
  [✅] T28-1  新增 maintenance_intent_template 数据模型和迁移
  [✅] T28-2  新增维护意图模板 CRUD API 与校验
  [✅] T28-3  新增 `/api/v1/solve/maintenance` 联合维护求解入口
  [✅] T28-4  维护意图合并目标状态、活动范围、观测事实覆盖和期望事实
  [✅] T28-5  复用 Phase 4 layered solve，保持一个 Planner/Scheduler run
  [✅] T28-6  前端新增维护意图管理页和 Solve 维护模式
  [✅] T28-7  集成测试证明公共 provider 活动只计划一次，全量回归和前端 build 通过

━━━━━━ TICKET-029：分层活动/状态 Phase 5B Scheduler 连续性软成本 ━━━━━━ [✅] 已完成
  [✅] T29-1  Scheduler 输入与输出携带 level-3 活动和 level-2 活动组元数据
  [✅] T29-2  ObjectiveRegistry 支持单一加权 CP-SAT 目标表达式
  [✅] T29-3  新增 activity group span / gaps / interruptions 软目标
  [✅] T29-4  Scheduler diagnostics 返回 objective terms 与连续性摘要
  [✅] T29-5  `/solve` / `/solve/layered` / `/solve/maintenance` 保持 objectives 数组透传
  [✅] T29-6  Solve 页新增活动连续性开关、权重输入和结果摘要
  [✅] T29-7  单元/集成测试、全量 pytest 与前端 build 验证

━━━━━━ TICKET-030：分层场景 Excel 导入底座 ━━━━━━ [✅] 已完成
  [✅] T30-1  importer 支持可选 activity_nodes / state_nodes / scope_guards sheets
  [✅] T30-2  rules 支持可选 activity_node_code 绑定三级活动
  [✅] T30-3  dry-run 校验层级、Scope Guard、rule 绑定和错误不落库
  [✅] T30-4  导入 upsert 分层节点和 Scope Guard，并替换 Scope Guard 前置条件
  [✅] T30-5  模板下载和 Data Management 导入摘要同步分层字段
  [✅] T30-6  集成测试覆盖 layered workbook import 和 `/solve/layered`
  [✅] T30-7  前端 `npm run build` 已通过 escalated rerun 验证

━━━━━━ TICKET-031：分层活动选择与维修解释 ━━━━━━ [✅] 已完成
  [✅] T31-1  `/solve/layered` 返回 `layered.activity_selection`
  [✅] T31-2  `/solve/maintenance` 复用 layered 字段解释维修活动选择
  [✅] T31-3  解释 selected / skipped、跳过原因和 selected step order
  [✅] T31-4  标记公共 provider 的目标/前置消费者和 `is_shared_provider`
  [✅] T31-5  Solve 页新增活动选择解释表
  [✅] T31-6  维护共享 provider 与已满足跳过集成测试、全量 pytest 和前端 build 验证

━━━━━━ TICKET-032：维护意图模板场景导入 ━━━━━━ [✅] 已完成
  [✅] T32-1  场景 Excel 支持可选 `maintenance_intents` sheet 和模板示例
  [✅] T32-2  dry-run 校验维护作用域、目标状态、候选活动和维护事实
  [✅] T32-3  按 `(machine_type_code, issue_type)` upsert `maintenance_intent_template`
  [✅] T32-4  导入摘要和 preview 展示维护意图计数
  [✅] T32-5  导入模板可通过现有 API 列表读取并用于 `/solve/maintenance`
  [✅] T32-6  维护导入/求解测试、场景导入回归、全量 pytest 和前端 build 验证

━━━━━━ TICKET-033：分层求解前健康诊断摘要 ━━━━━━ [✅] 已完成
  [✅] T33-1  `/solve/layered` 成功响应返回 `layered.preflight_health`
  [✅] T33-2  `/solve/maintenance` 复用同一字段
  [✅] T33-3  完整健康检查仍保留在 `diagnostics.layered_health`
  [✅] T33-4  Solve 页分层/维护解释区展示健康状态、计数和诊断明细
  [✅] T33-5  分层/维护聚焦测试、全量 pytest 和前端 build 验证

━━━━━━ TICKET-034：场景导入后分层健康诊断 ━━━━━━ [✅] 已完成
  [✅] T34-1  场景 Excel 支持可选 `layered_health_checks` sheet 和模板示例
  [✅] T34-2  dry-run 校验机型、目标状态节点、活动范围节点和 include_inactive
  [✅] T34-3  导入成功后执行声明的分层健康检查
  [✅] T34-4  导入响应返回 compact `post_import_health_checks`
  [✅] T34-5  Data Management 导入弹窗展示导入诊断计数和结果表
  [✅] T34-6  场景导入、分层 API、全量 pytest 和前端 build 验证

━━━━━━ TICKET-035：分层求解层级结果展示与验收闭环 ━━━━━━ [✅] 已完成
  [✅] T35-1  `/solve/layered` 与 `/solve/maintenance` 返回 `activity_tree` / `state_tree`
  [✅] T35-2  保留既有 `activity_summary` / `state_summary` 平铺字段
  [✅] T35-3  状态回放和状态树叶子展示目标状态来源活动或当前状态来源
  [✅] T35-4  Solve 页任务明细支持活动层级树展示
  [✅] T35-5  Solve 页 Gantt 支持二级活动分组和折叠查看
  [✅] T35-6  Solve 页展示维护复用/跳过解释与连续性解释
  [✅] T35-7  分层集成测试、全量 pytest、前端 e2e 与前端 build 验证

━━━━━━ STEP 1：求解可解释性深化 ━━━━━━          [ ] 未开始
  [ ] 1-1  定义解释数据结构（Planner/Scheduler 统一）
  [ ] 1-2  扩展 /solve 响应解释字段（保持向后兼容）
  [ ] 1-3  前端最小解释信息展示（不重做页面）

━━━━━━ STEP 2：多目标优化能力 ━━━━━━            [⏳] 首个切片完成
  [✅] 2-1  Scheduler 已支持单一加权目标表达式与权重生效
  [✅] 2-2  已新增 activity group span / gaps / interruptions 目标
  [✅] 2-3  TICKET-029 已补齐接口透传与回归测试；通用目标目录仍待后续扩展

━━━━━━ STEP 3：工序组能力 ━━━━━━                [ ] 未开始
  [ ] 3-1  数据模型与 schema 设计
  [ ] 3-2  求解链路兼容（不破坏现有规则）
  [ ] 3-3  前端分组展示入口

━━━━━━ STEP 4：A* 搜索策略 ━━━━━━               [ ] 未开始
  [ ] 4-1  Planner 策略接口抽象
  [ ] 4-2  A* 基线实现与开关
  [ ] 4-3  端到端对照与性能基线记录
```

---

## 当前已知问题 / 决策悬挂

- 决策：`TICKET-013` 已完成设计冻结；Phase 1 已通过 `TICKET-014` / `TICKET-015` / `TICKET-016` 分票落地，并在 `TICKET-021` 收敛进统一正向 BFS 主流程。
- 决策：数值型能力当前由正向 BFS 统一承载；`numeric.py` 可暂时保留为历史兼容工具，但不再作为 `build_rag()` 主流程分流。
- 决策：`TICKET-017` 已完成，numeric 重复步骤与阻塞重排的交叉兼容已覆盖。
- 决策：重复任务的阻塞定位改为实例级，`/api/v1/solve` 返回 `step_id`，前端 `BlockageDialog` 需传 `blocked_step_id`；`blocked_op_rule_id` 仅保留为兼容降级输入。
- 决策：当重复规则只提供 `blocked_op_rule_id` 且无法唯一定位实例时，后端返回 `AMBIGUOUS_BLOCKED_STEP`，避免默认命中第一个任务。
- 决策（2026-06-02）：自发式重复清洁/重复上下电统一建模为 effect-driven re-provider。需要洁净度的后续活动应显式声明数值前置条件（如 `cleanliness > 30`）；当前序机械活动 effect 破坏该条件时，Planner 通过状态回放发现 unmet precondition，并自动插入可重新提供该条件的活动（如清洁/reset），而不是依赖人工代次建模或独立全局 trigger。
- 决策：Strategy B 与 AB 的回归验证已同步覆盖 numeric repeated steps，确保 repair 插入与实例级阻塞不冲突。
- 决策：内网开发机一键启动采用 bootstrap / launch 两阶段；Python 继续公网 `pip install`，npm 通过项目级 `.npmrc` 使用公司内网镜像，PostgreSQL 复用既有环境，不引入 Docker 或 request/HTTP 数据加载。
- 决策：`start.bat` / `start.local.bat` / `start.intranet.bat` 已统一收敛到共享 PowerShell launcher，通过 mode 分流保留 Docker / local / intranet 三种入口。
- 待定：`primary_feature` 是否作为第二阶段的辅助元数据引入，而非第一阶段主方案。
- 决策：阈值约束优先作为活动前置条件参与 re-provider 闭包；最终目标层面的 `gte/lte` goal predicate 仍可作为后续独立扩展，不复用 `target_state` 的 equality 语义。
- 待定：`seeds/005_numeric_phase1_ui_seed.sql` 与 `seeds/006_numeric_phase1_gapped_repeat_ui_seed.sql` 后续是否补充 solve 结果相关表 cleanup，以提升重复加载稳健性。
- 决策：`Strategy A/AB` 的 blocked step 定位已改为优先按 `blocked_step_id` 精确定位，`blocked_op_rule_id` 仅作兼容回退。
- 决策：`step_role` diff 对重复 `op_rule_id` 已改为按同一 plan 内实例顺序/step_order 对齐，避免 numeric repeated step 错配。
- 决策：`start.bat` / `start.local.bat` 已收敛到共享 PowerShell launcher，并通过 `mode` 区分 docker/local/intranet 三种入口。
- 决策：已新增内网开发机配置教程 `docs/intranet-dev-config-guide.md`，重点说明 `.env`、`frontend/.npmrc`、数据库连通性与常见问题排查。
- 决策：Scheduler 多资源能力已完成；`resource_reqs` 是主契约，旧 `resource_type/resource_qty` 仅用于兼容旧数据与旧测试。
- 决策：TICKET-012 已完成落地，下一张实现票可恢复 TICKET-011 / STEP 1 求解解释性深化。

---

## 本轮新增 / 关键文件

- `app/core/planner/numeric.py` — 数值型 Phase 1 planner，实现 exact numeric 目标、重复步骤实例化、隐式子目标与循环检测。
- `tests/unit/test_numeric_planner.py` — 数值型 planner 单元测试。
- `tests/e2e/test_numeric_planning.py` — 数值型规划 API 级 E2E 测试。
- `seeds/005_numeric_phase1_ui_seed.sql` — 数值型 Phase 1 UI 手工验收种子。
- `seeds/006_numeric_phase1_gapped_repeat_ui_seed.sql` — 间断型重复任务 UI 手工验收种子。
- `docs/TICKET_017.md` — 数值型重复步骤与阻塞重排兼容性修复工单。
- `frontend/src/components/BlockageDialog.vue` — 阻塞弹窗改为上传实例级 `blocked_step_id`。
- `tests/integration/test_step3_api.py` — 增加重复 numeric 步骤的实例级阻塞回归。
- `tests/integration/test_blockage_strategies.py` — 增加 numeric repeated steps 的 A/B/AB 交叉回归。
- `deploy/scripts/bootstrap_dev.ps1` — 内网开发机首次环境准备脚本。
- `deploy/scripts/launch_dev.ps1` — 内网开发机日常启动脚本。
- `start.intranet.bat` — 内网开发机一键入口。
- `frontend/.npmrc` — 项目级 npm registry 配置。
- `docs/TICKET_018.md` — 内网开发机一键启动架构工单。
- `docs/TICKET_019.md` — 启动脚本统一收敛与模式分流工单。
- `docs/intranet-dev-config-guide.md` — 内网开发机配置教程。
- `docs/TICKET_020.md` — 内网开发机配置教程补充工单。
- `app/core/planner/bfs.py` — 正向 BFS 主策略实现。
- `docs/TICKET_021.md` — Planner 正向 BFS 搜索主策略改造工单。
- `tests/unit/test_forward_bfs.py` — BFS 主策略单元测试。
- `tests/unit/test_scheduler_multi_resource.py` — Scheduler 多资源约束与分配单元测试。
- `docs/TICKET_022.md` — Scheduler 多资源排程工单。
- `app/services/scenario_import.py` — TICKET-012 业务场景 Excel 导入解析、校验、模板生成与 strict upsert。
- `app/api/v1/imports.py` — TICKET-012 场景导入 API 与模板下载 API。
- `frontend/src/views/DataManagement/index.vue` — 数据管理页新增场景模板下载与导入弹窗。
- `tests/integration/test_scenario_import_api.py` — 场景导入 dry-run、导入后求解、错误不落库与 100+ rules 覆盖。
- `docs/layered_activity_state_requirements.md` — 分层活动与分层状态需求文档。
- `docs/TICKET_024.md` — 分层活动/状态 Phase 1 数据底座工单。
- `migrations/versions/004_layered_activity_state.py` — 活动/状态层级与 Scope Guard 迁移。
- `frontend/src/views/DataManagement/ActivityHierarchyPage.vue` — 活动三层管理页。
- `frontend/src/views/DataManagement/StateHierarchyPage.vue` — 状态三层管理页。
- `frontend/src/views/DataManagement/ScopeGuardPage.vue` — Scope Guard 管理页。
- `tests/integration/test_layered_activity_state_api.py` — 分层数据 API 与旧 solve 兼容回归。
- `docs/TICKET_025.md` — 分层活动/状态 Phase 2 展开预览工单。
- `app/services/layered_expansion.py` — 分层目标/活动范围/effective rule 展开服务。
- `frontend/src/views/DataManagement/LayeredExpansionPage.vue` — 展开预览页。
- `docs/TICKET_026.md` — 分层活动/状态 Phase 3 可达性和健康检查工单。
- `app/services/layered_health.py` — Provider/Consumer 图与分层规则健康检查服务。
- `frontend/src/views/DataManagement/LayeredHealthCheckPage.vue` — 健康检查页。
- `docs/TICKET_027.md` — 分层活动/状态 Phase 4 Planner/Scheduler 接入工单。
- `app/services/layered_solve.py` — 分层求解服务，连接展开结果、POP、Scheduler 和状态回放。
- `frontend/src/views/SolvePage/index.vue` — 求解页新增快照 / 分层模式与分层解释结果页签。
- `docs/TICKET_028.md` — 分层活动/状态 Phase 5A 维护意图模板与联合求解工单。
- `migrations/versions/005_maintenance_intent_template.py` — 维护意图模板迁移。
- `app/services/maintenance_solve.py` — 多维护意图归并与联合 layered solve 服务。
- `frontend/src/views/DataManagement/MaintenanceIntentTemplatePage.vue` — 维护意图模板管理页。
- `frontend/src/views/SolvePage/index.vue` — 求解页新增维护模式和维护合并结果展示。
- `docs/TICKET_029.md` — 分层活动/状态 Phase 5B Scheduler 连续性软成本工单。
- `app/core/solver/objectives.py` — 加权 objective 合并与活动组 span/gap/interruption 目标。
- `app/core/scheduler/loader.py` — Scheduler RAG 输入加载活动节点和二级活动组元数据。
- `app/core/scheduler/model.py` — Scheduler 模型记录 activity groups 并提供 objective cache。
- `app/core/scheduler/solver.py` — Scheduler 任务输出、持久化和连续性 diagnostics。
- `tests/unit/test_scheduler_multi_resource.py` — 增加连续性软目标模型测试。
- `docs/TICKET_030.md` — 分层场景 Excel 导入底座工单。
- `app/services/scenario_import.py` — 场景导入新增 activity/state/scope guard sheets、rule activity binding、模板示例和校验。
- `tests/integration/test_scenario_import_api.py` — 增加 layered workbook dry-run/import/solve 和错误不落库测试。
- `frontend/src/views/DataManagement/index.vue` — 导入摘要展示活动层级、状态层级和 Scope Guard 计数。
- `docs/TICKET_031.md` — 分层活动选择与维修解释工单。
- `app/services/layered_solve.py` — 新增 activity selection explanation 和 shared provider consumer 解释。
- `frontend/src/views/SolvePage/index.vue` — 分层/维修解释页新增活动选择解释表。
- `docs/TICKET_032.md` — 维护意图模板场景导入工单。
- `app/services/scenario_import.py` — 场景导入新增 `maintenance_intents` sheet、维护事实解析、校验、模板示例和 upsert。
- `app/api/v1/imports.py` — 导入响应返回已导入维护意图模板摘要。
- `frontend/src/views/DataManagement/index.vue` — 导入摘要和 preview 展示维护意图计数。
- `tests/integration/test_scenario_import_api.py` — 增加维护意图模板导入、重复导入 preview 和 `/solve/maintenance` 集成测试。
- `docs/TICKET_033.md` — 分层求解前健康诊断摘要工单。
- `app/services/layered_solve.py` — 分层成功响应新增 compact `layered.preflight_health`。
- `frontend/src/views/SolvePage/index.vue` — 分层/维护解释页新增求解前诊断摘要和诊断表。
- `tests/integration/test_layered_activity_state_api.py` — 增加 layered/maintenance preflight health 响应断言。
- `docs/TICKET_034.md` — 场景导入后分层健康诊断工单。
- `app/services/scenario_import.py` — 场景导入新增 `layered_health_checks` sheet、导入后健康检查执行和 compact 返回。
- `app/api/v1/imports.py` — 场景导入响应稳定返回 `post_import_health_checks`。
- `frontend/src/views/DataManagement/index.vue` — 导入弹窗展示导入诊断计数和 post-import 结果表。
- `tests/integration/test_scenario_import_api.py` — 增加导入后健康检查 dry-run/import 返回断言。
- `docs/TICKET_035.md` — 分层求解层级结果展示与 18.1-18.6 验收闭环工单。
- `app/services/layered_solve.py` — 新增 activity/state tree 返回与目标状态来源解释。
- `frontend/src/views/SolvePage/index.vue` — 任务明细层级树、Gantt 二级活动折叠、维修解释和连续性解释展示。
- `tests/integration/test_layered_activity_state_api.py` — 增加目标状态来源与维护来源断言。
- `frontend/e2e/tests/solve.spec.ts` — 任务明细 Tab 下验证基础求解结果。
- `frontend/e2e/tests/blockage-strategy-a.spec.ts` — 任务明细 Tab 下验证 Strategy A 阻塞重排。
- `frontend/e2e/tests/blockage-strategy-a-fill-gaps.spec.ts` — 任务明细 Tab 下验证 Strategy A 填空档场景。
- `frontend/e2e/tests/blockage-strategy-b.spec.ts` — 任务明细 Tab 下验证 Strategy B 维修插入。

---

## 深入参考

| 需要了解 | 去看 |
|----------|------|
| 系统宪法与硬约束 | [ANCHOR.md](./ANCHOR.md) |
| 数值型状态规划设计工单 | [TICKET_013.md](./TICKET_013.md) |
| 主数据导入设计文档 | [master-data-excel-import.md](./master-data-excel-import.md) |
| V0.2 归档总结 | [archive/ARCHIVE_V0.2.md](./archive/ARCHIVE_V0.2.md) |
| V0.2 归档状态快照 | [archive/STATE_V0.2.md](./archive/STATE_V0.2.md) |
| API 契约与错误格式 | [protocols/api.md](./protocols/api.md) |
| ORM/Schema 契约 | [protocols/db.md](./protocols/db.md) |
| Planner 协议 | [protocols/planner.md](./protocols/planner.md) |
| Scheduler 协议 | [protocols/scheduler.md](./protocols/scheduler.md) |
| 历史设计与演进 | [archive/](./archive/) |
---

## Update 2026-05-29: TICKET-012 当前任务切换

TICKET-012 重新激活为当前任务，范围从“主数据 Excel 单文件导入”重设计为“业务场景导入包”。目标是用一个 `.xlsx` 场景文件支撑真实端到端测试，覆盖 100+ 活动规则、资源、设备类型、设备实例、状态特征定义、起点/目标状态与 solve_case 元数据，并提供 dry-run 校验与 strict upsert 导入。

## Update 2026-05-29: TICKET-012 已完成

已新增 `POST /api/v1/imports/scenario`、`GET /api/v1/imports/scenario-template`、后端导入服务、前端导入入口和集成测试。导入支持完整业务场景 dry-run、行级错误、create/update 预估、strict upsert、导入后 solve_case ID 映射，并已通过导入后 `/solve` 验证和 105 条 rules dry-run 覆盖。

## Update 2026-05-29: 工程机一键启动适配

TICKET-012 新增 `openpyxl` 依赖后，已确认旧工程机 `.venv` 可能缺少该依赖。`deploy/scripts/launch_dev.ps1` 已增加启动前后端依赖自检：若 `openpyxl` 缺失，会自动执行 `pip install -r requirements.txt` 后再启动后端。`deploy/scripts/bootstrap_dev.ps1` 的 Python 探测也已增强，避免某个不可运行的 `py.exe/python.exe` 候选直接中断探测流程。

## Update 2026-05-29: 数据管理页 mounted 错误兜底

用户反馈 DataManagement 下 RulePage/ResourcePage/MachinePage 在 mounted 阶段出现 unhandled promise error。已将 Vite API proxy 默认目标改为同机后端 `http://127.0.0.1:8000`，并支持通过 `VITE_API_PROXY_TARGET` 覆盖；同时为 DataManagement 各子页的 mounted/load 请求增加 catch 兜底，避免后端或代理短暂不可用时冒泡为 Vue mounted hook 未处理异常。

# CURRENT STATE: V0.3

> 生成时间：2026-04-19
> 前置阅读：必须先读 ANCHOR.md

---

## 本版本目标

在 V0.2 稳定能力基础上，推进 V0.3 四项主线：求解可解释性深化、多目标优化、工序组能力、A* 搜索策略。
当前新增最高优先级专项：数值型状态规划能力设计与落地准备，先解决“重复执行实例化、多步数值推进、隐式数值子目标、副作用弯路控制”的架构方案冻结。
主数据单文件 Excel 导入保留，但不再作为当前最紧急任务。

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
2. 多目标能力边界：当前仅完整实现 `minimize_makespan`，`weight` 尚未参与真实加权求解。
3. 历史文档中仍有旧错误码命名残留，需逐步清理并与 API 协议统一。

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

━━━━━━ TICKET-012：主数据 Excel 单文件导入 ━━━━━━  [ ] 未开始
  [ ] T12-1  导入规范文档冻结（模板、DSL、校验规则）
  [ ] T12-2  后端导入 API（dry-run + strict_upsert）
  [ ] T12-3  前端导入入口与校验结果展示
  [ ] T12-4  模板文件与中文说明 sheet 交付
  [ ] T12-5  集成验证（成功导入 + 整批回滚）

━━━━━━ STEP 1：求解可解释性深化 ━━━━━━          [ ] 未开始
  [ ] 1-1  定义解释数据结构（Planner/Scheduler 统一）
  [ ] 1-2  扩展 /solve 响应解释字段（保持向后兼容）
  [ ] 1-3  前端最小解释信息展示（不重做页面）

━━━━━━ STEP 2：多目标优化能力 ━━━━━━            [ ] 未开始
  [ ] 2-1  目标组合规则与权重生效机制
  [ ] 2-2  新增至少一个非 makespan 目标实现
  [ ] 2-3  接口与回归测试补齐

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

- 决策：V0.3 当前最高优先级调整为 `TICKET-013`（数值型状态规划能力设计冻结）；`TICKET-012` 延后，`TICKET-011` 继续暂缓。
- 决策：`TICKET-013` 已完成设计冻结；Phase 1 已通过 `TICKET-014` / `TICKET-015` / `TICKET-016` 分票落地。
- 决策：数值型 Phase 1 已具备后端端到端与 API 级 E2E 验证能力；真实浏览器 UI 自动化尚未接入，当前通过专用 seed 支持手工 UI 验收。
- 决策：当前进入 `TICKET-017`，目标是交叉验证并修复 numeric 重复步骤与阻塞重排的兼容性。
- 决策：重复任务的阻塞定位改为实例级，`/api/v1/solve` 返回 `step_id`，前端 `BlockageDialog` 需传 `blocked_step_id`；`blocked_op_rule_id` 仅保留为兼容降级输入。
- 决策：当重复规则只提供 `blocked_op_rule_id` 且无法唯一定位实例时，后端返回 `AMBIGUOUS_BLOCKED_STEP`，避免默认命中第一个任务。
- 决策：Strategy B 与 AB 的回归验证已同步覆盖 numeric repeated steps，确保 repair 插入与实例级阻塞不冲突。
- 决策：内网开发机一键启动采用 bootstrap / launch 两阶段；Python 继续公网 `pip install`，npm 通过项目级 `.npmrc` 使用公司内网镜像，PostgreSQL 复用既有环境，不引入 Docker 或 request/HTTP 数据加载。
- 决策：`start.bat` / `start.local.bat` / `start.intranet.bat` 下一步统一收敛到一个共享 launcher，通过 mode 分流保留 Docker / local / intranet 三种入口。
- 待定：`primary_feature` 是否作为第二阶段的辅助元数据引入，而非第一阶段主方案。
- 待定：阈值目标（`gte/lte`）是否在数值型能力第二阶段通过显式 goal predicate 扩展，而不复用 `target_state` 的 equality 语义。
- 待定：`seeds/005_numeric_phase1_ui_seed.sql` 与 `seeds/006_numeric_phase1_gapped_repeat_ui_seed.sql` 后续是否补充 solve 结果相关表 cleanup，以提升重复加载稳健性。
- 决策：`Strategy A/AB` 的 blocked step 定位已改为优先按 `blocked_step_id` 精确定位，`blocked_op_rule_id` 仅作兼容回退。
- 决策：`step_role` diff 对重复 `op_rule_id` 已改为按同一 plan 内实例顺序/step_order 对齐，避免 numeric repeated step 错配。
- 决策：`start.bat` / `start.local.bat` 已收敛到共享 PowerShell launcher，并通过 `mode` 区分 docker/local/intranet 三种入口。
- 决策：已新增内网开发机配置教程 `docs/intranet-dev-config-guide.md`，重点说明 `.env`、`frontend/.npmrc`、数据库连通性与常见问题排查。

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

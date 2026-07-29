# TICKET-095: 计划调整与统一重排中心

> Status: completed
> Version: V0.3
> Created: 2026-07-14
> Completed: 2026-07-14

## Goal

在 Solve 页面提供“选择待调整活动范围 → 编辑约束 → 试算对比 → 确认新基线”的统一重排流程。普通调整保持活动集合、规则工期和系统工艺依赖不变；甘特框选只产生具体 `scope_step_ids`，不表达项目进度或执行状态；最早开始语义统一复用 `not_before`。

## Tasks

- [x] T95-0 冻结规格、记录回归基线并完成 ANCHOR/术语检查。
- [x] T95-1 增加计划族、基线版本、调整单和步骤 lineage 数据底座。
- [x] T95-2 实现调整单领域服务、范围契约、继承与 stale 状态。
- [x] T95-3 实现时间/冻结/人工先后约束编译和无解诊断。
- [x] T95-4 实现范围外稳定优先的词典优化、候选预览和确认基线。
- [x] T95-5 实现任务表、业务分组、甘特单击/矩形框选的同步范围选择。
- [x] T95-6 将阻塞 A/B/AB 与排期规则例外接入统一候选确认流程。
- [x] T95-7 完成 MI-HP-001、全量回归、协议文档和 STATE 回写。

## Locked semantics

- 系统不负责项目进度或现场执行管理，不推断已完成、进行中或未开始。
- 待调整范围由计划师显式选择；框选坐标和时间区间不持久化。
- 普通调整不增删活动、不改工期、不改资源、不覆盖 Planner 推导依赖。
- `not_before` 是唯一最早开始术语，不新增 `earliest_start`。
- 范围外任务允许为满足约束而移动，但优化时优先保持稳定。
- 候选计划确认后才替换计划族的当前基线。

## Out of scope

- 项目进度、实际开始/结束、完成百分比和进行中活动中断。
- 直接拖拽后原样保存排程。
- 普通调整中的活动增删替换、工期修改和资源实例调整。
- 删除或反转系统工艺依赖。
- 自动软化约束、自动放松建议和一次生成多套候选方案。

## Phase gates

每个阶段必须通过对应单元/集成/浏览器门禁及既有回归后才能进入下一阶段；不得用 mock、跳过测试或人工说明替代正式验收证据。完整准入与准出标准见 `docs/superpowers/specs/2026-07-14-plan-adjustment-replan-center.md`。

## Acceptance evidence

- PostgreSQL Alembic `012_scheduling_rules → 013_plan_adjustment` 成功，`alembic current` 为 head。
- 后端全量：361 passed；计划调整专项：8 passed。
- Chromium Playwright 全量：85 passed；包含显式范围请求、Strategy A `not_before`、B 维修插入候选确认。
- Vite production build passed（保留既有 chunk-size warning）。
- MI-HP-001 四组合质量门禁全部 passed；全规则 makespan overhead 12.5%，低于 15% 上限。
- `scripts/check_terminology.py` passed；调整实现无 `earliest_start`、`cutoff_min` 或框选几何 API 字段。

## Follow-up 2026-07-14：连续基线调整试算修复

- 已修复确认候选后，继承约束仍引用父计划 `CandidatePlanStep.id`，导致下一次“保存并试算”返回 `STEP_OUTSIDE_CHANGE_SCOPE` 的问题。
- 继承约束现在按稳定 `step_order` 重映射到当前基线；新候选快照在落库前同步重映射到候选步骤 ID，并兼容修复数据库中已经存在的旧快照。
- `PlanAdjustmentDrawer` 增加持续可见的保存中、试算成功、无解和请求失败反馈；调整上下文失效不再静默返回，删除约束会废弃旧预览。
- 真实 PostgreSQL 调整单 2 按原范围与 `1495 → 1493` 约束重放成功，状态为 `preview_ready`，继承任务由旧 ID `1412` 映射为当前 ID `1484`，生成候选计划 74。
- 验证：计划调整集成测试 9 passed；Solve Chromium 13 passed；Vite production build passed；`py_compile` 与目标文件 `git diff --check` passed。

## Follow-up 2026-07-14：甘特矩形框选修复

- 已修复 ECharts `custom` 甘特系列无法向 `brushSelected` 提供命中数据，导致矩形可绘制但调整范围不更新的问题。
- 甘特纯组件现在按框选区域与任务条实际像素矩形计算交集；任一班次片段相交即命中任务，同一任务自动去重，并继续通过既有 `brush-select` 事件同步到统一 `scope_step_ids`。
- 新增真实 Chromium 拖拽回归：启用右上角矩形框选工具，跨甘特任务条拖框后，“已选择 N 个活动”更新为全部命中任务数。
- 验证：框选专项连续 3 次 passed；Vite production build passed；Solve 其余 13 条 passed。既有“引用原子状态树”用例在整组运行时发生一次 `/solve/layered` 请求等待超时，单独重跑 passed，与本次甘特代码路径无关。

## Follow-up 2026-07-17：甘特任务标签简化

- 甘特图左侧任务标签默认仅显示活动名称，不再显示步骤编号或活动编码；名称缺失时保留稳定降级显示。
- 分组、状态泳道和计划对比视图统一优先使用活动名称；任务排序、求解数据和后端契约不变。
- 验证：Vite production build passed with the existing chunk-size warning；ANCHOR 检查无违反。

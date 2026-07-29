# 计划调整与统一重排中心规格

## 产品边界

本功能负责计划基线上的活动范围选择、约束式重排、候选对比和版本确认。它不记录或推断项目执行进度。普通调整克隆基线活动网络，只改变排程约束；阻塞维修和排期规则例外保留各自既有求解语义。

## 范围选择

计划师先进入独立调整模式，再通过任务表、活动组、状态包、甘特任务单击或甘特矩形框选形成共享选择集。任务条与框选矩形有交集即命中，多次框选累加。所有选择最终归一为去重排序的 `scope_step_ids`；框选坐标与时间区间不进入 API 或数据库。

确认范围后才能编辑约束。返回修改范围时，仍有效约束保留；删除被约束引用的任务必须明确确认同步删除相关约束；任何范围变更都会废弃已有候选预览。

## 约束语义

- `not_before`: `start_min >= value_min`
- `finish_not_after`: `end_min <= value_min`
- `fixed_start`: `start_min == value_min`
- `freeze`: 保持基线 `start_min`
- `priority`: `high/normal/low` 软性尽早开始
- `precedence`: 新增零间隔 Finish-to-Start 关系

约束只能涉及 `scope_step_ids`，人工关系两端均须在范围内；系统推导依赖不可删除、反转或覆盖。新增分钟字段使用 `_min` 后缀；禁止新增 `earliest_start` 同义字段。

## 稳定性优化

> TICKET-096 于 2026-07-20 替代本节原有的绝对开始时间位移目标；完整设计见 `docs/superpowers/specs/2026-07-17-plan-adjustment-relative-order-compactness.md`。

普通调整按词典顺序优化：硬约束可行；最小 makespan；范围外有意义顺序对反转数；全部有意义顺序对反转数；`high=4/normal=2/low=1` 加权尽早开始；既有连续性和注册排期规则软目标。绝对开始时间变化继续用于候选对比，但不参与优化。

## 生命周期与接口

计划族只有一个 baseline。调整单状态为 `draft → previewing → preview_ready/infeasible → confirmed/cancelled`，基线变化后旧草稿转为 `stale`。候选确认必须在锁定计划族后原子替换 baseline。

接口：

- `POST /api/v1/plans/{baseline_plan_id}/adjustments`
- `GET/PATCH /api/v1/plan-adjustments/{id}`
- `POST /api/v1/plan-adjustments/{id}/preview`
- `POST /api/v1/plan-adjustments/{id}/confirm`
- `POST /api/v1/plan-adjustments/{id}/cancel`
- `GET /api/v1/plans/{plan_id}/adjustments`

## 开发阶段门禁

### Stage 0 — 规格与基线

准入：当前 Alembic 012 可用，现有测试环境可运行。准出：TICKET/spec、术语扫描和既有后端/Solve Chromium/Vite 基线有记录。

### Stage 1 — 数据底座

准入：历史线性链、分支链、失败叶子夹具已定义。准出：012→013、唯一 baseline、并发版本与确认测试通过，Scheduler 结果不变。

### Stage 2 — 调整领域服务

准入：Stage 1 完成。准出：范围归属、约束/范围一致性、继承、取消、stale 和状态机集成测试通过。

### Stage 3 — 约束与诊断

准入：约束 wire shape 冻结。准出：六类约束的可行/边界/无解测试、环检测、冲突定位和无解不落候选验证通过。

### Stage 4 — 优化与候选

准入：硬约束门禁通过。准出：活动集合/工期/系统依赖不变，范围外稳定优先有确定性证明，候选确认事务通过。

### Stage 5 — 范围选择 UI

准入：真实调整 API 稳定。准出：任务表、分组、单击、矩形框选同步；请求不含框选坐标；范围变更不静默删约束；Chromium 与 build 通过。

### Stage 6 — 统一重排入口

准入：普通调整 E2E 稳定。准出：Strategy A 复用 `not_before`，B/AB 保持状态注入，规则例外保持显式任务语义，相关回归通过。

### Stage 7 — 总验收

准入：前六阶段证据齐全。准出：MI-HP-001、后端全量、Chromium 全量、Vite build、迁移、terminology、ANCHOR 与 diff 检查全部通过，STATE/协议同步。

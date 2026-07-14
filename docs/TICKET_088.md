# TICKET-088: 系统默认白夜双班日历

> Status: completed
> Version: V0.3
> Created: 2026-07-13
> Completed: 2026-07-13

## Goal

新增一个可继承的系统默认工作日历，按每天 08:00–20:00 白班和 20:00–次日 08:00 夜班运行；排程保留班次边界、名称和资源交接语义，同时兼容已有无班次日历与机器显式配置。

## Tasks

- [x] T88-1 数据迁移、系统默认约束和默认双班 revision
- [x] T88-2 日历 API、机器继承策略与稳定诊断
- [x] T88-3 带班次元数据的窗口编译、交集和 Scheduler 分片
- [x] T88-4 前端班次编辑、系统默认标识、继承选择和甘特展示
- [x] T88-5 单元/集成/浏览器测试、全量回归和协议文档
- [x] T88-6 STATE/TICKET 回写与 ANCHOR 检查

## Compatibility

- 旧 `weekly_windows` 不要求班次字段。
- 机器显式默认日历和状态维度映射优先于系统默认继承。
- 未启用日历时排程行为不变。

## Acceptance

- 系统只有一个默认日历 `DEFAULT_DUAL_SHIFT`，覆盖七天白夜两班。
- 18:00 开始、240 分钟任务产生白班 18:00–20:00 和夜班 20:00–22:00 两个片段，暂停为 0。
- 未配置专属日历的机器继承系统默认；显式配置不被覆盖。

## Verification

- PostgreSQL Alembic `011_default_dual_shift_calendar` applied; one system default revision with 14 weekly windows verified.
- Backend full regression: `334 passed`.
- Frontend production build passed with the existing large-chunk warning.
- Chromium full regression: `80 passed`.
- ANCHOR check: no violations.
- Follow-up 2026-07-13: reproduced system-default switching, added existing-default-to-new-default API coverage, fixed the frontend interceptor so HTTP `detail` is not masked as `未知错误`, added calendar error messages, and restarted the stale port-8000 backend with the current workspace. Live GET and POST default-calendar calls passed; frontend build, focused API test and focused Chromium test passed.
- Follow-up 2026-07-13: fixed `CALENDAR_START_REQUIRED` caused by the datetime picker retaining hidden seconds/milliseconds. All three solve modes now normalize `schedule_start_at` to exact minute precision before ISO serialization; the Solve E2E asserts zero seconds and milliseconds. Frontend build and all 8 Solve Chromium tests passed.

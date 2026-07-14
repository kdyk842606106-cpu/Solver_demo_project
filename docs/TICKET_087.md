# TICKET-087: 工作日历排程
> Status: completed
> Version: V0.3
> Created: 2026-07-12
> Completed: 2026-07-12

## Goal

在保持既有连续分钟轴默认行为不变的前提下，为快照、分层和维护求解增加可选工作日历：日历按工序输出状态维度模板解析，支持机器默认回退、多维度日历交集、周期班次、日期例外和跨非工作时段暂停。

## Scope

- 工作日历与不可变 revision 主数据、机器默认日历、状态维度映射。
- 状态维度模板正式关系、求解日历上下文与历史快照。
- CalendarCompiler、步骤日历解析、可暂停分片排程与分片资源占用。
- 三类求解 API、持久化、甘特图、数据管理和场景导入。
- 单元、集成、前端 E2E、协议与 STATE 回写。

## Tasks

- [x] T87-1 数据迁移、ORM、Schema 和日历主数据 API
- [x] T87-2 日历窗口编译、维度解析和求解快照
- [x] T87-3 Scheduler 分片建模、资源分配与诊断
- [x] T87-4 快照/分层/维护求解接入
- [x] T87-5 前端工作日历配置与分片甘特
- [x] T87-6 场景导入、测试、文档和 STATE 回写

## Out of Scope

- 集成阶段主数据、活动包日历和资源个人日历。
- 工作日历产生额外工序依赖。
- 实时执行跟踪、跨机器资源调配和不确定时长。

## Compatibility

`calendar_context` 缺省或 `enabled=false` 时，Planner、Scheduler、API 与前端行为必须与当前版本一致。

## Verification

- Alembic `009 -> 010` applied successfully on PostgreSQL.
- Backend full regression: `331 passed`.
- Frontend production build passed with the existing large-chunk warning.
- Chromium Solve Page E2E: `8 passed`, including explicit calendar-context submission.
- Follow-up UI verification: weekly schedules now configure workdays separately from time windows, support multiple shift groups, and pass the production build.

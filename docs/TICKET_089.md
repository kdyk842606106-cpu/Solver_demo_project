# TICKET-089: 集成排期经验规则与连续班次约束

> Status: complete
> Version: V0.3
> Created: 2026-07-13
> Completed: 2026-07-13

## Goal

在现有活动能力、状态维度、工作日历、Scheduler 和版本重排链路上，以最小数据改动加入可注册、可配置、可单独启用的集成排期经验规则；同时禁止任务跳过中间关闭或被规则禁止的 shift 后续作，并支持求解后按具体任务申请班次例外并生成子计划重排。

## Tasks

- [x] T89-1 `machine_type.scheduling_config`、责任子系统和规则注册契约
- [x] T89-2 连续 shift 日历约束与稳定错误诊断
- [x] T89-3 责任子系统连续性、作用域排他和班次限制 Compiler
- [x] T89-4 快照/分层/维护求解接入、规则快照和例外重排
- [x] T89-5 活动能力配置、求解选择、甘特诊断和版本展示
- [x] T89-6 单元/集成/浏览器回归、协议和 STATE 回写

## Follow-up completion tasks

- [x] T89-7 Integrate scheduling rule configuration and reference diagnostics into the existing unified validation check.
- [x] T89-8 Verify realistic snapshot/layered/maintenance scheduling and explicit post-solve exception replanning scenarios.

## Compatibility

- 机器类型没有 `scheduling_config` 时不施加经验规则。
- 未启用工作日历时连续分钟轴行为不变。
- `atomic_activity.activity_category` 继续兼容 `normal/repair/maintenance`，用户文案改为“活动角色”。
- 历史工作日历、计划版本和已持久化任务 JSON 保持可读。

## Acceptance

- 行吊任务不与同一机器计划内其他任务并行，Scheduler 自主选择合法顺序。
- 行吊班次限制过滤中间 shift 后，任务不能使用前后 shift 拼接；例外重排允许后可连续跨越。
- 责任子系统连续性和功能调测独占可作为独立软规则启用。
- 初始求解拒绝例外；求解后例外生成子计划且父计划不变，原因必填且无审批字段。
- 快照、分层、维护三种求解入口语义一致。

## Delivered

- Alembic 012 增加 `machine_type.scheduling_config JSONB NULL`，SQLite 测试方言继续回退为 JSON。
- 三个 Compiler 通过装饰器注册并各自负责参数校验与 IR 编译；主解析流程不按类型分支。
- 日历模型禁止任务跨任何空档暂停后续作，并返回连续窗口诊断。
- 三种求解入口固化规则快照；例外按父任务显式申请、映射到子计划任务并完整重排。
- 活动能力复用现有页面配置责任子系统与规则，求解页复用优化目标区域选择规则，成功和失败结果均支持任务例外。

## Verification

### Final completion verification

- Unified validation now covers stale responsibility plus invalid resource, state-dimension, shift, rule-type and rule-parameter references, required-rule disablement, and zero-match warnings.
- Realistic database integration covers crane hard exclusivity, functional-test soft violations, subsystem continuity, failed-plan exception candidates, child-plan exception replanning, parent immutability, explicit override carry, and snapshot/layered/maintenance parity.
- The persisted PostgreSQL `MI-CONT-001` scenario is initialized with responsible subsystems and an optional continuity rule; `scripts/validate_scheduling_rule_scenario.py` returned `done`, makespan 40, zero gap/interruption for STRUCTURE and TRANSFER, and no validation warning.
- Backend full regression: `348 passed`.
- Frontend production build: passed with the existing 4.6 MB chunk warning.
- Chromium single-worker full regression: `82 passed`.
- Local PostgreSQL: `012_scheduling_rules (head)`.

- Backend: `344 passed`。
- Focused scheduling rule/calendar/API suite: `23 passed`。
- Frontend production build: passed（保留既有 4.6 MB chunk warning）。
- Chromium: 单 worker 全量 `82 passed`，包含规则选择、例外重排和既有网络编辑器回归。
- Alembic: `012_scheduling_rules (head)`，010 → 011 → 012 链完整。
- ANCHOR audit: no violations。

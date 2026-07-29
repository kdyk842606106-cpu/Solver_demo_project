# TICKET-096：计划调整相对顺序稳定与紧凑排程

> Status: completed
> Version: V0.3
> Created: 2026-07-17
> Completed: 2026-07-20

> Scope note 2026-07-20: current implementation is narrowed to eliminating avoidable schedule gaps. Critical-path calculation/display, new wait-cause diagnostics, API/schema/database changes, and frontend redesign are explicitly deferred.

## Goal

修正普通计划调整把“少移动”解释为绝对开始时间变化的问题。调整求解必须先满足硬约束并取得最小工期，再以有业务意义的活动相对顺序反转数衡量稳定性，最后把排程左移压紧；基线中没有约束依据的空档不得因为绝对时间稳定目标而被保留。

## Scope

- 只改变普通计划调整的优化阶段，不改变活动集合、工期、资源需求、系统工艺依赖和约束 wire shape。
- `precedence` 继续表示最小时间差为 0 的 Finish-to-Start：后项不得早于前项结束，但不承诺紧邻。
- 绝对开始时间变化数和变化分钟数继续用于候选对比展示，不再作为求解目标。
- 基线中原本重叠或并行、且没有共同业务顺序来源的活动不建立软保序关系。

## Tasks

- [x] T96-0 冻结相对顺序对、词典目标和空档验收场景。
- [x] T96-1 在调整服务中编译基线顺序对和优化策略快照。
- [x] T96-2 将调整目标替换为 makespan、顺序反转和加权开始时间的词典阶段。
- [x] T96-3 完成单元、集成、用户问题复刻和相关回归，证明可避免空档被压缩。
- [x] T96-4 同步规格、Scheduler 协议、STATE，并完成 ANCHOR 检查。

## Locked design proposal

完整设计见 `docs/superpowers/specs/2026-07-17-plan-adjustment-relative-order-compactness.md`。

词典目标顺序：

1. 硬约束可行；
2. 最小化 makespan；
3. 最小化范围外有意义顺序对的反转数；
4. 最小化全部有意义顺序对的反转数；
5. 最小化优先级加权的开始时间总和；
6. 在以上最优值锁定后，应用既有连续性与注册排期规则软目标。

## Out of scope

- 把 `precedence` 改成强制无等待的相邻约束。
- 修改关键路径计算、关键活动判定或甘特图关键路径展示。
- 新增等待原因、左右浮时或顺序反转的 API/UI 诊断。
- 修改 Planner 推导的系统工艺依赖。
- 修改活动工期、资源需求或具体资源主数据。
- 自动删除、反转或软化用户约束。
- 为每次调整一次性生成多套候选方案。

## Acceptance summary

- 用户增加人工先后约束后，候选 makespan 在给定硬约束下被证明最优；未证明最优时必须明确返回阶段状态，不能宣称满足最小工期原则。
- 在 makespan 和顺序反转最优值锁定后，候选不存在“不移动其他活动即可把某活动提前”的可行改进。
- 无资源、日历、前序或已锁定顺序原因的基线空档不再保留。
- 有多前序汇合、资源占用、日历窗口或硬约束原因的等待允许保留；本票据不新增等待原因诊断。
- 相互独立的并行活动不因稳定性目标被强制串行。
- 既有活动集合、工期、资源需求、系统依赖和候选确认事务语义保持不变。

## Completion evidence

- 新增领域回归证明共享资源基线 `20→40` 空档被压紧为 `0→10`，并证明当保序会把 makespan 从 30 延长到 40 时，最小工期阶段优先选择 makespan 30 和必要反转。
- 新增端到端调整预览回归：把独立清洁活动的基线开始时间人工置为 10，候选重新压紧到 0，makespan 保持不变；候选快照记录 `relative_order_compact_v1`。
- 调整专项：`tests/unit/test_scheduler_adjustments.py` + `tests/integration/test_plan_adjustment_api.py`，13 passed。
- 相关 Scheduler、Objective、排期规则、阻塞和旧接口回归：68 passed。
- 后端全量：370 passed；使用项目内隔离 `--basetemp` 避免 Windows 系统临时目录清理权限问题。
- `py_compile`、术语检查和目标文件 `git diff --check` passed；无关键路径、API、数据库或前端改动。

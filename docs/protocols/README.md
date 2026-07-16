# 模块协议文档索引

> 描述当前代码实现的模块职责、输入输出契约和模块间数据流。以仓库现状为准。
>
> **上层文档**：[`../ANCHOR.md`](../ANCHOR.md)（系统宪法） · [`../STATE_V0.3.md`](../STATE_V0.3.md)（当前版本快照） · 最新 `../TICKET_*.md`（任务工单）

## 模块列表

| 模块 | 目录 | 文档 | 说明 |
|------|------|------|------|
| Planner | `app/core/planner/` | [planner.md](./planner.md) | 基于实例级 Partial Order Planner 和 precondition/effect 链构建 RAG |
| Scheduler | `app/core/scheduler/` | [scheduler.md](./scheduler.md) | 基于 RAG、多资源、日历、注册式排期规则和调整约束做 CP-SAT 排程 |
| API | `app/api/v1/` | [api.md](./api.md) | 对外 HTTP 接口（求解、主数据、日历、计划版本与调整） |
| DB | `app/db/` | [db.md](./db.md) | ORM 模型、Schema 与共享数据契约 |

## 当前数据流

```text
Client
  -> API (/api/v1/solve | /api/v1/solve/layered | /api/v1/solve/maintenance)
  -> optional layered expansion / maintenance intent merge
  -> Planner.build_rag(...)
  -> Planner.save_candidate_plan(...)
  -> Scheduler.solve_schedule(...)
  -> Scheduler.save_schedule_result(...)
  -> API response
```

计划调整使用独立候选确认流：

```text
current family baseline
  -> create/update plan_adjustment with explicit scope_step_ids
  -> Scheduler preview with normalized adjustment_context
  -> candidate plan + task diff + diagnostics
  -> explicit confirm
  -> atomically replace plan_family baseline
```

## 当前共享契约

- API 写入 `solve_request`
- Planner 写入 `candidate_plan` 和 `candidate_plan_step`
- Scheduler 读取 `candidate_plan_step`，写入 `schedule_result`
- 工作日历 revision、维度映射和解析结果固化在求解快照中，避免主数据更新导致历史计划漂移
- `plan_family` 维护唯一当前基线；`plan_adjustment` 保存范围、约束、预览诊断和候选关系
- `candidate_plan_step.predecessor_ids` 是 Planner 推导出的依赖边来源
- `parallel_groups` 来自 Scheduler 求解后时间重叠检测，非 Planner 预标记
- `solve_request.status` 模型默认 `pending`，但 API 创建时直接写入 `running`
- TICKET-036 后，分层状态目标按“活跃无子节点 = 原子状态”递归展开；聚合状态节点不绑定事实。
- TICKET-036 后，活动能力推荐通过一级/二级 `activity_node` 包 + `atomic_activity` + `activity_package_atomic_ref` 表达；旧三级 `activity_node` 仍作为兼容路径存在。

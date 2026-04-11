# 模块协议文档索引

> 描述当前代码实现的模块职责、输入输出契约和模块间数据流。以仓库现状为准。
>
> **上层文档**：[`../ANCHOR.md`](../ANCHOR.md)（系统宪法） · [`../STATE_V0.2.md`](../STATE_V0.2.md)（当前版本快照） · [`../v0.2-spec.md`](../v0.2-spec.md)（v0.2 规格书）

## 模块列表

| 模块 | 目录 | 文档 | 说明 |
|------|------|------|------|
| Planner | `app/core/planner/` | [planner.md](./planner.md) | 基于状态差异和 precondition/effect 链构建 RAG |
| Scheduler | `app/core/scheduler/` | [scheduler.md](./scheduler.md) | 基于 RAG 和资源容量做 CP-SAT 排程 |
| API | `app/api/v1/` | [api.md](./api.md) | 对外 HTTP 接口（求解 + 主数据维护） |
| DB | `app/db/` | [db.md](./db.md) | ORM 模型、Schema 与共享数据契约 |

## 当前数据流

```text
Client
  -> API (/api/v1/solve)
  -> Planner.build_rag(...)
  -> Planner.save_candidate_plan(...)
  -> Scheduler.solve_schedule(...)
  -> Scheduler.save_schedule_result(...)
  -> API response
```

## 当前共享契约

- API 写入 `solve_request`
- Planner 写入 `candidate_plan` 和 `candidate_plan_step`
- Scheduler 读取 `candidate_plan_step`，写入 `schedule_result`
- `candidate_plan_step.predecessor_ids` 是 Planner 推导出的依赖边来源
- `parallel_groups` 来自 Scheduler 求解后时间重叠检测，非 Planner 预标记
- `solve_request.status` 模型默认 `pending`，但 API 创建时直接写入 `running`

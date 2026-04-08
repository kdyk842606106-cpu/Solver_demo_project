# 模块协议文档索引

这些文档用于描述当前代码实现的模块职责、输入输出契约和模块间数据流。内容以仓库现状为准，不再保留尚未实现的设计假设。

## 模块列表

| 模块 | 目录 | 文档 | 说明 |
|------|------|------|------|
| Planner | `app/core/planner/` | [planner.md](./planner.md) | 基于状态差异和 precondition/effect 链构建 RAG |
| Scheduler | `app/core/scheduler/` | [scheduler.md](./scheduler.md) | 基于 RAG 和资源容量做 CP-SAT 排程 |
| API | `app/api/v1/` | [api.md](./api.md) | 对外 HTTP 接口与求解编排 |
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

查询链路：

```text
Client
  -> API query endpoints
  -> DB tables (solve_request / candidate_plan / schedule_result / machine_state)
```

## 当前共享契约

- API 写入 `solve_request`
- Planner 写入 `candidate_plan` 和 `candidate_plan_step`
- Scheduler 读取 `candidate_plan_step`，写入 `schedule_result`
- API 从 `solve_request`、`schedule_result`、`machine_state` 读取并返回查询结果

## 与代码对齐的注意事项

- `candidate_plan_step.predecessor_ids` 是 Planner 推导出的依赖边来源
- `parallel_groups` 不是 Planner 输入字段，而是 Scheduler 从最终任务时间重叠中检测出来的结果
- `solve_request.status` 的模型默认值虽然是 `pending`，但当前 API 创建记录时直接写入 `running`

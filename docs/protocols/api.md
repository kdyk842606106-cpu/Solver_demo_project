# API 模块协议

路径：`app/api/v1/`

当前 API 层负责：

- 接收求解请求
- 校验输入是否存在且归属于正确机台
- 编排 Planner 与 Scheduler
- 统一错误响应格式
- 提供状态查询接口

## 已实现端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/solve` | 提交求解请求并同步返回结果 |
| `GET` | `/api/v1/solve-requests/{request_id}` | 查询求解请求及排程结果 |
| `GET` | `/api/v1/machines/{machine_id}/state` | 查询机台最近的当前状态 |
| `GET` | `/api/v1/machines/{machine_id}/states` | 列出机台全部可选状态 |
| `GET` | `/health` | 健康检查 |

## `POST /api/v1/solve`

### 请求体

```json
{
  "machine_id": 1,
  "current_state_id": 1,
  "target_state_id": 2,
  "objective": "minimize_makespan",
  "overrides": null
}
```

### 字段约束

| 字段 | 类型 | 说明 |
|------|------|------|
| `machine_id` | `int` | 必须存在于 `machine` 表 |
| `current_state_id` | `int` | 必须存在于 `machine_state` 表，且属于该机台 |
| `target_state_id` | `int` | 必须存在于 `machine_state` 表，且属于该机台 |
| `objective` | `string` | 当前仅支持 `minimize_makespan` |
| `overrides` | `object \| null` | 透传保存到 `solve_request.overrides`，当前求解逻辑未消费 |

### 成功响应

```json
{
  "solve_request_id": 42,
  "status": "done",
  "candidate_plan_id": 7,
  "schedule": {
    "makespan": 45,
    "tasks": [
      {
        "step": 1,
        "op_code": "OP_WARMUP",
        "start": 0,
        "end": 30,
        "resource": "TECH-01",
        "predecessors": []
      },
      {
        "step": 2,
        "op_code": "OP_CALIBRATE",
        "start": 30,
        "end": 45,
        "resource": "TECH-02",
        "predecessors": [1]
      }
    ],
    "parallel_groups": []
  }
}
```

### 业务失败响应

业务失败仍返回 `200 OK`，通过 `status=failed` 区分：

```json
{
  "solve_request_id": 43,
  "status": "failed",
  "candidate_plan_id": 7,
  "error_code": "INFEASIBLE",
  "error_message": "Resource constraints cannot be satisfied"
}
```

可能出现的业务错误码：

| 错误码 | 来源 | 说明 |
|--------|------|------|
| `NO_SOLUTION` | Planner | 无可达路径，或当前已在目标状态 |
| `CIRCULAR_DEPENDENCY` | Planner | 构建出的依赖图存在环 |
| `INFEASIBLE` | Scheduler | 资源约束无法满足 |
| `SOLVER_TIMEOUT` | Scheduler | 当前实现里仅在 Scheduler 返回非 `infeasible` 且非 `optimal/feasible` 时由 API 映射 |
| `INTERNAL_ERROR` | Planner / 全局异常 | 未预期错误 |

### 参数错误响应

`HTTPException` 已被项目统一包装，不使用 FastAPI 默认 `detail` 列表格式：

```json
{
  "error_code": "HTTP_422",
  "error_message": "Machine with id=999 not found"
}
```

### 当前执行流程

```text
1. 校验 machine / current_state / target_state / objective
2. 创建 solve_request，状态直接写为 running
3. 调用 Planner.build_rag(...)
4. 失败则更新 solve_request.status=failed 并返回业务失败
5. 成功后调用 Planner.save_candidate_plan(...)
6. 调用 Scheduler.solve_schedule(...)
7. 成功则调用 Scheduler.save_schedule_result(...)
8. 更新 solve_request.status=done，写入 solved_at
9. 组装精简 schedule 响应
```

注意：

- 当前代码不会先创建 `pending` 再改为 `running`
- 返回给客户端的 `schedule.tasks` 是精简结构
- 持久化到 `schedule_result.tasks` 的结构比 API 返回更完整

## `GET /api/v1/solve-requests/{request_id}`

### 响应

```json
{
  "id": 42,
  "machine_id": 1,
  "status": "done",
  "objective": "minimize_makespan",
  "created_at": "2026-04-01T10:00:00+00:00",
  "solved_at": "2026-04-01T10:00:03+00:00",
  "candidate_plan_id": 7,
  "schedule": {
    "makespan": 45,
    "solver_status": "OPTIMAL",
    "tasks": [
      {
        "step_order": 1,
        "op_rule_id": 1,
        "op_rule_code": "OP_WARMUP",
        "start_min": 0,
        "end_min": 30,
        "duration_min": 30,
        "predecessors": [],
        "resources": [
          {
            "resource_id": 1,
            "resource_code": "TECH-01"
          }
        ]
      }
    ]
  }
}
```

说明：

- 只有当 `solve_request.status == "done"` 时才附带 `schedule`
- 查询接口返回的是数据库里保存的完整任务结构，不是 `POST /solve` 的精简格式

## `GET /api/v1/machines/{machine_id}/state`

返回该机台 `state_type="current"` 且 `created_at` 最新的一条状态。

```json
{
  "machine_id": 1,
  "machine_code": "M-001",
  "current_state": {
    "state_id": 1,
    "label": "Cold Dirty Uncalibrated",
    "features": {
      "temperature_level": "cold",
      "clean_level": "dirty",
      "calibration": "off"
    }
  }
}
```

## `GET /api/v1/machines/{machine_id}/states`

列出机台全部状态快照，供前端选择当前/目标状态：

```json
{
  "machine_id": 1,
  "machine_code": "M-001",
  "states": [
    {
      "state_id": 1,
      "label": "Cold Dirty Uncalibrated",
      "features": {
        "temperature_level": "cold",
        "clean_level": "dirty",
        "calibration": "off"
      }
    }
  ]
}
```

## `GET /health`

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

## 全局错误响应

| HTTP 状态码 | 格式 |
|------------|------|
| `404` / `422` | `{ "error_code": "HTTP_<status>", "error_message": "<detail>" }` |
| `500` | `{ "error_code": "INTERNAL_ERROR", "error_message": "...", "traceback": "..." }` |

当前 `500` 响应会返回 traceback，这更偏开发态行为。

## 建议中的主数据维护 API

为支持“前端录入数据后直接求解”，建议在现有接口之外增加一层主数据维护 API。该部分属于建议中的最小重构，不是当前已实现能力。

### 目标

- 让前端可以直接维护设备、状态、活动、资源
- 录入结果直接落现有数据库表
- `POST /api/v1/solve` 继续复用现有 Planner 和 Scheduler

### 路由组织建议

建议新增：

- `app/api/v1/master_data.py`

并在 `app.main` 中注册到 `/api/v1`。

### 建议新增接口

设备与特征：

- `GET/POST /api/v1/machine-types`
- `GET/PUT /api/v1/machine-types/{id}`
- `GET/POST /api/v1/machine-types/{id}/feature-defs`
- `PUT/DELETE /api/v1/feature-defs/{id}`
- `GET/POST /api/v1/machines`
- `GET/PUT /api/v1/machines/{id}`

状态：

- `GET /api/v1/machines/{id}/states`
- `POST /api/v1/machines/{id}/states`
- `PUT /api/v1/states/{id}`
- `DELETE /api/v1/states/{id}`

活动：

- `GET /api/v1/machine-types/{id}/op-rules`
- `POST /api/v1/machine-types/{id}/op-rules`
- `PUT /api/v1/op-rules/{id}`
- `DELETE /api/v1/op-rules/{id}`

资源：

- `GET/POST /api/v1/resources`
- `PUT/DELETE /api/v1/resources/{id}`

### 聚合接口要求

为了让前端表单更友好，建议接口支持嵌套写入，而不是把子表拆成多次请求。

状态创建/更新建议请求体：

```json
{
  "state_type": "snapshot",
  "label": "冷机/脏污/未校准",
  "features": {
    "temperature_level": "cold",
    "clean_level": "dirty",
    "calibration": "off"
  }
}
```

活动创建/更新建议请求体：

```json
{
  "code": "OP_WARMUP",
  "name": "升温",
  "duration_min": 30,
  "description": "将设备升温到工作温度",
  "is_active": true,
  "preconditions": [
    {
      "feature_key": "temperature_level",
      "operator": "eq",
      "feature_value": "cold"
    }
  ],
  "effects": [
    {
      "feature_key": "temperature_level",
      "new_value": "hot"
    }
  ],
  "resource_reqs": [
    {
      "resource_type": "TECHNICIAN",
      "quantity": 1,
      "is_required": true
    }
  ]
}
```

### 用户友好要求

主数据 API 的返回结构应以业务对象为中心，而不是要求前端直接理解这些底层概念：

- `machine_state_feature`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`
- `predecessor_ids`

### 最小校验建议

- 状态保存时校验 `feature_key` 是否属于对应 `machine_type`
- 枚举特征值必须在允许值范围内
- 活动至少包含一个 `effect`
- 求解前校验当前状态与目标状态不能相同

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
| `POST` | `/api/v1/solve/layered` | 从分层状态目标和活动范围发起一次联合求解 |
| `POST` | `/api/v1/solve/maintenance` | 从维护意图模板发起一次联合维护求解 |
| `GET` | `/api/v1/solve-requests/{request_id}` | 查询求解请求及排程结果 |
| `GET` | `/api/v1/machines/{machine_id}/state` | 查询机台最近的当前状态 |
| `GET` | `/api/v1/machines/{machine_id}/states` | 列出机台全部可选状态 |
| `POST` | `/api/v1/imports/scenario` | 业务场景 Excel dry-run / strict upsert 导入 |
| `GET` | `/api/v1/imports/scenario-template` | 下载业务场景 Excel 模板 |
| `GET` | `/health` | 健康检查 |

## `POST /api/v1/solve`

### 请求体

```json
{
  "machine_id": 1,
  "current_state_id": 1,
  "target_state_id": 2,
  "objective": "minimize_makespan",
  "objectives": [
    {
      "type": "minimize_makespan",
      "weight": 1.0
    }
  ],
  "parent_plan_id": null,
  "overrides": null,
  "blockage_constraints": null
}
```

### 字段约束

| 字段 | 类型 | 说明 |
|------|------|------|
| `machine_id` | `int` | 必须存在于 `machine` 表 |
| `current_state_id` | `int` | 必须存在于 `machine_state` 表，且属于该机台 |
| `target_state_id` | `int` | 必须存在于 `machine_state` 表，且属于该机台 |
| `objective` | `string` | 兼容旧字段，默认 `minimize_makespan` |
| `objectives` | `array \| null` | 目标数组；支持 `minimize_makespan` 以及 Scheduler 活动组连续性软目标，按 `weight` 合并为单一加权 CP-SAT 目标表达式 |
| `parent_plan_id` | `int \| null` | 阻塞重排/版本链的父计划 ID |
| `overrides` | `object \| null` | 透传保存到 `solve_request.overrides`，当前求解逻辑未消费 |
| `blockage_constraints` | `object \| null` | 阻塞策略输入，支持 `strategy=A/B/AB`、实例级 `blocked_step_id`、兼容用 `blocked_op_rule_id`、`strategy_a.not_before_offset`、`strategy_b.blockage_reason` |

### 成功响应

```json
{
  "solve_request_id": 42,
  "status": "done",
  "candidate_plan_id": 7,
  "state_delta": [
    {
      "feature_key": "calibration",
      "from_value": "off",
      "to_value": "on"
    }
  ],
  "critical_path": ["OP_WARMUP", "OP_CALIBRATE"],
  "schedule": {
    "makespan": 45,
    "tasks": [
      {
        "step_order": 1,
        "step_id": 100,
        "op_rule_id": 3,
        "op_rule_code": "OP_WARMUP",
        "op_rule_name": "Warm up",
        "start_min": 0,
        "end_min": 30,
        "duration_min": 30,
        "resources": [
          {
            "resource_id": 1,
            "resource_code": "TECH-01",
            "resource_type": "TECHNICIAN",
            "quantity": 1
          }
        ],
        "resource_type": "TECHNICIAN",
        "resource_reqs": [
          {
            "resource_type": "TECHNICIAN",
            "quantity": 1
          }
        ],
        "activity_node_id": null,
        "activity_node_code": null,
        "activity_node_name": null,
        "atomic_activity_id": null,
        "activity_group_id": null,
        "activity_group_code": null,
        "activity_group_name": null,
        "predecessors": [],
        "not_before": null,
        "step_role": "normal"
      },
      {
        "step_order": 2,
        "step_id": 101,
        "op_rule_id": 4,
        "op_rule_code": "OP_CALIBRATE",
        "op_rule_name": "Calibrate",
        "start_min": 30,
        "end_min": 45,
        "duration_min": 15,
        "resources": [
          {
            "resource_id": 2,
            "resource_code": "TECH-02",
            "resource_type": "TECHNICIAN",
            "quantity": 1
          }
        ],
        "resource_type": "TECHNICIAN",
        "resource_reqs": [
          {
            "resource_type": "TECHNICIAN",
            "quantity": 1
          }
        ],
        "predecessors": [1],
        "not_before": null,
        "step_role": "normal"
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
| `AMBIGUOUS_BLOCKED_STEP` | API 阻塞定位 | 旧调用只传 `blocked_op_rule_id` 且命中多个重复步骤，必须改传实例级 `blocked_step_id` |
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
6. 如有 Strategy A/AB，优先按 `blocked_step_id` 精确定位新计划中的实例并写入 `not_before`
7. 如有阻塞策略，记录 `blockage_event`
8. 调用 Scheduler.solve_schedule(...)
9. 成功则调用 Scheduler.save_schedule_result(...)
10. 调用 `compute_step_role_diff(...)` 标记 normal/repair/pulled_forward/delayed
11. 更新 solve_request.status=done，写入 solved_at
12. 组装包含 `state_delta`、`critical_path`、完整 task 资源信息的响应
```

注意：

- 当前代码不会先创建 `pending` 再改为 `running`
- 返回给客户端的 `schedule.tasks` 已包含 `step_id`、`resource_reqs`、完整 `resources`、`not_before`、`step_role`、活动/原子活动/活动组展示元数据
- 持久化到 `schedule_result.tasks` 的结构与 API 返回的排程字段基本一致，但不包含后置查询得到的 `step_id/step_role`

## `POST /api/v1/solve/layered`

从分层目标状态和活动能力范围发起求解。该入口会先展开目标状态树和活动范围，再复用 Planner / Scheduler 主链路。

请求体核心字段：

```json
{
  "machine_id": 1,
  "current_state_id": 1,
  "target_state_node_ids": [10],
  "activity_scope_node_ids": [20, 21],
  "include_inactive": false,
  "current_state_overrides": {},
  "goal_facts": [],
  "objectives": [
    {"type": "minimize_makespan", "weight": 1.0}
  ],
  "context": {"mode": "layered"}
}
```

响应在普通 `SolveResponse` 基础上增加：

- `layered.preflight_health`：求解前健康检查摘要。
- `diagnostics.layered_health`：完整健康检查结果。
- `diagnostics.layered_expansion`：目标事实、候选活动和 effective rule 展开结果。
- `layered.activity_summary` / `layered.state_summary`：兼容旧前端的平铺解释。
- `layered.activity_tree` / `layered.state_tree`：层级结果树。
- `layered.activity_selection`：候选活动 selected / skipped 解释。

TICKET-036 后，状态目标递归展开到活跃无子节点状态；原子活动通过 `atomic_activity_id` 表达真实身份，兼容字段 `activity_node_id` 可能为负数合成 ID。

## `POST /api/v1/solve/maintenance`

从一个或多个维护意图模板发起联合维护求解。服务会合并模板目标状态、候选活动范围、观测事实覆盖和期望事实，然后调用同一套分层求解链路。

请求体核心字段：

```json
{
  "machine_id": 1,
  "current_state_id": 1,
  "maintenance_intent_template_ids": [100, 101],
  "observed_facts": [],
  "desired_facts": [],
  "objectives": [
    {"type": "minimize_makespan", "weight": 1.0}
  ]
}
```

响应沿用 `/solve/layered` 的 `layered.*` 与 `diagnostics.*` 解释字段，`context.mode` 通常为 `maintenance`。

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

## 主数据维护 API（已实现）

路由文件：`app/api/v1/master_data.py`

提供设备、状态、活动、资源、分层目标、活动能力和维护意图的 CRUD / preview 接口。

核心端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET/POST/PUT/DELETE` | `/api/v1/machine-types` 等 | 设备类型、设备、状态快照、规则、资源、特征定义 |
| `GET/POST/PUT/DELETE` | `/api/v1/machine-types/{id}/state-nodes`、`/api/v1/state-nodes/{id}` | 任意深度状态目标树 |
| `GET/POST/PUT/DELETE` | `/api/v1/machine-types/{id}/activity-nodes`、`/api/v1/activity-nodes/{id}` | 一级/二级活动包与 legacy 三级活动节点 |
| `GET/POST/PUT/DELETE` | `/api/v1/machine-types/{id}/atomic-activities`、`/api/v1/atomic-activities/{id}` | 可复用原子活动库 |
| `GET/POST/DELETE` | `/api/v1/activity-nodes/{package_id}/atomic-activity-refs`、`/api/v1/activity-package-atomic-refs/{id}` | 二级活动包到原子活动的引用 |
| `GET/POST/PUT/DELETE` | `/api/v1/activity-nodes/{id}/scope-guards`、`/api/v1/scope-guards/{id}` | Scope Guard 与公共前置条件 |
| `POST` | `/api/v1/machine-types/{id}/layered-expansion` | 展开状态目标、活动范围和 effective rules |
| `POST` | `/api/v1/machine-types/{id}/layered-health-check` | Provider/Consumer 健康检查 |
| `GET/POST/PUT/DELETE` | `/api/v1/machine-types/{id}/maintenance-intent-templates`、`/api/v1/maintenance-intent-templates/{id}` | 维护意图模板 |

`OpRuleCreate/Update` 支持 `atomic_activity_id`，也保留 `activity_node_id`。两者不能同时传；新数据优先使用 `atomic_activity_id`。

详细接口格式请查阅 Swagger UI (`/docs`) 或直接阅读 `master_data.py` 源码。
---

## 业务场景导入 API（已实现）

业务场景导入包用于支撑真实端到端测试数据装载。TICKET-036 后，模板同时支持分层状态目标、活动包、原子活动、活动包引用、维护意图和导入后健康检查。

### `POST /api/v1/imports/scenario`

请求类型：`multipart/form-data`

字段：

- `file`：`.xlsx` 场景文件
- `mode`：固定为 `scenario_upsert`
- `dry_run`：`true | false`

语义：

- `dry_run=true` 只解析和校验，不写数据库。
- `dry_run=false` 使用 strict upsert 单事务导入，任意错误整批回滚。
- 导入范围覆盖 feature catalog、machine type、machine、state feature defs、resources、rules、states、solve cases，以及可选的 layered/maintenance sheets。

响应结构：

```json
{
  "status": "validated",
  "summary": {
    "scenario_code": "AFA_E2E_001",
    "dry_run": true,
    "error_count": 0,
    "rules_total": 120,
    "resources_total": 18,
    "states_total": 2,
    "activity_nodes_total": 3,
    "atomic_activities_total": 2,
    "activity_package_atomic_refs_total": 2,
    "state_nodes_total": 4,
    "maintenance_intents_total": 1,
    "layered_health_checks_total": 1,
    "solve_cases_total": 1
  },
  "preview": {
    "rules": {"create": 100, "update": 20},
    "resources": {"create": 18, "update": 0}
  },
  "solve_cases": [
    {
      "case_code": "AFA_FULL_FLOW",
      "machine_code": "AFA-001",
      "current_state_code": "START",
      "target_state_code": "TARGET"
    }
  ],
  "maintenance_intent_templates": [],
  "post_import_health_checks": [],
  "errors": []
}
```

错误项：

```json
{
  "sheet": "rules",
  "row": 12,
  "field": "effects",
  "message": "Unknown feature_key: wing_joined"
}
```

### `GET /api/v1/imports/scenario-template`

返回带中文 `instructions` sheet 的 `.xlsx` 模板。

# DB 模块协议

路径：`app/db/`

DB 层提供：

- SQLAlchemy ORM 模型
- AsyncSession 会话工厂
- Pydantic Schema
- 与 Planner、Scheduler、API 共享的数据契约

## 当前表结构

当前 ORM 共 14 张表：

### 机台与状态

1. `machine_type`
2. `machine`
3. `state_feature_def`
4. `machine_state`
5. `machine_state_feature`

### 工序规则

6. `op_rule`
7. `op_rule_precond`
8. `op_rule_effect`
9. `op_rule_resource_req`

### 资源

10. `resource`

### 求解与结果

11. `solve_request`
12. `candidate_plan`
13. `candidate_plan_step`
14. `schedule_result`

说明：代码注释里仍写“13 tables”，但按当前 ORM 实际上是 14 张表。

## 共享表契约

### `solve_request`

由 API 写入，供查询接口和结果链路使用。

关键字段：

- `machine_id`
- `current_state_id`
- `target_state_id`
- `objective`
- `status`
- `overrides`
- `created_at`
- `solved_at`

注意：

- ORM 默认值是 `pending`
- 但当前 API 创建记录时直接写入 `status="running"`
- 所以实际运行中常见状态流转为：`running -> done/failed`

### `candidate_plan`

由 Planner 写入。

关键字段：

- `solve_request_id`
- `total_steps`
- `search_method`

当前 `search_method` 固定为 `state_inference`。

### `candidate_plan_step`

由 Planner 写入，供 Scheduler 读取。

关键字段：

- `candidate_plan_id`
- `step_order`
- `op_rule_id`
- `predecessor_ids`

`predecessor_ids` 当前使用 PostgreSQL `INTEGER[]`，表示前驱步骤号数组。

### `schedule_result`

由 Scheduler 写入，供 API 查询。

关键字段：

- `solve_request_id`
- `candidate_plan_id`
- `makespan`
- `solver_status`
- `tasks`
- `created_at`

其中 `tasks` 为 JSONB，保存完整任务详情。

## 当前 Schema 现状

`app/db/schemas.py` 中定义了大量通用 Schema，但当前 API 路由并没有全面使用这些响应模型作为 `response_model`。

已实现接口实际更接近“手写 dict 响应”，因此要区分：

- Schema 定义的理想结构
- 路由函数实际返回结构

例如：

- `SolveResponse` 存在，但 `POST /api/v1/solve` 未显式声明 `response_model`
- `ErrorResponse` 存在，但 `422/404/500` 实际由全局异常处理器返回 dict

## 数据类型契约

| 类型 | 用途 |
|------|------|
| `String(64)` | 编码、特征键、资源类型 |
| `String(128)` | 名称、标签、位置 |
| `String(256)` | 特征值、effect 新值 |
| `Integer` | 时长、开始/结束时间、数量 |
| `DateTime(timezone=True)` | 创建时间、求解完成时间 |
| `JSONB` | `allowed_values`、`meta`、`overrides`、`tasks` |
| `ARRAY(Integer)` | `predecessor_ids` |

## 会话契约

`get_db_session()` 提供异步数据库会话，供 FastAPI 依赖注入使用。

约束：

- 每次请求使用一个会话
- 写操作需要显式 `commit()`
- 当前代码中 Planner 与 Scheduler 的持久化函数内部会自行 `commit()`

这意味着 API 编排层和下游模块共享同一个 session，但提交边界在多个函数内部。

## 面向前端数据维护的映射建议

为支持用户从前端维护求解数据，建议继续复用当前表结构，不新增一套前端专用配置表。

### 前端业务对象与数据库映射

设备：

- `machine_type`
- `machine`
- `state_feature_def`

状态：

- `machine_state`
- `machine_state_feature`

活动：

- `op_rule`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`

资源：

- `resource`

### 推荐原则

- 数据维护页面展示业务对象，不展示底层拆表
- API 在服务端负责把聚合请求拆分写入多张表
- Planner 和 Scheduler 继续直接读取当前业务表

### 为什么不建议新增中间表

如果再增加一层“前端配置表”，会引入：

- 配置表到业务表的同步逻辑
- 数据一致性问题
- 更高的维护成本

对当前项目而言，最小方案应是“前端录入 -> 现有业务表 -> 直接求解”。

### 对当前数据模型的约束提醒

现有 Scheduler 只会读取每个工序首个 `is_required=True` 的资源需求作为主资源约束，因此前端虽然可以维护多条资源需求，但在当前最小实现阶段应通过界面或文案明确：

- 当前版本按单主资源类型求解
- 更复杂的多资源联合排程不属于本轮最小重构范围

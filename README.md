# State-Driven Process Planning + Resource Optimization System

一个基于 FastAPI + PostgreSQL + OR-Tools 的两阶段求解系统：

1. `Planner` 根据当前状态和目标状态构建 RAG（Resource-Aware Graph）
2. `Scheduler` 基于 RAG 和资源约束生成最短工期排程

## 当前实现范围

- 后端 API：`app/api/v1/`
- 规划器：`app/core/planner/`
- 排程器：`app/core/scheduler/`
- 数据层：`app/db/`
- 前端静态页面：`frontend/index.html`

当前后端已实现的核心接口：

- `POST /api/v1/solve`
- `GET /api/v1/solve-requests/{request_id}`
- `GET /api/v1/machines/{machine_id}/state`
- `GET /api/v1/machines/{machine_id}/states`
- `GET /health`

## 项目结构

```text
app/
  api/v1/              FastAPI 路由
  core/planner/        状态推理与 RAG 构建
  core/scheduler/      CP-SAT 资源排程
  db/                  SQLAlchemy ORM、Schema、会话
docs/protocols/        模块协议文档
migrations/            Alembic 迁移
scripts/               数据库连接、种子数据加载等脚本
seeds/                 初始化与扩展种子数据
tests/                 unit / integration / e2e 测试
frontend/              静态前端页面
start.bat              Windows 一键启动脚本
```

## 环境准备

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

### 3. 启动 PostgreSQL

```bash
docker-compose up -d postgres
```

可选地启动 pgAdmin：

```bash
docker-compose --profile admin up -d pgadmin
```

### 4. 检查数据库连接

```bash
python scripts/test_db_connection.py
```

### 5. 执行迁移

```bash
alembic upgrade head
```

### 6. 加载种子数据

```bash
python scripts/load_seed_data.py --file seeds/001_initial_data.sql
python scripts/load_seed_data.py --file seeds/002_expanded_data.sql
```

### 7. 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问：

- Swagger UI: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`

## Windows 一键启动

仓库提供了 [`start.bat`](./start.bat)：

- 检查 Docker
- 启动 PostgreSQL
- 等待数据库就绪
- 测试数据库连接
- 执行迁移
- 加载两份种子数据
- 启动后端服务
- 打开 `frontend/index.html`

## API 示例

### 提交求解

```http
POST /api/v1/solve
Content-Type: application/json
```

```json
{
  "machine_id": 1,
  "current_state_id": 1,
  "target_state_id": 2,
  "objective": "minimize_makespan"
}
```

成功响应示例：

```json
{
  "solve_request_id": 1,
  "status": "done",
  "candidate_plan_id": 1,
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

失败响应示例：

```json
{
  "solve_request_id": 2,
  "status": "failed",
  "error_code": "NO_SOLUTION",
  "error_message": "Already at target state, no operations needed"
}
```

## 已知实现特征

- `solve_request` 在 API 中创建后直接写入为 `running`，不会先落库为 `pending`
- `POST /api/v1/solve` 的业务失败仍返回 `200 OK`，通过响应体中的 `status` 与 `error_code` 区分
- `422/404/500` 错误已被统一封装为 `{ "error_code", "error_message" }`
- Scheduler 的 `parallel_groups` 来源于排程结果的实际时间重叠检测，不是 Planner 预标记
- Scheduler 当前只使用每个工序的“首个必需资源类型”参与建模与分配

## 用户友好的最小化重构方案

目标是把系统从“依赖 seed 演示”演进为“用户可在前端维护数据并直接求解”，同时尽量不改动现有 Planner、Scheduler 和数据库核心结构。

### 设计原则

- 保留现有数据库模型、Planner 和 Scheduler
- 新增面向业务对象的主数据维护 API，而不是新增一套前端专用配置表
- 前端隐藏数据库 ID、子表和 JSON 细节，改用表单和选择器
- 先完成最小闭环，再考虑版本管理、批量导入、多资源联合排程

### 建议的前端模块

新增两个主模块：

1. `数据管理`
2. `求解`

`数据管理` 建议拆为 4 个页签：

- 设备与特征
- 状态管理
- 活动管理
- 资源管理

`求解` 模块建议流程：

- 选择设备
- 自动加载该设备可选状态
- 选择当前状态与目标状态
- 提交 `POST /api/v1/solve`
- 展示排程结果

### 建议的最小后端改造

建议新增一个薄 API 模块，例如 `app/api/v1/master_data.py`，只负责主数据维护，不改动现有 `solve` 主链路。

建议优先覆盖这些对象：

- `machine_type`
- `machine`
- `state_feature_def`
- `machine_state` + `machine_state_feature`
- `op_rule` + `op_rule_precond` + `op_rule_effect` + `op_rule_resource_req`
- `resource`

### 建议新增的最小接口

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

### 用户友好要求

前端只展示业务对象，不直接暴露以下内部结构：

- `machine_state_feature`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`
- `predecessor_ids`

接口也应优先支持聚合读写：

- 状态一次提交 `features`
- 活动一次提交 `preconditions`、`effects`、`resource_reqs`

### 必须补的最小校验

状态保存时：

- `feature_key` 必须属于对应设备类型
- 枚举型特征值必须合法

活动保存时：

- 至少包含一个 `effect`
- `preconditions` 和 `effects` 中的 `feature_key` 必须合法

求解前：

- 当前状态和目标状态不能相同
- 设备必须存在可用活动规则
- 活动引用的资源类型最好存在可用资源

### 推荐实施顺序

1. 新增主数据维护 API
2. 完成前端“数据管理”页
3. 将前端“求解”页切换到数据库动态数据
4. 最后补删除限制、校验和批量导入

## 测试

```bash
pytest -v
```

按层运行：

```bash
pytest tests/unit -v
pytest tests/integration -v
pytest tests/e2e -v
```

## 相关文档

- [`docs/protocols/README.md`](./docs/protocols/README.md)
- [`docs/protocols/api.md`](./docs/protocols/api.md)
- [`docs/protocols/planner.md`](./docs/protocols/planner.md)
- [`docs/protocols/scheduler.md`](./docs/protocols/scheduler.md)
- [`docs/protocols/db.md`](./docs/protocols/db.md)

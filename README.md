# State-Driven Process Planning + Resource Optimization System

基于 FastAPI + PostgreSQL + OR-Tools 的两阶段求解系统：Planner 构建 RAG（状态推导有向无环图），Scheduler 基于 RAG + 资源约束做 CP-SAT 最优排程。

> **AI 开发上下文**：请先阅读 [`docs/ANCHOR.md`](./docs/ANCHOR.md)、当前 [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md)，再阅读最新 `docs/TICKET_*.md`。旧 `CONTEXT` 入口已归档到 `docs/archive/cleanup_20260529/outdated_notes/`。

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

如果当前环境无法使用 Docker，也可以直接使用本地 PostgreSQL（见下方“非 Docker 启动”章节）。

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

如果你使用本地 PostgreSQL（不通过 Docker），请使用 [`start.local.bat`](./start.local.bat)：

- 不检查/启动 Docker
- 直接检查本地 PostgreSQL 连通性
- 执行迁移 + 加载种子 + 启动前后端

如果你在公司内网开发机工作，建议使用 [`start.intranet.bat`](./start.intranet.bat)：

- 不依赖 Docker
- 复用既有 PostgreSQL
- Python 依赖使用公网 `pip install`
- 前端依赖使用公司内网 npm 镜像
- 首次运行自动做 bootstrap，后续直接启动前后端

更详细的配置步骤、可修改配置项和常见问题见：[`docs/intranet-dev-config-guide.md`](./docs/intranet-dev-config-guide.md)

## 非 Docker 启动（本地 PostgreSQL）

适用于无法使用 Docker 的终端环境。

### 1. 本地 PostgreSQL 前置要求

- 已安装并启动 PostgreSQL 15+
- 已创建数据库与用户（与 `.env` 一致）
- 默认推荐：`solver / solver123 / solver_db`

### 2. 配置环境变量

```bash
copy .env.example .env
```

确认以下字段与本地 PostgreSQL 一致：

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=solver
DB_PASSWORD=solver123
DB_NAME=solver_db
```

### 3. 初始化数据库

```bash
python scripts/test_db_connection.py
alembic upgrade head
python scripts/load_seed_data.py --file seeds/001_initial_data.sql
python scripts/load_seed_data.py --file seeds/002_expanded_data.sql
python scripts/load_seed_data.py --file seeds/003_v0.2_seed_data.sql
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

新开一个终端：

```bash
cd frontend
npm run dev
```

或者在 Windows 上直接运行：

```bash
start.local.bat
```

公司内网开发机建议直接运行：

```bash
start.intranet.bat
```

该入口会在需要时先做环境准备，再启动后端与前端。

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
        "step_id": 10,
        "op_rule_id": 1,
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
        "predecessors": [],
        "not_before": null,
        "step_role": "normal"
      },
      {
        "step_order": 2,
        "step_id": 11,
        "op_rule_id": 2,
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

详见 [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md) 和 [`docs/protocols/`](./docs/protocols/README.md)。

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

- [`docs/ANCHOR.md`](./docs/ANCHOR.md) — 系统永久约束与架构原则
- [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md) — 当前版本状态账本
- `docs/TICKET_*.md` — 当前/历史任务工单
- `docs/archive/cleanup_20260529/outdated_notes/` — 已归档的旧上下文入口与过期临时说明
- [`docs/v0.2-spec.md`](./docs/v0.2-spec.md) — v0.2 开发规格书
- [`docs/protocols/`](./docs/protocols/README.md) — 模块协议文档（API / DB / Planner / Scheduler）

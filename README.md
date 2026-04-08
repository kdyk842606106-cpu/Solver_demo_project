# State-Driven Process Planning + Resource Optimization System

基于 FastAPI + PostgreSQL + OR-Tools 的两阶段求解系统：Planner 构建 RAG（状态推导有向无环图），Scheduler 基于 RAG + 资源约束做 CP-SAT 最优排程。

> **AI 开发上下文**：请先阅读 [`docs/CONTEXT.md`](./docs/CONTEXT.md)，包含完整的项目背景、代码地图和 v0.2 开发导读。

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

详见 [`docs/CONTEXT.md`](./docs/CONTEXT.md) 第七节。

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

- [`docs/CONTEXT.md`](./docs/CONTEXT.md) — AI 开发上下文入口
- [`docs/v0.2-spec.md`](./docs/v0.2-spec.md) — v0.2 开发规格书
- [`docs/protocols/`](./docs/protocols/README.md) — 模块协议文档（API / DB / Planner / Scheduler）

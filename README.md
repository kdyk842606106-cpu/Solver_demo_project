# State-Driven Process Planning + Resource Optimization System

基于 FastAPI + PostgreSQL + OR-Tools 的两阶段求解系统：Planner 构建 RAG（状态推导有向无环图），Scheduler 基于 RAG + 资源约束做 CP-SAT 最优排程。

> **AI 开发上下文**：请先阅读 [`docs/ANCHOR.md`](./docs/ANCHOR.md)、当前 [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md)，再阅读最新 `docs/TICKET_*.md`。旧 `CONTEXT` 入口已归档到 `docs/archive/cleanup_20260529/outdated_notes/`。
>
> **当前发布基线**：V0.3 RC（`v0.3.0-rc.2`）。当前实现契约以 STATE 与 [`docs/protocols/`](./docs/protocols/README.md) 为准；V0.2 规格和 gap report 仅用于历史追溯。

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
python scripts/load_seed_data.py --file seeds/003_v0.2_seed_data.sql
python scripts/load_seed_data.py --file seeds/008_aircraft_final_assembly_10000_seed.sql
```

### 7. 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问：

- Swagger UI: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`
- 前端页面: `http://localhost:8000/`。如果已经执行过 `npm run build`，后端会优先服务 `frontend/dist`；否则回退到 Vite 源码入口。

### 8. 生产构建预览

```bash
cd frontend
npm run build
npm run preview:api
```

默认会在 `http://127.0.0.1:5173` 服务 `frontend/dist`，并把 `/api/*` 代理到 `http://127.0.0.1:8000`。如果后端或前端端口被占用，可覆盖参数：

```bash
npm run preview:api -- --backend http://127.0.0.1:8012 --port 8013
```

## Windows 一键启动

仓库提供了 [`start.bat`](./start.bat)：

- 检查 Docker
- 启动 PostgreSQL
- 等待数据库就绪
- 测试数据库连接
- 执行迁移
- 加载 `001/002/003/008` 基础种子数据
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
python scripts/load_seed_data.py --file seeds/008_aircraft_final_assembly_10000_seed.sql
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

当前主线能力包括：

- 实例级 Partial Order Planner + CP-SAT Scheduler 两阶段求解。
- 多资源 `resource_reqs`、计划版本链、阻塞重排和 `step_role` diff。
- 分层/维护求解：状态目标树、活动能力范围、Scope Guard、维护意图和解释结果。
- TICKET-036 后的新模型：状态目标支持任意深度树，活跃无子节点作为原子状态；活动能力由一级/二级活动包组织，`atomic_activity` 作为可复用执行能力，旧三级 `activity_node` 保留为兼容路径。
- 业务场景 Excel 导入支持分层节点、原子活动、活动包引用、维护意图和导入后健康检查。

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

## 发布 Windows 验证机 RC

发布包由白名单脚本生成，不包含 `.env`、数据库、日志、虚拟环境、依赖缓存或历史 ZIP。发布前必须先提交前端生产构建产物，并保持 Git 工作区干净：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\package_release.ps1 -Version 0.3.0-rc.2
```

脚本默认执行后端全量测试、部署就绪检查、Chromium 回归和 Vite 生产构建，然后在 `release/` 生成 ZIP、SHA-256 和发布说明。验证机升级时先用 `pg_dump -Fc` 备份数据库，将现有 `.env` 复制到解压后的新版本目录，再运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\install_verify.ps1 -ExpectedCommit <发布提交的完整 SHA>
```

只有安装验证通过后才为同一提交创建 annotated Git Tag。RC 发布不触发 STATE/TICKET 归档或版本切换。

## 相关文档

- [`docs/ANCHOR.md`](./docs/ANCHOR.md) — 系统永久约束与架构原则
- [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md) — 当前版本状态账本
- `docs/TICKET_*.md` — 当前/历史任务工单
- `docs/archive/cleanup_20260529/outdated_notes/` — 已归档的旧上下文入口与过期临时说明
- [`docs/v0.2-spec.md`](./docs/v0.2-spec.md) — v0.2 历史开发规格书（非当前实现契约）
- [`docs/protocols/`](./docs/protocols/README.md) — 模块协议文档（API / DB / Planner / Scheduler）

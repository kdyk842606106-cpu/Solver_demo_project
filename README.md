# State-Driven Process Planning + Resource Optimization System

2026-11-09 源码快照分支同时包含运行所需的共享 `planner_experiment` 源码；从本分支启动或打包时，按 [solver/README.md](solver/README.md) 将 `PLANNER_PROJECT_PATH` / `PlannerRoot` 指向仓库内的 `solver` 目录。

Windows 完整离线部署入口为发布包中的 **`deploy.bat`**，内置前端、后端、Python、PostgreSQL 和共享求解器，并执行真实异步求解自检。源码打包与隔离部署说明见 [一键部署](docs/ONE_CLICK_DEPLOYMENT.md)。`start*.bat` 保留为已有开发环境的启动入口，不用于新机器完整部署。

默认前端已替换为 **React 联合求解工作区**：活动、活动包、资源与异步联合 CP-SAT 四页真实数据闭环。部署需迁移至 `020_planner_async_jobs` 并运行独立 worker；启动与验收说明见 [React 工作区](docs/REACT_WORKBENCH.md)。旧 Vue 页面不再作为默认入口，旧后端 API 和历史数据保留。

「多引擎求解」现已增加 **联合 CP-SAT** 和显式四引擎对比，直接联合选择活动与排程；原三引擎默认行为保留。支持边界、数据库迁移和验收结果见 [联合 CP-SAT 使用说明](docs/JOINT_CP_SAT.md)。

Planner exploration 支持四类状态关系：前置保留、转移消耗、系统自动绑定的实现效果，以及独立破坏效果。活动完成时统一生效，三引擎共享回放校验。新场景采用 [V2 契约](docs/PLANNER_SHARED_SCENARIO_V2.md)，保留 V1 输入兼容；实现与测试见 [TICKET-099](docs/TICKET_099.md) 和[验收记录](docs/validation/PLANNER_DELETE_EFFECTS_20261028.md)。

基于 FastAPI + PostgreSQL + OR-Tools 的两阶段求解系统：Planner 构建 RAG（状态推导有向无环图），Scheduler 基于 RAG + 资源约束做 CP-SAT 最优排程。

> **AI 开发上下文**：请先阅读 [`docs/ANCHOR.md`](./docs/ANCHOR.md)、当前 [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md)，再阅读最新 `docs/TICKET_*.md`。旧 `CONTEXT` 入口已归档到 `docs/archive/cleanup_20260529/outdated_notes/`。
>
> **当前发布基线**：V0.3 Beta（`v0.3.0-beta.2`）。当前实现契约以 STATE 与 [`docs/protocols/`](./docs/protocols/README.md) 为准；V0.2 规格和 gap report 仅用于历史追溯。

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

该入口会先校验当前分支提交，替换已占用 8000/5173 的旧 Solver 进程，再启动本工作树的后端与前端，避免浏览器继续显示其他工作树的页面。

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

## 发布 Windows 验证机 Beta

发布包由白名单脚本生成，包含前端构建、后端、求解器、Python、PostgreSQL 程序和离线依赖，不包含现有 `.env`、数据库、日志或历史 ZIP。正式发布要求主仓库及共享求解器工作区干净；打包在独立目录构建前端，不覆盖当前运行系统：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\package_release.ps1 -Version 0.3.1-beta.1 -PlannerRoot D:\planner -OutputDirectory D:\releases\planner-0.3.1
```

打包完成生成 ZIP、SHA-256、文件清单和版本来源信息。验收未提交改动时显式使用 `-AllowDirty`，产物会标记为工作区快照。发布前需完成相关回归测试，并在隔离环境解压 ZIP 验证。验证机无需另装 Python、Node.js 或 PostgreSQL；解压到新目录后运行：

```powershell
.\deploy.bat --api-port 8026 --db-port 55450
```

入口会初始化独立数据库、执行迁移、启动 API/worker 并完成真实异步求解与回放校验。不要复制原系统 `.env` 或指向正在运行的业务库。重复运行会先备份本安装数据库；`stop.bat` 只停止本目录实例。旧数据迁移和正式发布流程见 [一键部署说明](docs/ONE_CLICK_DEPLOYMENT.md)。正式发布验证通过后才为对应提交创建 annotated Git Tag；工作区快照不创建正式版本标签。

## 相关文档

- [`docs/ANCHOR.md`](./docs/ANCHOR.md) — 系统永久约束与架构原则
- [`docs/STATE_V0.3.md`](./docs/STATE_V0.3.md) — 当前版本状态账本
- `docs/TICKET_*.md` — 当前/历史任务工单
- `docs/archive/cleanup_20260529/outdated_notes/` — 已归档的旧上下文入口与过期临时说明
- [`docs/v0.2-spec.md`](./docs/v0.2-spec.md) — v0.2 历史开发规格书（非当前实现契约）
- [`docs/protocols/`](./docs/protocols/README.md) — 模块协议文档（API / DB / Planner / Scheduler）

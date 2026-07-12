# Phase 3: 技术选型评估笔记

> 生成时间：2026-04-25
> 评估范围：后端技术栈、前端技术栈、架构扩展性、代码质量
> 约束：仅读取分析，不修改源码

---

## 一、已选技术栈评估

### 后端技术

| 技术 | 当前版本 | 远期需求 | 适配性 | 备注 |
|------|---------|---------|--------|------|
| Python 3.11+ | 代码使用 `str \| None` 联合语法（3.10+），`asyncio.to_thread`（3.9+） | 持续支持 | ✅ | 未显式声明最低版本，但语法要求 ≥3.10 |
| FastAPI 0.109+ | `fastapi>=0.109.0` | 多机台 API、高并发 | ✅ | 原生 async 支持， lifespan 管理完善 |
| Uvicorn | `uvicorn[standard]>=0.27.0` | ASGI 服务 | ✅ | standard 包含 websockets、httptools 等优化依赖 |
| SQLAlchemy 2.0 async | `sqlalchemy[asyncio]>=2.0.25` | 大规模查询 | ✅ | 异步会话 + 显式 `expire_on_commit=False` |
| OR-Tools CP-SAT | `ortools>=9.15.6755` | 多目标优化、大规模排程 | ⚠️ | 版本较新，但多目标权重未生效 |
| PostgreSQL 15 | `postgres:15-alpine` | 规则库 500+ | ✅ | 容器化部署，含 healthcheck |
| Alembic | `alembic>=1.13.1` | 迁移管理 | ✅ | 同步引擎独立配置 |
| Pydantic v2 | `pydantic>=2.5.3` | 数据校验 | ✅ | settings 分离到 pydantic-settings |
| asyncpg / psycopg v3 | `asyncpg>=0.29.0`, `psycopg[binary]>=3.1.18` | 双模式连接 | ✅ | asyncpg 用于应用，psycopg 用于 Alembic |

### 前端技术

| 技术 | 当前版本 | 远期需求 | 适配性 | 备注 |
|------|---------|---------|--------|------|
| Vue 3 | `^3.5.13` | 复杂交互 | ✅ | Composition API，最新稳定版 |
| Element Plus | `^2.9.1` | UI 组件库 | ✅ | 适配 Vue 3 |
| ECharts | `^5.5.1` | 甘特图/可视化 | ✅ | 已用于排程结果展示 |
| Vite | `^5.4.14` | 构建工具 | ✅ | 但无代码分割/懒加载配置 |
| Axios | `^1.7.9` | HTTP 请求 | ✅ | 已引入 |

### 技术债务

1. **OR-Tools 多目标权重未生效**（高优先级）
   - `app/core/solver/objectives.py` 第 92-95 行明确注释：
     > "MVP: Only minimize_makespan is implemented. Weight field is ignored. Multi-objective weighted sum not yet implemented."
   - 当前 `ObjectiveRegistry.apply_all()` 对每个 objective 独立调用 `apply_to_model()`，但 CP-SAT 模型每次只能有一个优化目标。加权多目标需要线性组合或分层优化策略，当前架构预留了注册表但未实现权重组合逻辑。
   - **影响**：V0.3 STEP 2（多目标优化能力）被阻塞，无法交付"至少 2 类目标组合"。

2. **前端构建无代码分割配置**
   - `frontend/package.json` 仅有 `"build": "vite build"`，无 `rollupOptions.manualChunks` 或动态 `import()` 懒加载配置。
   - **影响**：随着功能增加，主包体积会持续增长，加载性能下降。

3. **异常处理 Schema 未绑定稳定枚举**
   - `main.py` 中 `generic_exception_handler` 返回 `error_code: "INTERNAL_ERROR"`，但 error_code 命名在不同文件中不一致（如 `NO_SOLUTION` vs `no_solution`）。
   - `STATE_V0.3.md` 明确列出技术债第 3 条："历史文档中仍有旧错误码命名残留，需逐步清理并与 API 协议统一。"
   - **影响**：API 错误码不稳定，前端映射表可能失效。

4. **Docker Compose 缺少应用服务定义**
   - 当前 `docker-compose.yml` 仅定义了 postgres + pgadmin，后端 FastAPI 服务和前端未容器化。
   - **影响**：生产部署仍需手动启动 Python/Node 进程，未实现一键全栈启动。

5. **SQLAlchemy async 连接池配置基本合理但有隐忧**
   - `session.py` 中 `pool_size=5, max_overflow=10`，连接超时 `connect_args={"timeout": 10}`。
   - 未配置 `pool_recycle`（连接复用超时），长期运行可能出现断连。
   - **影响**：低概率出现"连接已关闭"异常，难以复现。

6. **测试基础设施重复**
   - `STATE_V0.3.md` 已知技术债第 1 条：`tests/e2e/conftest.py` 与 `tests/conftest.py` 双引擎 + 重复 fixture，需统一。

---

## 二、架构扩展性评估

### 多机台并行求解

**当前状态：**
- `solve.py` 的 `solve()` 处理单 `machine_id`、单 `current_state_id`、单 `target_state_id`。
- FastAPI 的 `AsyncSession` 通过 `Depends(get_db_session)` 注入，每个请求有独立的会话生命周期（自动 commit/rollback/close）。
- 但 `solve()` 内部所有 Planner + Scheduler + 持久化操作在同一会话中串行完成，单次求解耗时较长会占用数据库连接。

**远期需求：** 多机台同时排程（多个 solve 请求并发）。

**评估：**
- ✅ FastAPI + Uvicorn 原生支持并发请求（async worker 模型）。
- ⚠️ `solve()` 函数本身没有内部并发（Planner 和 Scheduler 串行执行）。
- ⚠️ OR-Tools CP-SAT 的 `solver.solve()` 通过 `asyncio.to_thread()` 放到线程池执行，这释放了事件循环，但线程池大小未显式控制（默认依赖 asyncio 默认执行器）。
- ⚠️ 若多机台求解需要**跨机台资源调配**（ANCHOR.md 明确标注"不在范围内"），当前架构完全不支持。

**结论：** 单机台级别的并发求解可横向扩展（多开 Uvicorn worker），但单请求内部无并行优化。跨机台资源调配属于 V1.0+ 范畴，需重大架构变更。

### 外部系统集成（MES/ERP）

**当前状态：**
- API 设计为 RESTful CRUD + 同步求解（`POST /solve` 返回完整结果）。
- 无 webhook、无回调机制、无事件总线、无消息队列。
- `solve()` 返回的 payload 包含完整排程结果，但没有请求/响应的追踪 ID 链路。

**远期需求：** V1.0 目标包含"外部集成接口"。

**评估：**
- ⚠️ 当前 API 未预留扩展点。集成 MES/ERP 通常需要：
  - 异步任务提交 + 轮询/回调获取结果（求解可能耗时数秒至数分钟）
  - 工序执行状态的反向推送接口（MES 上报执行进度）
  - 主数据同步接口（物料、BOM、设备状态等）
- ⚠️ `docker-compose.yml` 仅包含数据库，无 Redis/RabbitMQ 等中间件预留。

**结论：** 外部集成需要在 V1.0 前引入异步任务架构（如 Celery/ARQ + Redis）和 webhook 机制，当前架构未预留。

### 实时执行追踪

**当前状态：**
- `ScheduleResult` 模型存储求解结果（计划态），无执行态追踪。
- `CandidatePlanStep` 有 `step_order`, `op_rule_id`, `predecessor_ids`, `not_before`, `step_role`，但无 `actual_start`, `actual_end`, `execution_status` 等字段。
- ANCHOR.md 明确标注"实时执行状态追踪（步骤级别）不在范围内"。

**远期需求：** 步骤级追踪。

**评估：**
- ⚠️ 数据模型未预留执行追踪字段。若未来需要追加，需迁移 `candidate_plan_step` 表，新增 `actual_start_min`, `actual_end_min`, `status`（planned/in_progress/completed/failed）等字段。
- ⚠️ 执行追踪需要新的 API 端点（如 `POST /plans/{id}/steps/{step_id}/progress`）。

**结论：** 执行追踪需要数据模型扩展 + 新 API 层，当前架构无预留字段，但扩展成本可控。

### 规则库规模化（500+ 规则）

**当前状态：**
- 规则通过 `load_rules()` 从数据库全量加载到内存（`app/core/planner/matcher.py`）。
- `find_ops_for_delta()` 遍历全部规则进行匹配。
- `build_rag()` 的 `max_ops = 50` 安全上限意味着即使规则库很大，RAG 构建也不会超过 50 个节点（但中间规则搜索仍遍历全部规则）。
- 数据库表 `op_rule` 未见索引优化（需查看迁移脚本，本次未读取）。

**远期需求：** 500+ 模板规则。

**评估：**
- ⚠️ 当前规则加载是全量 `SELECT * FROM op_rule WHERE machine_type_id = ?`，随着规则数量增长，内存占用和匹配时间线性增加。
- ⚠️ `find_ops_for_delta()` 对每条 delta 遍历全部规则筛选 candidates，时间复杂度 O(规则数 × delta数)。
- ⚠️ 数值型规划 `plan_exact_numeric_feature()` 内部也有规则遍历。
- ✅ PostgreSQL 可支撑 500+ 行数据，性能瓶颈在应用层规则匹配而非数据库。

**结论：** 500+ 规则需引入按特征键索引/缓存策略（如 `dict[feature_key, list[OpRule]]` 预分组），否则规则匹配会成为性能瓶颈。

### 多目标优化

**当前状态：**
- `build_model()` 接收 `objectives` 参数并调用 `ObjectiveRegistry.apply_all()`。
- 注册表中仅注册了 `minimize_makespan` 一个目标。
- `apply_all()` 对每个 objective 独立调用 `apply_to_model()`，无视 `weight` 字段。
- CP-SAT 原生支持多目标优化（通过 `model.minimize()` 的线性组合或分层优化）。

**远期需求：** 至少 2 类目标组合（如 minimize_makespan + minimize_resource_cost）。

**评估：**
- ⚠️ 当前实现无法交付 V0.3 STEP 2。
- ✅ OR-Tools CP-SAT 原生支持加权线性组合：`model.minimize(a*x + b*y)`。
- ✅ 注册表架构已预留扩展（新增 Objective 子类 + `@register_objective` 即可）。

**结论：** 技术栈（OR-Tools）本身支持多目标，但应用层未实现权重组合逻辑。属于"框架已支持，待实现"的已知技术债。

---

## 三、代码质量扫描

### solve.py

**文件路径：** `app/api/v1/solve.py`

**函数长度：**
- `solve()` 主函数：约 185 行（从 `@router.post("/solve")` 到 `except Exception` 块），远超 100 行红线。
- `_resolve_blocked_step_for_new_plan()`：约 45 行，尚可。
- `_compute_critical_path()`：约 35 行，尚可。

**圈复杂度：**
- `solve()` 内部包含多层逻辑：
  1. machine / current_state / target_state 三层验证（各含 if/raise）
  2. blockage_constraints 解析（5 个字段提取 + strategy 映射）
  3. 主 try 块内：build_rag → save_candidate_plan → _resolve_blocked_step → solve_schedule → save_schedule_result → compute_step_role_diff
  4. 异常处理分支（ AmbiguousBlockedStepError、RAG 失败、Scheduler 失败、通用 Exception）
  5. 响应组装（state_delta、critical_path、tasks_response）
- **判定**：高复杂度。一个函数承担了验证、编排、持久化、响应组装的全部职责。

**职责分离：**
- ❌ 混合了业务逻辑（Planner + Scheduler 调用顺序编排）
- ❌ 混合了持久化（多次 `db.flush()`、`db.commit()`、`db.rollback()`）
- ❌ 混合了响应组装（`tasks_response` 列表推导 + `state_delta` 转换 + `critical_path` 计算）
- ❌ 混合了阻塞策略解析（ blockage_constraints 字段提取应在 Schema 层或 Service 层完成）
- 按 ANCHOR.md 四层架构，这些逻辑应下沉到 Service 层，API 层只做参数解析和响应封装。

**其他问题：**
- `solve_req` 的 `objective` 字段（单数）仍在写入，但请求已使用 `objectives`（复数）数组，存在数据冗余。
- `Exception` 捕获块中嵌套了另一个 `try/except`，用于回滚失败时的状态更新，代码异味明显。

### search.py

**文件路径：** `app/core/planner/search.py`

**函数长度：**
- `build_rag()`：约 210 行（含 docstring），超过 100 行。
- `save_candidate_plan()`：约 50 行，尚可。
- `has_cycle()`：约 35 行，尚可。
- `format_rag()` / `find_parallel_groups()`：辅助函数，长度合理。

**循环复杂度：**
- `build_rag()` 核心逻辑包含多层嵌套：
  - 外层：delta 遍历 `for feature_key, (current_val, target_val) in delta.items()`
  - 内层：数值型分支 + 候选规则筛选 + `check_preconditions()`
  - 再外层：`while processed_idx < len(needed_ops) and processed_idx < max_ops`
  - 内层：`for precond in op.preconditions:`
  - 内层再嵌套：`find_provider()` → `find_ops_for_delta()` → `check_preconditions()`
  - 数值型结果合并：`for numeric_result in numeric_plans:` → `for planned_step in numeric_result.steps:`
- **判定**：中高复杂度。while + for + 条件分支嵌套 3-4 层。

**硬编码：**
- `max_ops = 50` 确实存在（第 155 行注释"safety cap"）。
- **问题**：50 是一个经验值，无文档说明为什么是 50 而非 100 或 20。对于大规模规则库，50 可能成为隐性瓶颈。
- 当前节点 ID 分配 `nid = len(nodes) + 1`（1-indexed），而 numeric steps 使用 `node_id = len(nodes) + 1` 独立分配，两者混合时可能产生 ID 冲突或理解混淆。

**设计问题：**
- `needed_ops` 列表在迭代过程中被追加（`needed_ops.append(provider)`），这是一种"增长型工作列表"模式，虽能实现依赖发现，但使循环终止条件难以预测。
- `op_id_to_node_id` 使用 `op.id` 作为 key，numeric steps 则使用 `instance_to_node_id` 分配新 ID。同一 `op_rule_id` 在 enum 路径和 numeric 路径中的处理方式不同，可能导致 RAG 中同一 op_rule 的节点 ID 不唯一（numeric 步骤中同一 op_rule_id 可出现多次，但 node_id 不同）。
- **关键发现**：`find_parallel_groups()` 判断并行条件的逻辑是"相同 predecessors 集合"，这在有向无环图中只是并行的充分条件而非必要条件。例如，两个无前置依赖但不同后继的节点也会被误判为不可并行。不过 ANCHOR.md 未要求严格的并行分组，当前实现为近似分组，可接受。

### scheduler/solver.py

**文件路径：** `app/core/scheduler/solver.py`

**函数长度：**
- `solve_schedule()`：约 120 行，略超 100 行红线。
- `_assign_resources()`：约 40 行，合理。
- `_detect_actual_parallel()`：约 20 行，合理。
- `save_schedule_result()`：约 45 行，合理。

**资源分配逻辑复杂度：**
- `_assign_resources()` 使用贪心策略：对每个任务，遍历资源池，找到第一个在时间区间不冲突的资源。
- **问题**：贪心策略不保证全局最优。例如，任务 A（需要 TECH-01）和任务 B（也需要 TECH-01）若 A 先被分配，B 可能被分配到次优资源或无法分配。
- **问题**：若资源池中没有空闲资源，任务 `resources` 留空（degraded mode），但无警告或错误码告知调用方。这在 `_assign_resources()` 注释中有说明："If no resource found in pool, leave empty (degraded mode)"。

**错误处理完整性：**
- ✅ `solve_schedule()` 覆盖了 `OPTIMAL`、`FEASIBLE`、`INFEASIBLE`、其他状态（如 `MODEL_INVALID`）。
- ✅ 对 `rag_data is None` 和 "has no steps" 的前置校验完整。
- ⚠️ `_assign_resources()` 的降级模式（空 resources）没有向上层传播警告信息。
- ⚠️ `solve()` 在 `sched_result.status not in ("optimal", "feasible")` 时返回错误，但未处理 "UNKNOWN"、"MODEL_INVALID" 等具体状态。

**其他问题：**
- `_detect_actual_parallel()` 使用 `combinations(tasks, 2)` 两两比较时间区间重叠，时间复杂度 O(n²)。任务数较多时（如 100+）性能会下降，但当前 `max_ops=50` 限制了规模。

### 测试覆盖

**目录结构：**
```
tests/
├── conftest.py              # 共享 fixture
├── unit/                    # 10 个文件，61.71 KB
│   ├── test_effects.py
│   ├── test_models.py
│   ├── test_numeric_planner.py    ← V0.3 新增
│   ├── test_objectives.py
│   ├── test_operators.py
│   ├── test_planner.py
│   ├── test_rule_evaluator.py
│   ├── test_schemas.py
│   └── test_step_role.py
├── integration/             # 6 个文件，127.85 KB
│   ├── test_blockage_strategies.py  ← 最大文件 40.23 KB
│   ├── test_master_data_api.py
│   ├── test_planner_integration.py
│   ├── test_pump_body_seed.py
│   └── test_step3_api.py
└── e2e/                     # 3 个测试文件 + conftest.py
    ├── conftest.py          # 15.83 KB，与根目录 conftest.py 重复（已知技术债）
    ├── test_numeric_planning.py
    ├── test_parallel.py
    └── test_serial.py
```

**覆盖评估：**
- **unit : integration : e2e 比例** ≈ 10 : 6 : 3（按文件数），偏重于单元测试和集成测试，E2E 较薄。
- **是否有覆盖率报告？** 无。`requirements.txt` 中没有 `pytest-cov`，项目中无 `.coveragerc` 或覆盖率 CI 配置（本次未找到）。
- **关键模块覆盖：**
  - ✅ `numeric.py` 有 `test_numeric_planner.py`（V0.3 新增）
  - ✅ `step_role.py` 有 `test_step_role.py`
  - ✅ `blockage` 策略有 `test_blockage_strategies.py`（最大文件，覆盖 A/B/AB + numeric 交叉）
  - ✅ `objectives.py` 有 `test_objectives.py`（但当前只有一个目标，测试也较薄）
  - ⚠️ `scheduler/solver.py`（CP-SAT 求解 + 资源分配）未见独立的单元测试文件，主要依赖 integration/e2e 测试间接覆盖。
  - ⚠️ `solve.py`（API 层）的单元测试未见，依赖 `test_step3_api.py` 和 e2e 测试。
- **STATE_V0.3.md 列出的测试约束：**
  - 约束 14："领域层必须有单元测试" — 已满足。
  - 约束 15："验收测试对应 STATE 文档中定义的验收场景" — 部分满足，但 V0.3 四项主线（可解释性、多目标、工序组、A*）均未开始，对应的验收测试也无从谈起。

---

## 四、关键发现

- **发现1：多目标优化能力存在架构性缺口。** OR-Tools CP-SAT 原生支持多目标，但 `ObjectiveRegistry.apply_all()` 仅对每个目标独立调用 `apply_to_model()`，且完全忽略 `weight` 字段。CP-SAT 模型只能有一个优化目标，因此当前架构无法直接支持"2 类目标组合"。需要重新设计 `apply_all()` 为加权线性组合（`model.minimize(Σ weight_i * target_i)`）或分层优化策略。这是 V0.3 STEP 2 的核心阻塞项。

- **发现2：solve.py 函数长度 185 行，严重违反单一职责原则，是 API 层的主要技术债务。** `solve()` 混合了输入验证、阻塞策略解析、Planner 调用、Scheduler 调用、多次持久化、响应组装、异常处理等 7 类职责。按 ANCHOR.md 四层架构，这些逻辑应下沉到 Service 层。当前结构使得单元测试难以编写（需要 mock 太多依赖），也是 `tests/unit/` 中无 `test_solve_api.py` 的原因。

- **发现3：max_ops = 50 是隐性瓶颈，且与规则库规模化目标冲突。** 当规则库增长到 500+ 时，`find_ops_for_delta()` 遍历全量规则的时间开销增加，而 `max_ops=50` 又限制了 RAG 节点数量。对于复杂泵体集成场景（多级嵌套工序 + 数值型多步推进），50 个节点可能不足。建议将其改为可配置参数（如通过 `SolveRequest.constraints` 传入），而非硬编码。

- **发现4：外部系统集成（MES/ERP）在 V1.0 需要重大架构增补。** 当前 `docker-compose.yml` 仅含数据库，无消息队列或任务队列。API 为同步阻塞式设计（`POST /solve` 等待 Planner + Scheduler 完成），无异步任务提交/回调机制。若 V1.0 需要对接 MES，必须引入异步架构（如 Celery/ARQ + Redis）和 webhook 推送能力。

- **发现5：数值型规划与 enum 规划的节点 ID 分配机制存在潜在冲突。** `search.py` 中 `op_id_to_node_id` 以 `op.id` 为 key（1 个 OpRule 对应 1 个 node），而 numeric steps 使用 `instance_to_node_id` 以 `instance_id` 为 key（1 个 OpRule 可对应多个 node）。两者混合时，`has_cycle()` 和 `format_rag()` 需要确保所有 node.id 唯一。当前实现中 numeric 步骤在 `needed_ops` 处理完成后追加节点， numeric 节点使用 `len(nodes) + 1` 分配 ID，与 enum 节点的 `op_id_to_node_id` 值域不重叠（因为 enum 节点最大 ID = 初始 needed_ops 数量 ≤ max_ops = 50），因此当前无冲突。但若未来 `max_ops` 放开或 enum 节点数超过 50，需确保 ID 分配策略一致。

- **发现6：前端构建工具链缺少生产优化配置。** Vite 5 默认支持代码分割，但 `package.json` 中未配置 `manualChunks`，也未引入动态 `import()` 懒加载。随着 Element Plus、ECharts 等库的使用，主包体积会逐渐膨胀，建议增加 vendor 代码分割配置。

---

## 五、自审查清单

- [x] 所有技术选型已评估（后端 9 项 + 前端 5 项）
- [x] 远期需求适配性已分析（并发、集成、追踪、规则库、多目标 5 个维度）
- [x] 架构扩展性 5 个维度已检查
- [x] 代码质量 4 个文件已扫描（solve.py、search.py、scheduler/solver.py、tests/）
- [x] 技术债务已识别（6 项）
- [x] 关键发现已记录（6 条）

---

## 六、遗漏与疑问

1. **未读取迁移脚本**：未检查 `alembic/versions/` 中的索引设计，无法确认 `op_rule(machine_type_id)`、`candidate_plan_step(candidate_plan_id)` 等关键查询路径是否有索引。
2. **未读取 `app/core/planner/matcher.py`**：`find_ops_for_delta()` 和 `find_provider()` 的具体实现未完全展开，对规则匹配的性能瓶颈评估基于推测。
3. **未读取 `app/core/planner/numeric.py` 完整内容**：只读取了接口和导入关系，未深入评估数值型规划算法的复杂度。
4. **OR-Tools 最新版本**：当前锁定 `>=9.15.6755`，需要确认是否有更新的 patch 版本包含已知 bug 修复。建议通过 `pip index versions ortools` 检查。
5. **数据库连接池调优参数**：`pool_recycle` 未配置，长期运行稳定性未验证。

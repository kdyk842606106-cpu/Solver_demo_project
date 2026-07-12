# ~~AI 开发上下文~~ (已废弃)

> **本文档已废弃** (2026-04-10)
>
> 本文档的内容已拆分到三层文档体系中：
> - **`docs/ANCHOR.md`** — 系统永久性约定（设计原则、架构、约束）
> - **`docs/STATE_V0.3.md`** — 当前版本快照（已完成、待做、状态）
> - **`docs/TICKET_*.md`** — 当前/历史任务工单，优先阅读编号最高且未归档的工单
>
> 请使用 `ANCHOR + STATE + 最新 TICKET` 作为 AI 开发入口。
> 本文件保留仅作历史参考，不再更新。

---

以下为废弃前的原始内容（仅供参考）：

---

> ~~**本文档用途**：AI Agent 的 **唯一入口文件**。~~
>
> ~~**阅读顺序**：本文 → [`v0.2-spec.md`](./v0.2-spec.md)（当前开发任务）→ 按需查阅 `protocols/`（模块细节）。~~

---

## 一、项目概要

单机台两阶段求解系统：用户给定当前状态 + 目标状态 → 系统自动规划工序路径并排程。

| 层 | 职责 | 核心技术 |
|----|------|----------|
| **Planner** | 状态差分析 → precond/effect 推导 → 生成 RAG（有向无环图） | 自实现算法 |
| **Scheduler** | 解析 RAG → 叠加资源约束 → CP-SAT 最优排程 | OR-Tools CP-SAT |

**核心创新**：依赖关系从 precondition/effect 链**自动推导**，并行分支**自然涌现**，不依赖显式依赖表。

---

## 二、技术栈

Python 3.11+ · FastAPI · PostgreSQL 15+ · SQLAlchemy 2.0 (async) · OR-Tools CP-SAT · Alembic · Docker Compose

---

## 三、项目目录

```
app/
  api/v1/
    solve.py              # POST /api/v1/solve — 求解主入口
    state.py              # GET  机台状态查询
    master_data.py        # CRUD 主数据维护（设备/状态/活动/资源）
  core/
    planner/
      state.py            # 状态加载 + delta 计算
      matcher.py          # 工序匹配（正向/反向）
      executor.py         # effect 应用 + precond 辅助
      search.py           # build_rag() + save_candidate_plan()
    scheduler/
      loader.py           # RAG 加载 + 资源加载
      model.py            # CP-SAT 约束建模
      solver.py           # 求解 + 资源分配 + 并行检测 + 持久化
  db/
    models.py             # SQLAlchemy ORM（14 张表）
    schemas.py            # Pydantic Schema
    session.py            # AsyncSession 工厂
    config.py             # 数据库配置
  main.py                 # FastAPI 入口

docs/
  CONTEXT.md              # ← 你在这里
  v0.2-spec.md            # v0.2 开发规格书
  protocols/              # 模块协议文档（实现细节）
    api.md / db.md / planner.md / scheduler.md
  archive/                # 已完成版本的历史文档
    v0.1-introduction.md / v0.1-roadmap.md

migrations/               # Alembic 迁移
seeds/                    # SQL 种子数据
tests/                    # unit / integration / e2e
frontend/                 # 静态前端（index.html）
```

---

## 四、数据模型（14 张表）

```
机台与状态（5）                工序规则（4）
┌─────────────┐              ┌────────────┐
│machine_type │◄─────────────│  op_rule    │
│  machine    │              │  op_rule_precond
│  state_     │              │  op_rule_effect
│  feature_def│              │  op_rule_resource_req
│  machine_   │              └────────────┘
│  state      │
│  machine_   │              资源（1）
│  state_     │              ┌────────────┐
│  feature    │              │  resource   │
└─────────────┘              └────────────┘

求解与结果（4）
┌───────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  solve_request    │───►│  candidate_plan  │───►│ schedule_result │
│                   │    │  candidate_plan_ │    │                 │
│                   │    │  step            │    │                 │
└───────────────────┘    └──────────────────┘    └─────────────────┘
```

**关键字段**：
- `candidate_plan_step.predecessor_ids` — `INTEGER[]`，Planner 推导出的依赖边
- `schedule_result.tasks` — `JSONB`，完整排程任务列表
- `op_rule_precond/effect` — precondition/effect 链的数据基础

---

## 五、已实现 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/solve` | 同步求解，返回完整排程结果 |
| `GET` | `/api/v1/solve-requests/{id}` | 查询求解请求及结果 |
| `GET` | `/api/v1/machines/{id}/state` | 查询机台当前状态 |
| `GET` | `/api/v1/machines/{id}/states` | 列出机台全部可选状态 |
| `GET` | `/health` | 健康检查 |
| — | `/api/v1/machine-types`, `/machines`, `/states`, `/op-rules`, `/resources` 等 | 主数据 CRUD（master_data.py） |

---

## 六、求解链路（数据流）

```
POST /api/v1/solve
  │
  ├── 校验 machine / state / objective
  ├── 创建 solve_request（status=running）
  │
  ├── Planner.build_rag(current_state_id, target_state_id)
  │     ├── load_state() → dict[str,str]
  │     ├── compute_state_delta()
  │     ├── 为每个 delta 匹配最优工序（effect→目标值, 多候选选最短耗时）
  │     ├── 分析 precond → 递归补齐依赖 + 中间工序
  │     ├── 环检测
  │     └── → PlanResult(rag=RAG)
  │
  ├── Planner.save_candidate_plan() → candidate_plan + candidate_plan_step
  │
  ├── Scheduler.solve_schedule(candidate_plan_id)
  │     ├── loader.load_rag() → steps + edges + 资源需求
  │     ├── model.build_model() → CP-SAT（precedence + cumulative 约束）
  │     ├── solver.Solve() → 最优排程
  │     ├── _assign_resources() → 绑定具体资源实例
  │     └── _detect_actual_parallel() → 并行组
  │
  ├── Scheduler.save_schedule_result()
  └── → SolveResponse
```

---

## 七、已知实现特征（Gotchas）

1. `solve_request` 创建时直接写 `status=running`，不经过 `pending`
2. `POST /solve` 业务失败仍返回 HTTP 200，通过 `status=failed` + `error_code` 区分
3. `parallel_groups` 来自 Scheduler 求解后时间重叠检测，非 Planner 预标记
4. Scheduler 只用每个工序的**首个** `is_required=True` 资源需求建模
5. 资源找不到时 Scheduler 回退容量为 1（容错，非业务语义）
6. `422/404/500` 已统一封装为 `{ "error_code", "error_message" }`
7. Planner 含 `max_ops=50` 硬编码安全上限

---

## 八、v0.1 基线总结

v0.1（tag: `v0.1`）已完成全部 5 个里程碑：

- ✅ 数据层 14 张表 + Alembic 迁移 + 种子数据
- ✅ Planner：状态推导 RAG 构建（delta 匹配 + 依赖补齐 + 环检测）
- ✅ Scheduler：CP-SAT 排程（precedence + 资源约束 + 并行检测）
- ✅ 端到端联调：`POST /solve` 全链路跑通
- ✅ 规则扩展验证：纯 SQL 插入即可生效
- ✅ 主数据维护 API + 前端数据管理页

---

## 九、v0.2 开发方向

**模块名称**：阻塞处理与约束扩展

**详细规格书**：[`docs/v0.2-spec.md`](./v0.2-spec.md)

**核心概念速览**：

| 策略 | 含义 | 系统行为 |
|------|------|----------|
| **策略 A** — 活动提拉 | 阻塞步骤在 T 之前不可执行 | `not_before` 约束注入 CP-SAT，其他步骤提拉填入窗口 |
| **策略 B** — 维修序列 | 插入预定义维修工序 | `blockage_reason` 写入状态特征，RAG 自动匹配维修序列 |
| **A+B** | 同时应用 | 两套约束并存，CP-SAT 仲裁资源冲突 |

**开发原则**：最小增量，复用 v0.1 求解链路，不修改已有表结构，只新增字段和表。

---

## 十、深入阅读指引

| 需要了解 | 去看 |
|----------|------|
| v0.2 完整规格（数据模型扩展、求解链路扩展、前端设计、开发顺序） | [`docs/v0.2-spec.md`](./v0.2-spec.md) |
| API 接口契约、请求/响应格式、错误码 | [`docs/protocols/api.md`](./protocols/api.md) |
| ORM 模型、Schema、会话契约 | [`docs/protocols/db.md`](./protocols/db.md) |
| Planner 算法细节、函数签名、失败语义 | [`docs/protocols/planner.md`](./protocols/planner.md) |
| Scheduler 求解流程、CP-SAT 建模、资源分配策略 | [`docs/protocols/scheduler.md`](./protocols/scheduler.md) |
| 项目启动、环境配置、测试运行 | [`README.md`](../README.md) |
| v0.1 原始设计文档（历史参考） | [`docs/archive/v0.1-introduction.md`](./archive/v0.1-introduction.md) |

---

## 十一、开发约定

- **不破坏 v0.1 链路**：阻塞约束参数为空时，行为与 v0.1 完全一致
- **策略 B 走已有 precond/effect 推导链路**，不单独开发匹配逻辑
- **step_role 标注在求解完成后 diff 计算**，不在求解过程中实时标注
- **not_before 单位统一为分钟**，与 `duration_min` 一致
- **blockage_reason 合法值由 op_rule_precond 表决定**，前端动态读取不硬编码

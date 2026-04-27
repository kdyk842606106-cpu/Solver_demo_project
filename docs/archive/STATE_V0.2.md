# CURRENT STATE: V0.2

> 生成时间：2026-04-10
> 前置阅读：必须先读 ANCHOR.md

---

## 本版本目标

实现阻塞处理与动态重排（策略A/B/AB），同时完成架构升级为 V0.3+ 打基础。

---

## V0.1 已完成基线（可直接使用）

### 数据库表（14 张，已有 Alembic 迁移 + 种子数据）

```
机台与状态:
  machine_type, machine, machine_state, machine_state_feature, feature_definition(已启用)

工序规则:
  op_rule (id, code, name, duration_min, description)
  op_rule_precond (id, op_rule_id, feature_key, feature_value)
  op_rule_effect (id, op_rule_id, feature_key, new_value)
  op_rule_resource_req (id, op_rule_id, resource_id, quantity, is_required)

资源:
  resource (id, code, name, resource_type, capacity)

求解与结果:
  solve_request (id, machine_id, current_state_id, target_state_id, objective, status, error_code)
  candidate_plan (id, solve_request_id, total_steps)
  candidate_plan_step (id, candidate_plan_id, op_rule_id, step_order, predecessor_ids)
  schedule_result (id, candidate_plan_id, makespan, tasks JSONB)
```

### 后端代码文件（实际路径）

```
app/
  main.py                        # FastAPI 入口，CORS，异常处理，路由注册
  api/v1/
    solve.py                     # POST /api/v1/solve
    state.py                     # GET 机台状态查询
    master_data.py               # CRUD 主数据维护
  core/
    planner/
      state.py                   # load_state() + compute_state_delta() + is_goal()
      matcher.py                 # load_rules() + check_preconditions() + find_ops_for_delta() + find_provider()
      executor.py                # apply_effects() + effects_satisfy_precondition()
      search.py                  # build_rag() + save_candidate_plan()
    scheduler/
      loader.py                  # load_rag() + load_resources()
      model.py                   # build_model() — CP-SAT 约束建模
      solver.py                  # solve_schedule() + save_schedule_result() + _assign_resources() + _detect_actual_parallel()
  db/
    models.py                    # SQLAlchemy ORM（14 张表）
    schemas.py                   # Pydantic Schema
    session.py                   # AsyncSession 工厂
    config.py                    # 数据库配置
```

### 已实现 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/solve | 同步求解，返回完整排程结果 |
| GET | /api/v1/solve-requests/{id} | 查询求解请求及结果 |
| GET | /api/v1/machines/{id}/state | 查询机台当前状态 |
| GET | /api/v1/machines/{id}/states | 列出机台全部可选状态 |
| GET | /health | 健康检查 |
| — | /api/v1/machine-types, /machines, /states, /op-rules, /resources | 主数据 CRUD |

### 求解链路（数据流）

```
POST /api/v1/solve
  ├── 校验 machine/state/objective → 创建 solve_request(status=running)
  ├── Planner.build_rag(current_state_id, target_state_id)
  │     load_state() → compute_state_delta() → 匹配工序 → 依赖补齐 → 环检测
  ├── Planner.save_candidate_plan() → candidate_plan + steps
  ├── Scheduler.solve_schedule(plan_id)
  │     load_rag() → build_model(CP-SAT) → Solve() → _assign_resources() → _detect_actual_parallel()
  └── save_schedule_result() → SolveResponse
```

### V0.1 已知实现特征（Gotchas）

1. solve_request 创建时直接写 status=running，不经过 pending
2. POST /solve 业务失败仍返回 HTTP 200，通过 status=failed + error_code 区分
3. parallel_groups 来自 Scheduler 求解后时间重叠检测，非 Planner 预标记
4. Scheduler 只用每个工序的首个 is_required=True 资源需求建模
5. 资源找不到时 Scheduler 回退容量为 1（容错，非业务语义）
6. 422/404/500 已统一封装为 { error_code, error_message }
7. Planner 含 max_ops=50 硬编码安全上限

### V0.1 技术债（本版本必须还清）

- op_rule_precond 只支持等值匹配，没有 operator 字段
- op_rule_effect 只支持 set，没有 effect_type 字段
- RAGBuilder 没有循环检测和深度限制
- Scheduler objectives 是单个枚举值，不是数组
- precond 匹配逻辑散落在 matcher.py，未抽象为 RuleEvaluator

---

## 本版本数据模型变更（V0.1 → V0.2）

### 新增表

```sql
-- feature_definition: 特征类型系统
feature_definition (
  feature_key PK, value_type, allowed_values JSONB, unit, description
)

-- blockage_event: 阻塞事件记录
blockage_event (
  id, plan_id FK, blocked_step_id FK, strategy VARCHAR(8),
  not_before_offset INTEGER, blockage_reason VARCHAR(64),
  note TEXT, created_at, created_by
)
```

### 扩展字段

```sql
op_rule_precond:
  + operator        VARCHAR(16) DEFAULT 'eq'
  + value_list      JSONB

op_rule_effect:
  + effect_type     VARCHAR(32) DEFAULT 'set'
  + delta_value     NUMERIC

op_rule:
  + is_repair       BOOLEAN DEFAULT FALSE
  + valid_from      TIMESTAMP
  + valid_to        TIMESTAMP

solve_request:
  + objectives      JSONB DEFAULT '[{"type":"minimize_makespan","weight":1.0}]'
  + constraints     JSONB DEFAULT '{}'
  + parent_plan_id  INTEGER FK → candidate_plan

candidate_plan:
  + version         INTEGER DEFAULT 1
  + parent_plan_id  INTEGER FK → candidate_plan(self)
  + replan_reason   VARCHAR(64)  -- initial/blockage_strategy_a/b/ab
  + status          VARCHAR(32) DEFAULT 'draft'

candidate_plan_step:
  + not_before      INTEGER  -- 分钟，NULL=无约束
  + step_role       VARCHAR(32) DEFAULT 'normal'  -- normal/repair/pulled_forward/delayed
```

---

## 本版本新增领域层文件（计划）

```
app/core/solver/          ← 新增目录（或在 core/ 下扩展）
  operators.py            # OperatorRegistry + 7 个 Operator 类
  effects.py              # EffectRegistry + 3 个 Effect 类
  rule_evaluator.py       # RuleEvaluator（策略模式统一入口）
  objectives.py           # ObjectiveRegistry + MinimizeMakespanObjective
```

---

## 本版本 API 扩展

### POST /api/v1/solve 请求体新增

```json
{
  "objectives": [{"type": "minimize_makespan", "weight": 1.0}],
  "constraints": {"enable_not_before": false},
  "blockage_constraints": {
    "blocked_step_id": "int",
    "strategy": "A|B|AB",
    "strategy_a": {"not_before_offset": "int"},
    "strategy_b": {"blockage_reason": "string"},
    "note": "string",
    "created_by": "string"
  },
  "parent_plan_id": "int|null"
}
```

### POST /api/v1/solve 响应体新增

```json
{
  "state_delta": ["..."],
  "critical_path": ["..."],
  "parallel_groups": ["..."],
  "steps": [{"not_before": "int|null", "step_role": "string"}]
}
```

### 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| CRUD | /api/v1/features | feature_definition 管理 |
| GET | /api/v1/plans/{id}/versions | 版本链查询 |
| GET | /api/v1/plans/{id}/diff/{other_id} | 版本对比 |

---

## 任务完成状态

```
━━━━━━ STEP 1：数据模型扩展 ━━━━━━               [✅] 已完成

  ✅ 1-1  新增 feature_definition 表
  ✅ 1-2  op_rule_precond 新增 operator / value_list
  ✅ 1-3  op_rule_effect 新增 effect_type / delta_value
  ✅ 1-4  op_rule 新增 is_repair / valid_from / valid_to
  ✅ 1-5  solve_request 新增 objectives / constraints / parent_plan_id
  ✅ 1-6  candidate_plan 新增 version / parent_plan_id / replan_reason / status
  ✅ 1-7  candidate_plan_step 新增 not_before / step_role
  ✅ 1-8  新增 blockage_event 表
  ✅ 1-9  种子数据（feature_definition + OP_REPAIR 规则）

━━━━━━ STEP 2：领域层架构升级 ━━━━━━             [✅] 已完成（准出审视通过）

  ✅ 2-1  OperatorRegistry + 7 个 Operator (eq/neq/gt/gte/lt/lte/in)
  ✅ 2-2  EffectRegistry + 3 个 Effect (set/increment/decrement)
  ✅ 2-3  RuleEvaluator（统一入口，类型安全）
  ✅ 2-4  RAGBuilder 升级（RuleEvaluator 调用 + 循环检测 + 深度限制）
  ✅ 2-5  ObjectiveRegistry + MinimizeMakespanObjective
  ✅ 2-6a Scheduler not_before 约束注入
  ✅ 2-6b Scheduler objectives 数组支持（当前仅完整实现 minimize_makespan，weight 暂未参与加权求解）
  ✅ 2-7a 阻塞处理编排主流程（策略 A/B/AB）
  ✅ 2-7b step_role 计算算法

━━━━━━ TICKET-005：STEP 2 收口审计修复 ━━━━━━     [✅] 已完成

  ✅ D1  新增 test_objectives.py（7 个测试）
  ✅ D2  新增 pulled_forward / delayed 集成测试
  ✅ D3  策略 AB 集成测试 >= 2 + 强断言
  ✅ D4  step_role.py 非 repair 新增步骤标为 normal
  ✅ D5  solve.py 异常兜底 try/except
  ✅ D6  新增 solver/__init__.py
  ✅ D7  删除 objectives.py 未使用 import

━━━━━━ TICKET-006：STEP 2 准出审视修复 ━━━━━━     [✅] 已完成（190 测试全通过）

  ✅ F1  移除 17 处 pytest.skip，替换为 assert
  ✅ F2  删除重复 TestStrategyAB 类（行 316-364）
  ✅ F3  删除 search.py 死导入 effects_satisfy_precondition

━━━━━━ TICKET-003：STEP 1 补丁 + API 安全加固 ━━━━ [✅] 已完成

  ✅ 3-P1 OpRule CRUD 补全 V0.2 字段（is_repair/valid_from/valid_to + value_list/effect_type/delta_value）
  ✅ 3-P2 schemas.py 合并重复 ScheduleTaskItem + CandidatePlanStepResponse 补 op_rule_code
  ✅ 3-P3 main.py traceback 泄露安全修复（DEBUG 开关）
  ✅ 3-P4 state.py 补 state_type + 三端点添加 response_model

━━━━━━ STEP 3：API 层扩展 ━━━━━━                 [✅] 已完成（TICKET-007 + TICKET-008）

  ✅ 3-1  /api/v1/features CRUD（已在 TICKET-003 完成）
  ✅ 3-2  /api/v1/rules 升级（已在 TICKET-003 完成）
  ✅ 3-3  POST /api/v1/solve 升级（state_delta + critical_path + step_role/not_before）
  ✅ 3-3b 清理遗留 objective 单值校验
  ✅ 3-4  GET /api/v1/plans/{id}/versions
  ✅ 3-5  GET /api/v1/plans/{id}/diff/{other_id}（211 测试全通过，含 null 边界场景）

━━━━━━ STEP 4：前端重构为 Vue 3 + Element Plus + ECharts ━━━━━━  [✅] 已完成

  ✅ 4-0  Vite 工程搭建（package.json / vite.config.js / src/main.js / App.vue）
  ✅ 4-0b API 层封装（src/api/index.js + masterData.js + solve.js + utils/errorCodes.js）
  ✅ 4-1  FeatureDefinitionPage（FeatureDefPage.vue — unit/description 字段）
  ✅ 4-2  RulePage 升级（operator: gt/gte/lt/lte/in + effect_type + delta_value + is_repair）
  ✅ 4-3  StatePage 升级（value_type 联动控件：enum/boolean/number/string）
  ✅ 4-4  BlockageDialog 组件（策略A/B/AB，blockage_reason 动态读取）
  ✅ 4-5  GanttChart 升级（ECharts custom series，step_role 颜色 + 对比模式）
  ✅ 4-6  SolvePage 升级（版本历史 + state_delta + critical_path + BlockageDialog 集成）

━━━━━━ TICKET-010：Gantt 标题与任务显示增强 ━━━━━━  [✅] 已完成

  ✅ T10-1  schedule.tasks[] 稳定返回 op_rule_name
  ✅ T10-2  普通模式标题升级为「步骤编号 + 活动编码 + 活动名称」
  ✅ T10-3  对比模式标题与 tooltip 同步增强并支持字段缺失降级
  ✅ T10-4  任务明细表新增活动名称列（名称为空显示 "—"）
```

---

## 验收标准

```
场景1（策略A）：
  标记 OP_CALIBRATE 阻塞，策略A，not_before=120min
  → 新计划中 OP_CALIBRATE.start_min >= 120
  → 不依赖 OP_CALIBRATE 的步骤被提拉至 120min 前
  → parent_plan_id 正确，replan_reason = 'blockage_strategy_a'

场景2（策略B）：
  标记 OP_CALIBRATE 阻塞，策略B，blockage_reason=hardware_fault
  → 步骤中出现 OP_REPAIR_HARDWARE（step_role=repair）
  → OP_REPAIR_HARDWARE 位于 OP_CALIBRATE 之前
  → blockage_event 表写入记录

场景3（策略AB）：
  策略A + B 同时使用
  → 同时出现 repair + pulled_forward 步骤
  → OP_CALIBRATE.start_min >= not_before_offset
  → CP-SAT 正确仲裁资源竞争

场景4（循环检测）：
  故意写入循环依赖规则
  → RAGBuilder 抛出 SOLVE_CYCLE_DETECTED，不死循环

场景5（类型安全）：
  feature_definition pressure_bar value_type=number
  precond operator=gte, value=3.5, current=3.8
  → RuleEvaluator 正确 float 比较，返回 True
```

### 验收结果（已验证）

- 验证结论：✅ 已通过（2026-04-19）
- 验证依据：
  - STEP 2 准出修复：190 测试全通过
  - STEP 3 API 扩展：211 测试全通过（含 diff 空值边界）
  - TICKET-010：普通模式/对比模式/名称缺失降级均已完成回归验证

---

## 当前已知问题 / 决策悬挂

1. ~~`solver.py:115` — 同步阻塞~~ → ✅ 已修复：`solver.py:118` 使用 `asyncio.to_thread()` 包装
2. ~~`search.py:207-209` — 硬编码 `==`~~ → ✅ 已修复：现使用 `RuleEvaluator().evaluate_precondition()`
3. ~~领域层 `session.commit()`~~ → ✅ 已修复：`app/core/` 下无 `session.commit()` 调用
4. 测试基础设施：`tests/e2e/conftest.py` 与 `tests/conftest.py` 存在双引擎 + 重复 fixture，长期需统一。（非阻塞，可延后）
5. ~~`solve.py` 策略A not_before 约束不生效~~ → ✅ 已修复：`save_candidate_plan()` 创建的
   `CandidatePlanStep` 未 flush 到 DB，而 session 配置了 `autoflush=False`，导致后续
   `select(CandidatePlanStep)` 查询找不到步骤行，`not_before` 赋值被静默跳过。
   修复方法：在查找 blocked step 之前添加 `await db.flush()`（`solve.py:207`）。
   同时改进了 `test_step3_api.py` 中策略A测试，使用 `blocked_op_rule_id`（前端实际路径）
   并增加 `not_before` 值和 `start_min` 约束的强断言。

---

## 深入参考

| 需要了解 | 去看 |
|----------|------|
| V0.2 完整规格（业务语义 + 策略详解 + 前端设计） | [v0.2-spec.md](./v0.2-spec.md) |
| API 接口契约、错误格式 | [protocols/api.md](./protocols/api.md) |
| ORM 模型、Schema 契约 | [protocols/db.md](./protocols/db.md) |
| Planner 算法细节 | [protocols/planner.md](./protocols/planner.md) |
| Scheduler CP-SAT 建模 | [protocols/scheduler.md](./protocols/scheduler.md) |
| V0.1 原始设计 | [archive/v0.1-introduction.md](./archive/v0.1-introduction.md) |
| 项目启动 / 测试运行 | [../README.md](../README.md) |

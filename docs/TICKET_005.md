# TICKET-005: V0.2 STEP 2 收口 — 缺陷修复与验收达标

> 对应 STATE_V0.2.md → STEP 2（收口阶段）
> 前置依赖：TICKET-004 已完成的全部实现
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

修复 TICKET-004 代码审计中发现的 7 个缺陷，使 STEP 2 全部验收条件达标、零技术债关闭。

**不做**：不新增功能、不改 API 契约、不改数据模型、不动前端。

---

## 审计发现的缺陷清单

| # | 严重度 | 缺陷描述 | 涉及文件 |
|---|--------|----------|----------|
| D1 | 阻塞 | `test_objectives.py` 不存在，ObjectiveRegistry 零测试覆盖 | 新增 `tests/unit/test_objectives.py` |
| D2 | 阻塞 | step_role `pulled_forward` 和 `delayed` 无任何测试覆盖 | 修改 `tests/integration/test_blockage_strategies.py` |
| D3 | 阻塞 | 策略 AB 集成测试仅 1 个（要求 >=2），且断言不充分 | 修改 `tests/integration/test_blockage_strategies.py` |
| D4 | 中等 | `step_role.py:129-132` 非 repair 新增步骤也标为 repair，语义歧义 | 修改 `app/core/solver/step_role.py` |
| D5 | 中等 | `solve.py` 主流程无 try/except 兜底，异常时 SolveRequest 成僵尸 | 修改 `app/api/v1/solve.py` |
| D6 | 低 | `app/core/solver/` 缺少 `__init__.py` | 新增 `app/core/solver/__init__.py` |
| D7 | 低 | `objectives.py:11` 未使用的 `cp_model` import | 修改 `app/core/solver/objectives.py` |

---

## 子任务清单

```
[ D1 ]  新增 test_objectives.py                ──┐
[ D2 ]  新增 pulled_forward / delayed 集成测试   ──┤── 可并行
[ D3 ]  新增第 2 个 AB 测试 + 强化现有 AB 断言   ──┤
[ D6 ]  新增 solver/__init__.py                 ──┤
[ D7 ]  删除 objectives.py 未使用 import         ──┘
[ D4 ]  step_role 非 repair 新增步骤逻辑修正     ──┐── 顺序执行
[ D5 ]  solve.py 异常兜底                       ──┘    （D4 影响 D2 测试断言）
```

---

## 一、各子任务详细要求

### D1：新增 `tests/unit/test_objectives.py`

**新增文件**：`tests/unit/test_objectives.py`

**必须覆盖的测试场景**（>= 5 个测试）：

| # | 测试 | 断言 |
|---|------|------|
| 1 | `ObjectiveRegistry.get("minimize_makespan")` | 返回 `MinimizeMakespanObjective` 实例 |
| 2 | `MinimizeMakespanObjective().objective_type` | `== "minimize_makespan"` |
| 3 | `ObjectiveRegistry.get("unknown")` | 抛出 `KeyError` |
| 4 | `apply_all([{"type":"minimize_makespan","weight":1.0}], mock_model)` | 调用 `model.model.minimize(model.makespan)` |
| 5 | `apply_all([], mock_model)` | 兜底调用 minimize_makespan |

**实现约束**：
- 使用 `unittest.mock.MagicMock` 模拟 `ScheduleModel`，不依赖真实 CP-SAT
- 不需要 DB、不需要 async

---

### D2：新增 `pulled_forward` / `delayed` 集成测试

**修改文件**：`tests/integration/test_blockage_strategies.py`

**在 `TestStepRoleIntegration` 类中新增 2 个测试**：

#### test_step_role_delayed_when_not_before_applied

```
场景：
  1. 父计划：正常求解 state 1→2，保存 + 排程，记录父计划各步骤 start_min
  2. 子计划：同样 state 1→2，但给第一个步骤加 not_before=100
  3. 保存 + 排程 + compute_step_role_diff
  4. 断言：被阻塞步骤的 step_role == "delayed"
```

#### test_step_role_pulled_forward_when_not_before_applied

```
场景：
  1. 父计划：正常求解 state 1→2，给某步骤设 not_before=100，保存 + 排程
  2. 子计划：同样 state 1→2，不设 not_before（约束释放）
  3. 保存 + 排程 + compute_step_role_diff
  4. 断言：该步骤的 step_role == "pulled_forward"
```

**断言硬要求**：
- 不允许 `pytest.skip` 逃逸 infeasible — 测试数据必须保证 feasible
- 必须从 `ScheduleResult.tasks` 提取实际 start_min 做数值比较

---

### D3：强化策略 AB 集成测试

**修改文件**：`tests/integration/test_blockage_strategies.py`

#### 3a. 强化现有 `test_strategy_ab_combined` 断言

在现有测试末尾追加：
```python
# 验证 repair 步骤存在
codes = {t.op_rule_code for t in sched_result.tasks}
assert "OP_REPAIR_WORN" in codes

# 验证 not_before 约束被执行
blocked_task = next(t for t in sched_result.tasks if t.step_order == blocked_step_order)
assert blocked_task.start_min >= 20
```

#### 3b. 新增 `test_strategy_ab_step_roles`

```
场景：
  1. 父计划：正常求解 state 1→2（无 repair、无 not_before）
  2. 子计划：策略 AB，state 3→4（含 blockage_reason + include_repair + not_before）
  3. compute_step_role_diff
  4. 断言：
     - step_role 值中同时存在 "repair"
     - 被阻塞步骤 step_role 为 "delayed"（因 not_before 导致延后）
```

---

### D4：`step_role.py` 逻辑修正

**修改文件**：`app/core/solver/step_role.py`

**当前代码**（第 129-132 行）：
```python
if rule and rule.is_repair and step.op_rule_id not in parent_steps_by_rule:
    role = "repair"
elif step.op_rule_id not in parent_steps_by_rule:
    role = "repair"
```

**修正为**：
```python
if step.op_rule_id not in parent_steps_by_rule:
    # is_repair=TRUE 的新增步骤标为 repair
    # 非 repair 的新增步骤（因状态差异产生）也标为 normal
    if rule and rule.is_repair:
        role = "repair"
    else:
        role = "normal"
```

**原因**：TICKET-004 规格明确 "op_rule.is_repair=TRUE 的新步骤一定标 repair"。非 repair 的新增标准工序不应误标为 repair——它是因起点/目标状态不同而自然产生的，语义上是 normal。

---

### D5：`solve.py` 异常兜底

**修改文件**：`app/api/v1/solve.py`

**在主流程（build_rag → save_candidate_plan → solve_schedule → compute_step_role_diff）外层包裹 try/except**：

```python
try:
    # ... 现有主流程 (line 128 ~ 223) ...
except Exception as exc:
    solve_req.status = "failed"
    solve_req.error_code = "INTERNAL_ERROR"
    solve_req.solved_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "solve_request_id": solve_req.id,
        "status": "failed",
        "error_code": "INTERNAL_ERROR",
        "error_message": str(exc),
    }
```

**约束**：
- try 范围从 `build_rag()` 调用开始，到 `return` 成功响应之前
- 不吞异常——记录到 SolveRequest 后仍返回错误响应
- 不暴露 traceback 给前端（只返回 `str(exc)` 摘要）

---

### D6：新增 `app/core/solver/__init__.py`

```python
# Solver Module - Strategy Pattern Registries & Rule Evaluation
```

保持与 `planner/__init__.py` 和 `scheduler/__init__.py` 风格一致。

---

### D7：删除 `objectives.py` 未使用 import

**修改文件**：`app/core/solver/objectives.py`

删除第 11 行：
```python
from ortools.sat.python import cp_model  # 删除此行
```

---

## 二、验收门禁（全部必须满足）

### 强制门禁（任一不满足 = 不通过）

| # | 验收条件 | 验证方式 |
|---|----------|----------|
| G1 | `pytest tests/ -v` **0 失败、0 跳过** | 测试输出 |
| G2 | `tests/unit/test_objectives.py` 存在且 >= 5 个测试覆盖 ObjectiveRegistry 全部公共 API | 文件审查 |
| G3 | step_role `pulled_forward` 有 >= 1 个集成测试，断言新 start < 父 start | 测试代码 |
| G4 | step_role `delayed` 有 >= 1 个集成测试，断言新 start > 父 start | 测试代码 |
| G5 | 策略 AB 集成测试 >= 2，且断言同时验证 repair 步骤存在 + not_before 约束生效 | 测试代码 |
| G6 | `solve.py` 主流程有 try/except 兜底，异常时 SolveRequest.status 更新为 "failed" | 代码审查 |
| G7 | `step_role.py` 中非 repair 新增步骤标为 "normal"（非 "repair"） | 代码审查 |

### 质量门禁

| # | 验收条件 | 验证方式 |
|---|----------|----------|
| Q1 | `app/core/solver/__init__.py` 存在 | 文件检查 |
| Q2 | `objectives.py` 无未使用 import | 代码审查 |
| Q3 | 集成测试中不允许用 `pytest.skip` 逃逸 scheduler infeasible（测试数据必须保证 feasible） | 测试代码审查 |
| Q4 | TICKET-004 完成标准清单中所有 `[ ]` 项全部变为 `[x]` | 文档更新 |

### 测试数量硬指标

| 类别 | 最低要求 | 当前 | TICKET-005 后目标 |
|------|----------|------|-------------------|
| Operator 单元测试 | >= 7 | 34 | 34 |
| Effect 单元测试 | >= 3 | 23 | 23 |
| RuleEvaluator 单元测试 | >= 3 | 26 | 26 |
| **Objective 单元测试** | **>= 5** | **0** | **>= 5** |
| **step_role 测试（4 种角色各有覆盖）** | **4 种** | **2 种** | **4 种** |
| 策略 A 集成测试 | >= 2 | 2 | 2 |
| 策略 B 集成测试 | >= 2 | 3 | 3 |
| **策略 AB 集成测试** | **>= 2** | **1** | **>= 2** |
| 循环检测测试 | >= 1 | 2 | 2 |
| 数值比较测试 | >= 2 | 6 | 6 |

---

## 三、完成标准

- [x] D1: test_objectives.py 新增，>= 5 个测试全部通过
- [x] D2: pulled_forward + delayed 集成测试各 1 个，全部通过
- [x] D3: 策略 AB 测试 >= 2 个，断言覆盖 repair + not_before
- [x] D4: step_role.py 非 repair 新增步骤标为 normal
- [x] D5: solve.py try/except 兜底
- [x] D6: solver/__init__.py 存在
- [x] D7: objectives.py 无未使用 import
- [x] 强制门禁 G1-G7 全部通过
- [x] 质量门禁 Q1-Q4 全部通过
- [x] `pytest tests/ -v` 输出：0 失败、0 跳过
- [x] TICKET-004 完成标准全部 `[x]`
- [x] STATE_V0.2.md STEP 2 状态更新为 `[✅] 已完成`

---

## 四、本次不做（明确排除）

| 排除项 | 原因 |
|--------|------|
| 新增功能 | 本 TICKET 只做缺陷修复和测试补全 |
| API 契约变更 | STEP 3 范围 |
| 数据模型变更 | 无需求 |
| 前端改造 | STEP 4 范围 |
| 性能优化 | 不在 STEP 2 范围 |
| conftest.py 测试基础设施统一 | STATE_V0.2 悬挂问题 #4，长期任务 |

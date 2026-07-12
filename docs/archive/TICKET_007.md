# TICKET-007: V0.2 STEP 3 — API 层扩展（响应体补全 + 版本链查询）

> 对应 STATE_V0.2.md → STEP 3
> 前置依赖：TICKET-006 已完成（190 测试全通过）
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

完成 STEP 3 中尚未实现的 API 层工作：

1. **POST /api/v1/solve 响应体补全**：新增 state_delta / critical_path / step_role / not_before
2. **清理遗留 objective 单值校验**：solve.py:76 的 `if objective != "minimize_makespan"` 已无必要
3. **GET /api/v1/plans/{id}/versions**：版本链查询端点
4. **新增集成测试**：覆盖以上三项

**不做**：不改数据模型、不动前端、不实现 diff 端点（TICKET-008 范围）。

---

## 子任务清单

```
[ A ]  POST /solve 响应体补全
[ B ]  清理遗留 objective 单值校验
[ C ]  GET /plans/{id}/versions 新端点
[ D ]  新增集成测试（test_step3_api.py）
```

---

## 一、各子任务详细要求

### A：POST /solve 响应体补全

**修改文件**：`app/api/v1/solve.py`

**新增字段**：

```json
{
  "state_delta": [
    {"feature_key": "temperature", "from_value": "cold", "to_value": "hot"}
  ],
  "critical_path": ["OP_CONNECT", "OP_CALIBRATE"],
  "schedule": {
    "makespan": 120,
    "tasks": [
      {
        "step": 1, "op_code": "OP_CONNECT",
        "start": 0, "end": 30, "resource": "TECH-01",
        "predecessors": [],
        "not_before": null,
        "step_role": "normal"
      }
    ],
    "parallel_groups": [[1,2]]
  }
}
```

**实现要点**：

1. `state_delta`：在 solve.py 中调用 `load_state(current_state_id)` + `load_state(target_state_id)`，
   再调用 `compute_state_delta()`，转为 `[{feature_key, from_value, to_value}]` 格式返回。

2. `critical_path`：在 solve.py 中新增 `_compute_critical_path(tasks)` 私有函数。
   算法：在 sched_result.tasks 上，找到结束时间等于 makespan 的叶节点，
   向上回溯每条"紧绷"边（task.start_min == predecessor.end_min），
   返回按 start_min 排序的 op_rule_code 列表。

3. `not_before` / `step_role`：在 `compute_step_role_diff` 执行后，
   用 `select(CandidatePlanStep)` 查询当前 plan 的所有步骤，
   建立 `op_rule_id → {not_before, step_role}` 映射，
   在构建 tasks_response 时合并。

### B：清理遗留 objective 单值校验

**修改文件**：`app/api/v1/solve.py`

删除以下代码段（约 76-80 行）：
```python
if request.objective != "minimize_makespan":
    raise HTTPException(
        status_code=422,
        detail=f"Unsupported objective: {request.objective}. MVP only supports 'minimize_makespan'",
    )
```

此校验在 V0.1 作为 MVP 占位符，V0.2 已支持 `objectives` 数组，无需再限制。

### C：GET /api/v1/plans/{id}/versions

**新建文件**：`app/api/v1/plans.py`
**注册路由**：`app/main.py` 中注册 `plans.router`

**端点规范**：

```
GET /api/v1/plans/{plan_id}/versions
```

返回从 plan_id 所在的版本链（向上追溯到 parent_plan_id = NULL 的根计划）：

```json
[
  {
    "id": 1, "version": 1, "replan_reason": "initial",
    "parent_plan_id": null, "status": "draft",
    "total_steps": 4, "created_at": "2026-04-14T..."
  },
  {
    "id": 2, "version": 2, "replan_reason": "blockage_strategy_a",
    "parent_plan_id": 1, "status": "draft",
    "total_steps": 4, "created_at": "2026-04-14T..."
  }
]
```

按 version 升序排列。实现方式：应用层循环向上追溯（不用 CTE，最多 20 跳防死循环）。

**404 处理**：plan_id 不存在时返回 404。

**Schemas 新增**：`schemas.py` 中新增 `PlanVersionItem`。

---

## 二、验收标准（强制门禁）

### 功能验收

```
□ POST /solve 响应体包含 state_delta（列表，每项含 feature_key/from_value/to_value）
□ POST /solve 响应体包含 critical_path（op_code 列表，按时间顺序）
□ POST /solve 响应 tasks 每项包含 not_before（null 或整数）和 step_role
□ POST /solve 不再对 objective 字段做单值校验（传入任意 objective 不影响流程）
□ GET /plans/{id}/versions 返回版本链，按 version 升序
□ GET /plans/{id}/versions 对不存在 id 返回 404
```

### 测试门禁

| # | 命令 | 要求 |
|---|------|------|
| G1 | `pytest tests/ -v` | 0 失败，0 跳过 |
| G2 | `pytest tests/integration/test_step3_api.py -v` | 0 失败，>= 5 个测试 |

### 测试场景（至少覆盖）

1. 初次求解（无 parent_plan_id）→ state_delta 非空，critical_path 非空，所有步骤 step_role=normal
2. 策略A重规划 → tasks 中出现 step_role=delayed 或 pulled_forward，not_before 正确
3. 策略B重规划 → tasks 中出现 step_role=repair
4. GET /plans/{id}/versions 初次求解 → 返回长度为 1 的列表
5. GET /plans/{id}/versions 重规划后 → 返回长度为 2 的列表，version 正确
6. GET /plans/9999/versions → 404

---

## 三、完成标准

- [ ] A: POST /solve 响应新增 state_delta / critical_path / not_before / step_role
- [ ] B: 遗留 objective 单值校验已删除
- [ ] C: GET /plans/{id}/versions 端点已实现并注册
- [ ] D: 新增集成测试 >= 6 个场景
- [ ] `pytest tests/ -v`：0 失败，0 跳过
- [ ] STATE_V0.2.md STEP 3 相关子任务更新为 ✅

---

## 四、本次不做（明确排除）

| 排除项 | 原因 |
|--------|------|
| GET /plans/{id}/diff/{other_id} | TICKET-008 范围 |
| 前端改造 | STEP 4 范围 |
| Alembic 迁移 | 无数据模型变更 |
| critical_path 存入数据库 | 本次只在响应体返回，不持久化 |

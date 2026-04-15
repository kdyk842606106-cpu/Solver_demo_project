# TICKET-008: V0.2 STEP 3 收口 — GET /plans/{id}/diff/{other_id}

> 对应 STATE_V0.2.md → STEP 3 子任务 3-5
> 前置依赖：TICKET-007 已完成（198 测试全通过）
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

实现版本对比端点，供前端 Gantt 对比视图使用：

```
GET /api/v1/plans/{plan_id}/diff/{other_plan_id}
```

**不做**：不改数据模型、不动前端、不改其他 API。

---

## 接口规范

### 请求

```
GET /api/v1/plans/{plan_id}/diff/{other_plan_id}
```

`plan_id` = base（旧）计划，`other_plan_id` = new（新）计划。

### 响应

```json
{
  "base_plan_id": 1,
  "new_plan_id": 2,
  "base_makespan": 65,
  "new_makespan": 95,
  "steps": [
    {
      "op_code": "OP_WARMUP",
      "base_start": 0,   "base_end": 30,
      "new_start": 0,    "new_end": 30,
      "step_role": "normal",
      "not_before": null
    },
    {
      "op_code": "OP_CALIBRATE",
      "base_start": 30,  "base_end": 45,
      "new_start": 120,  "new_end": 135,
      "step_role": "delayed",
      "not_before": 120
    },
    {
      "op_code": "OP_REPAIR_HARDWARE",
      "base_start": null, "base_end": null,
      "new_start": 0,    "new_end": 40,
      "step_role": "repair",
      "not_before": null
    },
    {
      "op_code": "OP_CLEANING",
      "base_start": 0,   "base_end": 20,
      "new_start": 0,    "new_end": 20,
      "step_role": "pulled_forward",
      "not_before": null
    }
  ]
}
```

**字段语义**：

| 字段 | 说明 |
|------|------|
| `step_role` | 取自 NEW 计划的 CandidatePlanStep.step_role |
| `not_before` | 取自 NEW 计划的 CandidatePlanStep.not_before |
| `base_start/end` | 旧计划中该 op_code 的 start_min/end_min；不存在则 null |
| `new_start/end` | 新计划中该 op_code 的 start_min/end_min；不存在则 null |
| 步骤顺序 | 按 new_start（null 排后）+ op_code 字母序稳定排序 |

**错误处理**：

- 任一 plan_id 不存在 → 404
- 任一 plan 无 ScheduleResult → 422（`PLAN_NOT_SCHEDULED`）

---

## 实现要点

**数据来源**：
- `start_min` / `end_min` 从 `ScheduleResult.tasks`（JSONB）读取
- `step_role` / `not_before` 从 `CandidatePlanStep` 读取（join OpRule 取 code）

**算法**：
1. 取两个计划各自最新的 ScheduleResult（按 id DESC 取第一个）
2. 解析 JSONB tasks → `op_rule_code → {start_min, end_min}` 两个 dict
3. 查新计划的 CandidatePlanStep + OpRule → `op_rule_code → {step_role, not_before}`
4. 取两个 dict 的 key 并集，构建 diff step 列表
5. 排序：new_start 升序（null 排最后），同 start 时按 op_code 字母序

---

## 验收标准

```
✅ GET /plans/{id}/diff/{other_id} 返回正确的 steps 列表
✅ base_start=null 当步骤仅存在于新计划（repair 新增步骤）
✅ new_start=null 当步骤仅存在于基础计划（步骤被移除）
✅ step_role / not_before 来自新计划
✅ 任一 plan 不存在 → 404
✅ plan 无 ScheduleResult → 422
✅ pytest tests/ -v — 0 失败，0 跳过（211 通过）
✅ 新增集成测试 >= 4 个场景（TestPlanDiff: 8 个 + TestPlanNotScheduled: 2 个）
```

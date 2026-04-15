# TICKET-003: STEP 1 补丁 + API 安全加固

> 状态：已完成 — 2026-04-11
> 来源：代码审视发现 TICKET_001 交付后残留 P1/P2 问题
> 预估工作量：0.5 次对话

---

## 问题描述

TICKET_001 完成了数据模型扩展（ORM + Schema + Migration），但 API 层（master_data.py）未同步传递 V0.2 新增字段，导致：
- 通过 API 创建/更新 OpRule 时 `is_repair`、`valid_from`、`valid_to` 被丢弃
- 子表 `OpRulePrecond.value_list` 和 `OpRuleEffect.effect_type/delta_value` 被丢弃
- 序列化响应缺少上述字段，前端拿到错误默认值

同时发现 `schemas.py` 存在重复类定义和 `state.py` 缺少 `response_model` 等 API 质量问题。

## 子任务清单

```
✅ 3-1a  master_data.py — create_op_rule() 补全 is_repair/valid_from/valid_to
✅ 3-1b  master_data.py — update_op_rule() 补全 is_repair/valid_from/valid_to
✅ 3-1c  master_data.py — _replace_rule_children() 补全 value_list/effect_type/delta_value
✅ 3-1d  master_data.py — _serialize_rule() 补全 is_repair/valid_from/valid_to
✅ 3-2a  schemas.py — 合并重复 ScheduleTaskItem，补 not_before/step_role
✅ 3-2b  schemas.py — CandidatePlanStepResponse 补 op_rule_code
✅ 3-3   main.py — 移除生产环境 traceback 泄露（DEBUG 开关）
✅ 3-4a  state.py — list_machine_states 响应补 state_type
✅ 3-4b  state.py — 三个端点添加 response_model
✅ 3-5   models.py — 文档注释 "13 tables" → "16 tables (V0.2)"
```

## 修改文件

| 文件 | 改动类型 |
|------|---------|
| `app/api/v1/master_data.py` | P1: CRUD 补全 V0.2 字段传递 + 序列化 |
| `app/db/schemas.py` | P1: 合并重复定义 + 补字段 + 新增 state query schemas |
| `app/main.py` | P2: traceback 泄露安全修复 |
| `app/api/v1/state.py` | P2: 补 state_type + response_model |
| `app/db/models.py` | P3: 文档注释修正 |

## 验证

- `pytest tests/ -v` — 80 passed, 0 failed

## 本次不做

- solver.py 的 asyncio.to_thread() 包装（STEP 2 Scheduler 升级时处理）
- search.py precondition 硬编码 == 替换（STEP 2 RuleEvaluator 处理）
- 领域层 session.commit() 重构（STEP 2）
- 测试双引擎统一（独立技术债）

# TICKET-016: V0.3 Phase 1 闭环层 — 隐式子目标 + Scheduler/API/E2E 验证

> 状态：已完成 — 2026-04-21
> 对应版本：V0.3
> 对应阶段：数值型状态规划 Phase 1 闭环层
> 前置依赖：`docs/TICKET_015.md` 已完成
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

完成数值型 Phase 1 的闭环验证，覆盖：

1. 数值 precondition 的隐式子目标规划
2. 隐式子目标循环检测
3. Scheduler 对重复 `op_rule_id` 步骤的完整兼容验证
4. `/api/v1/solve` 数值链路响应验证
5. E2E 场景验证重复步骤展示与无解错误

---

## 子任务清单

```text
[✅] A  扩展 NumericFeaturePlanner，支持 precondition 驱动的隐式子目标
[✅] B  增加 visited_goals 循环检测与结构化错误
[✅] C  验证 Scheduler 对重复 op_rule_id 步骤的完整排程兼容
[✅] D  补充 API 测试 A1-A4
[✅] E  补充 E2E 测试 E1-E4
[✅] F  运行相关测试并修复问题
[✅] G  文档回写：STATE/TICKET 状态同步
```

---

## 验收标准

```text
✅ 数值 rule 的 precondition 不满足时，可自动规划隐式子目标链
✅ 隐式子目标循环返回结构化错误，不死循环
✅ Scheduler 输出 tasks 长度与 numeric RAG 节点数一致
✅ `/api/v1/solve` 可返回重复 op_rule_code 的 schedule tasks
✅ E2E 可验证纯数值、混合目标、隐式子目标、无解错误四类场景
```

---

## 本次不做（明确排除）

- 不引入 `primary_feature`
- 不支持外部 `gte/lte` 目标 API 扩展
- 不修改 `target_state` 语义
- 不新增 occurrence 字段
- 不重构 Scheduler 核心建模

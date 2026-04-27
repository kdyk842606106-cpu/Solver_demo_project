# TICKET-015: V0.3 Phase 1 接入层 — build_rag 分流与重复步骤持久化

> 对应版本：V0.3
> 对应阶段：数值型状态规划 Phase 1 接入层
> 前置依赖：`docs/TICKET_014.md` 已完成
> 预估工作量：1 次对话
> 当前状态：已完成

---

## 本次任务范围（只做这些）

将 `NumericFeaturePlanner` 接入 Planner 主链路，覆盖：

1. `build_rag()` 按 `StateFeatureDef.value_type` 对 delta 分流
2. 数值型 exact 目标调用 `plan_exact_numeric_feature()`
3. 数值 steps 合并为统一 `RAGNode`
4. 允许同一 `op_rule_id` 在 RAG / `CandidatePlanStep` 中重复出现
5. 保持枚举型旧链路和阻塞策略 B 兼容
6. 补充集成测试验证重复步骤落库与串行依赖

---

## 子任务清单

```text
[✅] A  加载 machine_type 下的 StateFeatureDef 并按 feature_key 建索引
[✅] B  build_rag delta 分流：number 走 NumericFeaturePlanner，其他走旧枚举链路
[✅] C  合并 numeric step instances 为 RAGNode，按实例串行建边
[✅] D  保持枚举型 op_rule_id 去重逻辑不变
[✅] E  验证 save_candidate_plan 可保存重复 op_rule_id
[✅] F  补充 integration 测试 I1-I4
[✅] G  运行相关测试并修复问题
[✅] H  文档回写：STATE/TICKET 状态同步
```

---

## 验收标准

```text
✅ build_rag 可为 number feature 生成重复 op_rule_id 的 RAG 节点
✅ 数值同一 feature 的步骤按 predecessor 串行
✅ CandidatePlanStep 可保存多条相同 op_rule_id，step_order 不同
✅ 枚举型 V0.1/V0.2 旧链路测试保持通过
✅ 本票不引入隐式子目标、不修改 Scheduler 主体语义
```

---

## 本次不做（明确排除）

- 不实现数值 precondition 隐式子目标
- 不修改 `/api/v1/solve` 请求结构
- 不新增数据库字段
- 不引入 `primary_feature`
- 不支持外部 `gte/lte` 目标语义
- 不重做 Scheduler 资源建模

# ARCHIVE: V0.2

> 归档时间：2026-04-19

## 版本目标（一句话）

V0.2 完成阻塞处理与动态重排（策略 A/B/AB），并完成规则评估、效果应用、目标函数的注册表化架构升级，为 V0.3 的可解释性与多目标能力打下基础。

---

## 已完成能力清单

- 数据层扩展：`feature_definition`、`blockage_event` 新增；`op_rule_precond/operator+value_list`、`op_rule_effect/effect_type+delta_value`、`op_rule/is_repair+valid_from+valid_to`、`solve_request/objectives+constraints+parent_plan_id`、`candidate_plan/version链`、`candidate_plan_step/not_before+step_role` 落地。
- 领域层升级：`OperatorRegistry`（7 操作符）、`EffectRegistry`（3 效果）、`RuleEvaluator` 统一入口、`ObjectiveRegistry` 扩展点、RAG 循环检测与深度保护完成。
- 阻塞策略闭环：策略 A（`not_before`）、策略 B（`blockage_reason` 注入触发维修序列）、策略 AB（组合仲裁）在求解链路中可用。
- API 扩展完成：`/api/v1/features`、`/api/v1/plans/{id}/versions`、`/api/v1/plans/{id}/diff/{other_id}`、增强版 `/api/v1/solve`。
- 前端重构完成：Vue 3 + Element Plus + ECharts，Solve 页整合版本历史、对比模式、阻塞弹窗、关键路径、状态差、任务表。
- 展示增强（TICKET-010）：Gantt 与任务明细统一为“步骤编号 + 活动编码 + 活动名称”，并支持名称缺失降级。

---

## 关键架构决策（含原因）

- 决策 1：规则评估统一走 `RuleEvaluator` + 注册表。
  - 原因：避免 precond/effect 逻辑散落，支持零侵入新增 operator/effect/objective。
- 决策 2：阻塞语义不侵入 RAGBuilder，通过状态注入建模（`blockage_reason`）。
  - 原因：复用通用状态推导链路，减少策略分支逻辑耦合。
- 决策 3：step_role 在求解后通过新旧计划 diff 计算。
  - 原因：保持 Planner/Scheduler 纯度，避免提前混入展示语义。
- 决策 4：计划版本链采用 `candidate_plan.parent_plan_id` 自关联。
  - 原因：支持重排历史追溯、版本对比与前端时间线展示。
- 决策 5：前端 API 统一封装到 `src/api/`（含健康检查）。
  - 原因：避免组件层网络逻辑碎片化，统一错误处理与调用约束。

---

## 继承到下一版本的限制/技术债

- 测试基础设施：`tests/e2e/conftest.py` 与 `tests/conftest.py` 双引擎 + 重复 fixture，需后续统一（非阻塞）。
- Objectives 能力边界：当前完整实现为 `minimize_makespan`，`weight` 尚未参与真实加权求解。
- 错误码文档口径需持续对齐：历史文档存在旧命名残留，后续以协议文档与实际 API 为准逐步清理。

---

## 版本末数据模型状态（摘要）

- 机台与状态：`machine_type`、`machine`、`machine_state`、`machine_state_feature`、`feature_definition`
- 规则层：`op_rule`、`op_rule_precond`、`op_rule_effect`、`op_rule_resource_req`
- 资源层：`resource`
- 求解层：`solve_request`、`candidate_plan`、`candidate_plan_step`、`schedule_result`、`blockage_event`
- 关键字段状态：
  - `solve_request`: `objectives` / `constraints` / `parent_plan_id` / `blockage_constraints`
  - `candidate_plan`: `version` / `parent_plan_id` / `replan_reason`
  - `candidate_plan_step`: `not_before` / `step_role`
  - `schedule_result.tasks[]`: `op_rule_name` / `step_role` / `not_before`（前端展示闭环）

---

## 归档结论

V0.2 已完成既定目标，可进入 V0.3：求解可解释性深化 + 多目标优化 + 工序组 + A* 搜索。

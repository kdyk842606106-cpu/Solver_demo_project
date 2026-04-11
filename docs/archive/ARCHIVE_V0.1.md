# ARCHIVE: V0.1

> 归档时间：2026-04-10
> 状态：全部 5 个里程碑已完成

---

## 版本目标

建立基础求解链路：状态推导 RAG 构建 + CP-SAT 排程 + 主数据 CRUD + 前端数据管理。

## 已完成功能

1. **数据层**：14 张表 + Alembic 迁移 + 3 份种子数据 SQL
2. **Planner**：delta 匹配 + 依赖补齐（非 BFS，反向回溯） + 环检测
3. **Scheduler**：CP-SAT 排程（precedence + cumulative 资源约束 + 并行检测）
4. **端到端联调**：POST /solve 全链路跑通
5. **规则扩展验证**：纯 SQL 插入即可生效
6. **主数据 CRUD API** + **前端数据管理页**（静态 SPA）

## 最终数据模型

14 张表：machine_type, machine, machine_state, machine_state_feature, feature_definition,
op_rule, op_rule_precond, op_rule_effect, op_rule_resource_req, resource,
solve_request, candidate_plan, candidate_plan_step, schedule_result

## 关键架构决策

- Planner 使用 delta 匹配 + 依赖反向回溯（非传统 BFS），效率更高
- 依赖关系从 precond/effect 链自动推导，并行分支自然涌现
- Scheduler 使用 CP-SAT 硬约束建模（precedence + cumulative）
- 前端为静态 SPA（单页 index.html），非 Vue 工程

## 遗留技术债（交接至 V0.2）

- op_rule_precond 只支持等值匹配（无 operator 字段）
- op_rule_effect 只支持 set（无 effect_type 字段）
- RAGBuilder 无循环检测和深度限制
- Scheduler objectives 是单枚举值，非数组
- precond 匹配逻辑未抽象为 RuleEvaluator

## 详细历史文档

- [v0.1-introduction.md](./v0.1-introduction.md) — 原始设计文档
- [v0.1-roadmap.md](./v0.1-roadmap.md) — 5 个里程碑详细验收标准

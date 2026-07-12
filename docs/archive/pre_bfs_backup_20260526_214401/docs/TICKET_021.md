# TICKET-021: Planner 正向 BFS 搜索主策略改造

> 对应版本：V0.3
> 对应阶段：Planner 搜索策略重构
> 前置依赖：TICKET-014 / TICKET-015 / TICKET-016 / TICKET-017 已完成
> 预计工作量：2-4 次对话
> 当前状态：未开始

---

## 本次任务范围（只做这些）

将 Planner 的状态搜索逻辑从当前的「状态差 delta 匹配 + 逆向依赖补齐」改为「从 current_state 出发的正向 BFS 状态空间搜索」。

核心决策：

1. 正向 BFS 作为 Planner 主策略，不作为可选 fallback 或实验策略。
2. `numeric.py` 的数值型多步推进能力收敛进统一 BFS，不再长期维持独立分流。
3. 保持 `build_rag(...) -> PlanResult`、`save_candidate_plan(...)`、`CandidatePlanStep.predecessor_ids` 对外契约稳定。
4. 保持 Scheduler/API/前端调用链尽量零侵入。
5. 所有 precondition 判断和 effect 应用继续通过 `RuleEvaluator`。

---

## 背景与问题

当前 `app/core/planner/search.py` 的主流程并不是完整状态空间搜索，而是：

1. 计算 `current_state` 与 `target_state` 的 delta。
2. 为每个 delta 找能产生目标 effect 的规则。
3. 对已选规则递归补齐 precondition provider。
4. 将补齐出的规则集合转换成 RAG。

这个流程在简单枚举型目标上可用，但在以下场景中会暴露结构性限制：

- 多步状态演进依赖运行时中间状态，而不是静态 `current_state`。
- 同一个 `OpRule` 需要重复实例化时，delta provider 模型表达吃力。
- 数值型目标目前依赖 `numeric.py` 专用 BFS，与主 Planner 形成双轨。
- 含副作用规则可能被 delta provider 误选，产生「看似推进目标但走偏」的计划。
- 依赖关系补齐是逆向静态分析，不等价于真实执行路径。

---

## 目标设计

### 1. 统一正向 BFS

从 `current_state` 作为起点，重复执行：

1. 遍历所有可用 `OpRule`。
2. 通过 `RuleEvaluator.evaluate_preconditions(state, rule.preconditions)` 判断当前状态下是否可执行。
3. 通过 `RuleEvaluator.apply_effects(state, rule.effects)` 生成新状态副本。
4. 用 `freeze(state)` 做 visited 去重。
5. 用 `is_goal(next_state, target_state)` 判断是否到达目标。

搜索成功后，返回一条有序 transition path，再转换为 RAG。

### 2. numeric.py 收敛

将 `numeric.py` 中已经验证过的能力迁入统一 BFS 的规则展开和剪枝逻辑：

- 数值型 `increment/decrement/set` effect 由统一 `RuleEvaluator` 应用。
- 重复执行同一 `OpRule` 由 BFS path 自然表达。
- 隐式数值 precondition 不再走 `plan_precondition_goal()` 递归专用通道，而是通过正向状态推进自然满足。
- 数值搜索的安全限制保留为 BFS 配置：`max_depth`、`max_nodes`、visited 去重、无进展剪枝。

迁移完成后，`numeric.py` 应降级为：

- 删除；
- 或仅保留纯函数工具；
- 或暂时保留兼容包装，但不再被 `build_rag` 主流程调用。

### 3. RAG 输出契约

BFS 得到的 transition path 转换为：

```python
RAGNode(
    id=step_index,
    op_rule_id=transition.rule.id,
    op_rule_code=transition.rule.code,
    predecessors=[...],
)
```

第一阶段可采用保守串行依赖：

- 第 1 步无 predecessor。
- 第 N 步依赖第 N-1 步。

第二阶段再做依赖压缩：

- 根据每一步读取的 precondition feature 与之前步骤写入的 effect feature 推导真实 predecessor。
- 无依赖的步骤允许并行涌现。
- 该压缩不得改变 BFS path 的状态可达性。

---

## 子任务清单

```text
[ ] A  冻结 BFS 主策略契约
       - 明确 `search_method` 是否改为 `forward_bfs`
       - 明确 `build_rag` 函数签名保持不变
       - 明确旧 delta-provider 逻辑是否直接删除还是短期保留内部 fallback

[ ] B  建立当前回归基线
       - 记录 enum 简单目标场景
       - 记录多步 precondition 链场景
       - 记录 numeric repeated step 场景
       - 记录 blockage A/B/AB 场景
       - 记录 no_solution / cycle / max depth 诊断语义

[ ] C  新增 BFS 数据结构
       - `SearchNode`: state, path, depth
       - `Transition`: rule, before_state, after_state
       - `BfsPlanResult`: status, path, final_state, error_code, error_message
       - `BfsLimits`: max_depth, max_nodes

[ ] D  实现统一正向 BFS 核心
       - 从 current_state 初始化队列
       - 遍历当前状态下所有可执行规则
       - 通过 RuleEvaluator 统一应用 effects
       - 使用 freeze/unfreeze 做 visited
       - 支持重复 op_rule 实例进入 path
       - 返回最短操作步数路径

[ ] E  数值型能力迁入 BFS
       - 移除 `build_rag` 中对 `plan_exact_numeric_feature()` 的专用分流
       - 让 increment/decrement 规则在 BFS 中自然重复展开
       - 保留数值值域安全剪枝，避免无限递增/递减
       - 覆盖 exact numeric 目标和隐式 numeric precondition

[ ] F  repair/blockage 语义接入
       - 保持 `include_repair` 控制 repair 规则是否进入 BFS 候选规则集
       - 保持 `current_state_override` 注入语义
       - 验证 Strategy B/AB 的 repair step 仍可自然搜索出来

[ ] G  BFS path 转 RAG
       - 将 path 中每个 Transition 转为独立 RAGNode
       - 保留重复 op_rule_id 的多个 step 实例
       - 第一阶段采用串行 predecessor
       - 第二阶段增加 feature-level dependency compaction

[ ] H  替换 build_rag 主流程
       - 保留状态加载、machine_type/rule 加载、PlanResult 返回结构
       - 将原 delta-provider 主体替换为 forward BFS
       - 统一 no_solution/error 的错误消息和 error_code 来源
       - 将 `save_candidate_plan.search_method` 调整为最终确认值

[ ] I  补齐测试
       - unit: BFS 直接命中目标
       - unit: BFS 多步 precondition 链
       - unit: BFS visited 去重避免循环
       - unit: BFS max_depth/max_nodes 诊断
       - unit: numeric increment/decrement repeated step
       - integration: /solve enum 场景不回退
       - integration: /solve numeric repeated step
       - integration: blockage Strategy A/B/AB
       - e2e: numeric planning 现有场景保持通过

[ ] J  文档回写
       - 更新 `docs/protocols/planner.md`
       - 更新 `docs/STATE_V0.3.md`
       - 标记本 TICKET 子任务完成情况
```

---

## 验收标准

```text
✅ Planner 主策略为正向 BFS，而不是 delta-provider 逆向补齐
✅ `build_rag` 对外调用方式保持兼容
✅ enum 简单目标可正常生成 RAG 和 schedule
✅ 多步 precondition 链由正向状态推进自然发现
✅ 同一 op_rule 可重复实例化为多个 CandidatePlanStep
✅ numeric exact 目标不再依赖 `numeric.py` 专用主流程
✅ repair/blockage A/B/AB 回归通过
✅ 无解、深度上限、节点上限返回可诊断错误
✅ Scheduler/API/前端无需大范围改造
```

---

## 本次不做（明确排除）

- 不引入 A* 启发式搜索。
- 不实现多目标优化。
- 不新增数据库 schema。
- 不重做 Scheduler。
- 不重做前端页面。
- 不支持概率型/不确定时长建模。
- 不支持跨机台资源调配。

---

## 风险与注意事项

1. BFS 状态空间可能爆炸，必须设置 `max_depth`、`max_nodes` 和 visited 去重。
2. 对数值型特征要有边界剪枝，否则 increment/decrement 规则可能无限扩展。
3. 第一阶段串行 RAG 最稳，但可能降低并行度；feature-level dependency compaction 应单独测试。
4. 旧测试可能依赖 step_order 的具体顺序，替换搜索后要区分「契约要求」和「历史偶然」。
5. `numeric.py` 删除前要确认没有外部测试或导入直接依赖它的 public symbol。

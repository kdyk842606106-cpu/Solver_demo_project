# 泵体机械集成种子架构兼容性分析报告

> 生成时间：2026-04-23
> 关联文件：007_pump_body_integration_seed.sql / .md / test_pump_body_seed.py
> 分析范围：Solver Demo Project V0.3 Planner + Scheduler 架构

---

## 一、问题定义

### 1.1 用户原始需求

创建一个泵体机械集成场景的 Solver seed，要求：
1. 主线活动 ≥5，支线活动 ≥3，体现穿并行
2. 资源约束（单组单人工种争抢）
3. 每个主线机械活动降低洁净度 25 分
4. 洁净度低于阈值（≤30）时必须执行洁净作业
5. 至少出现 2 次洁净活动

### 1.2 第一次尝试（数值型方案）

使用 `pump_cleanliness_score`（number 类型）：
- 初始值 100
- 每次机械操作 `decrement 25`
- 洁净操作前置条件：`cleanliness_score ≤ 30`
- 洁净操作效果：`set 100`
- 精密装配（密封/轴承）前置条件：`cleanliness_score ≥ 30`

**预期行为**：
```
外壳(100→75) → 叶轮(75→50) → 主轴(50→25) 
→ [触发洁净: 25≤30] → 洁净(25→100) 
→ 密封(100→75) → 轴承(75→50) → 联轴器(50→25)
→ [触发洁净: 25≤30] → 洁净(25→100)
→ 测试(需≥50 ✓)
```

### 1.3 实际运行结果

**测试失败**：4/11 项未通过

| 失败项 | 现象 |
|--------|------|
| 主线操作完整性 | 两次洁净步骤完全未出现在计划中 |
| 洁净步数统计 | 实际 0 次，期望 2 次 |
| 依赖顺序 | 因洁净步骤缺失，依赖链断裂 |
| Makespan | 实际 510 分钟（无洁净），期望 ≥590 分钟 |

---

## 二、根因分析

### 2.1 Solver 两层架构

```
┌────────────────────────────────────────────────┐
│  第一层：Planner (RAGBuilder)                  │
│  ─────────────────────────────                  │
│  输入：current_state, target_state, rules       │
│  输出：RAG（有向无环图，节点=工序，边=依赖）      │
│  机制：precond/effect 静态匹配 + provider 回溯   │
├────────────────────────────────────────────────┤
│  第二层：Scheduler (CP-SAT)                     │
│  ─────────────────────────────                  │
│  输入：RAG + resources                           │
│  输出：排程（start_min, end_min, 资源分配）      │
│  机制：precedence 约束 + cumulative 资源约束    │
└────────────────────────────────────────────────┘
```

### 2.2 核心限制：Planner 不做前向状态模拟

Planner 的 `build_rag()` 在评估 precondition 时，**始终使用原始的 `current_state`**，而不是「执行到当前节点时的投影状态」。

```python
# app/core/planner/search.py — 核心逻辑
for precond in op.preconditions:
    evaluator = RuleEvaluator()
    if evaluator.evaluate_precondition(current_state, precond):
        continue  # ← 用 current_state 评估！不是投影状态
    # 只有不满足时才寻找 provider
```

**后果**：
- 当前状态 `cleanliness=100`
- 机械密封需要 `cleanliness ≥ 30` → ** Planner：已满足！**
- 不需要寻找洁净 provider
- 洁净操作永远不会被加入 RAG

### 2.3 为什么 Numeric Planner 也帮不上忙

当前 Numeric Planner (`numeric.py`) 的触发条件是：
- `current_value ≠ target_value` 且存在 delta

但目标状态 `cleanliness=100`，当前状态也是 `cleanliness=100`：
- **无 delta** → Numeric Planner 不启动
- 即使启动，它只规划「从 A 到 B 的精确数值链」，不处理「执行中阈值触发维护操作」

### 2.4 总结：语义鸿沟

| 用户想要的语义 | Solver 能表达的语义 |
|--------------|-------------------|
| 执行中状态动态变化（100→75→50→25） | 只比较 current vs target（100 vs 100，无差异） |
| 阈值触发（≤30 时自动插入 CLEAN） | 只支持「当前状态不满足 → 寻找 provider」 |
| Reactive：状态变化→自动响应 | 静态 RAG 构建，无执行期事件响应 |

---

## 三、可行方案对比

### 方案 A：枚举代次链式依赖（已落地）

**思路**：将「数值区间门槛」编码为「离散代次状态机」，利用 Planner 已有的 provider 回溯机制。

**实现**：
- Feature：`pump_cleanliness_generation`（enum）
- Values：`gen_0` → `gen_1` → `gen_2`
- `gen_0` = 可执行粗装（外壳/叶轮/主轴）
- `gen_1` = 可执行精装（密封/轴承/联轴器）
- `gen_2` = 可执行测试

**Planner 行为**：
- 目标状态 `gen_2`，当前 `gen_0` → **有 delta**
- 寻找 provider → 发现 Clean 操作可将 `gen_0→gen_1`，`gen_1→gen_2`
- Clean 前置条件要求 `gen_0`/`gen_1` → **已满足**
- Clean 加入 RAG，成为必经步骤

#### 优点
| 优点 | 说明 |
|------|------|
| **零架构侵入** | 不修改 Planner/Scheduler 任何代码 |
| **完全兼容现有所有 seed** | 不影响 001~006 号种子行为 |
| **测试通过率高** | 11/11 项测试全部通过 |
| **Makespan 合理** | 实测 620 分钟，符合预期 |
| **实现成本低** | 1 小时完成种子重写 + 测试验证 |
| **阻塞重排兼容** | Strategy A/B/AB 无需特殊处理 |

#### 缺点
| 缺点 | 说明 |
|------|------|
| **代次粒度固定** | 必须预先定义 gen_0/1/2，不能动态计算 |
| **丢失连续过程** | 无法表达「100→75→50→25」的渐变 |
| **不支持优化** | 无法实现「如果还剩 40，只做半量清洁」 |
| **状态机爆炸风险** | 若门槛多（30/50/70），代次数量线性增长 |
| **建模语义偏移** | 从「物理量（洁净度分数）」变为「逻辑标签（代次）」 |

---

### 方案 B：Planner 前向状态模拟

**思路**：改造 Planner，使其在评估 precondition 时使用「执行到当前节点时的投影状态」而非原始 current_state。

**需要改动**：

```python
# 新增：状态投影器
def simulate_path_effects(current_state: StateDict, path: list[OpRule]) -> StateDict:
    """沿执行路径模拟 effect 累积，返回投影状态。"""
    state = dict(current_state)
    for op in path:
        for effect in op.effects:
            state = apply_effect(state, effect)
    return state

# 改造：build_rag() 中的 precondition 评估
for precond in op.preconditions:
    projected_state = simulate_path_effects(current_state, path_to_this_op)
    if evaluator.evaluate_precondition(projected_state, precond):
        continue
    # 否则寻找 provider...
```

**额外要求**：
- 工作队列必须按拓扑序处理（当前是扁平列表循环）
- 需要支持增量状态更新（一个节点处理完后更新全局投影）
- 需处理循环依赖检测（状态模拟可能暴露新的循环模式）

#### 优点
| 优点 | 说明 |
|------|------|
| **语义保真** | 完全保留数值型洁净度阈值触发的原始设计 |
| **表达能力增强** | Planner 可处理任何「执行中状态变化→影响后续预条件」的场景 |
| **不修改 Scheduler** | 只动 Planner 层，Scheduler 零改动 |
| **向后兼容** | 不传新参数时行为与旧版完全一致 |

#### 缺点
| 缺点 | 说明 |
|------|------|
| **架构侵入性高** | 修改 Planner 核心 `build_rag()`，风险大 |
| **实现复杂度** | 需处理：拓扑序、增量状态、循环检测、副作用隔离 |
| **性能下降** | RAG 构建从 O(n) 变为 O(n²)（每节点需模拟全路径） |
| **测试回归量大** | 所有历史 seed（001~006）+ 阻塞重排 + numeric 能力需全量回归 |
| **开发周期长** | 估计 2-3 个 ticket，1-2 周工作量 |
| **引入新 bug 风险** | 状态模拟与现有 rule_evaluator 交互可能产生边缘 case |

---

### 方案 C：Reactive Planning（执行期动态重排）

**思路**：不仅改造 Planner，还扩展 Scheduler，使其在「执行期」监听状态变化事件，动态触发 replan。

```
Scheduler 执行中 ──→ 检测到 cleanliness 降至 25 ──→ 触发 replan
                          ↓
              暂停当前计划，插入 CLEAN，恢复执行
```

**需要新增**：
- 状态事件监听机制（Event Bus）
- 执行期检查点（Checkpoint）
- 动态 replan 触发器（Trigger）
- 计划版本热切换（Hot-swap）

#### 优点
| 优点 | 说明 |
|------|------|
| **最真实语义** | 支持「执行中阻塞→自动响应→动态调整」 |
| **超集能力** | 不仅解决洁净度，还覆盖所有执行期异常处理 |
| **面向生产** | 真实车间需要的正是这个能力 |

#### 缺点
| 缺点 | 说明 |
|------|------|
| **架构侵入性极高** | 需修改 Planner + Scheduler + API + DB 状态机 |
| **超出 V0.3 范围** | 当前版本定义为「一次性离线求解」，不支持执行期追踪 |
| **实现周期长** | 估计 4-6 个 ticket，4-8 周工作量 |
| **引入全新概念** | 执行状态、事件监听、热切换等需全新设计 |
| **前端需同步** | 甘特图需支持「执行中动态刷新」 |
| **测试复杂度指数级** | 需模拟时间流逝、事件触发、并发冲突 |

---

## 四、量化对比矩阵

| 维度 | 方案 A（枚举代次） | 方案 B（前向模拟） | 方案 C（Reactive） |
|------|------------------|------------------|-------------------|
| **实现成本** | ⭐ 低（1小时） | ⭐⭐⭐ 高（1-2周） | ⭐⭐⭐⭐⭐ 极高（4-8周） |
| **架构侵入性** | ⭐ 无 | ⭐⭐⭐ 高 | ⭐⭐⭐⭐⭐ 极高 |
| **语义保真度** | ⭐⭐ 中等（等价替代） | ⭐⭐⭐⭐ 高（完全保真） | ⭐⭐⭐⭐⭐ 完全真实 |
| **向后兼容性** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐⭐⭐ 好 | ⭐⭐⭐ 需大改 |
| **性能影响** | ⭐⭐⭐⭐⭐ 无 | ⭐⭐⭐ O(n²) | ⭐⭐ 运行时开销 |
| **测试回归量** | ⭐⭐⭐⭐⭐ 仅新增 | ⭐⭐ 全量回归 | ⭐ 需全新测试体系 |
| **生产可用性** | ⭐⭐⭐ 演示可用 | ⭐⭐⭐⭐ 接近生产 | ⭐⭐⭐⭐⭐ 生产级 |
| **与路线图匹配** | ⭐⭐⭐ V0.3 适配 | ⭐⭐⭐⭐ V0.4 规划 | ⭐⭐⭐⭐⭐ V1.0 方向 |

---

## 五、推荐决策

### 5.1 立即行动（本周末前）

**采用方案 A**，理由：
1. 当前 V0.3 的核心目标是「数值型状态规划能力」和「可解释性」，不是「执行期动态响应」
2. 方案 A 在 1 小时内完成，11 项测试全部通过，可立即演示
3. 方案 B/C 的改动会延迟 V0.3 主线交付，引入不可控风险

### 5.2 中期规划（V0.4 或后续版本）

**评估方案 B**，条件触发：
- 用户明确要求保留「数值型阈值触发」的原始语义（如论文复现、标准对标）
- V0.3 主线任务全部完成，有 1-2 周 buffer
- 全量回归测试资源就绪

### 5.3 长期方向（V1.0）

**规划方案 C**，作为产品演进方向：
- Reactive Planning 是真实车间集成的终极目标
- 但需与「执行状态追踪」「外部系统集成」等能力同步建设
- 建议在 V1.0 路线图中明确立项

---

## 六、附件

| 文件 | 位置 | 说明 |
|------|------|------|
| 已落地种子 SQL | `seeds/007_pump_body_integration_seed.sql` | 方案 A 实现 |
| 设计文档 | `seeds/007_pump_body_integration_seed.md` | 包含活动序列图 |
| 架构分析 | `seeds/007_pump_body_seed_analysis.md` | 失败根因深度分析 |
| 集成测试 | `tests/integration/test_pump_body_seed.py` | 11 项自动化测试 |
| 原始数值型种子 | `seeds/007_pump_body_integration_seed.sql.bak` | 方案 B 的输入基准 |

---

## 七、技术债务记录

若未来实施方案 B，需关注以下技术债务：

1. **Planner 层循环检测增强**：前向模拟可能暴露「状态循环」（如 A→decrement→B→increment→A），需与现有 `has_cycle()` 协同
2. **RuleEvaluator 状态隔离**：`apply_effect()` 当前返回新副本，但前向模拟需频繁调用，可能成为性能瓶颈
3. **Numeric + Enum 混合场景**：前向模拟需同时处理 `number` 的加减和 `enum` 的 set，混合路径的评估顺序需定义
4. **Scheduler 的 not_before 兼容**：前向模拟不改变 Scheduler 层，但需验证 `not_before` 约束与新增节点的交互

---

*报告生成：oc助手*
*审核状态：待用户确认决策方向*

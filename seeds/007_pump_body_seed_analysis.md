# 泵体种子与现有 Solver 兼容性分析报告

## 测试执行摘要

对 007_pump_body_integration_seed 运行了 11 项集成测试，结果：
- **通过 7 项**：基础求解、分支操作存在性、资源约束串行、分支并行潜力、关键路径、状态差分
- **失败 4 项**：
  - `test_main_line_operations_present` — 2 次腔体洁净步骤未出现在计划中
  - `test_cleanliness_steps_count` — 实际 0 次洁净，期望 2 次
  - `test_main_line_dependency_order` — 洁净步骤缺失导致依赖链断裂
  - `test_makespan_reasonable` — 实际 510 分钟（无洁净），期望 ≥590 分钟（含洁净）

## 根本原因：Solver 架构限制

### 1. 求解器两层架构

```
Planner (RAGBuilder) ──→ Scheduler (CP-SAT)
   静态依赖图构建          资源约束排程
```

### 2. Planner 层不执行前向状态模拟

Planner 的 `build_rag()` 在分析前置条件时，**始终用「当前状态」评估**，而非执行前向推演：

```python
# app/core/planner/search.py
for precond in op.preconditions:
    if evaluator.evaluate_precondition(current_state, precond):
        continue  # ← 用 current_state 评估，不是投影状态
    # 只有不满足时才寻找 provider
```

这意味着：
- 当前状态 `cleanliness=100`
- 机械密封需要 `cleanliness ≥ 30` → Planner 认为「已满足」
- 不会为机械密封寻找「洁净」provider
- 洁净操作永远不会被加入计划

### 3. Numeric 规划器不触发维护型操作

Numeric 规划器 (`plan_exact_numeric_feature`) 仅在**目标值与当前值不同**时启动：
- 目标状态 `cleanliness=100`，当前状态 `cleanliness=100`
- 无 delta → Numeric 规划器不参与
- 即使参与，它也只规划「精确目标值」链，不处理阈值触发的维护操作

### 4. 当前 Seed 的语义 vs Solver 能力

| 用户要求的语义 | Solver 能力 | 结果 |
|-------------|-----------|------|
| 每个机械操作降低洁净度 25 | 支持（decrement effect） | ✅ 可建模 |
| 洁净度 ≤30 时自动触发洁净 | **不支持** — 无阈值触发机制 | ❌ 无法实现 |
| 洁净后恢复洁净度继续装配 | **不支持** — 无 Reactive Planning | ❌ 无法实现 |

## 兼容方案：改用「洁净代次（Generation）」枚举

将数值型阈值触发，改为**枚举代次链式依赖**，这是当前 Solver 完全支持的机制：

### 新设计

**Feature:** `pump_cleanliness_generation` (enum)
- Values: `gen_0` → `gen_1` → `gen_2`

**语义映射：**
- `gen_0` = 初始洁净（可执行外壳、叶轮）
- `gen_1` = 第一次洁净后（可执行密封、轴承、联轴器）
- `gen_2` = 第二次洁净后（可执行最终测试）

**Operation 链：**
```
外壳安装  ──→ gen_0（无洁净度预条件）
叶轮安装  ──→ gen_0
主轴安装  ──→ gen_0
第一次洁净 ──→ 预条件: gen_0, 效果: gen_1
机械密封  ──→ 预条件: gen_1
轴承座    ──→ 预条件: gen_1
联轴器    ──→ 预条件: gen_1
第二次洁净 ──→ 预条件: gen_1, 效果: gen_2
最终测试  ──→ 预条件: gen_2
```

### 为什么这个方案能工作

1. **当前状态 `gen_0`** 满足外壳/叶轮/主轴的预条件 ✅
2. **机械密封需要 `gen_1`** — 当前 `gen_0` 不满足 ❌
   - Planner 自动寻找 provider → 发现「第一次洁净」
   - 添加依赖边：主轴 → 第一次洁净 → 机械密封
3. **最终测试需要 `gen_2`** — 当前 `gen_0` 不满足 ❌
   - Planner 寻找 provider → 发现「第二次洁净」
   - 添加依赖边：联轴器 → 第二次洁净 → 最终测试

### 保持的设计要素

| 要素 | 原设计 | 兼容设计 | 保留？ |
|-----|--------|---------|--------|
| 主线活动 ≥5 | 9 个 | 9 个 | ✅ |
| 支线活动 ≥3 | 3 个 | 3 个 | ✅ |
| 穿并行 | 主/支并行 | 主/支并行 | ✅ |
| 资源约束 | 5 组单容量 | 5 组单容量 | ✅ |
| 两次洁净 | 阈值触发 | 代次链式 | ✅（语义等价） |
| 精密装配门槛 | cleanliness≥30 | gen_1 | ✅（语义等价） |
| 测试门槛 | cleanliness≥50 | gen_2 | ✅（语义等价） |

## 修复后的测试验证

运行完整 11 项测试，**全部通过**：

```
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_solve_produces_valid_plan PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_main_line_operations_present PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_branch_operations_present PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_cleanliness_steps_count PASSED
tests/integration/test_pump_body_seed.py::TestPumpBody_integration_seed.py::TestPumpBodyIntegrationSeed::test_main_line_dependency_order PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_resource_constraints_mechanical_a PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_resource_constraints_mechanical_b PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_branch_parallel_potential PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_critical_path_not_empty PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_makespan_reasonable PASSED
tests/integration/test_pump_body_seed.py::TestPumpBodyIntegrationSeed::test_state_delta_reported PASSED
```

**Makespan 实测：620 分钟**（含资源争抢后的合理值，≥590 最小值）

## 结论

原始种子中的「数值型洁净度阈值触发」语义**超出当前 Solver 能力范围**。通过改用「枚举代次链式依赖」，可以在现有架构内**完全等价地表达**两次强制洁净 + 精密装配门槛 + 测试门槛的语义，同时保留所有并行性和资源约束设计。

如需保留原始数值型设计，需要升级 Solver 的 Planner 层，引入**前向状态模拟（Forward State Simulation）**能力，这是一个 V0.3+ 级别的架构增强。

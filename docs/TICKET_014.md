# TICKET-014: V0.3 Phase 1 准备层 — NumericFeaturePlanner 骨架与纯内存验证

> 对应版本：V0.3
> 对应阶段：数值型状态规划 Phase 1 准备层
> 前置依赖：`docs/TICKET_013.md` 设计已冻结
> 预估工作量：1 次对话
> 当前状态：已完成

---

## 本次任务范围（只做这些）

交付数值型精确目标规划的最小内存闭环，覆盖：

1. 新增 `app/core/planner/numeric.py`
2. 定义 `PlannedStep` 与 `NumericPlanResult` 轻量数据结构
3. 实现 `plan_exact_numeric_feature()` 的纯内存规划能力
4. 支持同一 `OpRule` 重复实例化生成多个步骤
5. 使用 `RuleEvaluator.apply_effects()` 推进状态副本
6. 补充 unit 测试，验证 `0 -> 80` 等核心场景

---

## 子任务清单

```text
[✅] A  新增 numeric.py 与数据结构
[✅] B  实现数值候选规则筛选与排序
[✅] C  实现精确目标 BFS / 有界搜索
[✅] D  确保状态不可变与重复 op_rule 不去重
[✅] E  补充 unit 测试覆盖核心成功/失败场景
[✅] F  运行相关测试并修复问题
[✅] G  文档回写：STATE/TICKET 状态同步
```

---

## 详细要求

### A：新增模块与数据结构

新增：

```text
app/core/planner/numeric.py
```

定义：

```python
@dataclass
class PlannedStep:
    instance_id: str
    op_rule: OpRule
    target_feature: str
    before_state: StateDict
    after_state: StateDict
    predecessor_instance_ids: list[str]

@dataclass
class NumericPlanResult:
    status: str
    steps: list[PlannedStep]
    final_state: StateDict | None = None
    error_code: str | None = None
    error_message: str | None = None
```

### B：候选规则筛选

Phase 1 候选规则必须满足：

- effect 中包含目标 `feature_key`
- `effect_type` 为 `increment` 或 `decrement`
- `delta_value` 可转为数值
- 推进方向朝向目标
- 应用后不离目标更远

排序规则：

1. 副作用更少
2. 步长更大
3. `duration_min` 更短

### C：精确目标搜索

实现 `plan_exact_numeric_feature()`：

```python
def plan_exact_numeric_feature(
    feature_key: str,
    current_state: StateDict,
    target_value: str,
    rules: list[OpRule],
    max_steps: int = 50,
) -> NumericPlanResult:
    ...
```

要求：

- 使用有界搜索，避免纯贪心无法处理 `0 -> 30`、`+20/+10` 场景
- 每次推进必须通过 `RuleEvaluator.apply_effects()`
- 返回的 `steps` 是步骤实例，不按 `op_rule_id` 去重
- 不修改输入 `current_state`

### D：错误码

本票至少覆盖：

- `NUMERIC_NO_PROVIDER`
- `NUMERIC_EXACT_TARGET_UNREACHABLE`
- `NUMERIC_MAX_STEPS_EXCEEDED`
- `NUMERIC_INVALID_VALUE`

---

## 验收标准

```text
✅ `0 -> 80` + `+20` 可生成 4 个 PlannedStep
✅ `0 -> 30` + `+20/+10` 可精确到达
✅ `0 -> 25` + `+20/+10` 返回不可精确到达错误
✅ 反向目标可通过 decrement 规则到达
✅ 方向不匹配规则不会作为候选
✅ 超过 max_steps 时返回结构化错误
✅ 非数值 current/target 返回结构化错误
✅ 输入 state 在规划后不被修改
```

---

## 本次不做（明确排除）

- 不接入 `build_rag()`
- 不保存 `CandidatePlanStep`
- 不修改 Scheduler
- 不修改 `/api/v1/solve` 请求或响应结构
- 不实现隐式数值子目标
- 不引入 `primary_feature`
- 不支持外部 `gte/lte` 目标语义

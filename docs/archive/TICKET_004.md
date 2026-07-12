# TICKET-004: V0.2 STEP 2 — 领域层架构升级

> 对应 STATE_V0.2.md → STEP 2
> 预估工作量：3-4 次对话（原估 2-3 次，因补充细节调高）

---

## 本次任务范围（只做这些）

实现 V0.2 领域层架构升级：策略模式注册表（Operator/Effect/Objective）、RuleEvaluator 统一入口、RAGBuilder 升级、Scheduler 升级、阻塞处理主流程。

**关于 API 层（solve.py）的说明**：STEP 2 允许对 `app/api/v1/solve.py` 做**最小必要改动**，仅限转发新参数（objectives/constraints/parent_plan_id/blockage_constraints）到领域层，以及为新字段写库。不重构接口契约，不新增 API 端点，不动 request/response 结构。API 接口契约的完整升级放 STEP 3。

---

## 子任务清单 + 依赖关系

```
[ 2-1 ]  OperatorRegistry + 7 Operator      ──────┐
[ 2-2 ]  EffectRegistry + 3 Effect          ──────┤──► [ 2-3 ] ──► [ 2-4 ]
[ 2-5 ]  ObjectiveRegistry + Objective       ──┬──┘                │
                                             │                    │
[ 2-6a] Scheduler not_before 约束           ──┴────────────────► [ 2-7 ]
[ 2-6b] Scheduler objectives 数组支持         ──────────────────► [ 2-7 ]
[ 2-7a] 策略 A/B/AB 编排逻辑（solver 主流程）───► step_role diff
[ 2-7b] step_role 计算算法
```

| 编号 | 内容 | 依赖 | 可并行 |
|------|------|------|--------|
| 2-1 | OperatorRegistry + 7 个 Operator | - | ✅ |
| 2-2 | EffectRegistry + 3 个 Effect | - | ✅ |
| 2-3 | RuleEvaluator（统一入口） | 2-1, 2-2 | |
| 2-4 | RAGBuilder 升级（RuleEvaluator + 循环检测 + 深度限制） | 2-3 | |
| 2-5 | ObjectiveRegistry + MinimizeMakespanObjective | - | ✅ |
| 2-6a | Scheduler not_before 约束 | 2-3 | |
| 2-6b | Scheduler objectives 数组 | 2-5 | |
| 2-7a | 阻塞处理编排主流程（策略 A/B/AB） | 2-4, 2-6a, 2-6b | |
| 2-7b | step_role 计算算法 | 2-7a | |

---

## 一、核心接口定义

### 1.1 Operator 接口

```python
# app/core/solver/operators.py

class Operator(ABC):
    """所有比较操作符的基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """操作符名称，必须与 op_rule_precond.operator 字段值一一对应。"""
        ...

    @abstractmethod
    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        """
        执行比较。

        Args:
            current_value:  当前状态中该特征的实际值（字符串）
            feature_value:  op_rule_precond 中存储的目标值（字符串）
            value_list:     op_rule_precond.value_list，op_type='in' 时使用

        Returns:
            bool: 当前值是否满足该操作符条件
        """
        ...

# 装饰器注册函数（供 OperatorRegistry 使用）
def register_operator(name: str):
    """将 Operator 子类注册到全局注册表。"""
    ...

class OperatorRegistry:
    @classmethod
    def get(cls, name: str) -> Operator:
        """根据 operator 名称获取 Operator 实例。"""
        ...

    @classmethod
    def evaluate_precond(
        cls,
        current_value: str,
        operator_name: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        """快捷方法：get(operator_name).evaluate(...)"""
        ...
```

**7 个 Operator 实现要求**：

| name | 语义 | 实现要点 |
|------|------|----------|
| `eq` | 相等 | `current_value == feature_value` |
| `neq` | 不等 | `current_value != feature_value` |
| `gt` | 大于 | `float(current_value) > float(feature_value)`；转换失败返 False |
| `gte` | 大于等于 | `float(current_value) >= float(feature_value)`；**当前代码缺失，需实现** |
| `lt` | 小于 | `float(current_value) < float(feature_value)`；转换失败返 False |
| `lte` | 小于等于 | `float(current_value) <= float(feature_value)`；**当前代码缺失，需实现** |
| `in` | 在集合中 | `value_list` 优先；若为 None 则退化解析 `feature_value` 逗号分隔 |

**注意**：`in` 操作符的 `value_list` 字段（JSONB）是专用存储，优先级高于逗号分隔的 `feature_value` 退化解析。

---

### 1.2 Effect 接口

```python
# app/core/solver/effects.py

class Effect(ABC):
    """所有状态变更效果类型的基类。"""

    @property
    @abstractmethod
    def effect_type(self) -> str:
        """效果类型名称，必须与 op_rule_effect.effect_type 值对应。"""
        ...

    @abstractmethod
    def apply(self, current_value: str | None, delta_value: float | None) -> str:
        """
        计算应用效果后的新状态值。

        Args:
            current_value: 当前状态中该特征的值，不存在时为 None
            delta_value:    op_rule_effect.delta_value（仅 increment/decrement 使用）

        Returns:
            str: 新的特征值（统一返回字符串）
        """
        ...

def register_effect(effect_type: str):
    """将 Effect 子类注册到全局注册表。"""
    ...

class EffectRegistry:
    @classmethod
    def get(cls, effect_type: str) -> Effect:
        ...

    @classmethod
    def apply(cls, current_value: str | None, effect_type: str, delta_value: float | None) -> str:
        """快捷方法：get(effect_type).apply(...)"""
        ...
```

**3 个 Effect 实现要求**：

| effect_type | 语义 | 实现要点 |
|-------------|------|----------|
| `set` | 覆盖赋值 | 返回 `new_value`（字符串）；忽略 `delta_value` |
| `increment` | 增量 | `float(current_value or 0) + delta_value`，结果转字符串 |
| `decrement` | 减量 | `float(current_value or 0) - delta_value`，结果转字符串 |

---

### 1.3 RuleEvaluator（统一入口）

```python
# app/core/solver/rule_evaluator.py

from app.core.solver.operators import OperatorRegistry
from app.core.solver.effects import EffectRegistry
from app.db.models import OpRulePrecond, OpRuleEffect
from app.core.planner.state import StateDict

class RuleEvaluator:
    """
    统一的规则评估器。
    策略模式：所有 precond 匹配和 effect 应用必须通过此类。
    """

    def evaluate_precondition(
        self,
        state: StateDict,
        precond: OpRulePrecond,
    ) -> bool:
        """
        判断 state 是否满足单个 precondition。

        委托 OperatorRegistry 执行实际比较。
        类型安全：数值比较失败（如非数字字符串）返回 False，不抛异常。
        """
        current = state.get(precond.feature_key)
        if current is None:
            return False
        return OperatorRegistry.evaluate_precond(
            current_value=current,
            operator_name=precond.operator,
            feature_value=precond.feature_value,
            value_list=precond.value_list,
        )

    def evaluate_preconditions(
        self,
        state: StateDict,
        preconditions: list[OpRulePrecond],
    ) -> bool:
        """判断 state 是否满足全部 preconditions。"""
        return all(self.evaluate_precondition(state, p) for p in preconditions)

    def apply_effect(self, state: StateDict, effect: OpRuleEffect) -> StateDict:
        """
        将单个 effect 应用于 state，返回新状态副本（不可变）。
        不修改原 state 对象。
        """
        new_state = dict(state)
        new_value = EffectRegistry.apply(
            current_value=state.get(effect.feature_key),
            effect_type=effect.effect_type,
            delta_value=effect.delta_value,
        )
        new_state[effect.feature_key] = new_value
        return new_state

    def apply_effects(
        self,
        state: StateDict,
        effects: list[OpRuleEffect],
    ) -> StateDict:
        """将多个 effects 依次应用于 state，返回最终新状态。"""
        result = dict(state)
        for e in effects:
            result = self.apply_effect(result, e)
        return result
```

**类型安全策略**：
- 所有 `float()` 强转包裹在 try/except 中，失败返回 False（而非抛异常）
- `None` 值的 increment/decrement 视为从 0 计算

---

### 1.4 Objective 接口

```python
# app/core/solver/objectives.py

from ortools.sat.python import cp_model
from app.core.scheduler.model import ScheduleModel

class Objective(ABC):
    """CP-SAT 优化目标基类。"""

    @property
    @abstractmethod
    def objective_type(self) -> str:
        """目标类型标识，必须与 objectives 数组中的 type 字段对应。"""
        ...

    @abstractmethod
    def apply_to_model(self, model: ScheduleModel) -> None:
        """将该目标注入到 CP-SAT 模型中。"""
        ...

def register_objective(objective_type: str):
    ...

class ObjectiveRegistry:
    @classmethod
    def get(cls, objective_type: str) -> Objective:
        """根据 type 获取 Objective 实例。"""
        ...

    @classmethod
    def apply_all(
        cls,
        objectives: list[dict],   # [{"type": "minimize_makespan", "weight": 1.0}, ...]
        model: ScheduleModel,
    ) -> None:
        """
        将 objectives 数组中所有目标加权求和后注入模型。
        当前 MVP 只实现 MinimizeMakespan，权重忽略。
        """
        ...
```

---

## 二、类型强转规则

> 数据库 `feature_value` / `new_value` 统一存为 `VARCHAR(256)` 字符串，
> 但 `feature_definition.value_type` 区分 `string/number/boolean/enum`。
> Operator/Effect 内部自行处理类型转换。

| feature_definition.value_type | Operator 比较方式 | Effect.apply 方式 |
|------------------------------|-------------------|-------------------|
| `string` | 字符串比较（eq/neq） | 直接写入 `new_value` 字符串 |
| `number` | `float()` 转换后数值比较 | 数值计算后转字符串（保留小数？见下） |
| `boolean` | `str → bool` 后比较 | 写入 `new_value` 字符串（`"true"/"false"`） |
| `enum` | 字符串比较（视为 string） | 写入 `new_value` 字符串 |

**数值精度规则**：
- increment/decrement 结果转字符串时，**保留最多 2 位小数**，末尾 0 省略
- 例：`3.5 + 0.3 → "3.8"`，`3.5 + 0.05 → "3.55"`

**类型转换失败处理**：
- 数值操作符（gt/gte/lt/lte）对非数字字符串返回 `False`
- increment/decrement 对非数字当前值，视为 0 处理

---

## 三、is_repair 过滤策略

> 这是策略 B 正确运作的前提条件。

**规则**：

| 调用场景 | `load_rules()` 行为 |
|----------|---------------------|
| 正常求解（build_rag） | 只加载 `is_active=True AND is_repair=FALSE` 的规则 |
| 策略 B 阻塞重排 | 加载全部 `is_active=TRUE` 规则（含 is_repair=TRUE） |

**实施方式**：

```python
# app/core/planner/matcher.py

async def load_rules(
    machine_type_id: int,
    session: AsyncSession,
    active_only: bool = True,
    include_repair: bool = False,   # 新增参数
) -> list[OpRule]:
    query = (
        select(OpRule)
        .where(OpRule.machine_type_id == machine_type_id)
        .options(...)
    )
    if active_only:
        query = query.where(OpRule.is_active == True)
        if not include_repair:
            query = query.where(OpRule.is_repair == False)   # 新增
    ...
```

**为什么这样设计**：
- 正常求解时排除 is_repair=TRUE，防止维修工序混入标准 RAG
- 策略 B 触发后，系统通过注入 `blockage_reason` 特征到 current_state，使维修工序的 precond 自然匹配，从而被自动选中——这是 RAG 自动推导的自然结果，不是特殊逻辑

---

## 四、完整数据流（阻塞处理）

```
POST /api/v1/solve
  │
  │  ┌─────────────────────────────────────────────────────────────┐
  │  │ API 层（solve.py — 最小改动，仅转发参数）                     │
  │  └─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  build_rag(current_state_id, target_state_id, session,          │
│              include_repair=False)                               │
│  ─ 常规求解：load_rules(include_repair=False)                    │
│  ─ 策略 B：先注入 blockage_reason → load_rules(include_repair=True)│
└─────────────────────────────────────────────────────────────────┘
  │ RAG（可能含维修节点）
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  save_candidate_plan(rag, solve_request_id, session,            │
│                      version=, parent_plan_id=, replan_reason=) │
│  ─ 写入 candidate_plan（version/parent_plan_id/replan_reason）    │
│  ─ 写入 candidate_plan_step（not_before/step_role=draft）        │
│  ─ 写入 blockage_event（策略 B 时）                              │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  solve_schedule(plan_id, session,                               │
│                 objectives=, constraints=)                       │
│  ─ load_rag() → 读 StepData（含 not_before）                    │
│  ─ build_model() → CP-SAT（含 not_before 约束 + objectives 数组） │
│  ─ solver.solve()（asyncio.to_thread 包装）                      │
│  ─ save_schedule_result()                                        │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  step_role 标注（solve_schedule 返回后，在同一 async 函数内）      │
│  ─ compute_step_role_diff(new_plan_id, parent_plan_id, session)  │
│  ─ 回写 candidate_plan_step.step_role                           │
└─────────────────────────────────────────────────────────────────┘
```

**关键说明**：

1. **blockage_reason 注入**：策略 B 时，在调用 `build_rag()` 前，将 `blockage_reason` 特征写入 current_state 的特征副本（不影响数据库原始状态）。写入值为 `blockage_event.blockage_reason`。

2. **not_before 来源**：`candidate_plan_step.not_before` 由调用方（solve.py 或独立编排函数）写入，Scheduler 的 `load_rag()` 读取该字段并在 CP-SAT 建模时注入 `start >= not_before` 约束。

3. **版本链写入时机**：`save_candidate_plan()` 在写入 DB 时完成 version 自增和 parent_plan_id 赋值。

4. **session.commit() 归属**：移除领域层的 `session.commit()` 后，commit 由最外层调用方控制（即 `solve.py` 中已有的 `await db.commit()` 调用）。

---

## 五、step_role 计算算法

```python
# app/core/solver/step_role.py

from typing import Optional

async def compute_step_role_diff(
    new_plan_id: int,
    parent_plan_id: Optional[int],   # None 表示初次求解
    session: AsyncSession,
) -> dict[int, str]:
    """
    计算并回写 step_role。

    返回值：{step_order: step_role}
    同时回写 DB：candidate_plan_step.step_role

    算法：
      1. parent_plan_id 为 None → 全部步骤 step_role = 'normal'
      2. 否则，对新计划每个 step：
         a. 在父计划中找同 op_rule_id 的步骤
            - 找不到 → step_role = 'repair'
            - 找到 → 比较 start_min
               · 新 start < 父 start → 'pulled_forward'
               · 新 start > 父 start → 'delayed'
               · 相等 → 'normal'
      3. 父计划有、新计划没有的步骤 → 忽略（不在本次 diff 范围内）
    """
    ...
```

**匹配键**：`op_rule_id`（工序规则 ID）

**维修工序识别**：新计划中出现 `op_rule.is_repair=TRUE` 的步骤（父计划中不存在同 ID），一定标注为 `repair`，即使其 start_min 早于父计划中某步骤。

---

## 六、子任务详情

### 2-1：OperatorRegistry + 7 Operator

**新增文件**：`app/core/solver/operators.py`

**验收条件**：
- 7 个 Operator（eq/neq/gt/gte/lt/lte/in）全部实现
- 使用 `@register_operator` 装饰器注册，禁止 if/elif 分发
- `OperatorRegistry.get()` 对未知 operator 抛出 `KeyError`
- `in` 操作符优先使用 `value_list`；无 value_list 时退化解析 `feature_value` 逗号分隔
- 每个 Operator 有独立单元测试（pytest fixture 测试 7 个操作符对各种 value_type 的行为）

### 2-2：EffectRegistry + 3 Effect

**新增文件**：`app/core/solver/effects.py`

**验收条件**：
- 3 个 Effect（set/increment/decrement）全部实现
- 使用 `@register_effect` 装饰器注册，禁止 if/elif 分发
- increment/decrement 的 `delta_value` 为 None 时视为 0
- 数值结果保留最多 2 位小数
- 每个 Effect 有独立单元测试

### 2-3：RuleEvaluator

**新增文件**：`app/core/solver/rule_evaluator.py`

**验收条件**：
- `evaluate_precondition(state, precond)` 正确委托 OperatorRegistry
- `evaluate_preconditions(state, list[precond])` 返回 all-match
- `apply_effect(state, effect)` 返回新状态副本，不修改原 dict
- `apply_effects(state, list[effect])` 链式调用 apply_effect
- 类型转换失败返回 False / 视为 0，不抛异常

### 2-4：RAGBuilder 升级

**修改文件**：`app/core/planner/search.py` + `matcher.py` + `executor.py` + `state.py`

**修改要点**：
1. `search.py:207-209`：`current_state[precond.feature_key] == precond.feature_value` → `RuleEvaluator().evaluate_precondition(current_state, precond)`
2. `matcher.py:check_preconditions()`：委托 `RuleEvaluator().evaluate_preconditions()`
3. `executor.py:apply_effects()`：委托 `RuleEvaluator().apply_effects()`
4. `state.py:state_matches_precondition()`：**保留作为向后兼容 thin wrapper**，内部调用 OperatorRegistry；对 gte/lte/in 改用 OperatorRegistry（替换掉原来 raise ValueError 的分支）
5. `search.py`：循环检测已有（`has_cycle()`），确认 max_ops=50 深度限制在 while 循环中生效
6. `matcher.py:load_rules()`：新增 `include_repair=False` 参数

**验收条件**：
- search.py 中不再有硬编码 `==` 的 precondition 比较
- 场景 4（循环检测）和场景 5（类型安全 gte/lte 数值比较）通过

### 2-5：ObjectiveRegistry + MinimizeMakespanObjective

**新增文件**：`app/core/solver/objectives.py`

**验收条件**：
- `MinimizeMakespanObjective.objective_type = "minimize_makespan"`
- `ObjectiveRegistry.get("minimize_makespan")` 返回正确实例
- `ObjectiveRegistry.apply_all([{"type":"minimize_makespan","weight":1.0}])` 正确注模
- `build_model()` 当前只用单目标（多目标加权暂不实现）

### 2-6a：Scheduler not_before 约束

**修改文件**：`app/core/scheduler/loader.py` + `model.py`

**修改要点**：
1. `loader.py`：`StepData` 新增 `not_before: Optional[int] = None`；`load_rag()` 中从 `candidate_plan_step.not_before` 填充该字段
2. `model.py:build_model()`：在 precedence 约束之后、资源约束之前，新增：
   ```python
   for step in rag_data.steps:
       if step.not_before is not None:
           model.add(task_vars[step.step_order].start >= step.not_before)
   ```

### 2-6b：Scheduler objectives 数组

**修改文件**：`app/core/scheduler/model.py`

**修改要点**：
- `build_model()` 新增参数 `objectives: list[dict] = [{"type": "minimize_makespan", "weight": 1.0}]`
- 内部调用 `ObjectiveRegistry.apply_all(objectives, self)`
- 当前 MVP：权重忽略，只实现 minimize_makespan

### 2-7a：阻塞处理编排主流程

**修改文件**：`app/api/v1/solve.py`（最小必要改动）

**修改要点**：

1. `SolveRequest` 构造时写入新字段：
   ```python
   solve_req = SolveRequest(
       ...
       objectives=request.objectives,
       constraints=request.constraints,
       parent_plan_id=request.parent_plan_id,
   )
   ```

2. 策略 B 时注入 `blockage_reason` 到当前状态特征副本（**不在 DB 中修改原始 current_state**）

3. 根据策略类型调用 `load_rules(include_repair=...)`

4. `solve_schedule()` 传入 `objectives` 和 `constraints` 参数

5. `save_candidate_plan()` 写入 `version`、`parent_plan_id`、`replan_reason`

6. `save_schedule_result()` 之后调用 `compute_step_role_diff()`

**注意**：策略 A/B/AB 的判断逻辑在 solve.py 中根据 `request.blockage_constraints` 的 `strategy` 字段路由。

### 2-7b：step_role 计算算法实现

**新增文件**：`app/core/solver/step_role.py`

**验收条件**：实现上述"第四節"中的完整算法，包含：
- parent_plan_id=None 时全 normal
- repair / pulled_forward / delayed / normal 四种角色
- op_rule.is_repair=TRUE 的新步骤一定标 repair

---

## 七、已知待修复问题（一并处理）

| 位置 | 问题 | 修复方式 |
|------|------|----------|
| `solver.py:115` | `solver.solve()` 同步阻塞 event loop | `asyncio.to_thread(solver.solve, schedule_model.model)` |
| `search.py:207-209` | precondition 硬编码 `==`，忽略 operator | 改用 `RuleEvaluator().evaluate_precondition()` |
| `search.py:351` | `session.commit()` 在领域层 | 移除；由 solve.py 控制 commit |
| `solver.py:305` | `session.commit()` 在领域层 | 移除；由 solve.py 控制 commit |

---

## 八、本次不做（明确排除）

| 排除项 | 原因 | 归属 |
|--------|------|------|
| API 接口契约变更（新增端点、request/response 结构变更） | STEP 3 独立 TICKET | STEP 3 |
| 前端改造 | STEP 4 独立 TICKET | STEP 4 |
| feature_definition CRUD API | STEP 3 | STEP 3 |
| 多目标优化（权重加权求和） | MVP 只实现 minimize_makespan | V0.3+ |
| 增量重排（而非一次性完整重新求解） | V0.2 规格确定一次性求解 | V0.3+ |
| `in` 操作符 value_list 字段的数据库唯一约束 | 长期数据完整性问题 | 后续 |

---

## 九、验证要求

### 9.1 零侵入验证

`blockage_constraints=None` 时：
- POST /solve 行为与当前 V0.1 **完全一致**（80 个现有测试全部通过）
- 所有新增逻辑（RuleEvaluator/EffectRegistry/ObjectiveRegistry）不改变现有求解结果

### 9.2 新增测试

| 测试类型 | 覆盖内容 | 数量 |
|----------|----------|------|
| 单元测试 | 每个 Operator 独立测试（含 gte/lte/in） | ≥7 |
| 单元测试 | 每个 Effect 独立测试（含 increment/decrement 边界） | ≥3 |
| 单元测试 | RuleEvaluator 组合测试 | ≥3 |
| 单元测试 | step_role 算法（normal/repair/pulled_forward/delayed） | ≥4 |
| 集成测试 | 策略 A 场景 | ≥2 |
| 集成测试 | 策略 B 场景（维修序列插入） | ≥2 |
| 集成测试 | 策略 AB 场景 | ≥2 |
| 集成测试 | 循环检测场景 | ≥1 |
| 集成测试 | 数值类型比较（gte/lte） | ≥2 |

### 9.3 验收场景（STATE_V0.2.md）

| 场景 | 要求 | 优先级 |
|------|------|--------|
| 场景 4 | 循环检测不死循环 | 必须 |
| 场景 5 | gte/lte 数值类型安全比较 | 必须 |
| 场景 1 | 策略 A not_before 约束 | 必须 |
| 场景 2 | 策略 B 维修序列插入 | 必须 |
| 场景 3 | 策略 AB | 必须 |

---

## 十、完成标准

- [x] 本 TICKET 评审通过
- [x] 所有新增测试通过
- [x] 80 个现有测试继续通过（零侵入）
- [x] 验收场景 1-5 全部通过
- [x] OperatorRegistry / EffectRegistry / ObjectiveRegistry 使用装饰器注册
- [x] 注册表内部无 if/elif 分支分发
- [x] `state_matches_precondition()` 的 if/elif 分发已消除
- [x] 领域层 `session.commit()` 调用已移除
- [x] `solve.py` 正确写入 objectives/constraints/parent_plan_id 并转发参数

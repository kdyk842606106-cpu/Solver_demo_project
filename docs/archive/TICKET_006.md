# TICKET-006: V0.2 STEP 2 准出审视修复 — 测试质量门禁达标

> 对应 STATE_V0.2.md → STEP 2（最终准出）
> 前置依赖：TICKET-005 已完成
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

修复 STEP 2 准出审视中发现的 3 项阻塞/必须修复问题，使 STEP 2 满足零跳过、零死代码的质量门禁要求。

**不做**：不新增功能、不改 API 契约、不改数据模型、不动前端、不处理建议改进项。

---

## 审视发现的缺陷清单

| # | 严重度 | 缺陷描述 | 涉及文件 |
|---|--------|----------|----------|
| F1 | 阻塞 | 17 处 `pytest.skip` 逃逸 infeasible，违反 Q3 门禁（0 跳过要求） | `tests/integration/test_blockage_strategies.py` |
| F2 | 必须 | `TestStrategyAB` 类重复定义，第一个类（行 316-364）是死代码 | `tests/integration/test_blockage_strategies.py` |
| F3 | 必须 | `effects_satisfy_precondition` 死导入未使用 | `app/core/planner/search.py:29` |

---

## 子任务清单

```
[ F3 ]  删除 search.py 死导入                    ── 独立，可先做
[ F2 ]  删除重复 TestStrategyAB 类（行 316-364）  ── 独立
[ F1 ]  移除 17 处 pytest.skip，替换为 assert     ── 最后做（需确保种子数据 feasible）
```

---

## 一、各子任务详细要求

### F1：移除 pytest.skip 逃逸 infeasible（阻塞级）

**修改文件**：`tests/integration/test_blockage_strategies.py`

**问题描述**：
17 处测试使用 `pytest.skip(...)` 在 scheduler 返回 infeasible 或 planner 返回 no_solution 时跳过测试。这违反 TICKET-005 验收门禁 Q3：
> "集成测试中不允许用 `pytest.skip` 逃逸 scheduler infeasible（测试数据必须保证 feasible）"

如果种子数据/资源配置有问题，所有这些测试将**静默跳过而非报错**，测试形同虚设。

**具体位置**（17 处）：
- 行 193: `pytest.skip(f"Scheduler returned infeasible (resource constraints): ...")`
- 行 235: `pytest.skip(f"Scheduler returned infeasible: ...")`
- 行 306: `pytest.skip(f"Scheduler returned infeasible: ...")`
- 行 362: `pytest.skip(f"Scheduler returned infeasible: ...")`
- 行 381: `pytest.skip(f"build_rag returned no_solution: ...")`
- 行 394: `pytest.skip(f"build_rag returned no_solution: ...")`
- 行 483: `pytest.skip(f"Scheduler returned infeasible: ...")`
- 行 518: `pytest.skip(f"Parent scheduler infeasible: ...")`
- 行 550: `pytest.skip(f"New plan scheduler infeasible: ...")`
- 行 590: `pytest.skip(f"Parent scheduler infeasible: ...")`
- 行 622: `pytest.skip(f"Child plan scheduler infeasible: ...")`
- 行 669: `pytest.skip(f"Parent scheduler infeasible: ...")`
- 行 691: `pytest.skip(f"Child plan scheduler infeasible: ...")`
- 行 734: `pytest.skip(f"Scheduler returned infeasible: ...")`
- 行 749: `pytest.skip("Parent build returned no_solution")`
- 行 764: `pytest.skip("New build returned no_solution")`
- 行 782: `pytest.skip(f"Scheduler returned infeasible: ...")`

**修复方案**：

将所有 `pytest.skip(...)` 替换为断言失败：

```python
# 原代码（错误）
if sched_result.status == "infeasible":
    pytest.skip(f"Scheduler returned infeasible: {sched_result.error_message}")

# 修复后（正确）
assert sched_result.status in ("optimal", "feasible"), \
    f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
```

对于 `build_rag` 返回 `no_solution` 的情况：

```python
# 原代码（错误）
if result.status == "no_solution":
    pytest.skip(f"build_rag returned no_solution: {result.error_message}")

# 修复后（正确）
assert result.status == "success", \
    f"Expected successful RAG build, got {result.status}: {result.error_message}"
```

**验证要求**：
- 修复后运行 `pytest tests/integration/test_blockage_strategies.py -v`
- 必须 0 失败、0 跳过
- 如果出现断言失败，说明种子数据有问题，需要修复种子数据（不是回退到 pytest.skip）

---

### F2：删除重复 TestStrategyAB 类定义

**修改文件**：`tests/integration/test_blockage_strategies.py`

**问题描述**：
同一文件中定义了两个 `class TestStrategyAB`：
- 第一个：行 316-364（1 个测试 `test_strategy_ab_combined`）
- 第二个：行 435-563（2 个测试 `test_strategy_ab_combined` + `test_strategy_ab_step_roles`）

Python 类重定义行为导致第一个类被完全覆盖，成为死代码。pytest 只会收集第二个类的 2 个测试。

**修复方案**：

删除第一个 `TestStrategyAB` 类（行 316-364 整个类定义）。

**理由**：
- 第二个类的 `test_strategy_ab_combined` 断言更强（包含 repair 步骤验证 + not_before 约束验证）
- 第二个类还有额外的 `test_strategy_ab_step_roles` 测试
- 保留第二个类即可满足 TICKET-005 D3 要求（策略 AB >= 2 个测试）

**删除范围**：
```python
# 删除从行 316 到行 364 的整个类定义
class TestStrategyAB:
    """Test Strategy AB: combined not_before + repair sequence."""

    @pytest.mark.asyncio
    async def test_strategy_ab_combined(self, integration_session):
        # ... 整个测试方法
```

---

### F3：删除 search.py 死导入

**修改文件**：`app/core/planner/search.py`

**问题描述**：
行 29 导入了 `effects_satisfy_precondition`，但在整个文件中从未使用。

```python
from app.core.planner.executor import effects_satisfy_precondition  # 未使用
```

**修复方案**：

删除该行导入语句。

**理由**：
- 类似于 TICKET-005 D7 修复的 `objectives.py` 死导入
- 保持代码整洁，避免误导审阅者

---

## 二、验收标准（强制门禁）

### 代码修复完成标准

- [x] F1: 17 处 `pytest.skip` 全部替换为 `assert`
- [x] F2: 第一个 `TestStrategyAB` 类（行 316-364）已删除
- [x] F3: `search.py:29` 死导入已删除

### 测试门禁（G1-G7）

| # | 门禁 | 验证命令 | 要求 |
|---|------|----------|------|
| G1 | 全量测试通过 | `pytest tests/ -v` | 0 失败、**0 跳过** |
| G2 | 集成测试通过 | `pytest tests/integration/ -v` | 0 失败、**0 跳过** |
| G3 | 单元测试通过 | `pytest tests/unit/ -v` | 0 失败 |
| G4 | 阻塞策略测试通过 | `pytest tests/integration/test_blockage_strategies.py -v` | 0 失败、**0 跳过** |
| G5 | 无 pytest.skip 残留 | `rg "pytest\.skip" tests/integration/test_blockage_strategies.py` | 0 匹配 |
| G6 | 无重复类定义 | `rg "^class TestStrategyAB" tests/integration/test_blockage_strategies.py` | 仅 1 匹配（行 435） |
| G7 | 无死导入 | `rg "effects_satisfy_precondition" app/core/planner/search.py` | 0 匹配 |

### 质量门禁（Q1-Q2）

| # | 门禁 | 验证方式 | 要求 |
|---|------|----------|------|
| Q1 | 策略 AB 测试数量 | 手动计数第二个 `TestStrategyAB` 类中的测试方法 | >= 2 个 |
| Q2 | 测试断言充分性 | 代码审查 `test_strategy_ab_combined` | 必须包含 repair 步骤验证 + not_before 约束验证 |

---

## 三、完成标准

- [ ] F1: 17 处 pytest.skip 全部替换为 assert
- [ ] F2: 重复 TestStrategyAB 类已删除
- [ ] F3: search.py 死导入已删除
- [ ] 强制门禁 G1-G7 全部通过
- [ ] 质量门禁 Q1-Q2 全部通过
- [ ] `pytest tests/ -v` 输出：0 失败、0 跳过
- [ ] STATE_V0.2.md STEP 2 状态确认为 `[✅] 已完成（准出审视通过）`

---

## 四、本次不做（明确排除）

| 排除项 | 原因 |
|--------|------|
| 建议改进项 1-6 | 非阻塞，可延后到 STEP 3 或技术债清理阶段 |
| `model.py` ↔ `objectives.py` 循环依赖 | 中等严重度，不影响功能，可延后重构 |
| `parent_steps_by_rule` dict 覆盖问题 | 中等严重度，边缘场景，可延后修复 |
| `RuleEvaluator()` 循环内实例化优化 | 性能优化，非功能缺陷 |
| `solve.py` 遗留单 objective 校验 | STEP 3 API 升级时统一处理 |
| 新增功能 | 本 TICKET 只做缺陷修复 |
| API 契约变更 | STEP 3 范围 |
| 数据模型变更 | 无需求 |
| 前端改造 | STEP 4 范围 |

---

## 五、执行顺序建议

```
1. F3（最简单，独立）
   └─ 删除 search.py:29 死导入

2. F2（独立，无依赖）
   └─ 删除 test_blockage_strategies.py:316-364 重复类

3. F1（最复杂，需验证种子数据）
   ├─ 替换 17 处 pytest.skip 为 assert
   ├─ 运行测试验证
   └─ 如有失败，修复种子数据（不是回退 pytest.skip）
```

---

## 六、风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| F1 修复后测试失败（种子数据 infeasible） | 中 | 高 | 检查 Resource 表容量配置，确保 TECHNICIAN 等资源容量 >= 并发需求 |
| F1 修复后测试失败（RAG no_solution） | 低 | 中 | 检查 OpRule precondition 是否过严，或 state 特征值不匹配 |
| 删除第一个 TestStrategyAB 后测试覆盖不足 | 极低 | 低 | 第二个类已有 2 个测试且断言更强，满足要求 |

---

## 七、参考资料

- STEP 2 准出审视报告（本次对话输出）
- TICKET-005 验收门禁定义
- STATE_V0.2.md STEP 2 验收场景
- ANCHOR.md 测试约束（约束 9-10）

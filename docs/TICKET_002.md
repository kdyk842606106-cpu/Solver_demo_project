# TICKET-002: 修复 MissingGreenlet 异步测试失败

> 对应 STATE_V0.2.md → 技术债修复
> 预估工作量：0.5 次对话

---

## 问题描述

3 个单元测试因 `MissingGreenlet` 错误失败：

```
FAILED tests/unit/test_models.py::TestMachineState::test_create_machine_state
  sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
FAILED tests/unit/test_models.py::TestMachineState::test_state_features_as_dict
  sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
FAILED tests/unit/test_models.py::TestOpRule::test_create_op_rule_with_precond_and_effect
  sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
```

## 根本原因

测试中访问 lazy-loaded 关系属性（如 `saved.features`）时，SQLAlchemy 尝试同步加载关系，但在异步上下文中没有 greenlet 上下文。

```python
# test_create_machine_state (line 167)
result = await async_session.execute(select(MachineState).where(...))
saved = result.scalar_one()
assert len(saved.features) == 2  # ← 这里触发 MissingGreenlet
```

`MachineState.features` 关系使用默认 `lazy='select'`，当在 async 测试中同步访问时触发。

## 影响范围

- 3/79 测试失败（其余通过）
- 集成测试中部分 `'error'` 返回值也源于此（异常向上传播）

## 修复方案

在查询时使用 `selectinload` 预加载关系，或在访问前 `await async_session.refresh()`：

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# 方案 A：查询时预加载
result = await async_session.execute(
    select(MachineState).where(MachineState.id == state.id).options(selectinload(MachineState.features))
)

# 方案 B：refresh 时指定要刷新的关系
await async_session.refresh(saved, ['features'])
```

## 子任务清单

```
□ 2-1  修复 TestMachineState.test_create_machine_state
□ 2-2  修复 TestMachineState.test_state_features_as_dict
□ 2-3  修复 TestOpRule.test_create_op_rule_with_precond_and_effect
□ 2-4  验证全部 79 测试通过
```

## 验证方法

```bash
python -m pytest tests/unit/test_models.py -v
python -m pytest tests/ -v --ignore=tests/integration/test_master_data_api.py
```

## 本次不做（明确排除）

- 不修改 `app/db/models.py` 中的 `lazy` 默认值（保持 `select`，避免影响生产代码）
- 不修改 `conftest.py` 全局配置
- 不修复 `tests/integration/test_master_data_api.py` 的 conftest 冲突（独立问题）

## 完成标准

- `python -m pytest tests/unit/test_models.py -v` 全部通过
- `python -m pytest tests/ --ignore=tests/integration/test_master_data_api.py -v` 至少 76+ 通过（允许 3 个 `MissingGreenlet` 之外的稳定失败）

# TICKET-001: V0.2 STEP1 数据模型扩展

> 对应 STATE_V0.2.md → STEP 1
> 预估工作量：1-2 次对话

---

## 本次任务范围（只做这些）

执行 V0.2 数据模型扩展：新增表、扩展字段、编写 Alembic 迁移、更新 ORM 模型和 Pydantic Schema、写入种子数据。

## 子任务清单

```
□ 1-1  新增 feature_definition 表 + ORM Model + Schema
□ 1-2  op_rule_precond 新增 operator / value_list 字段
□ 1-3  op_rule_effect 新增 effect_type / delta_value 字段
□ 1-4  op_rule 新增 is_repair / valid_from / valid_to 字段
□ 1-5  solve_request 新增 objectives / constraints / parent_plan_id 字段
□ 1-6  candidate_plan 新增 version / parent_plan_id / replan_reason / status 字段
□ 1-7  candidate_plan_step 新增 not_before / step_role 字段
□ 1-8  新增 blockage_event 表 + ORM Model + Schema
□ 1-9  种子数据：feature_definition 基础特征 + OP_REPAIR_HARDWARE / OP_REPAIR_APPROVAL 规则
```

## 输入（已知信息）

- 完整字段定义见 STATE_V0.2.md "本版本数据模型变更" 区块
- SQL 迁移清单见 v0.2-spec.md 第二节
- 详细 SQL 见 总AICONTEXT.md 附录 C（作为参考）
- 现有 ORM 在 app/db/models.py，Schema 在 app/db/schemas.py
- 现有迁移在 migrations/versions/001_initial.py

## 输出要求

1. **Alembic 迁移文件** `migrations/versions/002_v0.2_model_extension.py`
   - 按顺序执行所有 ALTER TABLE 和 CREATE TABLE
   - 包含 downgrade 函数

2. **ORM 模型更新** `app/db/models.py`
   - 新增 FeatureDefinition, BlockageEvent 模型
   - 现有模型新增字段（保持与迁移一致）
   - 所有新字段有合理默认值

3. **Pydantic Schema 更新** `app/db/schemas.py`
   - 新增对应的 Create/Read Schema
   - 新字段标注 Optional 或有默认值，确保向后兼容

4. **种子数据 SQL** `seeds/003_v0.2_seed_data.sql`
   - feature_definition: temperature_level, calibration_status, cleanliness, integration_status, blockage_reason, pressure_bar
   - OP_REPAIR_HARDWARE (is_repair=TRUE, precond: blockage_reason=hardware_fault)
   - OP_REPAIR_APPROVAL (is_repair=TRUE, precond: blockage_reason=pending_approval)

5. **验证**
   - alembic upgrade head 执行成功
   - 种子数据加载成功
   - 现有测试不被破坏（新字段有默认值）

## 本次不做（明确排除）

- 领域层代码改造（TICKET-002: STEP 2）
- API 层改造（TICKET-003: STEP 3）
- 前端改造（TICKET-004: STEP 4）

## 完成标准

- alembic upgrade head 无报错
- seeds/003 加载成功
- pytest 现有测试全部通过
- app/db/models.py 包含所有 V0.2 新增字段和新表
- app/db/schemas.py 包含对应 Schema

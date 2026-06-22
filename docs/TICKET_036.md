# TICKET-036: 状态目标与活动能力模型及交互重构

> Status: implemented
> Version: V0.3
> Requirement source: user planning discussion, 2026-06-22
> Depends on: `docs/TICKET_024.md`, `docs/TICKET_025.md`, `docs/TICKET_026.md`, `docs/TICKET_027.md`, `docs/TICKET_030.md`, `docs/TICKET_035.md`

## Scope

本工单将原“状态目标 / 活动能力 UI 改进”扩展为完整的第一版模型重构：

- 状态侧从固定三级改为任意深度状态树。
- 无子节点状态自动作为原子状态；有子节点状态作为聚合状态包。
- 普通维护流隐藏显式特征定义，创建/更新原子状态时后端自动确保 `feature_definition` 和 `state_feature_def` 存在。
- 活动侧新增可复用 `atomic_activity`，二级活动包通过引用表挂载原子活动。
- `op_rule` 支持 `atomic_activity_id`，旧 `activity_node_id` 保留兼容。
- 展开、健康检查、分层求解、维护求解、Scheduler loader 和场景导入兼容新模型。
- Data Management 集成低保真但真实可交互的状态目标工作台和活动能力工作台。

## Implemented

- [x] 新增 Alembic migration `007_atomic_activity_refactor.py`
  - `state_node.level` 放宽为 `level >= 1`
  - 新增 `atomic_activity`
  - 新增 `activity_package_atomic_ref`
  - `op_rule` 新增 `atomic_activity_id`
  - 旧三级 `activity_node` 自动迁移为原子活动和二级包引用

- [x] 后端模型与 Schema
  - `MachineType.atomic_activities`
  - `ActivityNode.atomic_refs`
  - `AtomicActivity`
  - `ActivityPackageAtomicRef`
  - `OpRule.atomic_activity_id`
  - 原子活动 CRUD 与包引用 CRUD schema
  - 展开/健康响应透出 `atomic_activity_id`

- [x] Master Data API
  - `GET/POST /machine-types/{id}/atomic-activities`
  - `PUT/DELETE /atomic-activities/{id}`
  - `GET/POST /activity-nodes/{package_id}/atomic-activity-refs`
  - `DELETE /activity-package-atomic-refs/{id}`
  - `OpRuleCreate/Update` 支持 `atomic_activity_id`
  - 状态节点支持任意正整数 level
  - 原子状态仅支持 `operator=eq`
  - 聚合状态不允许绑定事实
  - 有子节点状态必须保持聚合
  - 创建/更新原子状态自动补齐特征定义

- [x] 展开与求解兼容
  - 状态目标展开递归寻找无子节点叶子，不再依赖 `level == 3`
  - 同一展开范围内同一 `feature_key` 多目标值返回 `CONFLICTING_GOAL`
  - 活动范围展开支持一级/二级包到原子活动引用
  - 多包复用同一原子活动时按 `atomic_activity_id` 去重
  - 旧三级活动节点仍可展开，避免破坏已有数据
  - Scope Guard 继续从一级/二级包继承到原子活动有效规则
  - 分层/维护求解继续生成 candidate plan 和 schedule
  - Scheduler loader 对原子活动规则填充活动显示元数据

- [x] 场景导入兼容
  - 新增 `atomic_activities` sheet
  - 新增 `activity_package_atomic_refs` sheet
  - `rules.atomic_activity_code` 作为新规则绑定入口
  - 旧 `rules.activity_node_code` 仍兼容
  - 旧三级 `activity_nodes` 导入时自动派生原子活动和二级包引用
  - `state_nodes` 支持任意正整数 level
  - 状态叶子导入可自动补齐特征定义
  - 模板示例切换为一级/二级包 + 原子活动 + 包引用

- [x] 前端交互草图并集成
  - 新增 `StateTargetWorkspace.vue`
  - 重写 `ActivityCapabilityWorkspace.vue`
  - 重写 Data Management 入口页，状态目标不再使用旧折叠面板
  - 前端 API 新增原子活动和引用封装
  - 导入摘要展示原子活动和包引用计数

## Deferred

- 共享原子活动在 Scheduler 连续性目标中的归属策略仍作为遗留问题。
- 原子活动规则的完整新建/编辑表单未在本工作台内重做，当前仍通过已有规则 API/规则维护入口承接。
- Solve 页面仍保留部分“三级活动”显示文案，后续可改为“执行活动/原子活动”。
- 活动包固定执行序列、固定重复次数、硬连续性不进入本轮。

## Verification

- `python -m compileall app\api\v1\master_data.py app\services\layered_expansion.py app\services\layered_health.py app\services\layered_solve.py app\services\scenario_import.py app\core\scheduler\loader.py app\db\models.py app\db\schemas.py`
- `python -m pytest tests\integration\test_layered_activity_state_api.py`
- `python -m pytest tests\integration\test_scenario_import_api.py`
- `python -m pytest` (313 passed)
- `npm run build`

## Notes

- 活动 API 仍允许旧三级 `activity_node` 写入，以保留导入和既有测试兼容；新 Data Management 工作台只创建一级/二级活动包，原子活动通过 `atomic_activity` 维护。
- 原子活动在展开响应中使用 `atomic_activity_id` 表达真实身份；兼容字段 `activity_node_id` 对原子活动使用负值合成 ID，避免与真实活动包 ID 冲突。

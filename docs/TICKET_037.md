# TICKET-037: 网络编辑器绑定模型与 API

> Status: implemented
> Version: V0.3
> Completed: 2026-06-23
> Depends on: `docs/TICKET_036.md`, `docs/superpowers/specs/2026-06-23-state-activity-network-editor-design.md`

## Scope

本工单实现网络编辑器的后端语义层，不替换现有求解模型：

- 新增状态包成员引用表 `state_node_reference`。
- 新增状态-活动绑定表 `activity_state_binding`。
- 提供引用、绑定和覆盖刷新 CRUD API。
- 对可执行活动绑定同步 `op_rule.preconditions/effects`。
- 保持 `state_node`、`activity_node`、`atomic_activity`、`op_rule` 为 canonical 数据。

## Implemented

- [x] Alembic migration `008_network_editor_bindings.py`
- [x] ORM 模型：
  - `StateNodeReference`
  - `ActivityStateBinding`
- [x] Pydantic Schema：
  - 引用 create/response
  - 绑定 create/update/response
- [x] Master Data API：
  - `GET /machine-types/{id}/state-node-references`
  - `POST /state-nodes/{id}/references`
  - `DELETE /state-node-references/{id}`
  - `GET /machine-types/{id}/activity-state-bindings`
  - `POST /activity-state-bindings`
  - `PUT /activity-state-bindings/{id}`
  - `DELETE /activity-state-bindings/{id}`
  - `POST /activity-state-bindings/{id}/refresh-coverage`
- [x] 引用约束：
  - 同机型
  - 禁止自引用
  - 默认所在状态包 + 成员引用无环
  - 重复引用返回 409
- [x] 绑定约束：
  - `activity_node_id` / `atomic_activity_id` 二选一
  - 虚拟活动仅允许一级/二级 `activity_node`
  - 虚拟活动仅允许 `context_input` / `declared_output` 角色
  - 可执行活动仅允许 `input` / `output` 角色
  - 原子活动绑定要求明确 `op_rule_id`
  - 已有绑定不允许通过 PUT 改变 `machine_type_id`
  - 聚合状态绑定为 `state_package`
  - 叶子状态绑定为 `atomic_state`
- [x] 覆盖快照：
  - 默认展开当前绑定状态下所有 active leaf
  - 状态包成员引用按显示 DAG 展开引用子树叶子
  - 返回前重算 `complete` / `partial` / `stale`
  - 支持显式刷新覆盖快照
- [x] 规则同步：
  - executable input -> `op_rule_precond`
  - executable output -> `op_rule_effect`
  - 绑定覆盖缩小、停用或删除时，清理不再由任何 active binding 需要的旧 precondition/effect
  - 通过 `activity_state_binding.metadata_json._network_editor_managed_rule_facts` 记录绑定层接管的事实；删除绑定时不清理原本手写在 `op_rule` 上的同名 precondition/effect
  - 不修改 duration/resource/is_repair 等规则字段

## Verification

- `python -m pytest tests\integration\test_layered_activity_state_api.py -q`
- `python -m pytest tests\integration\test_scenario_import_api.py -q`
- `python -m pytest -q`

Final full backend regression after this ticket series: 321 passed.

## Notes

- 2026-06-24 补强：规则同步新增绑定层 provenance，只有网络编辑器实际新增或由其他 active binding 共同接管的 `op_rule_precond/effect` 会在覆盖缩小、停用或删除时被清理；如果同名 fact 原本手写在 `op_rule` 上，创建再删除 binding 后仍保留。回归：`python -m pytest tests\integration\test_layered_activity_state_api.py::test_network_editor_activity_state_bindings_coverages_and_rule_sync -q` 1 passed；`python -m pytest tests\integration\test_layered_activity_state_api.py -q` 15 passed；`python -m pytest tests\integration\test_scenario_import_api.py -q` 9 passed；`python -m pytest -q` 321 passed；`npm run build` passed。未启动后端服务，未执行 `/health` HTTP 探测。
- 2026-06-24 补强：状态包覆盖计算纳入 `state_node_reference` 显示 DAG；状态包成员引用实例作为绑定状态时，默认覆盖和刷新覆盖都会包含引用子树叶子，并同步到 `op_rule_precond/effect`。回归：网络编辑器集成测试 14 passed；全量后端 320 passed。

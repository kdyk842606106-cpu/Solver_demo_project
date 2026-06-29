# TICKET-040: 求解预检与求解器准备交接

> Status: implemented  
> Version: V0.3  
> Completed: 2026-06-23  
> Depends on: `docs/TICKET_038.md`, `docs/TICKET_039.md`

## Scope

本工单实现网络编辑器到现有 `/solve/layered` 的求解器准备交接。求解预检只做数据库交接就绪检查和摘要展示，不启动 Scheduler，不生成独立导出文件。

## Implemented

- [x] 求解预检 API：
  - `POST /api/v1/machine-types/{id}/network-editor/solver-precheck`
  - 旧 `POST /api/v1/machine-types/{id}/network-editor/export-preview` 仅作为 deprecated 兼容别名保留。
- [x] 求解预检内容：
  - 可执行原子活动
  - 关联 `op_rule`
  - 虚拟活动继承前置
  - 可执行活动自身输入
  - 可执行活动自身输出
  - 状态聚合 `AND` 规则
  - 虚拟活动 group/WBS 元数据
  - 资源需求摘要
  - 阻塞问题列表
- [x] 求解器准备数据：
  - `goal_facts`
  - `candidate_activities`
  - `effective_rules`
  - `layered_health_summary`
  - `layered_health_diagnostics`
- [x] `/solve/layered` 请求模板：
  - endpoint
  - runtime required fields
  - selected target state roots
  - selected activity scopes
  - objective
  - context metadata
- [x] 前端求解预检面板：
  - 目标事实 / 候选活动 / 规则 / 阻塞项
  - 状态包聚合 / 虚拟活动分组
  - `/solve/layered` 模板摘要
  - 可执行活动表
  - 阻塞项定位和覆盖刷新
  - `status=ready` 时显示“数据库交接就绪”
  - `status=blocked` 时模板摘要标记“仅预检摘要”并显示阻塞项数量
  - 不提供独立 JSON 或 `/solve/layered` 请求模板下载

## Verification

- `python -m pytest tests\integration\test_layered_activity_state_api.py -q`
- `npm run build`
- Historical browser artifact:
  - `output/network-editor-export-template.png`

## Notes

- 2026-06-25 补强：按最新需求口径把本工单收口为“求解预检与求解器准备交接”。正式 API 为 `network-editor/solver-precheck`，旧 `network-editor/export-preview` 只作为 deprecated 兼容别名保留；前端只展示数据库交接就绪摘要、阻塞项和 `/solve/layered` 模板摘要，不提供独立 JSON 或求解模板下载。
- 2026-06-24 补强：求解预检的 `/solve/layered` 请求模板现在在未选择活动范围时自动推断有可执行后代的顶层活动 scope，避免生成空候选活动请求；未选择目标状态时把 `target_state_node_ids` 放入 `required_runtime_fields`，提示用户补齐目标。回归：网络编辑器集成测试 15 passed，场景导入 9 passed，全量后端 321 passed，前端 build passed。
- 2026-06-24 补强：前端求解预检面板在 `status=blocked` 时仍展示摘要、阻塞项和模板预览，但网络编辑器不再提供独立 JSON 或求解模板下载入口，避免阻塞模型被误交给求解链路。回归：前端 build passed。
- 2026-06-24 补强：`solve_request_template` 新增 `handoff_mode`、`model_status`、`solver_handoff_ready` 和 `blocking_issue_count`，前端据此在 ready 时显示“数据库交接就绪”，blocked 时显示“仅预检摘要：阻塞 N 项”。回归：旧命名 focused case 1 passed；网络编辑器集成测试 20 passed；前端 build passed。
- 2026-06-24 补强：前端求解预检请求改用专用 payload，保留用户选择的目标状态根和活动范围，但固定 `view_mode=solver_ready`、`state_depth=0`、`activity_depth=0`，避免默认折叠深度把二级活动包下的原子活动裁剪出求解交接结果。回归：前端 build passed。
- 2026-06-24 补强：求解预检的 `ready/blocked` 状态现在会阻断不可消费的 executable：缺少输出、没有 active `op_rule`、多规则未显式选择、绑定规则无效或歧义都会进入 `blocking_issues`，避免交接 `op_rule_id=null` 的可执行活动。回归：网络编辑器集成测试 15 passed；全量后端 321 passed。

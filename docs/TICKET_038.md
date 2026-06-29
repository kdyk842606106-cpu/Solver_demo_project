# TICKET-038: 网络编辑器图投影与校验服务

> Status: implemented  
> Version: V0.3  
> Completed: 2026-06-23  
> Depends on: `docs/TICKET_037.md`

## Scope

本工单实现网络编辑器的只读图投影、分层校验和求解器准备预检服务，不启动 Scheduler，不新增持久化 GraphEdge。

## Implemented

- [x] 新增服务 `app/services/network_editor.py`
- [x] 图投影 API：
  - `POST /api/v1/machine-types/{id}/network-editor/graph`
  - 支持 `outline` / `implementation` / `solver_ready`
  - 状态、虚拟活动、原子活动、绑定和规则边统一投影
  - `GraphEdge` 作为响应对象，不持久化
- [x] 深度控制：
  - `state_depth`
  - `activity_depth`
  - 默认 `0` 表示不限深度，兼容旧请求
- [x] 建模校验与求解准备校验：
  - 覆盖缺口
  - 孤立状态 / 孤立活动
  - 活动缺少输入 / 输出建模提示
  - 虚拟活动未分解提示
  - 可执行活动缺少输入 / 输出
  - 状态-活动依赖环阻塞
  - 状态包成员引用、状态聚合层级和活动容器结构环阻塞
  - 状态包成员 / 活动归属更新成环防护
  - 活动参与求解标记一致性阻塞
  - 虚拟活动声明输出未被内部可执行活动完整实现
  - 跨层级绑定建模提示
  - 同一状态包范围内重复状态名提示
  - 多状态包出现状态求解准备提示
  - 多个可执行活动产出同一状态提示
  - 产出状态没有下游使用提示，选为目标状态时自动豁免
  - 跨层级绑定较多提示
  - 状态包覆盖范围较大提示
  - 复用现有 `layered-health-check` 诊断
- [x] 图统计：
  - 状态数量
  - 活动数量
  - 虚拟活动数量
  - 可执行活动数量
  - 最大状态深度
  - 最大活动深度
  - 最长依赖链
  - 孤立节点数量
  - 覆盖缺口数量
  - 部分实现虚拟活动数量
  - 跨层级绑定数量

## Verification

- `python -m pytest tests\integration\test_layered_activity_state_api.py -q`

## Notes

- 2026-06-24 补强：图投影、求解预检聚合规则、影响分析成员覆盖、`layered-expansion` 和 `layered-health-check` 均改为按默认所在状态包 + 成员引用显示 DAG 展开状态子树；成员引用作为局部根或求解目标时不再漏掉引用子树叶子。回归：网络编辑器集成测试 14 passed；场景导入 9 passed；全量后端 320 passed；前端 build passed。
- 2026-06-24 补强：求解器准备校验新增可执行活动规则可用性阻断：无 active `op_rule`、多个 active `op_rule` 但绑定未显式选择、绑定指向多个规则或无效规则都会返回 error；同时修正可执行活动缺少输出状态必须阻断求解交接的校验路径。回归：网络编辑器集成测试 15 passed；场景导入 9 passed；全量后端 321 passed；前端 build passed。
- `python -m pytest -q`

Depth control browser artifact:

- `output/network-editor-depth-controls.png`

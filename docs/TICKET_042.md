# TICKET-042: 修复网络编辑器展开容器批量移动验收失败
> Status: implemented
> Version: V0.3
> Completed: 2026-06-26
> Depends on: `docs/TICKET_041.md`

## Scope

本工单只修复全仓审查里的 P1：恢复 TICKET-041 网络编辑器展开容器移动验收。编辑模式下拖动展开的状态包容器或虚拟活动容器时，容器内部可保存节点必须跟随容器一起移动，并作为同一批 `layoutDraft` 更新进入统一提交路径。

本工单不处理 service 分层、pytest warning、前端包体积 warning、API 契约或后端数据模型。

## Implemented

- [x] `NetworkEditorX6Canvas.vue` 新增显式节点移动状态机，内部节点自由移动不再依赖 X6/foreignObject 的不稳定 native 拖拽命中。
- [x] `NetworkEditorX6Canvas.vue` 新增显式容器移动状态机，拖动 `.container-move-handle` 时同步平移容器和 child cells。
- [x] 容器 `mouseup` 时先快照容器与成员节点最终坐标，再逐项发出 `layout-change`，避免父组件重渲染后丢失 child 最终位置。
- [x] `NetworkEditorWorkspace.vue` 将 `layoutDraft` 叠回传给 X6 节点 props，保证 draft 坐标在 DOM 重渲染后仍是最新值。
- [x] `network-editor.spec.ts` 的拖拽 helper 对 X6 handle 使用所属 `[data-cell-id]` 作为真实鼠标 actionability 目标，并对 detach 竞态做短重试。
- [x] “moves internal nodes freely inside expanded containers” 用例改为拖动真实 `.layout-handle`，保持单节点自由移动与容器整体移动的语义区分。

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "moves expanded containers"` - 1 passed
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "moves internal nodes freely"` - 1 passed
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 8 passed
- `npm.cmd run build` - passed, with the existing Vite chunk-size warning

## Notes

- 拖动容器后 draft list 会同时出现状态位置和原子活动位置更新，提交按钮启用。
- 保留现有 E2E 断言阈值，未通过放宽断言掩盖移动失败。
- 本工单未修改 `/network-editor/graph`、`/network-editor/commit`、`/network-editor/solver-precheck`、`/solve` 或 `/solve/layered` 接口契约。

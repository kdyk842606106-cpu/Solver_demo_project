# TICKET-043: 修复网络编辑器新建状态草稿不显示在画布
> Status: implemented
> Version: V0.3
> Completed: 2026-06-27
> Depends on: `docs/TICKET_042.md`

## Scope

修复网络编辑器编辑模式下“新建状态”保存到草稿后，右侧草稿列表已出现但中间 X6 画布没有立即显示该状态的问题。

本工单只处理前端编辑态草稿可视化，不修改 `/network-editor/commit`、`/network-editor/graph`、后端数据模型或求解器契约。

## Implemented

- [x] `NetworkEditorWorkspace.vue` 将 `state_node:create` 草稿投影成 `draft-state:*` 临时图节点，并合并进画布可见状态节点。
- [x] 新建状态带有父状态包和 `_network_editor_layout` 时，临时节点按对应路径和布局显示在画布/容器内。
- [x] 拖动临时状态节点时，将最新布局回写到同一个 create 草稿 payload，提交仍走统一提交链路。
- [x] `NetworkEditorX6Canvas.vue` 的状态选中判断改为字符串比较，避免临时 ID 被 `Number(...)` 转成 0 后误选。
- [x] `network-editor.spec.ts` 增加抽屉保存后画布出现临时状态节点的回归断言。

## Verification

- `npm.cmd run build` - passed, with the existing Vite chunk-size warning
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` - 1 passed
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 8 passed

## Notes

## Follow-up 2026-06-27

- [x] Draft aggregate states are now included in state parent options, so a second new state can choose the first draft state package before unified submit.
- [x] Commit payload serialization converts draft parent IDs to `{ "_draft_ref": "<client_id>" }`.
- [x] Backend unified commit resolves `state_node.parent_id` draft refs before `StateNodeCreate` / `StateNodeUpdate` validation.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 8 passed; `python -m py_compile app\api\v1\master_data.py` passed.

## Follow-up 2 2026-06-27

- [x] Nested draft state packages now inherit parent draft graph paths, so a child state is wrapped by the newly created draft package on the X6 canvas.
- [x] Expanding/collapsing a draft state package no longer sends `draft-state:*` IDs to `/network-editor/graph`.
- [x] X6 expanded containers now render a low z-index body plus a high z-index title/action cell, keeping package actions clickable without blocking internal node dragging.
- [x] The regression test now creates a draft package, a draft child, and a nested draft child, then checks package containment and expand/collapse stability.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 8 passed; `python -m py_compile app\api\v1\master_data.py` passed.

## Follow-up 3 2026-06-27

- [x] Collapsed draft state packages now filter their draft descendants out of `x6VisibleStateNodes`, so children are visually folded into the package instead of staying on the canvas.
- [x] The regression test now asserts the draft child and nested draft state are hidden after collapsing the draft package.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 8 passed; `python -m py_compile app\api\v1\master_data.py` passed.

## Follow-up 4 2026-06-27

- [x] Referenced state package instances can now render as nested X6 containers under an expanded parent state package.
- [x] Child states added under a referenced package are placed inside the referenced package container, which itself remains inside the higher-level container.
- [x] X6 state ancestry now considers all visible graph instances for a parent state, including `state_node:*:ref:*` paths, instead of only the canonical parent node.
- [x] Draft state graph paths no longer duplicate the parent ID when the selected parent graph instance path already ends with that parent.
- [x] E2E now covers `state_node:4 -> state_node:1:ref:900 -> draft child` and verifies outer-container / inner-container / child-node containment.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "referenced state package"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 9 passed; `python -m py_compile app\api\v1\master_data.py` passed.

## Follow-up 5 2026-06-27

- [x] Collapsing a nested referenced state package now keeps the current outer root focus and folds only that nested container's descendants locally in X6.
- [x] Expanding the folded nested node restores its container and child nodes without a backend graph reload.
- [x] Backend graph reloads and root/focus changes clear the local folded-container set to avoid stale hidden nodes.
- [x] E2E now verifies the referenced-package child is hidden after inner collapse, the outer container remains visible, and the inner container/child return after re-expanding.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "referenced state package"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "queues drawer saves"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 9 passed; `python -m py_compile app\api\v1\master_data.py` passed.

## Follow-up 6 2026-06-27

- [x] Draft virtual activities are now projected as `draft-activity:*` resource-tree nodes and X6 graph nodes before unified submit.
- [x] Creating a second virtual activity can use the first draft level-1 virtual activity as its parent; activity parent options refresh from `allActivityNodes`.
- [x] Draft virtual activity containers expand locally, wrap draft child activity nodes, and collapse by filtering descendants without sending draft scope IDs to `/network-editor/graph`.
- [x] Unified submit serializes draft virtual activity parent, package, and binding refs to `{ "_draft_ref": "<client_id>" }`.
- [x] Backend unified commit resolves `activity_node.parent_id` and `atomic_activity.package_id` draft refs before schema validation.
- [x] E2E covers draft virtual activity parent/child creation, container containment, collapse hiding, and commit payload refs.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `python -m py_compile app\api\v1\master_data.py` passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "draft virtual activities"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 10 passed; `git diff --check` reported only existing LF/CRLF warnings.

- 新建状态在提交前使用 `draft-state:<client_id>` 作为临时 `state_node_id`，提交成功后仍由后端返回真实 ID 并通过 `loadAll()` 刷新。
- 本次没有改动 API、后端 commit 语义或数据库结构。
## Follow-up 7 2026-06-28

- [x] X6 state and activity nodes now consistently show input on the left and output on the right.
- [x] Rendered X6 edges anchor from the right output port to the left input port, including state -> activity input/context bindings and activity -> state output/declared-output bindings.
- [x] Visible port dragging now creates bindings through the existing edit-session draft confirmation flow; no API, backend, schema, or solver contracts changed.
- [x] E2E covers dragging from a state output port to an activity input port and confirms the binding is added to the draft queue.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "creates bindings by dragging"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 11 passed.

## Follow-up 8 2026-06-28

- [x] Impact analysis 404 / `HTTP_404` responses are now silent for the impact panel instead of surfacing "loading impact analysis failed"; other impact errors still use the normal operation-error path.
- [x] Drag-prefill now keeps a dashed pending binding edge on the X6 canvas after choosing the prefill-only action.
- [x] Adding the prefilled binding to the draft queue, or confirming the dropped binding directly, now replaces the pending edge with a dashed draft binding edge instead of clearing the line.
- [x] Pending binding previews are cleared when local edit/draft state is reset by machine-type changes, session resets, refresh, cancel, or successful submit.
- [x] E2E defaults the impact endpoint fixture to 404 and covers both prefill-to-form and confirm-to-draft drag flows.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "pending edge|confirming a dropped binding"` 2 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 12 passed.

## Follow-up 9 2026-06-28

- [x] Atomic activity input/output state selectors now include draft states queued in the current edit session.
- [x] Atomic activity input/output states are optional; users can create the atomic activity first and add boundary bindings later from the canvas.
- [x] New state creation now defaults to an atomic leaf state; upper branch nodes are explicitly created as state packages.
- [x] Unified submit serializes draft state refs in activity-state bindings and covered leaf state lists, and backend commit resolves those refs before validation.
- [x] E2E covers draft state options in atomic activity forms and saving atomic activities with empty boundary states.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `python -m py_compile app\api\v1\master_data.py` passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "(offers draft states|queues drawer saves|referenced state package)"` 3 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 13 passed.

## Follow-up 10 2026-06-28

- [x] Network Editor atomic-state creation now loads machine-type state dimensions through `getFeatureDefs`.
- [x] The atomic-state drawer uses a searchable state-dimension select instead of a raw `feature_key` text input.
- [x] Target value is selected from the chosen dimension's `allowed_values` when configured; binary dimensions default to `true`.
- [x] Save validation now references state dimension / target value and rejects values outside configured allowed values.
- [x] E2E fixtures expose binary state dimensions and fill atomic-state facts through the real select controls.
- Verification: `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "(offers draft states|queues drawer saves|referenced state package)"` 3 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 13 passed; `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor.spec.ts docs/STATE_V0.3.md docs/TICKET_043.md` reported only the existing STATE LF/CRLF warning.

## Follow-up 11 2026-06-28

- [x] Draft atomic activities are now projected as `draft-atomic-activity:*` X6 nodes and resource-tree atomic leaves before unified submit.
- [x] Draft atomic nodes inherit real or draft virtual package ancestry, so expanded activity views can show container -> nested container -> atomic node.
- [x] Collapsing a nested draft virtual container hides its draft atomic descendants locally; collapsing the parent draft virtual container hides all descendants.
- [x] Draft atomic binding endpoints and later binding payload serialization resolve temporary atomic IDs through `{ "_draft_ref": "<client_id>" }`.
- [x] E2E covers draft atomic resource-tree/X6 projection, nested virtual containers, local collapse hiding, parent collapse hiding, and commit payload package refs.
- Verification: `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor.spec.ts` passed; `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "draft virtual activities"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 13 passed.

## Follow-up 12 2026-06-28

- [x] Root-level state expansion now preserves multiple independent top-level expanded roots instead of replacing the previous root with the latest toggle.
- [x] X6 state-container expansion accepts multiple state roots, so two independent high-level states can remain expanded at the same time.
- [x] Nested state-container local collapse only applies when the node is actually inside another expanded root; root-level collapsed keys no longer intercept a later root expand action.
- [x] Graph reload now prunes stale local folded-container keys instead of clearing all folded state, preserving unrelated expanded-root local collapse state.
- [x] E2E covers expand A, expand B, collapse B while A remains expanded, then expand B and collapse A while B remains expanded.
- Verification: `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor.spec.ts` passed; `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "independent state root"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 14 passed.

## Follow-up 13 2026-06-28

- [x] Impact analysis now only sends committed state IDs and committed activity graph IDs to `/network-editor/impact`.
- [x] Draft state IDs, draft atomic activity graph IDs, and other non-committed selections reset the local impact panel instead of posting temporary IDs to the backend.
- [x] Dragging a draft atomic activity output to a draft state input no longer triggers the backend integer-parse error for `draft-state:*`.
- [x] E2E captures impact POST payloads in the draft atomic-activity flow and asserts no `draft-state:` or `draft-atomic-activity:` temporary IDs are sent.
- Verification: `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor.spec.ts` passed; `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "offers draft states"` 1 passed; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 14 passed.

## Follow-up 14 2026-06-28

- [x] Added standalone E2E script `frontend/e2e/tests/network-editor-full-flow.spec.ts` for the full editor node/edge creation flow.
- [x] The script starts from an empty editor fixture, enters edit mode, creates two draft atomic state nodes, a draft virtual activity node, and a draft atomic activity node.
- [x] It drags canvas ports to create both `context_input` and `declared_output` draft binding edges.
- [x] It asserts unified submit sends `state_node`, `activity_node`, `atomic_activity`, and `activity_state_binding` changes, with draft refs serialized as `_draft_ref`.
- Verification: `git diff --check -- frontend/e2e/tests/network-editor-full-flow.spec.ts` passed; `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` 1 passed.

## Follow-up 15 2026-06-28

- [x] Saving a newly created child state now locally expands the parent state container and clears that parent container's folded key.
- [x] Saving a new child virtual activity or atomic activity now locally expands the parent/package activity container.
- [x] First child additions through parent node actions now render inside the parent container immediately, without requiring a manual expand click.
- [x] The full-flow E2E covers parent state package -> first child state and parent virtual activity -> first child activity, asserting each child is inside its container on first save.
- Verification: `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor-full-flow.spec.ts` passed; `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` 2 passed; `npm.cmd run build` passed with the existing Vite chunk-size warning; `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` 14 passed.

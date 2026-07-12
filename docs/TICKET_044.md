# TICKET-044: Network Editor canvas right-click creation and pan
> Status: implemented
> Version: V0.3
> Completed: 2026-06-29
> Depends on: `docs/TICKET_043.md`

## Scope

Add front-end-only Network Editor canvas interactions for the X6 canvas:

- Right-button drag pans the canvas.
- Right-clicking blank canvas opens a creation menu.
- New state, virtual activity, and atomic activity drafts created from that menu appear at the clicked canvas position.
- Canvas size expands automatically when nodes are created or moved beyond the initial viewport.

This ticket does not change `/network-editor/graph`, `/network-editor/commit`, backend schemas, database migrations, or solver contracts.

## Implementation Plan

- [x] Emit blank-canvas context-menu coordinates from `NetworkEditorX6Canvas.vue` while preserving node context menus and port/node/container drags.
- [x] Add right-button blank panning with a movement threshold so drag does not open the add menu.
- [x] Add a blank-canvas creation menu in `NetworkEditorWorkspace.vue`.
- [x] Persist pending layout metadata for virtual activity and atomic activity creates, matching existing state create layout behavior.
- [x] Remove fixed-width clamping from new-node layout so X6 canvas resize can expand to content bounds.
- [x] Cover right-click creation, right-drag panning, and auto expansion in E2E.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_044.md` - passed, with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 14 passed.
- `npm.cmd run build` - passed, with the existing Vite chunk-size warning.

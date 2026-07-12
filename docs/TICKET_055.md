# TICKET-055: Network Editor edit-mode action buttons do not start connections
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_050.md`

## Scope

Fix Network Editor X6 action buttons so edit-mode clicks on expand/collapse, focus, create, and similar controls do not start a connection drag.

This is a frontend interaction fix only. It does not change backend APIs, database schema, commit payload semantics, or solver contracts.

## Implementation

- Added a per-DOM-event handled marker for X6 node action clicks so host-level action dispatch and X6 `node:click` dispatch do not double-handle the same click.
- Added a pointer-control guard before X6 connection drag startup. Events that start on `[data-action]`, form controls, links, or contenteditable controls now bypass canvas pan, node move, and port connection startup.
- Hardened `startConnectionDragFromPort()` with its own exclusion guard for action controls and layout/container move handles. This prevents the output-port hit tolerance from treating nearby top-right action buttons as connection starts.
- Gave the temporary connection edge a stable id so E2E can assert action-button long-presses do not create a transient connection line.
- Added an edit-mode E2E regression that holds down state-package expand and virtual-activity focus/expand buttons and asserts no temporary or pending binding edge appears.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "edit-mode action buttons"` - passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 18 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed with the existing Vite chunk-size warning.

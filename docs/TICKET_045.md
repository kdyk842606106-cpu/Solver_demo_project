# TICKET-045: Network Editor node action affordance refresh
> Status: implemented
> Version: V0.3
> Completed: 2026-06-29
> Depends on: `docs/TICKET_044.md`

## Scope

Refresh the X6 Network Editor node interaction affordances:

- State nodes render as ellipses.
- Expand/collapse use top-right icon buttons: plus for collapsed, minus for expanded.
- Editing is triggered by double-clicking nodes instead of an inline edit action.
- Adding a child state is shown as a hover-only button below an aggregate state node.

This ticket is front-end-only and does not change Network Editor API, commit payload semantics, backend models, or solver contracts.

## Implementation Plan

- [x] Update X6 node HTML and CSS for icon expand/collapse, hover child-state add button, and ellipse state shape.
- [x] Route node double-click to edit state/activity; child creation now uses the hover add affordance.
- [x] Keep existing node context menus, port dragging, layout dragging, and container operations intact.
- [x] Add/adjust E2E assertions for hover child creation, state ellipse styling, and double-click edit affordances.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor.spec.ts frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_045.md` - passed, with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 14 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed, with the existing Vite chunk-size warning.

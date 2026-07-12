# TICKET-051: Network Editor board-first compact workspace
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_050.md`

## Scope

Make the Network Editor workspace board-first by removing duplicated create buttons, compacting auxiliary panels, and giving the X6 canvas more default space.

This ticket is front-end-only and does not change backend APIs, database schema, commit payloads, or solver contracts.

## Implementation Plan

- [x] Move state/activity/atomic creation to a compact resource-pane create menu while keeping blank-canvas right-click creation.
- [x] Remove duplicated top-toolbar create buttons and compact secondary global actions.
- [x] Add collapsible resource and properties panes with the canvas taking released space.
- [x] Collapse validation/precheck details behind a compact status strip by default.
- [x] Compress summary metrics into key chips with overflow details.
- [x] Keep X6 nodes above edges and harden port hit testing so compact layout does not hide hover actions or port targets.
- [x] Update focused Network Editor E2E coverage and run build verification.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 16 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed with the existing Vite chunk-size warning.

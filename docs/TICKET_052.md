# TICKET-052: Network Editor single X6 canvas and full-page grid fix
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_051.md`

## Scope

Fix the follow-up layout regressions after the board-first compact Network Editor workspace:

- remove the visual double-canvas effect caused by the active X6 wrapper reusing legacy canvas styling;
- let the X6 grid fill the available board area when side panes are collapsed;
- rename the canvas pane title from `二部图画布` to `网络画板`.

This ticket is front-end-only and does not change backend APIs, database schema, commit payloads, or solver contracts.

## Implementation Plan

- [x] Make the active X6 wrapper a plain flex fill container instead of a legacy `.canvas` surface.
- [x] Change collapsed side panes to floating edge rails so they no longer occupy main grid columns.
- [x] Resize X6 from both content bounds and host container size, with `ResizeObserver` support.
- [x] Update E2E coverage for single X6 canvas, full wrapper fill, and the corrected title.
- [x] Run focused E2E/build verification and update `STATE_V0.3.md`.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 16 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed with the existing Vite chunk-size warning.

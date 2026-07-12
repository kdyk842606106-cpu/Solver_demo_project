# TICKET-046: Network Editor X6 canvas interaction regression fix
> Status: implemented
> Version: V0.3
> Created: 2026-06-29
> Completed: 2026-06-29
> Depends on: `docs/TICKET_044.md`, `docs/TICKET_045.md`

## Scope

Fix regressions introduced around the X6 Network Editor canvas and node action affordances:

- Keep canvas auto-expansion working when new or dragged nodes move beyond the initial viewport.
- Keep the hover-revealed "添加状态" child button reachable when the pointer moves from the node down to the button.
- Avoid showing the right-button panning/grab state on long right press until the pointer actually moves beyond the drag threshold.

This ticket is front-end-only and does not change Network Editor APIs, commit payload semantics, backend models, or solver contracts.

## Implementation Plan

- [x] Track and resize the X6 graph bounds with the same content padding used by full render.
- [x] Add a hover bridge around node/container child-create affordances so the button remains visible while moving to it.
- [x] Delay right-button panning visual state until the movement threshold is crossed and clean up listeners before context-menu emission.
- [x] Add E2E coverage for hover reachability, right long-press behavior, and expanded canvas bounds.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor.spec.ts frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_046.md` - passed, with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 14 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed, with the existing Vite chunk-size warning.

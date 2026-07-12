# TICKET-050: Network Editor X6 left-button canvas pan
> Status: completed - 2026-06-29
> Version: V0.3
> Created: 2026-06-29
> Depends on: `docs/TICKET_049.md`

## Scope

Change X6 Network Editor canvas panning from right-button drag to left-button hold-and-drag so browser right-button gestures no longer conflict with canvas movement.

This ticket is front-end-only and does not change backend APIs, commit payload semantics, database schema, or solver contracts.

## Implementation Plan

- [x] Replace right-button pan candidate with left-button canvas pan candidate.
- [x] Preserve node drag, container title drag, resize handles, action buttons, ports, and proxy edge clicks.
- [x] Keep right-click blank menu and node context behavior intact.
- [x] Update E2E coverage from right-drag pan to left-drag pan.
- [x] Run focused Network Editor E2E and build verification.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor-full-flow.spec.ts frontend/e2e/tests/network-editor.spec.ts docs/TICKET_050.md docs/STATE_V0.3.md` passed with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` passed: 3 tests.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` passed: 15 tests.
- `npm.cmd run build` passed with the existing Vite chunk-size warning.

## Completion Notes

- Left-button hold-and-drag now pans the X6 canvas from blank space and container background areas; nodes, title rows, edges, ports, action buttons, resize handles, and form controls keep their existing behaviors.
- Right-click behavior is menu-only again: blank right-click opens the add menu and node context behavior remains intact.
- Port connection drag was hardened while moving pan to the left button: SVG/HTML ports are excluded from pan starts, SVG port-to-cell lookup is more robust, and mouseup near an input port snaps to the nearest port so draft binding previews still appear reliably.

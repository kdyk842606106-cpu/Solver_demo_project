# TICKET-049: Network Editor X6 container title and right-button pan fixes
> Status: completed - 2026-06-29
> Version: V0.3
> Created: 2026-06-29
> Depends on: `docs/TICKET_048.md`

## Scope

Fix two X6 Network Editor regressions after the recent canvas interaction updates:

- Expanded parent activity/state containers must not duplicate or overlap parent title text.
- Right-button drag should pan the canvas from the whole board area while suppressing browser right-drag gestures.
- Expanded canvas bounds must keep far-right/far-bottom nodes fully visible after creation or drag.

This ticket is front-end-only and does not change Network Editor APIs, commit payload semantics, backend models, database schema, or solver contracts.

## Implementation Plan

- [x] Split container background rendering from container title/action rendering.
- [x] Make right-button pan candidate start on the whole X6 board while preserving action/port controls.
- [x] Suppress browser context/aux/drag/select defaults during right-button pan.
- [x] Ensure graph bounds expand after render, node/container drag, resize, and far-position creation.
- [x] Cover title duplication, right-button pan, and full-node visibility in E2E.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor.spec.ts frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_049.md docs/STATE_V0.3.md` passed with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` passed: 15 tests.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` passed: 3 tests.
- `npm.cmd run build` passed with the existing Vite chunk-size warning.

## Completion Note

Completed on 2026-06-29. The fix is limited to X6 front-end rendering/interaction and E2E coverage; no backend API, database, commit payload, or solver contract changes were made.

# TICKET-047: Network Editor X6 node text readability fix
> Status: implemented
> Version: V0.3
> Created: 2026-06-29
> Completed: 2026-06-29
> Depends on: `docs/TICKET_045.md`, `docs/TICKET_046.md`

## Scope

Fix the X6 Network Editor regression where node text is clipped after the node affordance refresh:

- Let node labels wrap inside the node instead of forcing single-line ellipsis.
- Give state/activity nodes enough stable space for wrapped names and the top-right expand/collapse icon.
- Keep container bounds and graph auto-expansion based on actual node dimensions.
- Preserve existing edit, hover create, right-click menu, port drag, and layout drag behavior.

This ticket is front-end-only and does not change Network Editor APIs, commit payload semantics, backend models, or solver contracts.

## Implementation Plan

- [x] Add stable node dimension calculation for long labels.
- [x] Update node/container bounds to use actual node sizes.
- [x] Update CSS so code/name/meta wrap cleanly without overlapping node actions or ports.
- [x] Add E2E coverage for long node names being visible without ellipsis clipping.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_047.md` - passed, with existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "referenced state package"` - 1 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 14 passed.
- `npm.cmd run build` - passed, with the existing Vite chunk-size warning.

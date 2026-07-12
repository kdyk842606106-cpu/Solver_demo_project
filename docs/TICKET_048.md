# TICKET-048: Network Editor X6 collapsed proxy edge visualization
> Status: complete
> Version: V0.3
> Created: 2026-06-29
> Depends on: `docs/TICKET_047.md`

## Scope

Implement collapsed proxy edges in the X6 Network Editor so relationships involving hidden child nodes remain visible after a parent state/activity is collapsed:

- Map hidden child endpoints to the nearest visible parent endpoint.
- Render collapsed proxy edges as dashed aggregate relationships with count labels.
- Show lightweight hidden input/output/internal relationship badges on parent nodes.
- Keep proxy edges visual-only; editing still requires expanding to concrete endpoints.

This ticket is front-end-only and does not change Network Editor APIs, commit payload semantics, backend models, database schema, or solver contracts.

## Implementation Plan

- [x] Add X6-specific edge endpoint resolution before `x6RenderedEdges`.
- [x] Aggregate proxy edges by visible endpoint pair and direction.
- [x] Add proxy edge styling and labels in the X6 canvas component.
- [x] Add parent node relation badges for folded input/output/internal relationships.
- [x] Cover folded state/activity proxy edges and internal folded relationships in E2E.

## Verification

- `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue frontend/e2e/tests/network-editor.spec.ts frontend/e2e/tests/network-editor-full-flow.spec.ts docs/TICKET_048.md docs/STATE_V0.3.md`
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium`
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium`
- `npm.cmd run build`

Notes: the build still reports the existing Vite chunk-size warning.

# TICKET-079: Network Editor state-transition selected detail projection
> Status: completed
> Version: V0.3
> Created: 2026-07-09
> Completed: 2026-07-09

## Scope

Implement Phase 3 of the Network Editor state-transition projection plan without
changing database schema, backend API contracts, Scheduler, or RAGBuilder:

- Add projection-owned selected state detail objects.
- Drive right-panel transition detail, realizer rows, warning rows, and
  precondition rows from the same projection object.
- Preserve existing semantic edit actions for realizer/precondition changes.
- Keep context defaults explicit: transition realizer creation still does not
  inherit the currently selected activity package.

## Implementation Summary

- Extended `buildStateTransitionProjection()` with `detailsByStateId`,
  `detailsByGraphId`, and `selectedDetails`.
- Each detail now carries display graph id, canonical state id, package/reference
  path ids, realizer activities, precondition rows, warnings, and
  draft-vs-committed source status.
- Updated `NetworkEditorWorkspace.vue` to read selected transition details and
  selected preconditions from projection output instead of rebuilding them in
  local computed blocks.
- Added E2E assertions for canonical/display state ids and draft source status,
  including referenced atomic state instances.

## Verification

- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition|referenced atomic library states|new transition realizers"`
  - 17 passed.
- `git diff --check`
  - passed with LF/CRLF warnings only.

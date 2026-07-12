# TICKET-075: Solve page allows state packages as layered targets
> Status: completed
> Version: V0.3
> Created: 2026-07-02

## Scope

Fix the Solve page layered target state selector so users can select state
packages, including top-level packages such as `机械集成完成`.

## Implementation Summary

- Removed the Solve page target-state tree rule that disabled `level < 2`
  state nodes.
- Added a stable `data-testid` on the layered target state tree select.
- Expanded Solve page E2E mocks to return layered state nodes, activity nodes,
  and maintenance templates through their real API paths.
- Added E2E coverage proving a top-level state package can be selected and is
  submitted as `target_state_node_ids`.

## Verification

- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium --grep "top-level state package"`
  - passed.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium`
  - 5 passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend solver changes.
- No change to activity-scope filtering.

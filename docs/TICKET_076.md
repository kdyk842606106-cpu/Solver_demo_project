# TICKET-076: Network Editor state transition relay visualization
> Status: completed
> Version: V0.3
> Created: 2026-07-03

## Scope

Replace the default Network Editor state-transition canvas projection from
direct state-to-state flow arrows with a state + small activity relay view.
The relay nodes are frontend-only render artifacts and do not change backend
data, solver behavior, or persisted graph contracts.

## Implementation Summary

- Added frontend-only transition relay groups derived from existing
  `STATE_TO_ACTIVITY` and `ACTIVITY_TO_STATE` bindings.
- Replaced rendered `STATE_FLOW` direct arrows with two relay edges:
  `state -> transition relay` and `transition relay -> state`.
- Added automatic state-transition arrangement that alternates state columns
  and relay columns, while writing only normal state layout drafts.
- Rendered relay nodes as compact, non-editable X6 activity chips that map
  selection back to the underlying real activity.
- Updated X6 edge routing so relay branches can use shared fork/join rails.
- Preserved layout-only state-to-state inference inside expanded state
  containers so existing package flow wrapping still works without drawing
  direct state-flow arrows.
- Updated Network Editor E2E coverage for relay nodes, relay edge roles,
  focus highlighting, auto arrange, and branch routing.

## Verification

- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state-transition"`
  - 11 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium`
  - 43 passed, 1 failed in the pre-existing expanded-container geometry case
    where the fixture persists `_network_editor_container: { width: 920, height: 760 }`
    but the assertion expects a compact container under 560x430.
- `git diff --check` on touched files
  - only reported existing LF/CRLF warnings.

## Out of Scope

- No backend API, schema, solver, or database changes.
- No changes to activity/state binding semantics.
- No new persisted relay node type.

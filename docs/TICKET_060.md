# TICKET-060: Render draft state references inside target state packages
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_059.md`

## Scope

Fix the Network Editor edit-session preview for adding an existing state as a member reference of a state package.

The key scenario is:

1. Enter edit mode.
2. Use the `状态包成员` form to add an existing state under a target aggregate state package.
3. Before unified submit, the draft `state_node_reference:create` should be rendered as a visible referenced state
   instance inside the target state package container.
4. The unified submit payload should still contain a `state_node_reference:create`; the original state body is not
   duplicated or converted into a new `state_node:create`.

## Changes

- Added frontend draft graph projection for `state_node_reference:create`.
- Draft state references now receive a unique graph id while preserving the referenced `state_node_id`.
- Draft reference path metadata now includes the target parent package so X6 container bounds can include the instance.
- State reference draft layout can be updated through the same draft-layout path used by draft state nodes.
- The `状态包成员` form now exposes stable test ids for the reference state and target package selects.
- Added Playwright coverage proving a draft referenced state appears inside its target package container and commits as a
  `state_node_reference:create`.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "draft referenced state"` — 1 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "referenced state package|draft referenced state"` — 2 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 22 passed.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend schema or API changes.
- No solver behavior changes.
- No change to state reuse identity semantics; reuse remains driven by exact code/name matching rather than state
  dimension equality.

# TICKET-056: Network Editor folded parent move preserves container bounds
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_055.md`

## Scope

Fix the Network Editor X6 behavior where dragging a collapsed parent state/activity node and then expanding it could create an oversized container.

This is a frontend layout/draft fix only. It does not change backend APIs, database schema, commit payload semantics, or solver contracts.

## Root Cause

Collapsed package-node dragging updated only the parent node layout. Descendant state/activity nodes kept their previous absolute layout. When the parent was expanded afterward, X6 computed the container bounds from both the moved parent and the unmoved descendants, so the container stretched across the distance between them.

## Implementation

- X6 node dragging now moves currently rendered descendant cells during the drag, so visible children track the parent immediately.
- X6 node drag completion emits a batched `layout-change.updates` payload plus the drag delta for expandable parent nodes.
- Moving a folded state package translates descendant state instance layouts by the same delta, including descendants that were not currently rendered in X6.
- Moving a folded virtual activity translates descendant virtual/atomic activity layouts by the same delta, including package atomic refs that were not currently rendered in X6.
- Workspace layout handling accepts batched layout updates, completes hidden descendants from the full state/activity trees, writes the result into `layoutDraft`, queues draft updates for each affected node, and shows one summary message instead of one message per descendant.
- Existing single-node layout behavior remains supported.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "folded package descendants"` - passed, with child nodes intentionally absent from the initial folded graph response.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 19 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed with the existing Vite chunk-size warning.

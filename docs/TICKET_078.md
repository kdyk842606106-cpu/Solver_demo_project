# TICKET-078: Network Editor state-transition group boundary projection
> Status: completed
> Version: V0.3
> Created: 2026-07-09
> Completed: 2026-07-09

## Scope

Implement Phase 2 of the Network Editor state-transition projection plan without
changing database schema, backend API contracts, Scheduler, or RAGBuilder:

- Add read-only `NetworkGroupProjection` records for state packages.
- Derive folded state-package boundary proxy edges inside the frontend
  state-transition projection helper.
- Route state-transition canvas rendering, badges, focus, and auto-layout
  through projection-owned proxy edges where package endpoints are folded.
- Keep projection, relay, proxy, and layout artifacts UI-only and stripped from
  commit payloads.

## Constraints

- State packages remain containers, not solver nodes.
- Proxy edges summarize existing semantic bindings and relay edges only.
- Package-to-package creation and persisted package-level transitions remain out
  of scope.
- Activity package boundary projection is deferred until after the state package
  read model is stable.

## Verification Plan

- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition|collapsed proxy|activity expansion|referenced atomic library states"`
- `npm.cmd run build`

## Implementation Summary

- Extended `networkEditorStateTransitionProjection.js` with state-package
  `groupsByGraphId`, transition `backboneEdges`, folded package `proxyEdges`,
  and projection-owned `visibleEdges`.
- Updated `NetworkEditorWorkspace.vue` so the state-transition canvas renders
  projection visible edges, keeps X6 raw state visibility separate from
  transition summary decoration, and derives state-transition layout container
  ids from projection groups.
- Allowed projection-owned proxy edges to participate in nested auto-layout
  edge normalization while keeping ordinary aggregate edges out of ELK input.
- Added E2E coverage for folded nested state packages producing projection
  proxy edges and relation badges.

## Verification

- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition|collapsed proxy|activity expansion|referenced atomic library states"`
  - 18 passed.
- `git diff --check`
  - passed with LF/CRLF warnings only.

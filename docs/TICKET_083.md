# TICKET-083: Network Editor local state expansion and layout isolation
> Status: completed
> Version: V0.3
> Created: 2026-07-11
> Completed: 2026-07-11

## Scope

Separate state-transition node expansion from graph focus so expanding a state
package preserves other high-level nodes and auto arrange cannot leak child
layout coordinates or routes into the parent level.

- Build staged state visibility locally from the complete projection graph.
- Keep expansion per graph instance and preserve independent roots.
- Limit nested auto arrange drafts to the active expanded package.
- Place transition relays with their visible output target package.
- Keep expansion, route signatures, and relay ownership frontend-only.

## Constraints

- No database, backend API, projection contract, Scheduler, or RAGBuilder changes.
- Activity expansion and activity auto arrange remain unchanged.
- Existing package proxy counts, AND semantics, and coverage snapshots remain unchanged.

## Verification Plan

- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state expansion|independent state root|auto arrange|relay|high-parallel|collapsed proxy"`
- `npm.cmd run build`
- `git diff --check`

## Completed Work

- Added graph-instance-local `expandedStateGraphIds` and active expanded-package state; node expansion no longer rewrites `selectedStateRootIds`.
- Built staged visibility from the complete state projection so each expansion adds only direct children while preserving other roots and siblings.
- Scoped nested ELK input, transient routes, layout signatures, caches, and persisted layout drafts to the active expanded package.
- Kept the active package anchored; local auto arrange writes descendant positions and the active container size only.
- Assigned relays to the nearest common expanded output package and included owned relays in the rendered state-container bounds.
- Stabilized nested X6 layout by using the collapsed child-package header as the parent-level anchor, preventing child size changes from moving siblings or overlapping parent titles.
- Kept proxy, relay, ownership, route, and signature fields frontend-only; commit payload and backend contracts are unchanged.

## Verification

- Focused Playwright suite: 13 passed.
- Production build: passed with the existing Vite chunk-size warning.
- `git diff --check`: passed with existing LF/CRLF conversion warnings only.
- Backend tests were not required because no backend projection, API, schema, Scheduler, or RAGBuilder code changed.

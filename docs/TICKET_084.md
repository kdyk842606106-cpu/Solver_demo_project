# TICKET-084: Network Editor expanded state-container collision avoidance
> Status: completed
> Version: V0.3
> Created: 2026-07-11
> Completed: 2026-07-11

## Scope

Prevent a locally expanded nested state package from covering visible sibling
packages in the state-transition canvas.

- Keep sibling and ancestor layout coordinates unchanged.
- Place non-ELK transition relays near their visible output states.
- Keep the expanded container outer frame anchored at the collapsed node's
  original top-left position and move intersecting sibling packages instead.
- Restore the parent-level geometry after collapse.

## Constraints

- No backend API, database, projection contract, Scheduler, or RAGBuilder changes.
- Collision displacement is UI-only and must not enter layout drafts or commit payloads.
- Existing proxy counts, package binding semantics, and local auto-arrange scope remain unchanged.

## Completed Work

- Anchored non-ELK relay fallback positions to visible output states instead of retaining unrelated global fallback coordinates.
- Corrected container-title obstacle rectangles to read X6 container `x`/`y` coordinates.
- Anchored level-2 and deeper state-container outer frames at the exact collapsed-node position so expansion grows rightward and downward.
- Added sibling collision displacement that preserves the expanded package anchor and remains display-only.
- Added a wide six-leaf child-package E2E fixture that verifies exact expansion anchoring, no sibling overlap, and parent-level coordinate restoration after collapse.

## Verification

- Focused Playwright regression: 3 passed.
- State expansion/relay/proxy regression: 13 passed.
- Production build: passed with the existing Vite chunk-size warning.
- `git diff --check`: passed with existing LF/CRLF conversion warnings only.
- Backend tests were not required because no backend code or contract changed.

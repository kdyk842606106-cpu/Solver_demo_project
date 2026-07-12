# TICKET-082: Network Editor proxy obstacle routing and spacing
> Status: implementation_complete_verification_partial
> Version: V0.3
> Created: 2026-07-11

## Scope

Improve the staged state-transition canvas so folded state-package proxy edges
do not pass through visible nodes and package spacing leaves readable routing
and label channels immediately after expansion.

- Keep the package projection semantics and proxy counts unchanged.
- Share balanced state-transition spacing across fallback, expanded-container,
  and ELK layout paths.
- Route folded proxies around visible nodes while preserving right-to-left port
  semantics and existing proxy interactions.
- Keep all route and label metadata frontend-only.

## Constraints

- No database, backend API, Scheduler, or RAGBuilder changes.
- Activity-package vertical layout remains unchanged.
- Expanded containers may grow and rely on canvas scrolling for readability.
- Existing staged expansion behavior must not regress.

## Verification Plan

- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "high-parallel|state package binding|collapsed proxy|state-transition"`
- `npm.cmd run build`
- Browser verification at 1280x900 on the mechanical high-parallel fixture.
- `git diff --check`

## Implementation Result

- [x] Centralized the state-transition fallback, expanded-container, and ELK
  spacing metrics.
- [x] Preserved at least 88px horizontal and 72px vertical visible clearance
  between the high-parallel state-package cards.
- [x] Replaced folded proxy short routes with X6 Manhattan obstacle routing
  while retaining right-side output and left-side input ports.
- [x] Kept expanded container backgrounds out of the obstacle map while nodes
  and container titles remain obstacles.
- [x] Added route collision fallback for stale ELK paths and readable proxy
  label offset/background styling.
- [x] Preserved projection counts, proxy interactions, and UI-only commit
  stripping behavior.

## Verification Result

- Focused Network Editor E2E: 24 passed.
- The high-parallel fixture still renders 6 level-2 packages, 8 proxy edges,
  and 0 hidden relay nodes.
- Browser geometry sampling verifies that no proxy path enters a non-endpoint
  package node, no proxy label overlaps a package node, and visible gaps meet
  the 88px / 72px minimums.
- `npm.cmd run build`, JavaScript syntax checks, and `git diff --check` passed;
  only the existing Vite chunk-size and LF/CRLF warnings remain.
- The final in-app browser visual handoff could not run because Browser Use
  rejected the local `127.0.0.1` URL under its URL safety policy. No alternate
  browser surface was used to bypass that restriction, so this ticket remains
  verification-partial despite deterministic browser geometry coverage.

# TICKET-085: Network Editor nested state-container ancestor bounds
> Status: completed
> Version: V0.3
> Created: 2026-07-12
> Completed: 2026-07-12

## Scope

Keep every expanded ancestor state-package frame large enough to contain the
complete bounds of its expanded descendant containers, including transition
relays owned by those descendants.

- Preserve the existing node positions and nested expansion anchor.
- Grow ancestor frames rightward and downward without shrinking them.
- Restore the parent-level frame automatically when the nested package folds.
- Keep the adjustment frontend-only and display-only.

## Constraints

- No backend API, database, projection contract, Scheduler, or RAGBuilder changes.
- Do not feed ancestor display growth into ELK input, layout signatures, drafts,
  persisted metadata, or commit payloads.
- Activity-container behavior and existing sibling collision avoidance remain unchanged.

## Verification Plan

- Add a high-parallel state-transition regression that expands the top-level
  package and `传动机构就绪`, then verifies all state cards, owned relays, the
  nested frame, and the expanded ancestor frame are mutually contained.
- Verify the nested package anchor remains fixed and folding restores the
  ancestor frame and sibling positions without creating a layout draft.
- Run focused Network Editor Playwright regressions, the production build, and
  `git diff --check`.

## Completed Work

- Added a final-render-only bottom-up bounds pass for expanded state containers.
- Expanded each ancestor frame to include the complete descendant container
  rectangle, which already includes transition relays owned by that descendant.
- Kept ancestor top-left coordinates, node positions, layout signatures, drafts,
  persisted metadata, and commit payloads unchanged.
- Expanded the high-parallel E2E fixture to nine child states and nine complete
  relay transitions, with containment, anchor, sibling restoration, frame
  restoration, and no-draft assertions.

## Verification

- Focused high-parallel containment regression: 1 passed.
- State expansion / relay / proxy / auto-arrange regression: 13 passed.
- Production build: passed with the existing Vite chunk-size warning.
- `git diff --check`: passed with existing LF/CRLF conversion warnings only.
- ANCHOR check: no violations.

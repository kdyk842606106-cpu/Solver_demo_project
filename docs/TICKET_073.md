# TICKET-073: Blank layered activity scope uses all atomic activities
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Supersedes: `docs/TICKET_067.md`

## Scope

Correct the layered solve activity-scope default semantics.

When `activity_scope_node_ids` is empty, the request means "use all active
atomic activities" rather than "default to all level-1 activity scopes".
Explicitly selected activity scopes continue to filter candidates by the
selected activity hierarchy.

## Implementation Summary

- `solve_layered()` now passes an empty `activity_scope_node_ids` list through
  to layered expansion instead of resolving it to top-level activity nodes.
- `expand_layered_context()` treats an empty activity scope list as a global
  atomic activity pool:
  - atomic activities referenced by active level-2 packages keep their package
    path and inherited Scope Guard preconditions;
  - atomic activities without a package reference are still eligible and use an
    atomic-only source path;
  - explicit activity scope selections keep the previous scoped behavior.
- Solve page placeholder now says the blank activity range defaults to all
  atomic activities.
- `LayeredExpansionRequest` and `LayeredSolveRequest` schema descriptions now
  document the empty-list behavior.
- Integration coverage adds a standalone atomic activity that is not attached
  to an activity package. Blank scope can schedule it; explicitly selecting the
  original top-level activity scope cannot.

## Verification

- `.venv\Scripts\python.exe -m py_compile app\services\layered_expansion.py app\services\layered_solve.py app\db\schemas.py`
  - passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q`
  - 4 passed, existing SQLite drop-order warning remains.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium`
  - 4 passed, existing SQLite drop-order warning remains in the web server log.

## Out of Scope

- No change to explicit activity-scope filtering.
- No change to solver objectives or continuity optimization.
- No new API fields.

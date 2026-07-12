# TICKET-067: Optional layered activity scope default
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_065.md`
> Superseded by: `docs/TICKET_073.md` (blank scope now means all active atomic activities)

## Scope

Allow layered solve requests to omit the activity scope selection.

When no `activity_scope_node_ids` are provided, the backend should default to all
active top-level activity scopes for the selected machine type. Explicitly
selected scopes continue to behave as before.

## Implementation Summary

- `solve_layered()` now resolves an empty activity scope list to all active
  level-1 `ActivityNode` rows for the machine type.
- The resolved scope ids are used for layered expansion and preflight health.
- The solve request override metadata records:
  - `activity_scope_node_ids`;
  - `requested_activity_scope_node_ids`;
  - `activity_scope_defaulted`.
- The layered response echoes the same defaulting metadata.
- Solve page no longer requires an activity range in layered mode and explains
  that an empty selection uses all level-1 activity scopes.

## Verification

- `.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q`
  - 4 passed.
- `.venv\Scripts\python.exe -m py_compile app\services\layered_solve.py`
  - passed.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.

## Out of Scope

- No change to snapshot solve.
- No change to explicit activity-scope filtering.
- No hard constraints added.
- No changes to TICKET-064 atomic-state detection.

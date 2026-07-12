# TICKET-065: State package continuity scheduling
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_029.md`, `docs/TICKET_064.md` remains planned and out of scope

## Scope

Replace the Solve page continuity preference with state-package continuity for
layered and maintenance solves.

The old activity-group continuity objectives remain available for compatibility,
but the user-facing preference now optimizes around target state packages: states
under the same package should be achieved as compactly as possible, and ancestor
packages should also prefer compact achievement across their child packages.

## Implementation Summary

- Added Scheduler state continuity metadata:
  - `StepData.state_continuity_groups`;
  - `TaskResult.state_continuity_groups`;
  - `ScheduleModel.state_groups`.
- Added objective types:
  - `minimize_state_group_span`;
  - `minimize_state_group_gaps`;
  - `minimize_state_group_interruptions`.
- `solve_layered()` now derives state package memberships from target goal
  `source_path` ancestors when a planned task directly provides a goal fact.
- `solve_maintenance()` inherits the same behavior through layered solve; direct
  desired facts without state-node source paths do not create state groups.
- Schedule diagnostics now return `state_group_continuity` alongside the legacy
  `activity_group_continuity`.
- Solve page now sends state-package continuity objectives only in layered and
  maintenance modes; snapshot mode continues to send only `minimize_makespan`.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/unit/test_scheduler_multi_resource.py tests/integration/test_state_group_continuity.py -q`
  - 7 passed.
- `.venv\Scripts\python.exe -m py_compile app\core\solver\objectives.py app\core\scheduler\loader.py app\core\scheduler\model.py app\core\scheduler\solver.py app\services\layered_solve.py app\api\v1\solve.py`
  - passed.
- `.venv\Scripts\python.exe -m pytest tests\unit\test_objectives.py tests\unit\test_scheduler_multi_resource.py tests\integration\test_state_group_continuity.py -q`
  - 15 passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_planner_integration.py tests\e2e\test_serial.py -q`
  - 29 passed.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.

## Out of Scope

- No database migration.
- No hard adjacency or hard sequencing constraints.
- No changes to atomic-state detection rules from TICKET-064.
- No removal of legacy activity-group objective types.

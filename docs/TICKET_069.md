# TICKET-069: Solve page Gantt traditional/state-lane switch
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_065.md`, `docs/TICKET_068.md`

## Scope

Improve the Solve page Gantt readability by adding a traditional/state-lane
view switch:

- Traditional view preserves the current task/activity-group Gantt behavior.
- State-lane view groups tasks by the most specific state package in
  `state_continuity_groups`.
- State-lane visibility depends on state package membership data, not on
  whether the continuity objective was enabled.

## Implementation Notes

- No solver behavior change.
- No new API fields; only document fields that are already returned.
- Diff mode falls back to traditional Gantt.
- Tasks without a state package membership are shown in an unassigned state
  lane when at least one other task has state package membership.

## Verification

- `.venv\Scripts\python.exe -m py_compile app\db\schemas.py`
  - passed.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium --grep "switches between"`
  - 1 passed.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium`
  - 4 passed.
- `git diff --check -- frontend/src/views/SolvePage/index.vue frontend/src/components/GanttChart.vue app/db/schemas.py frontend/e2e/fixtures/mock-api.ts frontend/e2e/tests/solve.spec.ts docs/TICKET_069.md`
  - only reported the existing LF/CRLF warnings.

## Out of Scope

- No new scheduling objective.
- No backend migration.
- No changes to state package continuity scoring.

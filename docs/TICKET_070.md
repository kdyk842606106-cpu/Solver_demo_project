# TICKET-070: Solve page continuity switch and state-lane fallback fix
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_069.md`

## Scope

Fix regressions reported after TICKET-069:

- Snapshot mode continuity should remain clickable as activity continuity.
- Layered/maintenance modes should keep state package continuity.
- State-lane no-data messaging should not appear while users are simply viewing
  the traditional Gantt.
- State-lane availability should tolerate result payloads where state package
  membership is present in diagnostics but missing on individual task rows.

## Verification

- `.venv\Scripts\python.exe -m py_compile app\db\schemas.py`
  - passed.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium`
  - 4 passed.
- `git diff --check -- frontend/src/views/SolvePage/index.vue frontend/e2e/tests/solve.spec.ts docs/TICKET_070.md docs/STATE_V0.3.md`
  - only reported the existing LF/CRLF warnings.

## Out of Scope

- No solver objective changes beyond restoring the existing activity continuity
  objective selection for snapshot mode.
- No API shape changes.

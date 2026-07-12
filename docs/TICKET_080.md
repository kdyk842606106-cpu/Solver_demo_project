# TICKET-080: Network Editor activity focus preserves staged expansion
> Status: completed
> Version: V0.3
> Created: 2026-07-10
> Completed: 2026-07-10

## Scope

Fix the Network Editor activity canvas regression where entering a virtual
activity focus or revealing an activity from validation could still set
`activityDepth = 0`, which is the explicit expand-all mode.

## Implementation Summary

- Changed activity focus canvas entry to use `activityDepth = 2`, so entering a
  package shows the package and its direct children only.
- Changed activity issue reveal and atomic activity resource selection to use
  staged depth instead of expand-all.
- Left the explicit "expand all" action as the only UI path that sets
  `activityDepth = 0`.
- Updated E2E coverage so focus canvas entry on a level-1 activity shows its
  level-2 activity and keeps the nested atomic activity hidden.

## Verification

- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "activity packages one level|focus canvas|folded package descendants|collapsed proxy"`
  - 4 passed.
- `git diff --check`
  - passed with LF/CRLF warnings only.

## Follow-up: State-transition preview depth

State-transition preview could still surface atomic activity nodes when a level-1
activity was expanded because positive `activity_depth` counted direct package
atomic refs as one level below the scope root. The frontend visibility helper now
treats atomic refs below a top-level activity scope as third-level items, and the
backend graph projection mirrors that rule for positive-depth requests.

Follow-up verification:

- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "activity packages one level|focus canvas"`
  - 2 passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py::test_network_editor_activity_depth_two_hides_nested_atomic_refs -q`
  - 1 passed, with the existing SQLite drop-order warning.
- `.venv\Scripts\python.exe -m py_compile app\services\network_editor.py tests\integration\test_master_data_api.py`
  - passed.

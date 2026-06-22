# TICKET-035: Layered solve hierarchy tree result display

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_027.md`, `docs/TICKET_031.md`, `docs/TICKET_033.md`

## Scope

Expose hierarchical activity and state result trees for layered and maintenance
solves. Existing responses already include flat `activity_summary` and
`state_summary`; this ticket adds tree-shaped fields and updates the Solve UI to
render them as expandable hierarchy tables. It also closes the presentation
items required by `docs/layered_activity_state_requirements.md` 18.1-18.6:
state-source display, task/Gantt hierarchy viewing, maintenance explanation,
and continuity explanation.

This ticket must preserve the existing flat summary fields and must not change
Planner, Scheduler, health-check, or replay semantics.

## In Scope

- Add `layered.activity_tree` to successful layered/maintenance solve
  responses.
- Add `layered.state_tree` to successful layered/maintenance solve responses.
- Each tree node should carry the same useful counts as the flat summary:
  - activity tree: scheduled task count and task step orders;
  - state tree: goal leaf count, satisfied leaf count, and status.
- Solve page should render activity/state result tables using tree data when
  available and fall back to flat summaries for older responses.
- State replay and state tree leaf rows should expose the source activity or
  current-state source for satisfied target facts.
- Solve page task details should support activity hierarchy rows.
- Solve page Gantt should support level-2 activity grouping and collapse.
- Solve page should show maintenance reuse/skip explanations and continuity
  explanations from existing solve diagnostics.
- Add integration assertions for tree nesting and aggregate counts.

## Out of Scope

- No drag/drop or editable hierarchy in solve results.
- No change to Data Management hierarchy CRUD pages.
- No change to Scheduler grouping or continuity objectives.
- No new persistence tables.

## Acceptance Criteria

- [x] `/solve/layered` success responses include `layered.activity_tree` and
      `layered.state_tree`.
- [x] Tree fields preserve level-1/2/3 nesting.
- [x] Tree aggregate counts match scheduled tasks and goal completion.
- [x] Existing `activity_summary` and `state_summary` remain present.
- [x] State tree leaf rows and replay goal rows expose target-state source.
- [x] Solve page renders tree tables with fallback to old summary fields.
- [x] Solve page task details and Gantt support activity hierarchy viewing.
- [x] Solve page shows maintenance reuse/skip and continuity explanations.
- [x] Focused integration tests pass.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- `app/services/layered_solve.py`
  - Added `layered.activity_tree` and `layered.state_tree` with preserved
    level-1/2/3 nesting.
  - Kept existing flat `activity_summary` and `state_summary` response fields.
  - Added source metadata to replay goal results and level-3 state tree rows:
    source type, step order, op rule, and activity node where applicable.
- `frontend/src/views/SolvePage/index.vue`
  - Renders state and activity hierarchy tables from tree fields, with fallback
    to existing flat summary fields.
  - Renders task details as an activity hierarchy tree for layered results.
  - Adds Gantt level-2 activity grouping and collapse controls.
  - Adds maintenance reuse/skip explanation tables.
  - Adds target-state source and continuity explanation tables.
- `tests/integration/test_layered_activity_state_api.py`
  - Asserts tree nesting, aggregate counts, and target-state source metadata for
    layered and maintenance solve responses.
- `frontend/e2e/tests/*.spec.ts`
  - Updated task-table assertions to target the visible task detail tab so
    newly added hidden explanation tables do not break existing solve/blockage
    e2e flows.

## Verification

- `python -m pytest tests/integration/test_layered_activity_state_api.py::test_layered_solve_consumes_scope_guards_and_schedules_level3_activities tests/integration/test_layered_activity_state_api.py::test_maintenance_solve_merges_intents_and_reuses_shared_provider -q`
  - 2 passed.
- `python -m pytest tests/integration/test_layered_activity_state_api.py -q`
  - 6 passed.
- `npm run build`
  - First sandbox run failed with esbuild `spawn EPERM`.
  - Escalated rerun passed.
- `python -m pytest -q`
  - 309 passed.
- `npm run test:e2e`
  - First sandbox run failed with `EPERM` when Playwright wrote `test-results`.
  - Escalated rerun after selector compatibility updates passed: 7 passed.
- Final verification after e2e compatibility updates:
  - `python -m pytest -q`: 309 passed.
  - `npm run build`: passed after escalated rerun.

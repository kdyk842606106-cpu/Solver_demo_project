# TICKET-034: Scenario import post-import layered health checks

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_026.md`, `docs/TICKET_030.md`, `docs/TICKET_032.md`, `docs/TICKET_033.md`

## Scope

Add an explicit post-import diagnostic hook to scenario Excel import. Workbooks
can optionally declare layered health checks to run after successful import,
using state-node and activity-node codes from the same workbook or existing
master data.

This ticket exposes diagnostics after import without changing import success
semantics, Planner/Scheduler logic, or the existing health-check engine.

## In Scope

- Add optional `layered_health_checks` sheet to scenario import and template.
- Validate declared checks during dry-run:
  - machine type exists or is created by the workbook;
  - target state node codes exist for the same machine type;
  - activity scope node codes exist for the same machine type;
  - each check has at least one target and one activity scope.
- Execute declared checks after successful import by calling the existing
  layered health-check service.
- Return compact check results as `post_import_health_checks`.
- Surface post-import diagnostic counts and results in Data Management import
  dialog.
- Add integration coverage for dry-run validation and successful post-import
  health execution.

## Out of Scope

- No automatic inference of health-check scopes when the workbook does not
  declare them.
- No persistence of health-check templates.
- No import rollback based solely on health warnings or blocking diagnostics.
- No new health diagnostic codes.

## Acceptance Criteria

- [x] Dry-run validates `layered_health_checks` references.
- [x] Successful import returns `post_import_health_checks`.
- [x] Failed/dry-run responses return an empty `post_import_health_checks`.
- [x] Data Management shows declared post-import checks and result rows.
- [x] Focused integration tests pass.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- Added optional `layered_health_checks` sheet support to scenario import and
  template generation.
- Added dry-run validation for check code uniqueness, machine type, target
  state node codes, activity scope node codes, boolean `include_inactive`, and
  non-empty target/scope sets.
- Added post-import execution of declared checks after layered nodes, Scope
  Guards, maintenance intents, and rules are flushed.
- Returned compact results under `post_import_health_checks`, including status,
  summary counts, blocking/warning counts, and UI-safe diagnostic rows.
- Failed and dry-run responses now return an empty `post_import_health_checks`
  list for a stable response shape.
- Data Management import dialog now shows declared post-import check counts and
  result rows after actual import.

## Verification

- `python -m pytest tests/integration/test_scenario_import_api.py::test_scenario_import_maintenance_intent_template_and_maintenance_solve -q`
  - 1 passed.
- `python -m pytest tests/integration/test_scenario_import_api.py -q`
  - 8 passed.
- `python -m pytest tests/integration/test_layered_activity_state_api.py -q`
  - 6 passed.
- `python -m pytest -q`
  - 309 passed.
- `npm run build`
  - passed after escalated rerun due sandbox `esbuild` `spawn EPERM`.
  - Existing Vite chunk-size warning remains.

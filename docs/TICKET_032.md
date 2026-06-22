# TICKET-032: Maintenance intent template scenario import

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_028.md`, `docs/TICKET_030.md`, `docs/TICKET_031.md`

## Scope

Extend scenario Excel import so maintenance intent templates can be configured
together with layered activity/state data. This closes the configuration gap for
Phase 5 self-directed maintenance planning: imported maintenance intents should
immediately be usable by `/solve/maintenance` without manually recreating them
in the UI.

This ticket reuses the existing `maintenance_intent_template` data model and
maintenance solve contract. It must not add fixed maintenance sequences or alter
Planner/Scheduler selection logic.

## In Scope

- Add optional `maintenance_intents` sheet to scenario import and template.
- Validate maintenance intent rows against existing layered semantics:
  - `scope_activity_node_code` must reference a level-2 activity node;
  - target state node codes must exist for the same machine type;
  - candidate activity scope codes must exist for the same machine type;
  - observed/desired fact templates must use known feature keys and `eq`;
  - each imported intent must define at least one target state node or desired
    fact.
- Upsert maintenance intent templates by `(machine_type_code, issue_type)`.
- Add import summary/preview counts and frontend import summary display.
- Add integration coverage proving imported templates can drive a maintenance
  solve and repeated import previews as update.

## Out of Scope

- No new maintenance solve semantics.
- No support for non-`eq` maintenance facts.
- No imported history/manual/recommended ordering.
- No fixed maintenance sequence expansion.
- No automatic post-import health check execution.

## Acceptance Criteria

- [x] Scenario dry-run validates `maintenance_intents`.
- [x] Scenario import persists and updates maintenance intent templates.
- [x] Imported maintenance templates can be listed from existing master data API.
- [x] Imported maintenance templates can be used by `/solve/maintenance`.
- [x] Data Management import dialog shows maintenance intent counts.
- [x] Focused integration tests pass.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- Added optional `maintenance_intents` sheet support to scenario import and
  template generation.
- Added maintenance fact-template parsing for `feature:eq:value` DSL and JSON
  object/array payloads, constrained to existing maintenance `eq` semantics.
- Added strict validation for level-2 maintenance scope, same-machine-type
  target/candidate node codes, known fact feature keys, active flag, metadata
  JSON, and non-empty maintenance goals.
- Added upsert persistence by `(machine_type_id, issue_type)` into the existing
  `maintenance_intent_template` table.
- Extended import preview/summary response with `maintenance_intents` counts.
- Data Management import dialog now shows maintenance intent totals and preview
  labels for layered import objects.
- Added integration coverage proving imported maintenance intents list through
  the existing master-data API, run through `/solve/maintenance`, and preview as
  updates on repeated import.

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

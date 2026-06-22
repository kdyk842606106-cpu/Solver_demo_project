# TICKET-030: Layered scenario Excel import baseline

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_024.md`, `docs/TICKET_025.md`, `docs/TICKET_026.md`, `docs/TICKET_027.md`, `docs/TICKET_029.md`

## Scope

Extend the existing business scenario Excel importer so real layered activity
and state data can be loaded in bulk. This closes the Phase 1 import gap while
preserving the current flat scenario import contract.

The importer remains a master-data ingestion layer. It must not run Planner or
Scheduler during import.

## In Scope

- Add optional workbook sheets:
  - `activity_nodes`;
  - `state_nodes`;
  - `scope_guards`.
- Add optional `rules.activity_node_code` column so imported rules can bind to
  level-3 activity nodes by business code.
- Keep old scenario workbooks valid when the new optional sheets/column are
  absent.
- Validate layered data before import:
  - machine type references exist or are created by the same workbook;
  - activity and state parent codes exist in the same machine type;
  - parent level is exactly one level above child;
  - level-1 nodes cannot have parents;
  - level-2/3 nodes require parents;
  - level-1/2 state nodes are aggregate only;
  - level-3 state nodes require defined feature keys and target values;
  - op rules can bind only to level-3 activity nodes;
  - Scope Guards can attach only to level-1/2 activity nodes;
  - level-1 activity Scope Guards can reference only level-1 state nodes.
- Strict upsert imported layered rows:
  - upsert activity nodes by `(machine_type, code)`;
  - upsert state nodes by `(machine_type, code)`;
  - replace scope guard preconditions on upsert;
  - bind rules to imported or existing activity nodes.
- Update generated scenario template and import instructions.
- Add integration coverage proving:
  - old workbooks remain compatible;
  - layered dry-run validates and previews rows;
  - import creates layered nodes and binds rules;
  - imported layered data can be used by `/solve/layered`.

## Out of Scope

- No maintenance intent template Excel import.
- No import-triggered layered health check yet.
- No Excel import for fact lifetime, setup reuse, manual order, or recommended
  order metadata.
- No change to the existing import API endpoint shape.

## Acceptance Criteria

- [x] Existing scenario import tests continue to pass without workbook changes.
- [x] Template download includes the new optional layered sheets and
      `rules.activity_node_code`.
- [x] Dry-run preview includes activity/state/scope guard create/update counts.
- [x] Import upserts activity nodes, state nodes, scope guards, and rule
      activity bindings transactionally.
- [x] Invalid hierarchy or invalid Scope Guard references fail validation and
      do not write data.
- [x] Integration test imports a layered scenario and solves it through
      `/solve/layered`.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- Scenario parser now reads optional `activity_nodes`, `state_nodes`, and
  `scope_guards` sheets while keeping existing flat workbooks compatible.
- Generated template now includes optional layered sheets and optional
  `rules.activity_node_code`.
- Dry-run validation now checks:
  - activity/state parent code existence and exact parent level;
  - level-1 parent prohibition and level-2/3 parent requirement;
  - level-1/2 aggregate state restrictions;
  - level-3 state feature/target requirements;
  - rule binding only to level-3 activity nodes;
  - Scope Guard attachment only to level-1/2 activities;
  - level-1 activity Scope Guard references only level-1 state nodes.
- Import upserts activity nodes and state nodes by `(machine_type, code)`.
- Import upserts Scope Guards by `(machine_type, activity_node_code, name)` and
  replaces their preconditions.
- Rules can now bind to level-3 activity nodes via `activity_node_code`.
- Data Management import summary now shows activity hierarchy, state hierarchy,
  and Scope Guard counts.

## Verification

- `python -m pytest tests/integration/test_scenario_import_api.py -q`
  - 7 passed.
- `python -m pytest tests/integration/test_scenario_import_api.py tests/integration/test_layered_activity_state_api.py -q`
  - 13 passed.
- `python -m pytest -q`
  - 308 passed.
- `npm run build`
  - passed after escalated rerun due sandbox `esbuild` `spawn EPERM`.
  - Existing Vite chunk-size warning remains.

# TICKET-028: Phase 5A maintenance intent templates and joint solve

> Status: completed - 2026-06-16
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_027.md`

## Scope

Implement the first Phase 5 slice: model maintenance intents as goal/capability
templates and solve one or more intents through the existing layered Planner and
Scheduler path.

This ticket focuses on self-emergent maintenance planning. Scheduler continuity
soft costs are intentionally deferred to a follow-up Phase 5 ticket.

## In Scope

- Add `maintenance_intent_template` data model and migration.
- Add CRUD APIs for templates under a machine type.
- Each template stores:
  - issue type and display name;
  - a scope activity node, normally a level-2 maintenance/repair capability
    package;
  - candidate activity scope IDs;
  - target state node IDs;
  - observed fact templates;
  - desired fact templates;
  - active flag and metadata.
- Add maintenance solve API:
  - `POST /api/v1/solve/maintenance`
- Maintenance solve must:
  - accept multiple intent template IDs;
  - merge target state nodes and activity scopes;
  - apply observed fact overrides to the current state for this solve only;
  - convert desired facts into a synthetic target state;
  - run one Planner/Scheduler path, not one solve per intent;
  - reuse Phase 4 layered solve semantics;
  - expose which intents were merged and rely on the joint Planner run to reuse
    shared provider activities.
- Add frontend:
  - template management entry under Data Management;
  - maintenance solve mode on the Solve page.
- Add tests proving:
  - multiple maintenance intents solve jointly;
  - common provider activity appears once;
  - current-state-satisfied preparation steps are skipped naturally;
  - old `/solve` and layered solve remain compatible.

## Out of Scope

- No Scheduler group span/gap/interruption/setup-reuse soft costs.
- No hard sequence modeling for maintenance packages.
- No historical/manual/recommended ordering.
- No personnel shift or crew scheduling.
- No fact lifetime modeling.

## Acceptance Criteria

- [x] Templates can be created, listed, updated, and deleted with validation.
- [x] Maintenance solve accepts multiple template IDs and returns one schedule.
- [x] Observed facts affect only the maintenance solve input state.
- [x] Desired facts and target state nodes are solved as one joint target set.
- [x] Common providers are not duplicated in the generated plan.
- [x] Frontend exposes template management and maintenance solve mode.
- [x] Existing `/solve` and `/solve/layered` regression tests pass.
- [x] Backend test suite and frontend build pass.

## Implementation Summary

- Added `MaintenanceIntentTemplate` model and Alembic revision
  `005_maintenance_intent_template.py`.
- Added maintenance intent CRUD APIs:
  - `GET /api/v1/machine-types/{machine_type_id}/maintenance-intent-templates`
  - `POST /api/v1/machine-types/{machine_type_id}/maintenance-intent-templates`
  - `PUT /api/v1/maintenance-intent-templates/{template_id}`
  - `DELETE /api/v1/maintenance-intent-templates/{template_id}`
- Added `POST /api/v1/solve/maintenance` and
  `app/services/maintenance_solve.py`.
- Extended `LayeredSolveRequest` and `app/services/layered_solve.py` so callers
  can pass solve-only current-state overrides and direct goal facts.
- Added Data Management maintenance intent template UI and Solve page
  maintenance mode.
- Added integration coverage proving two maintenance intents jointly solve and
  reuse a shared provider activity once.

## Verification

- `python -m pytest tests/integration/test_layered_activity_state_api.py -q`
  - 6 passed.
- `python -m pytest -q`
  - 301 passed.
- `npm run build`
  - sandbox run failed with Windows/esbuild `spawn EPERM`.
  - escalated rerun passed; existing chunk-size warning remains.

## Implementation Notes

- Use the existing layered solve service as the execution path wherever possible.
- Template target facts should remain data-driven. Do not create hard activity
  order from the template.
- Desired fact templates are exact feature goals for this ticket.
- Observed fact templates are solve-time current-state overrides only and should
  not mutate persisted machine state snapshots.

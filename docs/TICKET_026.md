# TICKET-026: Phase 3 layered reachability and health check

> Status: completed - 2026-06-16
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_025.md`

## Scope

Implement Phase 3 of the layered activity/state requirements: diagnose whether
expanded layered goals and candidate activities form a usable Provider/Consumer
graph before they enter the Planner/Scheduler path.

This phase remains a side-effect-free preview and diagnostics layer. It must not
change the existing `/api/v1/solve` request/response contract.

## In Scope

- Add a backend health-check service that reuses the Phase 2 expansion output
  and builds:
  - goal facts;
  - providers by produced fact;
  - consumers by required fact;
  - per-rule effective precondition diagnostics.
- Add diagnostics for:
  - `NO_PROVIDER`: no candidate activity can produce a goal fact;
  - `AMBIGUOUS_PROVIDER`: multiple candidate activities can produce a goal fact;
  - `BROKEN_CHAIN`: an effective precondition has no provider in the candidate
    activity set and is not already a selected goal fact;
  - `SELF_DEPENDENCY`: a Scope Guard requirement for an activity scope can only
    be produced inside the same guarded subtree;
  - `CONFLICTING_GOAL`: selected goal facts request multiple target values for
    the same `feature_key`.
- Add API endpoint:
  - `POST /api/v1/machine-types/{machine_type_id}/layered-health-check`
- Add frontend diagnostics entry under Data Management for running the health
  check with the same layered target/activity selection inputs.
- Add tests proving the diagnostics above and old solve compatibility.

## Out of Scope

- No change to `/api/v1/solve`.
- No Planner/Scheduler consumption of the health-check result.
- No post-solve state replay validation.
- No import pipeline hook yet; this phase exposes the reusable API that import
  and pre-solve flows can call in later phases.
- No maintenance-intent model.
- No hard activity ordering or Scheduler continuity optimization.

## Acceptance Criteria

- [x] API returns a Provider/Consumer graph summary for expanded layered input.
- [x] API returns `NO_PROVIDER` for a required goal fact with no candidate
      provider.
- [x] API returns `BROKEN_CHAIN` for an effective precondition with no provider.
- [x] API returns `SELF_DEPENDENCY` when a Scope Guard depends on a fact only
      produced inside its own guarded subtree.
- [x] API returns `CONFLICTING_GOAL` for incompatible target values on the same
      `feature_key`.
- [x] Frontend exposes the health check under Data Management.
- [x] Existing `/solve` remains unchanged and regression tests pass.
- [x] Backend test suite and frontend build pass.

## Completed

- Added `app/services/layered_health.py` as a side-effect-free
  Provider/Consumer health-check service.
- Added `POST /api/v1/machine-types/{machine_type_id}/layered-health-check`.
- Added response schemas for:
  - provider graph fact nodes;
  - provider and consumer references;
  - structured health diagnostics;
  - health-check summary and status.
- Added Data Management tab `健康检查` backed by
  `frontend/src/views/DataManagement/LayeredHealthCheckPage.vue`.
- Extended frontend API wrapper with `checkLayeredHealth()`.
- Extended layered integration coverage for `NO_PROVIDER`,
  `AMBIGUOUS_PROVIDER`, `BROKEN_CHAIN`, `SELF_DEPENDENCY`,
  `CONFLICTING_GOAL`, graph counts, and old solve compatibility.

## Verification

```text
python -m pytest tests/integration/test_layered_activity_state_api.py
4 passed

python -m pytest tests/integration/test_layered_activity_state_api.py tests/integration/test_master_data_api.py tests/unit/test_partial_order_planner.py tests/unit/test_scheduler_multi_resource.py tests/integration/test_step3_api.py tests/integration/test_blockage_strategies.py
66 passed

python -m pytest
299 passed

npm run build
passed
```

## Implementation Notes

- The service should be deterministic, side-effect free, and implemented in the
  service layer.
- The health check should consume normalized expansion data instead of
  duplicating hierarchy traversal.
- Diagnostics should be returned as data, not raised as exceptions, unless the
  selected input nodes do not exist.
- Phase 3 is allowed to report conservative diagnostics. Planner-level proof of
  solvability remains a later Phase 4 responsibility.

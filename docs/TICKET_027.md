# TICKET-027: Phase 4 layered Planner/Scheduler integration

> Status: completed - 2026-06-16
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_026.md`

## Scope

Implement Phase 4 of the layered activity/state requirements: allow Planner and
Scheduler to consume expanded layered targets, scoped level-3 activities, and
Scope Guard effective preconditions in a real solve flow.

This phase adds a new layered solve entrypoint and keeps the existing
`POST /api/v1/solve` contract unchanged.

## In Scope

- Add backend layered solve service that:
  - accepts machine, current state, layered target state nodes, and activity
    scope nodes;
  - expands target states into level-3 goal facts;
  - expands activity scopes into candidate level-3 activity rules;
  - injects Scope Guard preconditions into effective rules consumed by the
    Planner;
  - creates a synthetic target state snapshot for persistence compatibility;
  - reuses existing `SolveRequest`, `CandidatePlan`, `CandidatePlanStep`, and
    Scheduler persistence;
  - returns schedule output in the same shape as existing solve responses;
  - returns layered activity-tree and state-tree summaries;
  - runs post-solve state replay against effective preconditions and effects.
- Add API endpoint:
  - `POST /api/v1/solve/layered`
- Add frontend layered solve mode to the Solve page:
  - choose target state nodes and activity scopes;
  - run layered solve;
  - inspect layered summaries and replay validation.
- Add integration tests proving:
  - Planner consumes Scope Guard inherited preconditions;
  - only selected level-3 candidate activities enter the solve;
  - Scheduler schedules the resulting level-3 activities;
  - state replay validates final layered goals;
  - existing `/solve` remains unchanged.

## Out of Scope

- No change to existing `/api/v1/solve` request/response behavior.
- No blockage replan support for layered solve.
- No maintenance-intent templates.
- No Scheduler continuity optimization.
- No history/manual/recommended ordering logic.
- No database migration.

## Acceptance Criteria

- [x] Layered solve accepts state-node targets and activity-node scopes.
- [x] Planner consumes the expanded level-3 goal facts as a joint target set.
- [x] Planner consumes only candidate level-3 activity rules from selected
      activity scopes.
- [x] Scope Guard preconditions affect planning order.
- [x] Scheduler schedules only selected level-3 activity rules.
- [x] Response includes activity-tree summary, state-tree summary, effective
      precondition explanation, and post-solve state replay validation.
- [x] Frontend exposes layered solve mode.
- [x] Existing `/solve` regression tests still pass.
- [x] Backend test suite and frontend build pass.

## Progress

- Added `app/services/layered_solve.py` as the Phase 4 layered solve service.
- Added `POST /api/v1/solve/layered`.
- Added `LayeredSolveRequest`.
- Layered solve now:
  - expands layered targets and activity scopes;
  - creates a synthetic target state snapshot for solve persistence;
  - passes effective Scope Guard preconditions to POP;
  - persists `CandidatePlan` / `CandidatePlanStep` through the existing path;
  - schedules through the existing Scheduler;
  - returns activity/state tree summaries, effective precondition explanations,
    and post-solve state replay validation.
- Added Solve page `快照 / 分层` mode with layered target/activity selectors and
  a `分层解释` result tab.
- Added integration test coverage for Scope Guard-driven layered solve.

## Verification

```text
python -m pytest tests/integration/test_layered_activity_state_api.py -q
5 passed

python -m pytest tests/integration/test_layered_activity_state_api.py tests/integration/test_master_data_api.py tests/unit/test_partial_order_planner.py tests/unit/test_scheduler_multi_resource.py tests/integration/test_step3_api.py tests/integration/test_blockage_strategies.py
67 passed

python -m pytest
300 passed

npm run build
passed after escalated rerun
```

## Implementation Notes

- Use the Phase 2 expansion service as the normalization source.
- Use the Phase 3 health-check service for diagnostics, but do not block on
  health warnings that the current state may already satisfy.
- The layered solve service may create a synthetic target `MachineState` so the
  existing solve persistence model remains intact.
- Keep all rule evaluation and state replay behind `RuleEvaluator`.

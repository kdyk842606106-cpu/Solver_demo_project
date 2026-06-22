# TICKET-029: Phase 5B scheduler continuity soft costs

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_028.md`

## Scope

Implement the first continuity-optimization slice for layered activity scheduling.
The goal is to let Scheduler prefer compact execution of tasks that belong to
the same level-2 activity package while keeping all continuity behavior soft.

This ticket must not turn activity hierarchy order into hard dependencies.
Planner still derives required task instances from facts, and Scheduler still
only schedules level-3 tasks.

## In Scope

- Extend Scheduler task input with level-2 activity group metadata:
  - `activity_node_id`, `activity_node_code`, `activity_node_level`;
  - `activity_group_id`, `activity_group_code`, `activity_group_name`.
- Add weighted objective support for:
  - `minimize_makespan`;
  - `minimize_activity_group_span`;
  - `minimize_activity_group_gaps`;
  - `minimize_activity_group_interruptions`.
- Keep default behavior identical when no new objective is provided.
- Ensure continuity objectives are soft costs only:
  - they may influence ordering among otherwise valid schedules;
  - they must not add hard precedence or hard contiguous-window constraints;
  - they must not make a feasible schedule infeasible.
- Return Scheduler diagnostics explaining continuity:
  - per group task count;
  - group span;
  - internal idle gap;
  - interruption count;
  - objective weights used.
- Persist and expose activity group metadata in schedule task JSON.
- Add frontend controls on Solve page to enable/disable continuity preference and
  tune its weight.
- Show continuity summary in solve result UI.
- Add tests proving:
  - old solve behavior remains unchanged by default;
  - continuity objectives can reduce interruption/gap for same level-2 activity
    groups without hard-ordering tasks;
  - layered/maintenance solve can pass continuity objectives through to Scheduler.

## Out of Scope

- No hard sequence or hard adjacency constraints.
- No historical/manual/recommended ordering.
- No personnel shift scheduling.
- No fact lifetime modeling.
- No setup-reuse metadata model yet. `setup_reuse_cost` needs explicit shared
  setup/area/context facts and will be handled in a later ticket.

## Acceptance Criteria

- [x] Scheduler model supports weighted multi-objective expressions without
      breaking default `minimize_makespan`.
- [x] `StepData` and schedule task output carry activity group metadata.
- [x] Continuity diagnostics are returned for schedule results.
- [x] `/solve`, `/solve/layered`, and `/solve/maintenance` accept and preserve
      continuity objectives through the existing `objectives` array.
- [x] Frontend Solve page exposes continuity preference controls for snapshot,
      layered, and maintenance modes.
- [x] Unit tests cover Scheduler continuity cost calculations.
- [x] Integration tests cover layered or maintenance continuity pass-through.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- `StepData`, `TaskResult`, persisted task JSON, and solve responses now carry
  level-3 activity node metadata and parent level-2 activity group metadata.
- Scheduler builds `activity_groups` from scheduled level-3 activity bindings
  and keeps groups with at least two scheduled tasks for continuity costs.
- `ObjectiveRegistry.apply_all()` now builds one weighted CP-SAT objective
  expression instead of issuing multiple `minimize()` calls.
- Added objective types:
  - `minimize_activity_group_span`;
  - `minimize_activity_group_gaps`;
  - `minimize_activity_group_interruptions`.
- Continuity remains a soft optimization layer only. It does not add hard
  precedence, hard adjacency, or hard contiguous-window constraints.
- Scheduler diagnostics now include `objective_terms` and
  `activity_group_continuity` with per-group span, internal gap, interruption
  count, compactness flag, and objective weights.
- Solve page exposes an optional continuity switch and weight input. When off,
  requests continue to send only `minimize_makespan`; when on, snapshot,
  layered, and maintenance modes all send the continuity objectives through the
  existing `objectives` array.

## Verification

- `python -m pytest tests/unit/test_objectives.py tests/unit/test_scheduler_multi_resource.py tests/integration/test_layered_activity_state_api.py -q`
  - 22 passed.
- `python -m pytest -q`
  - 306 passed.
- `npm run build`
  - passed after escalated rerun due sandbox `esbuild` spawn restriction.
  - Existing Vite chunk-size warning remains.

## Implementation Notes

- Use the existing `objectives` array instead of adding a new solve request
  field.
- Prefer one combined weighted objective expression inside CP-SAT. Do not call
  `model.minimize()` multiple times for separate objectives.
- The first implementation may compute group span/gap/interruption over the
  set of scheduled tasks only; it does not need to reason about skipped tasks.
- A group with fewer than two scheduled tasks has zero continuity cost.

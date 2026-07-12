# TICKET-031: Layered activity selection and maintenance explanation

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_027.md`, `docs/TICKET_028.md`, `docs/TICKET_030.md`

## Scope

Add a lightweight explanation layer for layered and maintenance solves that
shows why candidate level-3 activities were selected or skipped, and where a
selected provider is reused by multiple goals or downstream preconditions.

This ticket must not alter Planner selection logic, Scheduler ordering, or the
existing solve contracts. It only adds response/UI explanation fields.

## In Scope

- Add `layered.activity_selection` to `/solve/layered` and `/solve/maintenance`
  responses.
- For every candidate rule from layered expansion, explain:
  - selected in the final schedule;
  - skipped because all effects were already satisfied in the input state;
  - skipped because its effects were not demanded by selected goals or selected
    downstream preconditions;
  - skipped by Planner minimal-set selection when it could contribute but was
    not required in the chosen plan.
- For selected rules, expose provider reuse:
  - goal facts satisfied by this provider;
  - downstream scheduled rules whose preconditions can be satisfied by this
    provider;
  - `is_shared_provider` when more than one consumer is present.
- Add frontend Solve layered/maintenance tab table for activity selection
  explanation.
- Add integration tests for:
  - maintenance shared provider is reported as shared;
  - already satisfied provider is reported as skipped when an observed fact
    overrides current state.

## Out of Scope

- No change to Planner scoring or provider selection.
- No full proof of why POP chose one alternative provider over another.
- No historical/manual/recommended order explanation.
- No setup reuse explanation beyond provider consumers.
- No topology-level explanation for every possible valid schedule order.

## Acceptance Criteria

- [x] Layered solve response includes `layered.activity_selection`.
- [x] Maintenance solve response includes the same field because it reuses
      layered solve.
- [x] Scheduled shared provider rules include multiple consumers and
      `is_shared_provider=true`.
- [x] Candidate rules skipped due already satisfied facts are identified.
- [x] Solve page displays activity selection explanation.
- [x] Focused integration tests pass.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- Added `layered.activity_selection` to layered solve output.
- Maintenance solve inherits the field because it delegates to layered solve.
- For each candidate effective rule, the response now reports:
  - `selected` / `skipped` status;
  - reason code;
  - selected step order when scheduled;
  - comparable effect facts;
  - goal and scheduled-precondition consumers;
  - `is_shared_provider` when one selected provider serves multiple consumers.
- Skip reasons currently include:
  - `effects_already_satisfied`;
  - `not_demanded_by_selected_plan`;
  - `not_required_by_minimal_plan`.
- Solve page now displays an `活动选择解释` table in the layered/maintenance
  explanation tab.

## Verification

- `python -m pytest tests/integration/test_layered_activity_state_api.py::test_maintenance_solve_merges_intents_and_reuses_shared_provider -q`
  - 1 passed.
- `python -m pytest tests/integration/test_layered_activity_state_api.py -q`
  - 6 passed.
- `python -m pytest -q`
  - 308 passed.
- `npm run build`
  - passed after escalated rerun due sandbox `esbuild` `spawn EPERM`.
  - Existing Vite chunk-size warning remains.

# TICKET-025: Phase 2 target and effective-rule expansion preview

> Status: completed - 2026-06-16
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_024.md`

## Scope

Implement Phase 2 of the layered activity/state requirements: expand selected
state targets and activity scopes into planner-ready facts and effective rules,
while keeping the existing `/solve` contract unchanged.

This phase provides a verifiable preview layer before Planner/Scheduler consume
the new structures in Phase 4.

## In Scope

- Add a backend expansion service that:
  - expands selected state nodes into level-3 goal facts;
  - expands selected activity nodes into level-3 candidate activities;
  - builds effective preconditions for each candidate op rule:
    - self activity rule preconditions;
    - level-2 Scope Guard preconditions;
    - level-1 Scope Guard preconditions;
  - keeps effects and resource requirements only from the level-3 activity's
    own op rule;
  - preserves source metadata for every inherited precondition.
- Add API endpoint:
  - `POST /api/v1/machine-types/{machine_type_id}/layered-expansion`
- Add Data Management frontend preview page for selecting:
  - target state nodes;
  - activity scope nodes;
  - previewing expanded goal facts, candidate activities, and effective rules.
- Add tests proving:
  - target state expansion recursively reaches leaf level-3 states;
  - activity scope expansion recursively reaches level-3 activities;
  - Scope Guards are inherited from level-1 and level-2 activities;
  - effects are not inherited from Scope Guards;
  - existing `/solve` remains unchanged.

## Out of Scope

- No change to `/api/v1/solve` request/response.
- No Planner consumption of expanded goal facts.
- No Scheduler continuity optimization.
- No maintenance-intent model.
- No Provider/Consumer health-check graph beyond basic preview diagnostics.

## Acceptance Criteria

- [x] API expands a level-1 state target into all descendant level-3 goal facts.
- [x] API expands a level-2 activity scope into all descendant level-3
      candidate activities.
- [x] Effective rule preview includes self preconditions and inherited Scope
      Guard preconditions with source labels.
- [x] Effective rule preview includes effects only from the bound op rule.
- [x] Frontend exposes a preview page under Data Management.
- [x] Regression tests show old solve flow still passes.
- [x] Backend test suite and frontend build pass.

## Completed

- Added `app/services/layered_expansion.py` as the side-effect-free expansion
  service.
- Added `POST /api/v1/machine-types/{machine_type_id}/layered-expansion`.
- Added response schemas for:
  - expanded goal facts;
  - expanded candidate activities;
  - effective rule previews;
  - source-aware effective preconditions;
  - non-fatal diagnostics.
- Added Data Management tab `展开预览` backed by
  `frontend/src/views/DataManagement/LayeredExpansionPage.vue`.
- Extended frontend API wrapper with `previewLayeredExpansion()`.
- Added integration coverage for recursive state expansion, activity expansion,
  Scope Guard inheritance, op-rule-owned effects, and old solve compatibility.

## Verification

```text
python -m pytest tests/integration/test_layered_activity_state_api.py
3 passed

python -m pytest tests/integration/test_layered_activity_state_api.py tests/integration/test_master_data_api.py tests/unit/test_partial_order_planner.py tests/unit/test_scheduler_multi_resource.py tests/integration/test_step3_api.py tests/integration/test_blockage_strategies.py
65 passed

python -m pytest
298 passed

npm run build
passed
```

## Implementation Notes

- This is a preview and normalization layer. It should be deterministic and
  side-effect free.
- The service should tolerate legacy op rules with no `activity_node_id` by
  simply excluding them from scoped expansion unless a future phase adds a
  fallback mode.
- Diagnostics should be returned as data, not exceptions, for non-fatal issues
  such as a selected activity leaf with no op rule.

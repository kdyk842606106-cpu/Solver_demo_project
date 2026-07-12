# TICKET-024: Phase 1 layered activity/state data foundation

> Status: completed - 2026-06-16
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`

## Scope

Implement Phase 1 of the layered activity/state requirements without changing
the existing `/solve` contract or Planner/Scheduler behavior.

This ticket establishes the managed data foundation for later target expansion,
effective-rule expansion, maintenance-intent planning, and continuity
optimization.

## In Scope

- Add three-level `activity_node` data model.
- Add three-level `state_node` data model.
- Add `scope_guard` and `scope_guard_precond` data model.
- Allow `op_rule` to optionally bind to one level-3 activity node.
- Add backend CRUD APIs for activity nodes, state nodes, and scope guards.
- Add validation for:
  - parent/child level consistency;
  - same machine type within each tree;
  - level-1 activity Scope Guard can only reference level-1 state nodes;
  - level-2 activity Scope Guard can reference level-1/2/3 state nodes;
  - op rules can bind only to level-3 activity nodes.
- Add minimal frontend management pages under Data Management.
- Keep all existing solve, blockage, scheduler, import, and rule CRUD behavior
  backward compatible.
- Add migration and focused tests.

## Out of Scope

- No target-state tree expansion into Planner goals.
- No effective-rule expansion into Planner input.
- No maintenance intent model or joint maintenance solve.
- No Scheduler continuity optimization.
- No historical/manual sequence or recommended sequence soft constraints.
- No change to the current `/api/v1/solve` request/response contract.

## Acceptance Criteria

- [x] Existing master-data CRUD and `/solve` flow still passes.
- [x] A machine type can have level-1/2/3 activity nodes.
- [x] A machine type can have level-1/2/3 state nodes.
- [x] A level-3 activity node can be linked from an op rule.
- [x] A level-1 or level-2 activity node can have Scope Guards.
- [x] Level validation rejects invalid parent chains.
- [x] Scope Guard validation rejects state references disallowed by activity
      level.
- [x] Deleting nodes in use is rejected rather than silently breaking rules.
- [x] Data Management UI exposes activity hierarchy, state hierarchy, and
      Scope Guard management.
- [x] Regression tests cover the new APIs and prove the existing solve path is
      unchanged.

## Completed

- Added `activity_node`, `state_node`, `scope_guard`, and
  `scope_guard_precond` ORM models and migration `004_layered_activity_state`.
- Added nullable `op_rule.activity_node_id` so existing rules remain valid
  while new rules can bind to level-3 activity nodes.
- Added master-data CRUD APIs with hierarchy and Scope Guard validation.
- Added frontend Data Management tabs:
  - 活动层级
  - 状态层级
  - 作用域约束
- Extended RulePage so op rules can optionally bind to level-3 activity nodes.
- Added integration coverage in
  `tests/integration/test_layered_activity_state_api.py`.

## Verification

```text
python -m pytest tests/integration/test_layered_activity_state_api.py tests/integration/test_master_data_api.py
3 passed

python -m pytest tests/unit/test_partial_order_planner.py tests/unit/test_scheduler_multi_resource.py tests/integration/test_step3_api.py tests/integration/test_blockage_strategies.py
61 passed

python -m pytest
297 passed

npm run build
passed
```

## Implementation Notes

- This phase intentionally stores hierarchy metadata separately from the current
  planner tables so old rules remain valid.
- `op_rule.activity_node_id` must remain nullable.
- Scope Guards must not contain effects or resource requirements.
- Phase 2 will consume these data structures to build effective preconditions.

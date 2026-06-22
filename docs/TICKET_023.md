# TICKET-023: Partial Order Planner replaces forward BFS

> Status: completed - 2026-06-01
> Version: V0.3

## Scope

Replace the Planner main strategy with an instance-level Partial Order Planner
while keeping the existing `/solve`, RAG, Scheduler, and persistence contracts.

## Completed

- [x] Created implementation branch `codex/partial-order-planner`.
- [x] Added `app/core/planner/partial_order.py`.
- [x] Implemented in-memory POP structures:
  - `Fact`
  - `ActivityInstance`
  - `OpenPrecondition`
  - `CausalLink`
  - `OrderingConstraint`
  - `PopPlanResult`
- [x] Switched `build_rag()` from `forward_bfs_plan()` to POP.
- [x] Changed persisted `candidate_plan.search_method` to `partial_order`.
- [x] Kept the existing RAG and `candidate_plan_step.predecessor_ids` contract.
- [x] Supported repeated operation instances for numeric `increment/decrement`
  chains.
- [x] Added causal-link threat protection and write-conflict ordering.
- [x] Added transitive reduction before RAG output.
- [x] Added POP diagnostics in the existing solve diagnostics payload.
- [x] Added focused POP unit tests and updated integration expectations.
- [x] Updated Planner protocol documentation.

## Follow-up Extension - 2026-06-02

- [x] Added `sub` and `reset` effect semantics to the registered effect system.
- [x] Extended POP with state/effect replay and re-provider closure for unmet
  downstream preconditions and repairable final numeric goal drift.
- [x] Covered repeated cleaning, repeated power switching, and unrelated-branch
  parallel preservation in POP unit tests.
- [x] Synchronized Excel import, RulePage effect selection, planner helper
  semantics, and planner documentation.

## Verification

```text
tests/unit/test_planner.py
tests/unit/test_forward_bfs.py
tests/unit/test_scheduler_multi_resource.py
tests/unit/test_partial_order_planner.py
tests/integration/test_planner_integration.py
tests/integration/test_step3_api.py
tests/integration/test_blockage_strategies.py
```

Result:

```text
104 passed
```

Known warnings are pre-existing SQLAlchemy table-drop ordering warnings and a
pytest cache warning in `.pytest_cache`.

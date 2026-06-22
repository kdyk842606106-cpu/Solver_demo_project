# Planner Module Protocol

Path: `app/core/planner/`

Planner is responsible for deriving a legal operation DAG from a current
machine state, a target machine state, and the active operation rule library.
The current main strategy is an instance-level Partial Order Planner (POP).

## Core Entry Points

### `build_rag(current_state_id, target_state_id, session, current_state_override=None, include_repair=False) -> PlanResult`

Returns:

```python
PlanResult(
    status="success" | "no_solution" | "error",
    rag=RAG(...) | None,
    error_message=str | None,
    diagnostics=dict | None,
)
```

`RAG` remains Scheduler-compatible:

```python
RAG(
    nodes=[
        RAGNode(
            id=1,
            op_rule_id=3,
            op_rule_code="OP_WARMUP",
            predecessors=[],
        )
    ],
    edges=[(1, 2)],
)
```

### `save_candidate_plan(rag, solve_request_id, session) -> int`

Persists the RAG to:

- `candidate_plan`
- `candidate_plan_step`

`candidate_plan.search_method` is now `partial_order`.

## Main Strategy: Partial Order Planner

The planner no longer uses `forward_bfs` as the `build_rag()` main path.
`bfs.py` is retained as a historical implementation and regression reference.

Current POP flow:

1. Load `current_state` and `target_state`.
2. Apply `current_state_override` when Strategy B/AB injects repair state.
3. Compute target obligations from the current/target state delta.
4. Load active `OpRule` rows for the machine type.
5. Create virtual `START` and `FINISH` instances.
6. Add all target facts as open preconditions of `FINISH`.
7. Resolve open preconditions by selecting providers:
   - `START` facts when current state already satisfies the fact;
   - existing activity instances when their effects can safely support the fact;
   - new `OpRule` activity instances.
8. Add causal links and ordering constraints.
9. Detect and protect causal links from threats.
10. Convert real activity instances to the existing RAG contract.
11. Apply transitive reduction before returning edges.

Planner objective:

```text
minimize selected activity instance count
tie-break by lower total duration_min
```

Scheduler still optimizes makespan on the generated DAG.

## POP Internal Structures

The following structures are in memory only:

- `Fact`
- `ActivityInstance`
- `OpenPrecondition`
- `CausalLink`
- `OrderingConstraint`
- `PopPlanResult`

No database migration is required for the POP replacement.

## Effect and Precondition Semantics

- All precondition evaluation still goes through `RuleEvaluator`.
- All effect application semantics still come from the registered effect system.
- `set` / `reset` effects can directly provide exact facts.
- `increment` / `decrement` / `sub` effects can synthesize repeated numeric provider
  chains, such as `0 -> 20 -> 40`.
- Existing `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, and `in` preconditions can be
  represented as open preconditions.
- `sub` is treated as a `decrement` alias. `reset` is treated as a set-like
  effect that restores a feature to `new_value`.
- No database migration is required for `sub` / `reset`; `effect_type` is stored
  as `String(32)` and the semantics are provided by the registered effect
  system.

Current repeated-activity capability:

- Repeated maintenance activities should be driven by downstream preconditions,
  not by a hardcoded global trigger concept. For example, activities that need a
  clean environment should declare `cleanliness > threshold`; if prior mechanical
  effects make that false, Planner should insert a cleaning provider before the
  affected consumer.
- This is the same POP obligation shape as repeated power switching: an effect
  breaks a support fact, and a later consumer requires that fact again.
- The planner performs state/effect replay plus re-provider closure for unmet
  preconditions and repairable final goal drift. Final drift applies to numeric
  and non-numeric facts when a direct provider exists, such as restoring
  `cleanliness=100` or `power=off` before finish.
- Re-provider insertion must add only the minimal required ordering edges
  around the affected feature, such as `latest_writer -> provider -> consumer`.
  Unrelated branches remain unconstrained so Scheduler can still discover
  resource-feasible parallel execution.

## Repair / Blockage Semantics

- Strategy B / AB still injects `blockage_reason` through
  `current_state_override`.
- `include_repair=True` still controls whether repair rules are loaded.
- RAGBuilder remains generic: it does not know the business concept of
  blockage. It only sees state features, preconditions, effects, and rules.

## Output Contract

Planner to Scheduler still uses `candidate_plan_step`:

| Field | Meaning |
|---|---|
| `step_order` | RAG node id, starting at 1 |
| `op_rule_id` | Referenced operation rule; duplicates are allowed |
| `predecessor_ids` | Predecessor `step_order` values |

Repeated `op_rule_id` values represent separate activity instances and remain
valid for Scheduler, blockage positioning, and step role diff.

## Diagnostics

POP diagnostics include:

```json
{
  "planner_strategy": "partial_order",
  "planner_objective": "minimize_activity_instances",
  "planner_tie_break": "total_duration_min",
  "selected_instance_count": 0,
  "total_duration_min": 0,
  "open_precondition_count_peak": 0,
  "causal_link_count": 0,
  "ordering_count_before_reduction": 0,
  "ordering_count_after_reduction": 0,
  "threats_detected": 0,
  "threats_resolved": 0,
  "provider_branches": 0,
  "provider_rejections": {}
}
```

API still maps Planner `no_solution` to `NO_SOLUTION`.

# Partial Order Planner Gap and Requirements Report

> Created: 2026-06-01
> Baseline: `docs/STATE_V0.3.md`, `docs/protocols/planner.md`, current `forward_bfs` implementation
> Scope: Planner domain model, search strategy, RAG generation, Scheduler contract, API diagnostics, test coverage

---

## 1. Purpose

This report evaluates the gap between the current Planner implementation and the capability required for a Partial Order Planner (POP) suitable for large integration-planning scenarios.

The immediate trigger is a real diagnostic case:

- `rules_count = 107`
- `goal_feature_count = 107`
- `max_depth = 500`
- `max_nodes = 20000`
- `limit_type = max_nodes`
- `max_depth_seen = 10`
- `visited_count = 46503`
- `queue_size_peak = 26503`
- `duplicate_state_skips = 167342`

The result shows that the current failure is not caused by insufficient depth. It is caused by combinatorial state growth from many weakly ordered or independent goal features.

The key product requirement is:

> Search a very large rule/state space for a shortest or low-cost set of required activities, including repeated operation instances such as repeated power-on/power-off, then construct a partial-order DAG for scheduling.

---

## 2. Current Planner Baseline

The current Planner main strategy is `forward_bfs`.

Relevant implementation:

- `app/core/planner/bfs.py`
- `app/core/planner/search.py`
- `app/core/planner/state.py`
- `app/core/solver/rule_evaluator.py`
- `app/core/scheduler/solver.py`

Current flow:

1. Load `current_state` and `target_state`.
2. Compute initial state delta.
3. Treat changed target features as BFS goal features.
4. Load active `OpRule` records for the machine type.
5. Expand executable rules from the current full state.
6. Apply effects through `RuleEvaluator`.
7. Use frozen full state as `visited` key.
8. Stop when all target delta features are satisfied.
9. Convert the discovered linear transition path into RAG nodes and predecessor edges.
10. Pass the RAG to Scheduler.

Current strengths:

- Rule evaluation is centralized through `RuleEvaluator`.
- Effects are applied to immutable state copies.
- Repeated `op_rule_id` can be represented as repeated plan steps.
- Scheduler accepts a DAG through `CandidatePlanStep.predecessor_ids`.
- Multi-resource scheduling is already supported through `resource_reqs`.
- BFS diagnostics now expose search failure causes.

Current limits:

- Search object is still a linear execution path.
- Full-state BFS enumerates many equivalent orderings of independent operations.
- Final-state delta cannot express intermediate facts whose final value returns to the initial value.
- Planning does not explicitly represent causal links.
- Planning does not explicitly represent threats, delete effects, or causal-link protection.
- Activity instances exist only after BFS transitions are generated, not as first-class search objects.

---

## 3. Why Current BFS Fails on Large Integration Cases

The current BFS treats the state as a full feature assignment:

```text
state = {
  S8.1.1 = installed | not_installed,
  S8.1.2 = installed | not_installed,
  ...
}
```

With many independent or weakly dependent operations, BFS explores combinations of completed features.

For `n` independent binary features, the reachable state space is approximately:

```text
2^n
```

This is different from map navigation, where:

```text
state = current_location
```

In map navigation, reaching the same location collapses future search. In integration planning, reaching a different subset of completed facts usually creates a different state, even if those facts are order-independent.

In the observed diagnostic case:

```text
depth_enqueued:
1  -> 7
2  -> 23
3  -> 54
4  -> 118
5  -> 268
6  -> 639
7  -> 1570
8  -> 3847
9  -> 9120
10 -> 20482
11 -> 10374
```

This confirms shallow exponential growth. The search reaches only depth 10 before `max_nodes` is exceeded.

The current BFS is therefore not aligned with large multi-goal planning where the desired output is a partial-order DAG rather than a linear activity sequence.

---

## 4. Why State-Difference Reverse Topology Is Also Insufficient

The previous state-difference reverse-topology strategy is useful but not enough for the target requirement.

It works roughly as:

```text
target delta feature -> choose provider rule -> recursively satisfy provider preconditions -> build dependency edges
```

It is fast when:

- each goal has a single obvious provider;
- operation effects are monotonic;
- the plan does not need repeated instances of the same rule;
- final-state delta captures all required work.

But it fails or becomes unreliable when:

1. Multiple provider rules can satisfy the same goal and a global minimum is required.
2. One rule can satisfy multiple goals and should be preferred over separate rules.
3. Several goals share the same precondition provider.
4. The same `op_rule_id` must be instantiated multiple times.
5. Intermediate state changes are required even when final-state delta is zero.
6. Effects can delete or invalidate facts required by later steps.

Example:

```text
initial: power = off
target:  power = off

OP_A requires power = on, effects A_done = true, power = off
OP_B requires power = on, effects B_done = true, power = off
POWER_ON effects power = on
```

Final delta for `power` is zero, but a valid plan requires:

```text
POWER_ON#1 -> OP_A#1 -> POWER_ON#2 -> OP_B#1
```

This cannot be represented safely by final-state delta alone. It requires operation instances, open preconditions, causal links, and threat handling.

---

## 5. Required Planner Model: Instance-Level Partial Order Planning

The target Planner should search over activity support structures, not linear execution sequences.

Core concepts:

### 5.1 Fact

A fact is a normalized planning predicate:

```text
feature_key operator value
```

Initial Phase 1 should focus on exact facts:

```text
feature_key == value
```

Examples:

```text
S8.1.1 == installed
power == on
seal_test == passed
```

### 5.2 Activity Instance

An activity instance is one concrete occurrence of an `OpRule`.

```text
ActivityInstance(
  instance_id="POWER_ON#2",
  op_rule_id=10001,
  preconditions=[power == off],
  effects=[power == on]
)
```

The same `op_rule_id` may appear multiple times:

```text
POWER_ON#1
POWER_ON#2
POWER_ON#3
```

This is mandatory for repeated power-on/power-off, repeated setup, repeated test, repeated numeric increment, or repair insertion.

### 5.3 Open Precondition

An open precondition is not just a global goal. It belongs to a consumer activity instance.

```text
OpenPrecondition(
  consumer_instance_id="OP_A#1",
  fact=power == on
)
```

This is necessary because two activities may both require the same fact, but one provider instance may not safely support both if an intermediate activity deletes that fact.

### 5.4 Causal Link

A causal link records that one activity instance supports a precondition of another.

```text
POWER_ON#1 -- power == on --> OP_A#1
```

This is stronger than a simple DAG edge. It explains why the edge exists.

### 5.5 Ordering Constraint

Ordering constraints form the final partial-order graph.

```text
provider_instance -> consumer_instance
```

Additional ordering constraints may be required to protect causal links from threats.

### 5.6 Threat

A threat is an activity whose effects can invalidate a causal link.

Example:

```text
POWER_ON#1 -- power == on --> OP_B#1
OP_A#1 effects power = off
```

If `OP_A#1` can occur between `POWER_ON#1` and `OP_B#1`, then it threatens the causal link.

Resolution options:

1. Promotion: place the threatening activity after the consumer.
2. Demotion: place the threatening activity before the provider.
3. Re-provider: instantiate a new provider, e.g. `POWER_ON#2`.
4. Reject branch if no safe resolution exists.

---

## 6. Target Search Strategy

The recommended strategy is an instance-level goal-directed partial-order search.

High-level flow:

```text
1. Convert current_state and target_state into initial facts and target goals.
2. Create virtual START and FINISH instances.
3. Add target goals as open preconditions of FINISH.
4. Repeatedly select one open precondition.
5. Find candidate providers:
   - an existing activity instance;
   - current START facts;
   - a new instance of an OpRule whose effect can satisfy the fact.
6. Add causal link and ordering constraint.
7. Add the provider's own preconditions as open preconditions.
8. Detect and resolve threats.
9. Stop when no open preconditions remain and no unresolved threats remain.
10. Convert activity instances and orderings into RAG.
11. Apply transitive reduction to reduce redundant edges.
```

The search state is not:

```text
full machine state
```

It is:

```text
selected activity instances
open preconditions
causal links
ordering constraints
```

This avoids enumerating arbitrary linear orderings of independent work.

---

## 7. Cost and "Shortest Path" Definition

The phrase "shortest activity path" must be formalized.

Candidate cost definitions:

| Cost | Meaning | Notes |
|---|---|---|
| Activity count | Minimize number of activity instances | Best Phase 1 target |
| Total duration | Minimize sum of `duration_min` | Does not equal makespan |
| Makespan | Minimize scheduled completion time | Requires Scheduler feedback |
| Weighted business cost | User-defined operation cost | Needs data model extension |
| Risk-adjusted cost | Penalize unstable/repair/optional operations | Later extension |

Recommended Phase 1:

```text
Planner objective: minimize activity instance count
Tie-break: lower total duration
Scheduler objective: minimize makespan on the resulting DAG
```

This is not globally makespan-optimal, but it gives a clear and testable first implementation.

Global makespan optimization would require a deeper integration between Planner and Scheduler and should be treated as a later phase.

---

## 8. Current Project Gaps

### GAP-1: Search object is full state, not partial plan

Current:

```text
SearchNode(state, path)
```

Needed:

```text
PopSearchNode(
  instances,
  open_preconditions,
  causal_links,
  ordering_constraints
)
```

Impact:

- Current BFS enumerates state subsets and order permutations.
- POP searches support structures directly.

### GAP-2: Activity instances are not first-class during planning

Current:

- Repeated `op_rule_id` is represented after BFS creates repeated transitions.
- The planner path is still a linear list.

Needed:

- `ActivityInstance` must exist during search.
- Multiple instances of one `OpRule` must be valid and distinguishable.

Impact:

- Required for repeated power-on/power-off.
- Required for repeated setup/test/repair operations.
- Required for instance-level blockage positioning.

### GAP-3: Preconditions are not represented as open obligations

Current:

- Preconditions are checked only against the current full BFS state.

Needed:

- Preconditions should become explicit obligations:

```text
consumer instance needs fact F
```

Impact:

- Enables causal-link explanation.
- Enables provider reuse.
- Enables threat detection.

### GAP-4: No causal-link model

Current:

- RAG edges are inferred from prior writers after BFS path discovery.

Needed:

- Explicit causal links during planning:

```text
provider -- fact --> consumer
```

Impact:

- Required to explain why an activity exists.
- Required to detect whether a delete effect threatens a later precondition.

### GAP-5: No threat detection

Current:

- Effects are applied sequentially in BFS state simulation.
- BFS naturally avoids invalid final states only along one linear sequence.

Needed:

- POP must detect threats in partial orders:

```text
An activity can occur between provider and consumer and can invalidate the causal fact.
```

Impact:

- Required for repeated on/off.
- Required for temporary support states.
- Required for safe parallelism.

### GAP-6: Final-state delta cannot express intermediate work

Current:

- Goal facts are derived from `compute_state_delta(current_state, target_state)`.

Needed:

- Goals must include:
  - final target facts;
  - selected activity preconditions;
  - intermediate facts generated during planning;
  - optional explicit goals not represented by final state delta.

Impact:

- Required when final value equals initial value but intermediate transitions are mandatory.

### GAP-7: No domain-level implication or abstraction model

Current:

- Every feature is treated as an independent state component unless rules connect it.

Needed:

- Optional implication/normalization layer:

```text
S8.10 installed implies S8.1..S8.9 installed
S8.1 not installed implies later installation facts are invalid
```

Impact:

- Reduces meaningless state combinations.
- Improves diagnostics and pruning.
- Can also support POP provider pruning.

### GAP-8: No POP-specific diagnostics

Current BFS diagnostics expose:

- expanded nodes
- visited count
- queue size
- precondition checks
- duplicate-state skips
- top enqueued rules

Needed POP diagnostics:

- open preconditions count
- unresolved threats count
- selected instance count
- provider branch count
- rejected provider count by reason
- reused provider count
- new instance count
- causal link count
- ordering constraint count before/after transitive reduction
- most ambiguous goals
- top provider candidates per failed goal

### GAP-9: Tests focus on BFS, not POP semantics

Needed test families:

- single-goal provider selection
- multi-goal shared provider
- one activity satisfying multiple goals
- repeated power-on/power-off instances
- delete-effect threat resolution
- impossible causal link
- transitive edge reduction
- large weakly ordered target set
- Scheduler compatibility from generated POP DAG

---

## 9. Data Model Requirements

Phase 1 can keep database schema mostly unchanged and implement POP internal structures in memory.

### Existing tables that can be reused

- `op_rule`
- `op_rule_precond`
- `op_rule_effect`
- `candidate_plan`
- `candidate_plan_step`
- `schedule_result`

### Internal-only structures needed first

```python
Fact
ActivityInstance
OpenPrecondition
CausalLink
OrderingConstraint
PopSearchNode
PopPlanResult
```

### Optional later persistence

For explainability and debugging, later versions may persist:

- causal links;
- provider fact for each predecessor edge;
- threat resolution decisions;
- planner diagnostics.

Possible future table:

```text
candidate_plan_edge
  plan_id
  from_step_order
  to_step_order
  reason_type
  feature_key
  required_value
```

This is not required for Phase 1 if `candidate_plan_step.predecessor_ids` remains the Scheduler contract.

---

## 10. Algorithm Requirements

### REQ-1: Provider index

Build an index from effects to provider rules:

```text
Fact(feature_key, eq, value) -> [OpRule]
```

Initial scope:

- support `set` effects;
- support exact enum/string facts;
- optionally support exact numeric `set`.

Later:

- increment/decrement numeric provider synthesis;
- gte/lte facts;
- conditional effects.

### REQ-2: Open precondition selection heuristic

Choose which open precondition to resolve next.

Recommended heuristic:

1. Current-state unsatisfied.
2. Fewest candidate providers first.
3. Consumer with highest downstream constraint first.
4. Goal facts before auxiliary facts only when provider count ties.

Reason:

- Resolving the most constrained fact first reduces branching.

### REQ-3: Provider choice

Provider options:

1. `START` if current state satisfies the fact.
2. Existing selected instance whose effects satisfy the fact and can be safely ordered.
3. New activity instance from provider rules.

Provider ranking:

1. Existing safe provider.
2. Rule satisfying multiple open goals.
3. Lower activity cost.
4. Lower duration.
5. Lower ambiguity.

### REQ-4: Activity instance creation

Creating a provider rule creates a new `ActivityInstance`.

Rules:

- Same `op_rule_id` may be instantiated multiple times.
- Instance IDs must be stable within one plan.
- Instance-level predecessor edges must map to `CandidatePlanStep.step_order`.

### REQ-5: Threat detection

For every causal link:

```text
A -- fact F --> B
```

Any activity `T` threatens the link if:

1. `T` can be ordered between `A` and `B`; and
2. `T` has an effect that can make `F` false or different.

Initial exact-value threat rule:

```text
F = (feature_key == value)
T effects feature_key = other_value
other_value != value
```

### REQ-6: Threat resolution

Resolution options:

1. Promote threat after consumer:

```text
B -> T
```

2. Demote threat before provider:

```text
T -> A
```

3. Re-provider:

```text
create A2 -- F --> B
```

Recommended Phase 1:

- Try promotion/demotion first when acyclic.
- If impossible and the fact is reusable through an available provider, create a new provider instance.
- Otherwise reject the branch.

### REQ-7: Cycle detection

Ordering constraints must remain acyclic.

Any new constraint must be checked before accepting the branch.

### REQ-8: Cost search

Use Dijkstra or A* over partial-plan states.

Phase 1 cost:

```text
cost = selected_instance_count
tie_break = total_duration_min
```

Potential heuristic:

```text
ceil(unresolved_goal_count / max_goals_satisfied_by_one_rule)
```

The heuristic must be admissible if exact optimality is claimed.

### REQ-9: Transitive reduction

Before returning RAG:

1. Convert ordering constraints to edges.
2. Remove redundant transitive edges.
3. Keep edges needed for Scheduler precedence.

This reduces:

- Scheduler precedence count;
- graph visual complexity;
- critical-path noise.

---

## 11. API and Strategy Requirements

### 11.1 Planner strategy selection

Add planner strategy support:

```text
forward_bfs
partial_order
auto
```

Recommended initial behavior:

```text
auto:
  if goal_feature_count > 30 or rules_count > 80:
      partial_order
  else:
      forward_bfs
```

This preserves existing small-case behavior while routing large cases away from BFS explosion.

### 11.2 Solve request extension

Optional request field:

```json
{
  "planner_strategy": "auto"
}
```

Default should remain backward compatible.

### 11.3 Response diagnostics

Extend `diagnostics` with:

```json
{
  "planner_strategy": "partial_order",
  "selected_instance_count": 0,
  "open_precondition_count_peak": 0,
  "causal_link_count": 0,
  "ordering_count_before_reduction": 0,
  "ordering_count_after_reduction": 0,
  "threats_detected": 0,
  "threats_resolved": 0,
  "provider_branches": 0,
  "provider_rejections": {
    "cycle": 0,
    "threat_unresolved": 0,
    "no_provider": 0
  }
}
```

---

## 12. Scheduler Compatibility

The Scheduler can remain mostly unchanged if POP outputs the same RAG contract:

```text
RAGNode(
  id=step_order,
  op_rule_id=...,
  op_rule_code=...,
  predecessors=[...]
)
```

Important compatibility points:

- repeated `op_rule_id` must remain allowed;
- predecessor IDs must refer to instance step orders, not rule IDs;
- transitive reduction must not remove required causal ordering;
- Scheduler resource constraints should still determine actual parallel timing.

POP should not decide exact start times. It should output a safe partial order.

---

## 13. Recommended Phased Implementation

### Phase 0: Preserve and measure

Goal:

- Keep `forward_bfs` stable.
- Keep diagnostics.
- Add strategy skeleton.

Deliverables:

- `PlannerStrategy` enum or equivalent.
- `planner_strategy` diagnostics.
- No behavior change unless explicitly selected.

### Phase 1: POP for monotonic exact facts

Scope:

- exact enum/string facts;
- `set` effects;
- no destructive effects or treat destructive conflicts as branch rejection;
- instance-level activities;
- causal links;
- DAG generation;
- transitive reduction.

Use cases:

- many target features;
- shared providers;
- one rule satisfying multiple goals;
- large weakly ordered plans.

Out of scope:

- repeated on/off threat re-provider;
- numeric increments;
- complex delete-effect recovery.

### Phase 2: Threat detection and repeated support facts

Scope:

- detect delete-effect threats;
- promotion/demotion ordering;
- re-provider instance creation;
- repeated power-on/power-off patterns.
- effect-driven unmet-precondition repair for downstream consumers.

Use cases:

- `power=off -> power=on -> work -> power=off -> power=on -> work`;
- repeated setup/teardown;
- temporary support states.
- repeated cleaning when mechanical effects reduce `cleanliness` below a later
  activity's explicit precondition threshold.

Clarified requirement (2026-06-02):

- Repeated cleaning is not modeled as a standalone global threshold trigger.
- Activities that require a clean environment must declare explicit
  preconditions, such as `cleanliness > 30`.
- If earlier activity effects make that precondition false, POP should treat it
  the same way as repeated power-on/power-off: create or reuse a provider that
  re-satisfies the consumer's support fact, then order it before the consumer.
- This keeps cleaning and power switching under one repeated-support/re-provider
  mechanism.

### Phase 3: Numeric and resource-aware planning integration

Scope:

- numeric exact and threshold facts;
- repeated numeric provider synthesis;
- numeric replay for checking whether downstream numeric preconditions remain
  true after prior effects;
- optional planner cost weights;
- Scheduler feedback loop for makespan-sensitive alternatives.

### Phase 4: Explainability and persistence

Scope:

- persist causal links or edge reasons;
- expose why each activity was selected;
- expose why each predecessor edge exists;
- expose threat resolution decisions.

---

## 14. Acceptance Criteria

### AC-1: Large weakly ordered target set does not exceed BFS-style node explosion

Given 100+ target features with weak dependencies:

- POP should select required instances without enumerating linear orderings.
- Diagnostics should show selected instances and causal links, not 20000+ full-state expansions.

### AC-2: Shared provider is selected once

Given:

```text
OP_A requires P
OP_B requires P
OP_P provides P
```

Expected:

```text
OP_P appears once unless deleted/threatened.
```

### AC-3: One provider satisfying multiple goals is preferred

Given:

```text
OP_X provides G1
OP_Y provides G2
OP_Z provides G1 and G2
```

Expected under activity-count cost:

```text
OP_Z is selected.
```

### AC-4: Repeated power-on is represented with multiple instances

Given:

```text
OP_A requires power=on and effects power=off
OP_B requires power=on
POWER_ON effects power=on
```

Expected:

```text
POWER_ON#1 -> OP_A
OP_A -> POWER_ON#2 -> OP_B
```

### AC-5: Generated DAG remains schedulable

For every successful POP plan:

- `CandidatePlanStep` rows are persisted.
- Scheduler returns feasible/optimal if resources allow.
- repeated `op_rule_id` works correctly.

### AC-6: Transitive reduction removes redundant edges

Given:

```text
A -> B
B -> C
A -> C
```

Expected:

```text
A -> C is removed unless it carries a non-redundant explicit constraint.
```

---

## 15. Main Risks

### Risk 1: POP implementation complexity

POP is more complex than BFS. It requires careful internal data structures and deterministic diagnostics.

Mitigation:

- implement in phases;
- keep BFS as fallback;
- keep Phase 1 monotonic and exact.

### Risk 2: Rule data quality

POP depends heavily on complete and correct precondition/effect semantics.

If an operation actually powers off the system but the effect is missing, POP may produce unsafe parallelism.

Mitigation:

- add rule health checks;
- add conflict/threat diagnostics;
- expose edge reasons for manual review.

### Risk 3: "Shortest" may not match business expectation

Minimizing activity count may not minimize makespan or operational risk.

Mitigation:

- define Phase 1 objective explicitly;
- allow future weighted cost;
- let Scheduler optimize timing after POP.

### Risk 4: Provider branching can still explode

POP avoids order permutation explosion but can still face provider-combination explosion.

Mitigation:

- provider ranking;
- dominance pruning;
- beam limit as optional non-exact mode;
- diagnostics for most ambiguous goals.

---

## 16. Recommended Next Ticket

Create a new implementation ticket:

```text
TICKET-023: Partial Order Planner Phase 1 - Monotonic exact-fact DAG planning
```

Proposed scope:

1. Add planner strategy selection.
2. Add `app/core/planner/partial_order.py`.
3. Implement internal structures:
   - `Fact`
   - `ActivityInstance`
   - `OpenPrecondition`
   - `CausalLink`
   - `OrderingConstraint`
   - `PopPlanResult`
4. Build exact-fact provider index from `set` effects.
5. Implement Dijkstra search over open preconditions.
6. Convert selected instances and ordering constraints to RAG.
7. Add transitive reduction.
8. Add unit tests for shared provider, multi-goal provider, large weakly ordered target set.
9. Keep `forward_bfs` as fallback.

Explicitly out of scope for TICKET-023:

- full threat re-provider;
- numeric increment/decrement synthesis;
- makespan-global optimality;
- persistent causal-link tables.

---

## 17. Summary

The current `forward_bfs` strategy is correct for small or strongly sequential state-space problems, but it is structurally mismatched with large integration cases where many target features are independent or weakly ordered and the required output is a partial-order DAG.

The old state-difference reverse-topology approach avoids some order explosion but cannot safely handle global provider choice, repeated operation instances, intermediate facts whose final delta is zero, or delete-effect threats.

The required next Planner capability is therefore an instance-level Partial Order Planner:

```text
open preconditions + activity instances + causal links + ordering constraints + threat handling
```

The recommended implementation path is phased. Start with monotonic exact facts
and DAG generation, then add effect replay, unmet-precondition repair, and
repeated support facts such as repeated power-on/power-off and repeated cleaning.
For cleaning, the preferred requirement baseline is re-provider driven: downstream
activities declare cleanliness preconditions, and prior mechanical effects that
break those preconditions force POP to insert a cleaning provider.

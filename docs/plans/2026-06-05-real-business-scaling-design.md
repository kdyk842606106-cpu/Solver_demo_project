# Real Business Scaling Design Notes

> Date: 2026-06-05
> Scope: conceptual design notes for real multi-subsystem collaboration and
> 5000+ activity-scale rule libraries.
> Status: planning note, not an implementation ticket.

## Core Judgment

At real business scale, the main problem is not "store activities in database
and solve a DAG". The main problem is:

```text
Govern a multi-subsystem process knowledge base,
then let the engine generate an explainable plan from facts, interfaces,
soft/hard constraints, and state events.
```

The system should not require people to manually maintain a global DAG. It
should use facts as the collaboration language, activity blocks as management
views, atomic activities as solving units, and soft constraints as the source of
engineering order.

## 1. Rule Library: From Text to Standard Facts

### Problem

The rule library is maintained by multiple subsystems. Each subsystem can
describe its own activities, preconditions, and outputs, but it often cannot
know which exact activity in another subsystem provides a required condition.

If the model requires maintainers to fill:

```text
Activity A depends on Activity B
```

the library will not scale.

### Direction

Use facts, not activity references, as the cross-subsystem contract:

```text
Activity A consumes Fact X.
Activity B provides Fact X.
The system derives Activity A -> Activity B.
```

Subsystem teams can submit natural-language descriptions first:

```text
Needs low-voltage power-on completed.
Needs main bus communication confirmed.
Provides hydraulic module A installed.
```

Then the library governance workflow maps the text to standard facts:

```text
power.low_voltage.status = on
bus.main.communication = normal
hydraulic.A.install_status = installed
```

### Required Layers

```text
Raw text layer
  Original subsystem description, kept as business evidence.

Standard fact layer
  Typed, governed fact definitions with owner, domain, unit, and meaning.

Activity rule layer
  Preconditions/effects bound to standard facts.
```

### Required Workflow States

```text
draft_text
  The subsystem has only provided natural-language text.

mapped
  Text has been mapped to one or more standard facts.

verified
  The owner or interface responsible person has confirmed the mapping.

ambiguous
  The text may map to multiple facts.

orphan
  A required fact has no provider activity.

conflict
  Two mappings or fact definitions conflict.
```

### Product Capability Needed

Build a rule mapping workbench:

- left side: raw text submitted by subsystem teams;
- middle: recommended standard facts;
- right side: current providers and consumers;
- actions: confirm mapping, create fact, mark ambiguity, assign owner.

AI can assist with text-to-fact recommendation, but final confirmation must stay
human-in-the-loop because a wrong mapping can produce a valid-looking but wrong
plan.

## 2. Activity Hierarchy: Management View, Not Dependency Truth

### Problem

Activity hierarchy cannot be treated as a strict encapsulation boundary. A
cross-subsystem activity may depend on a specific internal activity inside an
activity block rather than on the whole block.

This means atomic modeling and modular management cannot share the same
relationship model.

### Direction

Separate the four concepts:

```text
Hierarchy
  Used for management, ownership, and display.

Atomic activity
  Used as the executable and solvable unit.

Fact / Port
  Used for dependency and cross-level collaboration.

Preference / Cost
  Used to keep the generated plan orderly.
```

An activity block should expose public outputs instead of acting as a pure
black box:

```text
Block: electrical_power_preparation

public outputs:
  power.low_voltage.status = on
  bus.main.communication = normal
  electrical.power_ready = true

internal activities:
  E1 check power interface
  E2 low-voltage power on
  E3 main bus communication check
  E4 power preparation complete
```

External subsystems depend on the public fact:

```text
hydraulic_install_A needs power.low_voltage.status = on
```

The solver can still trace that the fact is provided by internal activity `E2`.

## 3. Hard Constraints vs Engineering Order

### Problem

If too many relationships are modeled as hard constraints, the DAG becomes too
linear. Once a blockage occurs, there is very little room to pull forward
unrelated activities.

If too few relationships are modeled as hard constraints, the result may be
feasible but disorderly and unnatural for engineers.

### Direction

Classify constraints:

```text
Causal hard constraints
  Without this fact, the activity cannot run.

Safety/process hard constraints
  Physical, safety, or process constraints that must never be violated.

Interface hard constraints
  Cross-subsystem shared states that must be satisfied.

Engineering preference constraints
  Preferred ordering, grouping, batching, and continuity rules.
```

Only the first three categories should become hard DAG edges. Engineering
preferences should enter the cost function, not the DAG.

### Examples of Soft Preferences

```text
Keep activities from the same group close together.
Avoid frequent subsystem switching.
Batch activities in the same physical area.
Prefer mainline milestones.
Allow low-risk branches to be pulled forward.
Place interface-provider activities close to their consumers.
Reduce repeated power on/off or setup/teardown switching.
```

The plan should optimize a weighted cost:

```text
total_cost =
  makespan_cost
+ subsystem_switch_penalty
+ activity_group_split_penalty
+ repeated_state_toggle_penalty
+ preferred_order_violation_penalty
+ high_risk_early_execution_penalty
```

This preserves order under normal conditions while keeping flexibility under
blockage or what-if scenarios.

## 4. State Management: Events, Not Manual State Selection

### Problem

With many activities and many state variables, users cannot manually select or
maintain every current state value. A UI that asks planners to choose every
feature value will not scale.

### Direction

Current state should be derived from:

```text
baseline state
+ completed activity effects
+ external system sync events
+ manual correction events
+ quality/inspection events
```

Users should maintain events and exceptions, not full state snapshots.

### State Model

```text
baseline_state
  A known state snapshot at a specific time.

state_event
  A state-changing event:
  - activity completed
  - activity paused
  - activity failed
  - activity reverted
  - manual correction
  - external system sync
  - quality verdict
  - blockage or exception

derived_current_state
  Cached current state generated by replaying baseline + events.
```

The user-facing workflow should be:

```text
Select project / machine / batch.
System shows current status board.
User confirms only exceptions or corrections.
System derives solve input.
```

The target state should also come from a business target template:

```text
Target: complete hydraulic subsystem A integration

Expands to:
  hydraulic.A.install_status = installed
  hydraulic.A.leak_test = passed
  hydraulic.A.pressure_test = passed
  interface.P1.status = sealed
  documents.hydraulic.A = completed
```

The planner should work from target condition sets, not from users manually
selecting hundreds of target feature values.

## 5. Data Management Priorities

The data side should evolve from flat rule tables into a governed process
knowledge base.

Priority directions:

```text
Standard fact dictionary
  Typed facts, value domains, units, ownership, and lifecycle.

Subsystem / module / interface model
  Explicit boundaries and cross-system interface facts.

Parameterized activity templates
  Avoid manually maintaining thousands of near-duplicate rules.

Activity block public outputs
  Cross-level dependency through facts/ports, not block containment.

Rule mapping workbench
  Natural-language text -> standard fact mapping with review states.

Rule health checks
  Reachability, orphan facts, provider gaps, cycles, write conflicts,
  resource completeness, and ambiguous mappings.

Versioned knowledge packages
  Rule library version, scenario version, state baseline version, and what-if
  version should be traceable.
```

## 6. Compute Engine Priorities

At 5000+ activity scale, the engine must avoid full-library search.

Priority directions:

```text
Provider / consumer indexes
  Index by effect fact, precondition fact, subsystem, operation group, and
  resource type.

Goal-relevant rule retrieval
  Load only rules related to the target delta, required interface facts,
  blockage events, and reachable providers.

Hierarchical planning
  Plan local subsystem fragments first, then coordinate through interface facts.

Hard/soft constraint separation
  Keep causal/safety/interface constraints hard; move engineering order into
  cost terms.

Business cost function
  Include risk, rework cost, priority, subsystem switching, repeated setup, and
  preferred order violations.

Incremental replanning
  Reuse unaffected portions of existing plans after blockage or state changes.

Planner-Scheduler feedback loop
  Let Scheduler report resource infeasibility back as local constraints rather
  than forcing the Planner to know all resource details.

Explainability and diagnostics
  Report which subsystem, interface fact, provider gap, resource, or mapping
  caused infeasibility.

Performance benchmarks
  Maintain fixed benchmarks for 500, 1000, and 5000+ rule libraries, plus
  50/200/500 selected-step plans.
```

## 7. Rigidity Metric

The system should measure how rigid a generated plan is.

Potential metric:

```text
DAG rigidity =
  hard_edge_count / activity_count
+ critical_path_activity_ratio
+ inverse_average_slack
+ inverse_parallel_group_count
```

High rigidity suggests too many preferences were encoded as hard constraints.
Low rigidity suggests missing structure, grouping, or preference constraints.

This metric can feed back into rule library governance.

## Recommended First Steps

1. Add data concepts for subsystem, module, interface fact, activity group, and
   activity block public output.
2. Add a standard fact dictionary and unresolved text-to-fact mapping workflow.
3. Build provider/consumer indexes for rule retrieval.
4. Define a first soft-constraint cost model for plan regularity.
5. Add state-event-based current state derivation design before expanding UI
   state selection.
6. Add rule health checks and performance benchmarks before attempting full
   5000+ scale.

## Final Principle

```text
Hierarchy manages knowledge.
Facts express dependency.
Ports expose cross-level contracts.
Atomic activities execute and solve.
Soft constraints create engineering order.
Events maintain state.
```

This separation is the main architectural move required for real-scale
multi-subsystem planning.

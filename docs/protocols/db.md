# DB Module Protocol

Path: `app/db/`

The DB layer provides:

- SQLAlchemy ORM models
- async session factory
- Pydantic schemas
- shared persistence contracts for Planner, Scheduler, and API

## Current Core Tables

- `machine_type`
- `machine`
- `state_feature_def`
- `machine_state`
- `machine_state_feature`
- `op_rule`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`
- `resource`
- `work_calendar`
- `work_calendar_revision`
- `machine_state_dimension_calendar`
- `feature_definition`
- `activity_node`
- `state_node`
- `state_node_reference`
- `activity_state_binding`
- `scope_guard`
- `scope_guard_precond`
- `atomic_activity`
- `activity_package_atomic_ref`
- `maintenance_intent_template`
- `solve_request`
- `plan_family`
- `candidate_plan`
- `candidate_plan_step`
- `schedule_result`
- `blockage_event`
- `plan_adjustment`

## `solve_request`

Written by API and used as the root request record.

Important fields:

- `machine_id`
- `current_state_id`
- `target_state_id`
- `objective`
- `objectives`
- `constraints`
- `parent_plan_id`
- `blockage_constraints`
- `overrides`
- `status`
- `created_at`
- `solved_at`

Runtime status flow is normally:

```text
running -> done | failed
```

For layered solves, `overrides` stores the immutable replay envelope:

- `effective_model_version`
- `effective_model_summary`
- `effective_model_snapshot` (`schema = effective-model/v1`)

Historical replay reads this envelope instead of resolving the old request
against current master data.

## `candidate_plan`

Written by Planner.

Important fields:

- `solve_request_id`
- `total_steps`
- `search_method`
- `version`
- `parent_plan_id`
- `replan_reason`
- `status`

Current `search_method` is `partial_order`.

Historical rows may retain `forward_bfs`; this is a compatibility value, not a
runtime strategy selector.

## `candidate_plan_step`

Written by Planner and read by Scheduler.

Important fields:

- `candidate_plan_id`
- `step_order`
- `op_rule_id`
- `predecessor_ids`
- `not_before`
- `step_role`

`predecessor_ids` stores predecessor `step_order` values. Repeated
`op_rule_id` values are valid and represent separate activity instances.

## Layered State / Activity Contracts

TICKET-097 freezes the body-reference model:

- `state_node.state_kind = aggregate` means state package.
- Non-aggregate state rows are atomic state bodies and must have
  `parent_id IS NULL`.
- Atomic state bodies carry `feature_key`, `operator`, and `target_value`.
- `state_node_reference` is the only package-to-atomic-state membership.
- Aggregate package-to-package hierarchy continues to use `state_node.parent_id`.
- Atomic state writes auto-ensure global `feature_definition` and per-machine-type
  `state_feature_def` rows.
- `activity_node` level 1/2 rows are management packages used only for
  organization, reuse entry points, filtering, and explanation.
- `atomic_activity` rows are reusable executable activity definitions.
- `activity_package_atomic_ref` attaches atomic activities to activity packages,
  allowing reuse across packages and owning package-local layout.
- `op_rule.atomic_activity_id` is the preferred executable binding. Existing
  `op_rule.activity_node_id` remains nullable and supports legacy level-3
  activity-node data.
- `activity_state_binding.atomic_activity_id` is the current executable endpoint.
  Historical package bindings remain read-only and are excluded from the
  effective model.

Migration 014 changes body-side foreign keys to `RESTRICT`: a state or activity
body cannot be deleted while referenced, bound, used by a rule, or used by a
historical plan. Parent-package foreign keys may still cascade the membership
row when the package itself is deleted; the referenced body is never cascaded.

Reference identity is stable. Package/body endpoints cannot be updated in place;
moving a member means deleting the old reference and creating a new reference.

`scope_guard` and `scope_guard_precond` are retained only as historical audit
tables. TICKET-097 performs no DDL or DML against them. Current-model write paths
return a sunset error, imports reject non-empty sheets, and all solve services
ignore the tables. Release requires both tables to remain empty.

`maintenance_intent_template` is also historical compatibility data. The
maintenance-intent product direction is no longer maintained and is not part of
`effective-model/v1`.

## `schedule_result`

Written by Scheduler and read by API.

Important fields:

- `solve_request_id`
- `candidate_plan_id`
- `solver_status`
- `makespan`
- `tasks`
- `parallel_groups`
- `critical_path`

Task JSON includes both legacy primary resource fields and the canonical
multi-resource fields:

- `resource_type`
- `resource_reqs`
- `resources`

## Work Calendar Persistence

- `work_calendar` stores calendar identity and the single active system-default
  marker.
- `work_calendar_revision` stores immutable weekly windows, exceptions, shift
  metadata, and revision fingerprints used by solve snapshots.
- `machine_state_dimension_calendar` maps machine state dimensions to calendars;
  machine-level default policy is stored on `machine`.
- Calendar-aware solve results persist resolved revision and segment metadata so
  replay does not drift when master data changes.

## Plan Families and Adjustments

- `plan_family` owns one current baseline plan and groups its candidates.
- `candidate_plan.plan_family_id` and lifecycle status distinguish baseline and
  unconfirmed candidate snapshots.
- `plan_adjustment` stores scope step ids, normalized constraints, inherited
  constraint removals, preview diagnostics, candidate linkage, and draft state.
- Confirming an adjustment atomically promotes its candidate to family baseline;
  sibling drafts become stale.

## Constraints

- Keep SQLAlchemy ORM models and Pydantic schemas separate.
- Domain modules must not import FastAPI modules.
- Planner persistence remains `candidate_plan` + `candidate_plan_step`; POP
  causal links and threat decisions are not persisted in the current version.
- Import and CRUD paths may preserve legacy level-3 `activity_node` rows, but
  new Data Management flows should prefer `atomic_activity` bindings.

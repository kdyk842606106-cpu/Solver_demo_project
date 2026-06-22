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
- `solve_request`
- `candidate_plan`
- `candidate_plan_step`
- `schedule_result`
- `blockage_event`

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

## Constraints

- Keep SQLAlchemy ORM models and Pydantic schemas separate.
- Domain modules must not import FastAPI modules.
- Planner persistence remains `candidate_plan` + `candidate_plan_step`; POP
  causal links and threat decisions are not persisted in the current version.

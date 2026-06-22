# TICKET-022: Scheduler multi-resource scheduling

> Status: completed - 2026-05-27
> Version: V0.3

## Scope

Make Scheduler support operations that require more than one resource type at
the same time.

## Completed

- [x] Model every required resource in `StepData.resource_reqs`, not only the
  legacy primary `resource_type`.
- [x] Build CP-SAT cumulative constraints for each required resource type.
- [x] Load all resource types required by a RAG before solving.
- [x] Assign concrete resources for every requirement after solving.
- [x] Respect resource instance `capacity` during assignment.
- [x] Persist and expose `resource_reqs`, `resource_type`, and full `resources`
  data in schedule task JSON.
- [x] Add focused unit regression tests.
- [x] Add Pump Body integration coverage for an operation requiring two resource
  types.
- [x] Update Scheduler protocol and STATE notes.

## Verification

```text
tests/unit/test_scheduler_multi_resource.py
tests/unit/test_schedule_graph.py
tests/integration/test_step3_api.py
tests/integration/test_blockage_strategies.py
tests/integration/test_pump_body_seed.py
```

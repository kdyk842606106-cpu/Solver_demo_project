# TICKET-066: Mechanical integration state continuity validation data
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_065.md`

## Scope

Add mechanical-integration-flavored verification data for the state-package
continuity scheduler behavior.

The goal is to prove the new continuity behavior with a business-shaped state
tree rather than only abstract ROOT/CHILD test names:

- top package: mechanical integration complete;
- child package: structure assembly complete;
- child package: transfer mechanism ready;
- four target leaf states realized by four independent mechanical tasks.

## Implementation Summary

- Extended `tests/integration/test_state_group_continuity.py` with a mechanical
  integration layered solve fixture.
- The fixture creates a mechanical integration machine type, current state,
  target state package tree, activity packages, atomic activities, operation
  rules, effects, and one shared mechanical-team resource.
- Added a regression test that verifies:
  - the top-level state package appears in `state_group_continuity`;
  - both child state packages appear as ancestor continuity groups;
  - each planned task carries top-level and child state-package membership;
  - both child state packages are scheduled compactly.
- Added `seeds/010_mechanical_integration_state_continuity_seed.sql` and loaded
  it into the local PostgreSQL database. The seed creates machine
  `MI-CONT-001`, target state package `MECH_INTEGRATION_COMPLETE`, activity
  scope `MECH_INTEGRATION_ACT`, and all solve-relevant rules/resources.

## Verification

- `.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q`
  - 3 passed.
- `.venv\Scripts\python.exe scripts\load_seed_data.py --file seeds\010_mechanical_integration_state_continuity_seed.sql`
  - loaded 56 statements and reset PostgreSQL sequences.
- Direct `solve_layered()` check against the imported database seed:
  - status `done`;
  - makespan `40`;
  - `MECH_INTEGRATION_COMPLETE`, `STRUCTURE_ASSEMBLY_COMPLETE`, and
    `TRANSFER_MECHANISM_READY` all appear in `state_group_continuity`;
  - both child packages are compact.

## Out of Scope

- No database migration.
- No changes to objective behavior from TICKET-065.
- No changes to TICKET-064 atomic-state detection.

# TICKET-068: Network Editor state dimension template and state reuse closure
> Status: completed
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_067.md`

## Scope

Align Network Editor atomic state creation with the State Target Workspace:

- Atomic states choose a template state dimension first.
- Concrete solver dimensions are derived as `template_key__normalized_state_name`.
- Atomic state metadata records `dimension_template_key` and `state_object_name`.
- Existing atomic states are searchable by name and can be reused.
- Exact matches by machine type, normalized name, template dimension, and target value reuse the same `StateNode`; adding it under another package creates a `StateNodeReference`.

## Implementation Notes

- Legacy atomic states with direct `feature_key` remain readable and editable.
- New template-backed states are validated server-side.
- Backend validation creates or updates the concrete `StateFeatureDef` from the template allowed values.
- Network Editor unified commit also converts exact template-backed state creates into reuse/reference operations.
- State dimension management continues to show only template dimensions; its empty state now says the current machine type has no state dimension templates.

## Verification

- `.venv\Scripts\python.exe -m py_compile app\api\v1\master_data.py`
  - passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -k "template_dimension or exact_template_state" -q`
  - 3 passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q`
  - 4 passed.
- `npm.cmd run build`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "same state dimension|exact same-name template|exact template state|draft states in the state reference entry"`
  - 4 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "searches existing atomic state names|exact same-name template|exact template state"`
  - 3 passed.

## Known Follow-Up

- `network-editor-full-flow.spec.ts` still contains two stale expectations from older Network Editor behavior: dragging a binding to a virtual activity package, and a `white-space: normal` assertion where the current node name style is `nowrap`. These are not part of the state dimension template path and should be refreshed in a separate E2E cleanup.

## Out of Scope

- No database migration.
- No automatic migration for legacy direct `feature_key` states.
- No automatic duplication or branching of realizer activity bindings.
- No changes to TICKET-064 atomic-state detection unification.

# TICKET-053: Network Editor existing graph load and database write-back hardening
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_052.md`

## Scope

Harden the existing machine-type Network Editor database loop without adding instance-level network models or changing solver contracts:

- load existing state/activity/atomic graph data from `POST /machine-types/{machine_type_id}/network-editor/graph`;
- write node layout, package reference layout, bindings, and draft-created nodes through `POST /machine-types/{machine_type_id}/network-editor/commit`;
- preserve business metadata while updating `_network_editor_layout`;
- reject stale revisions and validation-blocked commits without leaving partial database writes.

## Implementation

- Backend graph projection now exposes package atomic reference identity on atomic graph nodes, including `reference_id`, `reference_ids`, `package_ref_ids`, `parent_graph_id`, ref-owned `metadata_json`, and base `atomic_metadata_json`.
- Backend commit handling now supports `activity_package_atomic_ref:update`, resolves draft refs for package/atomic endpoints, and writes package-ref layout metadata separately from reusable atomic activity metadata.
- Atomic activity creation with a `package_id` can submit `package_ref_metadata_json`; layout is stored on the package ref while non-layout atomic metadata remains on `AtomicActivity.metadata_json`.
- Validation review failures now roll back before returning `422`, matching the no-half-commit expectation.
- Frontend layout draft serialization now targets package atomic refs when graph nodes carry `reference_id`, clears pending layout state after graph reload/type changes, and redraws from the post-commit graph response.
- E2E fixtures now model package atomic refs and assert package-ref layout updates plus graph reload redraw.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/integration/test_master_data_api.py -k network_editor` - 4 passed, 1 deselected; existing SQLite DROP foreign-key-cycle warning remains.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` - 17 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` - 3 passed.
- `npm.cmd run build` - passed with the existing Vite chunk-size warning.

# TICKET-059: Verify adding an atomic activity reference to a new activity package
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_058.md`

## Scope

Verify that a newly created activity node can receive an atomic activity reference through the Network Editor unified
commit flow.

The key scenario is:

1. Create a new level-1 virtual activity.
2. Create a new level-2 activity package under it.
3. Add an existing atomic activity as an `activity_package_atomic_ref` under that new level-2 package.
4. Submit all changes in one network-editor commit, using draft refs for the new activity nodes.

## Result

The path works.

`network-editor/commit` resolves the `activity_package_atomic_ref.package_id` draft ref to the newly created level-2
activity package, writes the package ref, and graph reload projects the referenced atomic activity under the new package
with its ref-owned layout metadata.

## Verification

- `.venv\Scripts\python.exe -m pytest tests/integration/test_master_data_api.py::test_network_editor_commit_adds_atomic_ref_to_new_activity_package -q` — 1 passed.
- `.venv\Scripts\python.exe -m pytest tests/integration/test_master_data_api.py -k network_editor -q` — 5 passed, 1 deselected, with the existing SQLite DROP foreign-key-cycle warning.

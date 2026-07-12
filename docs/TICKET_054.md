# TICKET-054: Network Editor demo seed data
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_053.md`

## Scope

Add one reusable demo dataset for the existing machine-type Network Editor and load it into the local PostgreSQL database.

The demo is intentionally scoped to the current `machine_type_id` network model. It does not add new schema, solver contracts, or backend APIs.

## Implementation

- Added `seeds/009_network_editor_demo_seed.sql`.
- The seed is idempotent: rerunning it replaces only `NETWORK_EDITOR_DEMO_CELL` / `NED-DEMO-001` rows and leaves unrelated data alone.
- The dataset includes:
  - one machine type and one machine instance;
  - seven state feature definitions and current/target snapshots;
  - state hierarchy with one referenced state instance and `_network_editor_layout` metadata;
  - activity hierarchy with two activity packages, six atomic activities, and package-ref layout metadata;
  - six executable op rules, resource requirements, and semantic activity-state bindings;
  - package-level context/output bindings so the Network Editor graph opens as a connected demo.
- Updated `scripts/load_seed_data.py` to execute seed SQL with `exec_driver_sql()` instead of SQLAlchemy `text()` so JSON layout metadata such as `"x":80` is not misread as a bind parameter.

## Verification

- `.venv\Scripts\python.exe scripts\test_db_connection.py` - passed.
- `.venv\Scripts\python.exe scripts\load_seed_data.py --file seeds\009_network_editor_demo_seed.sql` - 65 statements executed successfully.
- Service-level Network Editor graph projection for `NETWORK_EDITOR_DEMO_CELL` returned 13 state instances, 9 activity nodes, 19 bindings, 32 edges, and a revision.
- Network Editor validation status is `warning` with 0 blocking issues.
- Network Editor solver precheck status is `ready` with 0 blocking issues.

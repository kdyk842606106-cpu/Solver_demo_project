# TICKET-063: Reference existing states from the state create drawer
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_061.md`

## Scope

Add a Network Editor path for referencing an existing state while the user is adding an atomic state.

The desired behavior is:

1. User opens the `新建状态` drawer.
2. User can choose a state package and select an existing state to reference into that package.
3. If saving a new state is blocked by an exact same-name or same-code state, the drawer stays open
   and auto-fills that existing state into the reference selector.
4. Clicking `引用到状态包` queues `state_node_reference:create`, renders the draft reference under the target
   package immediately, and leaves the referenced state body unchanged.

## Changes

- Added a `引用已有` selector and `引用到状态包` action to the state create drawer.
- Added state drawer form support for `reference_state_node_id`.
- The reference selector now lists committed states and new `state_node:create` drafts in the current edit session.
- Exact duplicate state creates now auto-fill the reference selector when the duplicate points to a committed or draft state.
- The drawer reference action reuses the existing `queueStateReuseReference()` path, including shared-state-package
  sync/fork decisions and draft graph projection.
- Unified commit now resolves `_draft_ref` for `state_node_reference.state_node_id` and
  `state_node_reference.parent_state_node_id`.
- Unified commit also resolves nested `state_package_fork.added_state.state_node_id` reuse payloads for draft states.
- Draft state labels without codes no longer render as `null 状态名`.
- Added E2E coverage for same-name atomic state rejection, automatic reference selector fill, draft reference rendering,
  and `state_node_reference:create` commit payload serialization.
- Added backend integration coverage for `state_node_reference:create` targeting a draft-created state.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "draft states in the state reference entry|state reference entry|same-name|same state dimension|atomic reference entry"` — 6 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 27 passed.
- `.venv\Scripts\python.exe -m pytest tests/integration/test_master_data_api.py -k network_editor -q` — 5 passed, 1 deselected, with the existing SQLite DROP foreign-key-cycle warning.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend schema changes.
- No solver behavior changes.
- No automatic reference creation without the user clicking `引用到状态包`.

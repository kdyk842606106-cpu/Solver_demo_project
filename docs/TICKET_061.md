# TICKET-061: Reject exact same-name state creation and point users to references
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_060.md`

## Scope

Change Network Editor duplicate-state handling so an exact same-name or same-code state is not silently reused and is not
allowed through the duplicate review dialog.

The desired behavior is:

1. User attempts to create a state whose name or code exactly matches an existing state in the same machine type.
2. The editor rejects the create attempt immediately.
3. The message names the existing state and tells the user to reference that state instead.
4. No draft `state_node:create` or `state_node_reference:create` is queued automatically.

## Changes

- Replaced exact duplicate auto-reuse with a hard frontend rejection for exact same-name or same-code state creation.
- Exact duplicate detection now checks both committed states and draft `state_node:create` changes in the current edit
  session.
- The rejection message now says to reference the existing state, including the concrete state label.
- The duplicate-state dialog is now reserved for similar-name review, not exact duplicate handling.
- Existing same-dimension/different-name semantics remain unchanged: state dimensions classify facts but do not decide
  state identity.
- X6 state node metadata now labels referenced state instances as `引用实例`.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "same-name|same state dimension"` — 3 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 24 passed.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend schema or API changes.
- No solver behavior changes.
- No change to explicit `状态包成员` reference creation.

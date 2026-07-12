# TICKET-072: Restore state snapshot entry in Data Management
> Status: completed - 2026-07-02
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_071.md`

## Scope

Restore a visible Data Management entry for maintaining machine state snapshots
so users can create/select `current` snapshots used by the Solve page.

## Implementation Notes

- `StatePage.vue` already existed and still uses the current
  `/machines/{machine_id}/states` APIs.
- `DataManagement/index.vue` now exposes a `状态快照` tab between `状态目标`
  and `活动能力`.
- No backend API, database, solver, or Network Editor behavior changes.

## Verification

- `npm.cmd run build` passed with the existing Vite chunk-size warning.

## Out of Scope

- No redesign of the state snapshot form.
- No automatic conversion from Network Editor state targets to current-state
  snapshots.

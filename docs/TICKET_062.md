# TICKET-062: Reference existing atomic activities from the atomic create drawer
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_061.md`

## Scope

Add a Network Editor path for referencing an existing atomic activity while the user is adding an atomic activity.

The desired behavior is:

1. User opens the `新建原子活动` drawer.
2. User can choose an activity package and select an existing atomic activity to reference into that package.
3. If saving a new atomic activity is blocked by an exact same-name or same-code atomic activity, the drawer stays open
   and auto-fills that existing activity into the reference selector.
4. Clicking `引用到活动包` queues `activity_package_atomic_ref:create`, renders the draft reference under the target
   package immediately, and leaves the atomic activity body unchanged.

## Changes

- Added a `引用已有` selector and `引用到活动包` action to the atomic activity drawer.
- Added exact duplicate detection for atomic activity create against committed atomic activities and draft atomic
  activities in the current edit session.
- Duplicate atomic activity creates now auto-fill the reference selector instead of creating a duplicate body.
- Added frontend draft projection/resource-tree support for `activity_package_atomic_ref:create`.
- Added commit serialization for draft package and atomic refs in `activity_package_atomic_ref` payloads.
- Draft package atomic refs can carry layout metadata and update that same draft when moved.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "atomic reference entry"` — 1 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "same-name|same state dimension|atomic reference entry"` — 4 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 25 passed.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend schema or API changes.
- No solver behavior changes.
- No automatic reference creation without the user clicking `引用到活动包`.

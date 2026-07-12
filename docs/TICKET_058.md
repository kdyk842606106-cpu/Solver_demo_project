# TICKET-058: State reuse identity uses name/code, not state dimension
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_057.md`

## Scope

Correct the Network Editor duplicate-state reuse semantics.

State dimensions (`feature_key/operator/target_value`) provide the binary fact choice and classification for an atomic
state. They do not define whether two business states are the same reusable state. Reuse should be driven primarily by
same-name matching inside the machine type, with exact code match remaining a strong explicit identity signal.

## Changes

- Removed atomic fact/dimension equality from frontend duplicate-state candidate reasons.
- Kept exact state code and exact state name as certain duplicate signals.
- Kept similar-name matching as a review candidate, not an automatic fact-based reuse.
- Updated the user guide, acceptance matrix, and main Network Editor requirements document to state that dimensions are
  classification/fact metadata, not reuse identity.
- Added Playwright coverage proving that a new atomic state with the same `feature_key/operator/target_value` but a
  different name is created as a new state draft instead of being auto-reused.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "same state dimension"` — 1 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 21 passed.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

## Out of Scope

- No backend schema or API changes.
- No change to solver fact semantics; state facts still use `feature_key/operator/target_value` for planning.
- No change to backend duplicate-name validation warnings.

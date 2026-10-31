# TICKET-099：Planner 四类依赖与独立破坏效果

> Status: complete — 2026-10-28
> Created: 2026-10-28
> Scope: approved in this chat; retain all pre-existing uncommitted changes.

## Contract

Each activity owns one automatically created primary output state, named from the activity and bound by stable ID. Users maintain required and transition preconditions and independent `delete_effect_state_ids`. Required states survive the activity, transition states are consumed at completion, outputs become true, and independent delete effects become false without requiring those facts at start. Empty transition lists are allowed and do not imply zero duration.

At completion: `S' = (S - transition - delete_effects) union outputs`. Delete effects are writes for the entire running interval under the existing conservative locking policy. They are not causal precedence edges or reversible transitions. Conflicting roles are rejected for new v2 input. Legacy v1 defaults to no independent deletions and remains loadable without rewriting stored snapshots or hashes.

## Implementation order

- [x] Versioned contract and compatibility boundary.
- [x] Shared engine model, serial/parallel simulator, A*/GA negative-goal relevance, Validator.
- [x] Exploration API/service, LEGACY POP/CP-SAT, JSON/Excel, reference protection.
- [x] Frontend auto output and three manual binding groups; delete-effect graph overlay.
- [x] Regression, three-engine integration, browser tests, production build and old-scenario verification.

Verification: exploration backend 460 passed; Planner engines 73 passed; current Planner browser 16 passed; production build passed. Ten legacy scenarios retain identical semantics, and isolated Git HEAD engine replays retain candidate metrics and fingerprints. Old retired Network Editor browser suites remain outside this Planner acceptance; their obsolete entry point times out. Full evidence and boundaries: [acceptance record](validation/PLANNER_DELETE_EFFECTS_20261028.md). ANCHOR: no violations.

## Boundaries

No database schema migration, knowledge-repository implementation, deployment, commit, or alteration of historical run snapshots. TICKET-098 remains deferred and unchanged.

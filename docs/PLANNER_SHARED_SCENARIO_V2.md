# Planner Shared Scenario V2

V2 extends the existing [V1 contract](PLANNER_SHARED_SCENARIO_V1.md) with independent activity delete effects. New scenarios use `schema_version: 2` and `planner-shared-scenario/v2`; V1 payloads remain readable. Engine capability `independent-delete-effects/v1` is checked before execution, including when a V1 payload explicitly contains the new field. Older engines must fail explicitly instead of ignoring deletes.

## Four relations

| Relation | Input | Completion |
|---|---|---|
| required | Must be true | Preserved by the activity |
| transition | Must be true | Removed |
| output | Automatic primary output; legacy additional outputs retained | Added |
| delete effect | `delete_effect_state_ids`, no truth requirement | Removed if present |

All three manual groups accept zero or more atomic state IDs. Activity name changes keep IDs stable; uncustomized output names follow the name. Completing an activity restores its result's validity; deleting that result never deletes execution history. Zero transitions do not require milestone configuration.

New writes reject output/delete, required/delete, required/transition, transition/output and transition/delete overlaps. Duplicate deletion IDs are normalized. Missing referenced states are rejected. Atomic state deletion and activity deletion protect incoming delete references. Packages organize selection; delete effects do not bind to mutable package membership.

## Execution and search

At completion `S' = (S - transition - delete_effects) union outputs`, after events at that boundary as in V1. Parallel readers/writers use existing conservative interval locks, including deletes. Negative goals must retain deleting activities and prerequisite providers in search relevance. Negative-goal providers, threat resolution and re-providers are tested for A*, GA and LEGACY. Graph delete overlays are state influences and never mandatory precedence edges. Delete effects do not become reversible transition edges.

## Compatibility and persistence

Absent delete lists mean empty. Reading a V1 record or historical snapshot does not mutate JSON or hashes. New input uses V2; actual payload hashes include deletion lists. Results retain schema v4's existing shape, with Validator `temporal-event-validator-v5` to distinguish the new semantics. V4 candidates without deletes remain replayable. No database columns/tables are added.

JSON import remaps deletion IDs and recreates each managed primary output exactly once; draft commits resolve temporary references recursively, including `draft:<activity>:output`. Existing `created_refs` remains unchanged; the additional `created_output_refs` map reports automatic output identities. Excel adds optional `活动破坏效果` with `活动引用/状态引用`, `活动附加输出` and `状态目标`; old workbooks without these sheets import with empty deletions. Export preserves customized primary output names, initial/positive/negative state selections and legacy additional outputs.

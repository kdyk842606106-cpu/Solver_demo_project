# TICKET-064: Unify atomic state detection
> Session note 2026-07-02: 本轮处理的是“虚拟活动作为管理包、不直接绑定状态”的独立语义修正；TICKET-064 的原子状态判定统一未推进，状态保持 planned。
> Session note 2026-07-02 follow-up: 本轮处理的是 Network Editor 状态包容器逐轴安全 resize、父容器联动扩展和状态包自动整理换行；未修改原子状态判定规则、后端 helper、API 字段或 schema，TICKET-064 继续保持 planned。
> Status: planned
> Version: V0.3
> Created: 2026-07-01
> Depends on: `docs/ANCHOR.md` V0.3 terminology layer, `docs/状态活动网络图编辑器_需求设计文档.md` terminology mapping

## Scope

Unify the implementation rules used to decide whether a `StateNode` is an atomic state.

This ticket is intentionally separate from the terminology cleanup. The cleanup changed user-visible wording only; this ticket should change behavior only after the current drift is covered by tests.

## Current Audit

The codebase currently uses several related but different rules:

- `app/api/v1/master_data.py`
  - `_validate_state_node_payload()` treats non-aggregate states as atomic and requires `feature_key`, `operator == "eq"`, and `target_value`.
  - `_leaf_ids_under_state()` treats a node as a covered leaf only when it has no state children and has `feature_key + target_value`.
  - `_binding_type_for_state()` additionally requires `state_kind != "aggregate"` for direct atomic-state binding.
- `app/services/network_editor.py`
  - `_state_leaf_ids_under()` uses no children plus `feature_key + target_value`, but does not check `state_kind`.
  - Graph projection sets `is_leaf` from `bool(node.feature_key and node.target_value)`.
  - Solver-ready coverage, validation details, impact analysis, and precheck summaries then consume `leaf_state_ids` / `covered_leaf_state_ids`.
- `app/services/layered_expansion.py`
  - `_is_leaf_node()` currently means "no active children" for both state and activity trees.
  - Fact expansion later filters by `feature_key`, so an empty aggregate package can be structurally leaf-like but not fact-convertible.
- `app/services/layered_health.py`
  - `_state_leaf_fact_keys()` also starts from "no active children", then only emits facts when `feature_key + target_value` can form an exact fact key.
- `app/services/layered_solve.py`
  - Completed state-node preconditions expand through descendant state leaves and then require `feature_key + target_value`.
- `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
  - `isAtomicStateNode()` currently accepts `node.is_leaf === true || !!node.feature_key || node.state_kind === "atomic"`, which is broader than backend fact-convertible logic because `feature_key` alone is enough.

## Recommended Canonical Rule

Use one named helper concept in backend services:

```text
atomic state = active StateNode, not aggregate, no active state children/references in the chosen view,
               and fact-convertible via feature_key + operator + target_value
```

Notes:

- `state_node_reference` affects where a state appears and which package coverage includes it; it must not create a new state identity.
- `include_inactive=true` may include inactive children for audit views, but the helper should make that choice explicit.
- Empty aggregate packages should stay packages, not become atomic states.
- For this version, fact-convertible means `feature_key` is present and `target_value` is not empty; persisted atomic states still use `operator == "eq"` unless a separate operator-expansion ticket changes that.

## Implementation Tasks

- [ ] Add a shared backend helper for state package children and atomic-state/fact-convertible detection.
- [ ] Align `_leaf_ids_under_state()`, `_binding_type_for_state()`, Network Editor graph projection, solver-ready coverage, layered expansion, layered health, and layered solve on that helper.
- [ ] Narrow the frontend `isAtomicStateNode()` mirror so `feature_key` alone is not enough.
- [ ] Preserve API field names: `is_leaf`, `leaf_state_ids`, `covered_leaf_state_ids`, and issue codes remain compatibility fields.
- [ ] Add regression tests covering:
  - aggregate package with no children does not become an atomic state;
  - atomic state without `target_value` is not fact-convertible;
  - `state_node_reference` contributes to package coverage without changing state identity;
  - inactive atomic states are excluded by default and included only in audit views;
  - frontend user-visible diagnostics still say "原子状态".

## Out of Scope

- No database schema rename.
- No API field rename.
- No migration of `leaf_*` compatibility fields.
- No change to state identity or duplicate-state reuse semantics.

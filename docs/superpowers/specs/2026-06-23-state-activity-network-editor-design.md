# State-Activity Network Editor Design Freeze

> Date: 2026-06-23
> Status: Design frozen for implementation planning
> Source requirement: `docs/状态活动网络图编辑器_需求设计文档.md`
> Baseline: `docs/TICKET_036.md` and current V0.3 layered activity/state model

## Goal

Freeze the next design step for a state-activity layered network editor without
replacing the existing solver data model. The editor should become the visual
entry point for maintaining solver-ready state/activity input, but V0.3
`state_node`, `activity_node`, `atomic_activity`, `op_rule`, Scope Guard,
layered expansion, layered health checks, and layered solve remain the
canonical backend contracts.

This document intentionally stops at design freeze. It does not introduce a
migration, UI implementation, or API code change by itself.

## Baseline And Mapping

| Requirement area | Current V0.3 support | Frozen decision |
| --- | --- | --- |
| State hierarchy | `state_node` supports arbitrary-depth trees. Active childless nodes expand as atomic states; aggregate nodes do not bind facts. | Keep `state_node` as canonical state object. Parent completion remains AND over active leaf descendants. |
| Activity hierarchy | `activity_node` supports level 1/2 packages and legacy level 3 nodes. `atomic_activity` is the preferred executable capability. | Map requirement "virtual activity" to level 1/2 `activity_node`; map "executable activity" to `atomic_activity + op_rule`. |
| State-activity-state graph | Solver dependencies are derived from `op_rule.preconditions/effects`; current UI has form/tree workspaces and solve-result network graph only. | Add an editor semantic binding layer. Graph edges are projections from bindings, not primary truth. |
| State package binding | Target expansion can expand aggregate state nodes to leaf facts, but activity-specific coverage snapshots are not persisted. | Add `activity_state_binding` to persist package binding and covered leaf snapshot. |
| Coverage gap after child changes | Current expansion detects target facts, but no per-activity stale coverage state exists. | Binding coverage status is computed from `covered_leaf_state_ids` versus current active leaf descendants. |
| State package member references | Current `state_node.parent_id` is a compatibility tree. | Keep `parent_id` as the default package membership and add `state_node_reference` for additional state package appearances. |
| Virtual activity declared input/output | Scope Guard can represent inherited preconditions; no declared output package model exists. | Represent virtual declarations with `activity_state_binding` rows on level 1/2 `activity_node`. |
| Executable activity input/output | `op_rule.preconditions/effects` are canonical for solver execution. | Executable bindings synchronize to and from the linked `op_rule`; `op_rule` stays canonical for Planner/Scheduler. |
| Modeling validation | Layered expansion and health check already detect many solver-readiness problems. | Add editor validation that wraps existing checks and adds coverage/reference/orphan issues. |
| Solver precheck | `/solve/layered` already consumes target states and activity scopes. | Add solver precheck that shows database handoff readiness and the executable facts/rules that existing layered solve would read. |

## Frozen Data Model Additions

### `state_node_reference`

Purpose: allow a state to appear in additional state packages without
duplicating the state object.

Fields:

- `id`
- `state_node_id`: referenced real state node.
- `parent_state_node_id`: additional containing state package.
- `sort_order`
- `is_active`
- `metadata_json`
- `created_at`

Rules:

- `state_node.parent_id` remains the compatibility default containing package.
- A reference cannot point a node to itself.
- References must be same `machine_type_id`.
- Reference graph plus default package graph must be acyclic.
- Deleting a real state deletes its references; deleting a reference never
  deletes the real state.

### `activity_state_binding`

Purpose: persist the editor's state-activity-state relationships and state
package coverage snapshots.

Fields:

- `id`
- `machine_type_id`
- `activity_node_id`: nullable; used for virtual activity declarations on
  level 1/2 packages.
- `atomic_activity_id`: nullable; used for executable activity bindings.
- `op_rule_id`: nullable; used when an executable binding is synchronized to a
  concrete rule.
- `state_node_id`: bound state or state package.
- `binding_role`: `input`, `output`, `context_input`, `declared_output`.
- `binding_type`: `state_package` for aggregate nodes, `atomic_state` for leaf
  nodes.
- `coverage_policy`: `snapshot`.
- `covered_leaf_state_ids`: JSON array of active leaf `state_node.id` values at
  the time the user confirmed coverage.
- `coverage_status`: stored last-known value `complete`, `partial`, or `stale`;
  services recompute it before returning responses.
- `is_inherited`: true when the row represents inherited virtual context on an
  executable activity projection.
- `is_active`
- `metadata_json`
- `created_at`
- `updated_at`

Rules:

- Exactly one of `activity_node_id` or `atomic_activity_id` is required.
- `op_rule_id` is optional for virtual activity rows and required once an
  executable activity is handed off as solver-ready.
- Binding an aggregate state always creates a package snapshot by expanding
  active leaf descendants at bind time.
- Binding a leaf state stores that one leaf id in `covered_leaf_state_ids`.
- Coverage is `complete` when the snapshot equals current active leaf
  descendants, `partial` when it covers a non-empty strict subset, and `stale`
  when it references inactive/missing leaves or excludes newly added active
  leaves.
- A virtual activity's `context_input` bindings are projected into child
  executable activities during solver precheck, but they do not directly create
  `op_rule_precond` rows until confirmed as part of a rule sync.

## Synchronization With Existing Solver Model

The solver continues to consume `op_rule.preconditions` and `op_rule.effects`.
The binding layer is an editor-facing semantic model with controlled sync
rules:

- For executable input bindings, each covered leaf state becomes one
  `op_rule_precond` row using the leaf state's `feature_key`, `operator`, and
  `target_value`.
- For executable output bindings, each covered leaf state becomes one
  `op_rule_effect` row with `effect_type = set` and `new_value =
  state_node.target_value`.
- Existing `op_rule` rows remain readable even if no binding rows exist; the
  editor should generate a read-only projection from current preconditions and
  effects for legacy data.
- If an executable activity has multiple `op_rule` rows, the MVP editor does
  not auto-merge them. It shows a blocking modeling issue and routes full rule
  editing to the existing rule maintenance path.
- Virtual activity bindings do not create solver tasks. Their context inputs
  are inherited into effective rules through solver precheck, aligned with the
  existing Scope Guard semantics.
- Planner/Scheduler behavior continues to read the existing database contracts;
  solver precheck is an on-screen readiness preview, not an independent export.

## API Contract Sketch

All paths live under existing master-data API routing.

### Unified Edit Commit

- `POST /api/v1/machine-types/{machine_type_id}/network-editor/commit`

The network editor uses a page-level edit session. Opening the workspace,
refreshing submitted data, switching machine type, completing a successful
commit, or cancelling an edit session leaves the board in preview mode. Preview
mode reads submitted database state only; it may expand, collapse, focus,
inspect, validate, run solver precheck, and show impact analysis, but it must
not create draft changes or call write APIs.

The user must click `enter edit` before changing the board. Entering edit mode
captures the current graph `base_revision` and opens a local ordered
`draft_changes` list. State saves, activity saves, binding changes, coverage
refreshes, container moves, container resizing, auto-layout, state package
member changes, and sync/fork decisions are all queued into this draft list.
None of those single actions writes to the database.

`network-editor/commit` is the only write entry point from the board. The
request carries `base_revision`, `allow_warnings`, and ordered draft changes.
The backend verifies that the submitted revision still matches the current
database projection, applies all changes to the canonical tables in one
transaction, runs editor validation, and rolls back the whole batch on structural
errors or revision conflict. Solver-readiness warnings may be returned for
confirmation; if the user confirms, the frontend resubmits with
`allow_warnings=true`. A successful commit clears the draft and returns the page
to preview mode.

### References

- `GET /api/v1/machine-types/{machine_type_id}/state-node-references`
- `POST /api/v1/state-nodes/{state_node_id}/references`
- `DELETE /api/v1/state-node-references/{reference_id}`

The list endpoint returns references with state and package display fields so
the frontend can render duplicate appearances without duplicating nodes. The
network editor queues reference create/delete/update operations into the unified
edit draft instead of treating each operation as an immediate save.

### Bindings

- `GET /api/v1/machine-types/{machine_type_id}/activity-state-bindings`
- `POST /api/v1/activity-state-bindings`
- `PUT /api/v1/activity-state-bindings/{binding_id}`
- `DELETE /api/v1/activity-state-bindings/{binding_id}`
- `POST /api/v1/activity-state-bindings/{binding_id}/refresh-coverage`

Create/update accepts one activity identity, one state node, role, active flag,
and optional explicit `covered_leaf_state_ids`. If explicit coverage is omitted,
the backend defaults to full current active leaf coverage. The network editor
queues binding create/update/delete/coverage refresh operations into the unified
edit draft and writes them only through `network-editor/commit`.

### Graph Projection

- `POST /api/v1/machine-types/{machine_type_id}/network-editor/graph`

Request:

- selected state root ids
- selected activity scope ids
- view mode: `outline`, `implementation`, or `solver_ready`
- include inactive flag

Response:

- state nodes with primary/reference path metadata
- activity nodes with virtual/executable type
- projected edges from binding rows
- coverage summaries
- layout metadata passthrough when present
- validation issue summary

`GraphEdge` is response-only in the MVP:

```ts
type GraphEdge = {
  id: string
  source_id: string
  target_id: string
  type: "STATE_TO_ACTIVITY" | "ACTIVITY_TO_STATE"
  binding_id: string
}
```

### Validation

- `POST /api/v1/machine-types/{machine_type_id}/network-editor/validate`

The endpoint returns two issue groups:

- `modeling_issues`: incomplete but saveable modeling problems.
- `solver_ready_issues`: blocking or warning issues for solver handoff.

It must reuse `layered-expansion` and `layered-health-check` for provider,
consumer, broken-chain, self-dependency, and conflicting-goal diagnostics, then
add editor-only checks:

- orphan states and activities in the selected graph
- executable activity missing input or output binding
- stale or partial package coverage
- virtual activity declared output missing child executable implementation
- reference cycles
- duplicate state display paths
- cross-level binding warnings

### Solver Precheck

- `POST /api/v1/machine-types/{machine_type_id}/network-editor/solver-precheck`

The endpoint returns the solver-ready database projection without launching the
Scheduler and without exporting an independent data file:

- executable atomic activities and linked `op_rule_id`
- expanded inherited preconditions
- expanded own preconditions/effects
- excluded virtual activities with group metadata
- blocking issues that prevent solver handoff
- a solver precheck summary compatible with existing `/solve/layered` concepts

If a deprecated `export-preview` compatibility route exists, it must behave as
an alias for solver precheck. The product surface should not expose download
actions for a separate JSON export or solver template; the solver reads the
canonical database records after unified commit.

## Frontend MVP

Add a `Network Editor` workspace under Data Management. It replaces neither
the existing state target workspace nor the activity capability workspace; it
coordinates them visually.

Layout:

- top toolbar: machine type selector, enter edit, unified submit, cancel edit,
  validate, mode switch, depth controls, solver precheck
- left resource pane: state tree, activity tree, references, unplaced nodes,
  search/filter
- center canvas: one X6 free-board canvas, local expand/collapse, state package
  containers, virtual activity containers, semantic ports, semantic edge
  projection, impact highlighting
- right properties pane: selected state/activity/binding details, coverage
  snapshot, inherited context, suggested actions
- bottom validation drawer: modeling issues and solver-ready issues

X6 Canvas Refactor:

- X6 is the official canvas engine for the next board implementation. The
  product must not continue extending the current hand-written DOM/SVG
  bipartite shell as the final free-board surface.
- X6 owns canvas interaction only: cells, groups, ports, edges, selection,
  drag, resize, pan, zoom, and hit testing. Domain behavior remains in the
  existing network editor business layer.
- Existing backend contracts stay unchanged in this refactor. The board reads
  `network-editor/graph`, queues local `draftChanges`, writes only through
  `network-editor/commit`, and runs solver handoff checks through
  `network-editor/solver-precheck`.
- The front-end implementation must introduce a thin canvas boundary rather
  than wiring business rules directly into X6 event callbacks:
  - graph adapter: converts submitted graph data and local draft overlays into
    X6 cells
  - cell factory: defines state, state reference, state package container,
    virtual activity container, atomic activity, and semantic edge shapes
  - container projection: maps expand/collapse state to X6 group nodes and
    parent/child membership
  - edge projection: redirects hidden-child edges to collapsed containers and
    creates aggregate edge cells when fan-in or fan-out is too dense
  - draft bridge: converts X6 moves, resizes, connection changes, and deletions
    into the existing edit draft model
- The center surface is one coordinate space. It must not visually or logically
  split state nodes and activity nodes into separate columns. Auto-layout may
  propose a readable arrangement, but manual placement is canonical once saved.
- A high-level state package or virtual activity has two visual states:
  collapsed node and expanded container. Expanded state replaces the node shape
  with a container shape for the same business object; it must not render as a
  normal node plus a separate decorative boundary.
- State package containers may contain only state nodes and state reference
  instances. Virtual activity containers may contain only virtual activity nodes
  and atomic activity nodes; context and declared-output states remain outside
  the virtual activity container and are represented by semantic edges or focus
  strip boundary labels.
- Child node positions remain absolute canvas coordinates stored in
  `_network_editor_layout`; container size remains in
  `_network_editor_container`. This refactor does not migrate persisted layout
  metadata to parent-relative coordinates.

Page state machine:

- The default state is preview mode. Preview mode is not an unsaved edit state
  and not an auto-save state; it is a read-only view of submitted database data.
- In preview mode, the user can select nodes, inspect details, expand/collapse
  containers, enter virtual activity focus, run validation, run solver precheck,
  view impact analysis, and change display modes.
- In preview mode, the board hides or disables write actions such as create,
  edit, delete, connect, drag layout, resize container, refresh coverage, and
  state package member maintenance. Central draft enqueue logic must reject any
  write attempt that reaches it outside edit mode.
- Clicking `enter edit` starts an edit session and enables board editing. All
  writes go into the visible edit draft list and update the local working board
  only.
- Drawer `save`, canvas drag, semantic connection, coverage refresh,
  auto-layout, sync/fork choice, and container resize are draft operations. They
  must not call database write endpoints on their own.
- Clicking `cancel edit` asks for confirmation, discards the current draft,
  reloads submitted layout/data, and returns to preview mode.
- Clicking `unified submit` runs commit precheck and then applies the entire
  draft through `network-editor/commit`. Success clears the draft and returns to
  preview mode; blocking errors or a user choice to return from the review
  dialog keep the draft in edit mode.

Modes:

- `outline`: shows aggregate states, virtual activities, package bindings, and
  incomplete decomposition.
- `implementation`: shows virtual containers, executable activities, inherited
  context, own inputs, and outputs.
- `solver_ready`: hides virtual activities as tasks, expands package coverage,
  and focuses on executable rule input/output.

Interaction boundaries:

- Creating or editing state nodes enters the edit draft and is applied through
  unified submit to existing state-node APIs.
- Creating or editing activity packages and atomic activities enters the edit
  draft and is applied through unified submit to existing activity APIs.
- Connecting a state to an activity queues a draft create/update for
  `activity_state_binding`; the binding is persisted only by unified submit.
- Drag-based free-board layout is persisted as metadata through the same edit
  draft and unified submit path as semantic changes.
- The MVP does not edit duration, resources, cost, advanced operators, or
  multi-rule merge behavior.

## Validation Semantics

Modeling validation is saveable and advisory:

- isolated state
- isolated activity
- activity missing input
- activity missing output
- virtual activity not decomposed
- virtual activity partially implemented
- partial/stale state package coverage
- duplicate display name within sibling scope
- cross-level binding notice

Solver-ready validation can block solver handoff:

- executable activity has no input state
- executable activity has no output state
- executable activity has no single linked `op_rule`
- state reference or primary tree cycle
- unresolved stale coverage on a required package binding
- declared virtual output not implemented by child executable outputs
- missing provider or broken chain from layered health check
- conflicting goal facts from layered expansion

## Explicit Non-Goals For MVP

- no duration editing in the graph editor
- no resource editing in the graph editor
- no cost editing
- no Scheduler rewrite
- no automatic planner execution from save
- no automatic state rollback or invalidation inference
- no OR or CUSTOM aggregation
- no automatic generation of executable activities
- no automatic network optimization
- no replacement of existing RulePage for advanced rule maintenance

## Implementation Tickets To Create Next

1. **TICKET-037: Network editor binding model and API**
   - Add `state_node_reference` and `activity_state_binding`.
   - Add CRUD schemas, master-data read endpoints, and the unified commit
     request model used by the board.
   - Add unit/integration tests for reference cycles, coverage snapshots, and
     executable binding sync to `op_rule`.

2. **TICKET-038: Graph projection and validation service**
   - Build graph projection from state nodes, activity nodes, atomic activities,
     bindings, and existing rules.
   - Wrap layered expansion and layered health check.
   - Return modeling and solver-ready issue groups.

3. **TICKET-039: Data Management network editor MVP**
   - Add the `Network Editor` tab.
   - Implement the three-pane canvas workflow, binding property panel, and
     preview/edit/unified-submit state machine.
   - Support create/update/delete binding operations and coverage refresh as
     draft changes that submit only through unified commit.

4. **TICKET-040: Solver precheck and solver-readiness handoff**
   - Implement solver precheck endpoint and UI panel.
   - Show inherited context and expanded input/output facts.
   - Verify solver precheck matches existing layered solve expectations.

5. **TICKET-041: End-to-end acceptance and documentation**
   - Add a representative scenario with aggregate states, reference states,
     virtual activity declarations, executable activity bindings, stale coverage,
     and solver precheck.
   - Update user documentation and scenario import guidance after the MVP is
     implemented.

## Acceptance Criteria For This Design Freeze

- The design keeps V0.3 solver contracts canonical and avoids a parallel
  flowchart-only data model.
- State package coverage snapshots and state package member references have
  explicit persistence designs.
- Every new editor-facing API explains how it projects to or synchronizes with
  existing `op_rule.preconditions/effects`.
- Validation is split into modeling and solver-ready phases.
- The frontend workflow has an explicit preview mode, edit mode, visible draft
  list, cancel-edit discard path, and unified submit commit path; no single
  board action writes directly to the database.
- The next implementation work is split into small tickets instead of one
  broad editor implementation.

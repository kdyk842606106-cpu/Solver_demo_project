# Network Editor State-Transition Projection Model Plan

> **For agentic workers:** REQUIRED: Use superpowers:plan-execution to implement this plan. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Turn the current state-transition MVP into a stable multi-level projection model. The editor should let users
read and maintain state transitions across nested state packages while keeping containers, relay nodes, proxy edges,
layout artifacts, and solver semantics clearly separated.

**Architecture:** Keep the V0.3 canonical data model: `StateNode`, `StateNodeReference`, `AtomicActivity`,
`ActivityPackageAtomicRef`, `ActivityStateBinding`, `OpRule`, and the existing Network Editor graph/commit APIs remain
the source of truth. Add a frontend projection layer first, then optionally extract shared projection helpers into a
service/API response only if frontend-only implementation creates duplication or inconsistent semantics.

**Why this exists:** The current `状态转移` view solved the first readability problem by hiding dense activity nodes and
showing `state -> relay -> state`. The next problem is multi-level management: folded state packages, reference
instances, transition relays, package-level paths, and auto-layout proxy edges are all derived in different places. That
makes the view harder to reason about and makes future package-level editing risky.

**中文摘要：** 本计划把前面讨论的 Airflow TaskGroup 启发落到 Network Editor 的下一阶段设计：状态包、活动包、relay
chip、proxy edge 都是投影/组织结构，不是求解器真实节点；真实语义仍由原子状态、原子活动、绑定和规则承载。实施重点不是新增
schema，而是先抽出统一的 `StateTransitionProjection`，让画布、右侧详情、折叠代理边、自动布局和提交过滤都从同一个只读投影
读取，避免多处各自推导造成引用实例、包级边界和布局行为不一致。

---

## Design Principles

- [ ] **Containers are not solver nodes.** State packages, activity packages, expanded containers, relay chips, and proxy
  edges organize the view. They must not become executable activities, solver facts, or persisted graph-edge records.
- [ ] **Business bodies and canvas instances stay separate.** A `StateNode` or `AtomicActivity` is the reusable body.
  A `StateNodeReference` or `ActivityPackageAtomicRef` is the package membership/display instance. Layout belongs to
  the instance when an instance exists.
- [ ] **Projection is a first-class read model.** The canvas should consume a single state-transition projection instead
  of recomputing relay groups, warnings, edge visibility, selected-state details, and layout inputs in unrelated
  computed blocks.
- [ ] **Folded and expanded views differ only by projection granularity.** Folding a package may replace child edges
  with package proxy edges, but the underlying semantic transitions are unchanged.
- [ ] **Package-level links expand through roots/leaves.** If future UI allows a package-to-package transition, it must
  be expanded to atomic state/activity bindings by explicit boundary rules. A package-level edge cannot be saved as an
  independent solver dependency.
- [ ] **UI-only artifacts are stripped before commit.** Relay positions, proxy edges, route vertices, draft grouping
  metadata, and layout-only helper fields must never leak into semantic commit payloads.

## Current Gap

The current implementation already has useful pieces:

- `状态转移` is a frontend projection over backend `view_mode: "implementation"`.
- Realizer activities are derived from `ACTIVITY_TO_STATE` / `output` bindings.
- Preconditions are derived from `STATE_TO_ACTIVITY` / `input` and `context_input` bindings.
- Relay chips are frontend-only render artifacts and map selection back to the underlying activity.
- Referenced atomic library states can be projected as visible reference instances.
- Nested container auto-layout can assign transient relay nodes to the deepest common expanded state container.

The missing piece is a unified projection contract. Today these concerns are spread across the workspace, canvas, layout
helper, and tests:

- target-state summaries and warnings
- relay group derivation
- visible-state filtering
- reference graph-id to canonical state-id mapping
- folded proxy edge aggregation
- package membership path derivation
- selected-state detail data
- auto-layout relation inputs
- commit stripping for UI-only artifacts

That is manageable for MVP, but brittle for multi-level editing.

## Target Projection Contract

Introduce a frontend-side read model with a shape close to:

```ts
interface StateTransitionProjection {
  semanticTransitions: StateTransition[]
  visibleTransitions: StateTransition[]
  stateInstancesByGraphId: Map<string, StateInstanceProjection>
  groupsByGraphId: Map<string, NetworkGroupProjection>
  relayGroups: TransitionRelayGroup[]
  proxyEdges: TransitionProxyEdge[]
  selectedDetails: Map<string, StateTransitionDetail>
  layoutInput: StateTransitionLayoutInput
  warnings: ProjectionWarning[]
}

interface NetworkGroupProjection {
  graphId: string
  bodyId: number | string
  kind: 'state_package' | 'activity_package'
  expanded: boolean
  parentGroupId: string | null
  childGraphIds: string[]
  rootStateGraphIds: string[]
  leafStateGraphIds: string[]
  boundaryInputGraphIds: string[]
  boundaryOutputGraphIds: string[]
  proxyEdgeIds: string[]
}

interface StateTransition {
  id: string
  realizerActivityGraphId: string
  inputStateGraphIds: string[]
  outputStateGraphIds: string[]
  canonicalInputStateIds: number[]
  canonicalOutputStateIds: number[]
  opRuleIds: number[]
  sourceBindingIds: number[]
  draftChangeIds: string[]
  warnings: ProjectionWarning[]
}
```

The exact implementation can stay plain JavaScript in `NetworkEditorWorkspace.vue` at first. The important part is that
all downstream consumers read from the same projection:

- X6 node data
- relay chip rendering
- edge rendering
- selected-state right panel
- warning badges
- auto-layout input
- focused flow highlighting
- E2E assertions

## Phase 1: Extract Pure Projection Builders

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Add: `frontend/src/views/DataManagement/networkEditorStateTransitionProjection.js`
- Modify: `frontend/e2e/tests/network-editor.spec.ts`

- [ ] **Step 1: Move relay derivation into a pure helper**

Create `buildStateTransitionProjection()` or a smaller `buildTransitionRelayGroups()` helper that accepts explicit
arguments:

- committed graph edges
- draft binding edges
- committed bindings fallback
- visible state nodes
- canonical state lookup
- activity lookup
- deleted binding ids

The helper should not read Vue refs directly.

- [ ] **Step 2: Return canonical and visible endpoints together**

Each transition should preserve both display graph ids such as `state_node:30:ref:901` and canonical ids such as
`state_node:30`. This prevents detail panels, bindings, and layout from each inventing their own reference parsing.

- [ ] **Step 3: Centralize warning calculation**

Move warning derivation into the projection:

- missing realizer
- multiple realizers
- multi-output realizer
- missing op rule
- aggregate/package target warning
- hidden endpoint / projection mismatch warning

Canvas badges and right-panel detail should consume the same warning objects.

- [ ] **Step 4: Preserve existing behavior with focused tests**

Run and keep passing the current state-transition coverage:

```powershell
npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition"
npm.cmd run build
```

## Phase 2: Add Group Boundary Semantics

**Files:**
- Modify: `frontend/src/views/DataManagement/networkEditorStateTransitionProjection.js`
- Modify: `frontend/src/views/DataManagement/networkEditorAutoLayout.js`
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/e2e/tests/network-editor.spec.ts`

- [ ] **Step 1: Build `NetworkGroupProjection` for state packages**

For each visible state package/container, compute:

- direct visible child graph ids
- reference instance children
- nested state-package children
- canonical body id
- expansion state
- local roots and leaves

Use the existing reference-aware children graph. Do not fall back to direct `parent_id` only.

- [ ] **Step 2: Define roots/leaves for folded packages**

For a folded state package:

- roots are visible/canonical child states with no incoming transition from another child in the same package
- leaves are visible/canonical child states with no outgoing transition to another child in the same package
- package-level incoming edges summarize transitions entering roots
- package-level outgoing edges summarize transitions leaving leaves

If a package has no transition-bearing children, it should not invent roots/leaves.

- [ ] **Step 3: Generate proxy edges from group boundaries**

Replace ad hoc collapsed relation badges/edges for state-transition mode with projection-owned proxy edges:

- internal proxy: all endpoints inside the same folded package
- incoming proxy: outside endpoint to folded package
- outgoing proxy: folded package to outside endpoint
- cross-package proxy: folded package to folded package

Proxy edges are visual-only and must carry references to the underlying transition ids for focus highlighting.

- [ ] **Step 4: Make auto-layout consume group boundaries**

Auto-layout should receive direct-child layout units and boundary proxy edges from the projection. It should not need to
infer deep container relationships from raw graph edges on its own.

## Phase 3: Unify Selected-State Details and Editing

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/src/views/DataManagement/networkEditorStateTransitionProjection.js`
- Modify: `frontend/e2e/tests/network-editor.spec.ts`

- [ ] **Step 1: Drive right-panel details from projection**

Selected target details should read a `StateTransitionDetail` object containing:

- selected display instance graph id
- canonical state id
- package path / reference path
- realizer activities
- precondition states
- warning list
- draft vs committed source status

- [ ] **Step 2: Keep edit actions semantic**

Right-panel actions should still write existing draft changes:

- adding a realizer creates an `activity_state_binding` `output`
- adding a precondition creates an `activity_state_binding` `input`
- removing a committed precondition queues `activity_state_binding:delete`
- removing a new precondition cancels the draft

The projection should update immediately after draft changes.

- [ ] **Step 3: Separate context defaults from implicit inheritance**

Explicitly encode which actions may inherit current package context:

- adding/referencing a state inside a selected state package may default to that package
- creating a transition realizer must not inherit the selected activity package unless the user chooses it
- adding preconditions binds state facts, not UI containers

Keep the existing regression for transition realizers not inheriting selected activity packages.

## Phase 4: Package-Level Transition Interaction

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/src/views/DataManagement/networkEditorStateTransitionProjection.js`
- Modify: `frontend/e2e/tests/network-editor.spec.ts`
- Optional modify: `docs/network-editor-user-guide.md`
- Optional modify: `docs/network-editor-acceptance-matrix.md`

- [ ] **Step 1: Start read-only**

Expose package-level transition summaries before adding write affordances. A folded state package should show:

- count of target states with realizers
- count of target states missing realizers
- count of incoming/outgoing/internal transitions
- strongest warning state

- [ ] **Step 2: Add inspect, not edit, for proxy edges**

Clicking a package proxy edge should open an inspection list of underlying transitions. Editing still requires selecting
the concrete target state or expanding the package.

- [ ] **Step 3: Decide whether package-to-package creation is allowed**

Before implementing package-level create, make a product decision:

- **Conservative option:** users may inspect package-level edges only; edits stay atomic.
- **Guided expansion option:** users may start from a package-level intent, but the UI must ask which atomic target state
  and which realizer activity to create/update.
- **Bulk operation option:** users may generate multiple atomic transitions from a package template. This requires
  preview/review before draft creation.

Default recommendation: start with conservative inspect-only behavior.

## Phase 5: Documentation and Acceptance

**Files:**
- Modify: `docs/network-editor-user-guide.md`
- Modify: `docs/network-editor-acceptance-matrix.md`
- Optional add: `docs/TICKET_078.md`
- Modify: `docs/STATE_V0.3.md` after implementation

- [ ] **Step 1: Document the projection split**

Update user-facing docs to explain:

- state packages organize and summarize transitions
- relay chips are visual representatives of realizer activities
- proxy edges summarize hidden transitions
- editing still targets concrete states and realizer activities

- [ ] **Step 2: Add acceptance rows**

Acceptance should cover:

- folded package shows transition summary without changing semantic bindings
- expanding package reveals the same underlying transitions
- referenced atomic state detail resolves to canonical state id
- relay/proxy artifacts are absent from unified commit payload
- auto-arrange layout submit preserves preview geometry

- [ ] **Step 3: Record implementation in ticket/state**

If this plan becomes an implementation task, create a new ticket and update `STATE_V0.3.md` only after verified changes.

## Verification Matrix

Minimum verification after implementation:

```powershell
npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition|referenced atomic library states|auto arrange|container"
npm.cmd run build
```

If backend graph projection or commit payload handling changes:

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -k network_editor -q
.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q
```

Known local constraint from recent STATE notes: backend pytest may be blocked if the local `.venv\Scripts\python.exe`
still points at a missing Python install. In that case, record the blocker and run frontend coverage.

## Out of Scope

- No database schema change.
- No persisted `GraphEdge`, relay node, proxy edge, or package-transition table.
- No Scheduler/RAGBuilder behavior change.
- No automatic op-rule generation beyond existing transition realizer repair paths.
- No hard one-realizer-one-target enforcement.
- No historical migration of directly parented atomic states.
- No package-level bulk edit until inspect-only package summaries prove usable.

## Implementation Notes

- Keep the first extraction small. The first merge should be behavior-preserving and mostly move existing projection
  logic into a pure helper.
- Prefer explicit argument objects over importing shared Vue state into projection helpers.
- Keep data shape names close to current terminology: state package, reference instance, realizer, precondition, relay,
  proxy edge.
- Do not move solver-ready semantics into this projection. Solver-ready remains a separate read model focused on
  executable rules and facts.
- Treat the Airflow TaskGroup analogy as a design pattern, not a feature dependency: it informs roots/leaves, visual
  grouping, and proxy edges, but our reference-instance model remains canonical.

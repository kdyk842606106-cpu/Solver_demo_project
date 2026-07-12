# Network Editor State-Transition MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:plan-execution to implement this plan. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Reframe the Network Editor around a state-transition knowledge graph: business users start from target states,
see how each target state is achieved by a realizer activity, and maintain that activity's precondition states without
being forced to read a dense state/activity bipartite graph.

**Architecture:** Keep the current V0.3 database model and backend network-editor contracts. Implement the MVP as a
frontend projection over the existing `implementation` graph response, with inline edits recorded as existing
`draftChanges` and persisted only through unified submit.

**Tech Stack:** Vue 3, Element Plus, X6 canvas component, existing `frontend/src/api/masterData.js` wrappers, existing
FastAPI/SQLAlchemy network-editor endpoints, Playwright E2E, Vite build.

---

## Chunk 1: State-Transition Projection

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`
- Modify: `frontend/e2e/tests/network-editor.spec.ts`

- [x] **Step 1: Rename visible implementation view**

Change the user-facing `实现` view label to `状态转移`, while preserving the backend value `implementation`.

- [x] **Step 2: Derive target-state realizer summaries**

Add frontend computed data that derives, from current graph edges and draft binding edges:
- realizer activities by target state from `ACTIVITY_TO_STATE` / `output`
- precondition states by realizer activity from `STATE_TO_ACTIVITY`
- relationship warnings for missing realizer, multiple realizers, multi-output realizer, and package target

- [x] **Step 3: Inject compact state-card metadata**

Pass state-transition metadata into visible state nodes so X6 state cards can render target state name, realizer activity,
precondition count, and short warning tags. Long realizer names should clamp to two lines with full text in a title.

- [x] **Step 4: Reduce default canvas density**

In `状态转移` view, default to state nodes as the canvas backbone. Hide activity nodes and output edges unless selected or
diagnostic context requires them. Show precondition edges only for the selected target state or selected realizer
activity, keeping the existing aggregation threshold of 5.

- [x] **Step 5: Keep development access to the old full graph**

Add a development/test-only switch or query/localStorage flag that restores the full state/activity graph for regression
and debugging. Do not expose it as a normal toolbar view.

## Chunk 2: Right-Panel Inline Modeling

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/e2e/tests/network-editor-full-flow.spec.ts`

- [x] **Step 1: Add target-state detail section**

When a state is selected, make the right panel start with target-state details, including package path, atomic/package
target status, relationship warnings, and the primary `添加达成活动` action when no realizer exists.

- [x] **Step 2: Add realizer activity section**

Support selecting an existing atomic activity or creating a new atomic activity as the selected state's realizer. The
created/selected realizer should queue an `activity_state_binding` draft with `binding_role: "output"` and no required
`op_rule_id`.

- [x] **Step 3: Add precondition section**

Support adding/removing precondition states for the selected realizer. New precondition drafts use
`binding_role: "input"`; if the chosen precondition is a state package, default `covered_leaf_state_ids` to all currently
active leaf descendants.

Progress 2026-06-30: adding and removing precondition states is implemented and covered by E2E. Removing a committed
precondition queues an `activity_state_binding:delete` draft and immediately hides the edge from the state-transition
projection; removing a newly added precondition draft cancels that draft.

- [x] **Step 4: Preserve edit-session semantics**

All inline edits must require edit mode, enter `draftChanges`, update the state-transition projection immediately, and
write to the database only through `统一提交`.

## Chunk 3: Documentation and Acceptance

**Files:**
- Modify: `docs/network-editor-user-guide.md`
- Modify: `docs/network-editor-acceptance-matrix.md`
- Modify: `docs/TICKET_057.md`
- Modify: `docs/STATE_V0.3.md`

- [x] **Step 1: Update user-facing docs**

Document `状态转移`, `达成活动`, `待补达成活动`, warning-only exceptions, and the state-first modeling flow.

- [x] **Step 2: Update acceptance evidence**

Add acceptance rows or notes for default canvas clarity, selected-state precondition expansion, inline realizer/precondition
draft editing, and the test-only full graph fallback.

- [x] **Step 3: Record verification**

Update the ticket and state snapshot with completed implementation notes and commands after verification.

## Chunk 4: Verification

- [x] Run focused Playwright coverage for the new state-transition view and inline modeling flow.
- [x] Run existing `network-editor.spec.ts` and `network-editor-full-flow.spec.ts` regressions.
- [x] Run `npm.cmd run build`, accepting the existing Vite chunk-size warning only.

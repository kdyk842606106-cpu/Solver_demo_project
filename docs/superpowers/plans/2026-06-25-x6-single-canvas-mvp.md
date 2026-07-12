# X6 Single Canvas MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:plan-execution to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current hand-written two-zone network editor board with an X6-backed single free-board MVP while preserving the existing preview/edit/draft/commit business flow.

**Architecture:** Keep `NetworkEditorWorkspace.vue` as the business orchestration shell and introduce a focused X6 canvas component for rendering and interactions. The canvas emits domain-neutral events for selection, expansion, layout movement, container sizing, and semantic connections; the workspace converts those events into existing draft changes and API calls.

**Tech Stack:** Vue 3, Element Plus, `@antv/x6`, existing `network-editor/graph`, `network-editor/commit`, and Playwright e2e tests.

---

## Chunk 1: Dependency And Canvas Boundary

### Task 1: Add X6 Dependency

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Install dependency**

Run:

```powershell
cd frontend
npm install @antv/x6 --save
```

Expected: `package.json` gains `@antv/x6`, `package-lock.json` resolves the package, and no source files change.

### Task 2: Create X6 Canvas Component

**Files:**
- Create: `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`

- [ ] **Step 1: Move only the board rendering boundary**

Create a component that accepts:

- `stateNodes`
- `activityNodes`
- `edges`
- `selectedStateId`
- `selectedActivityGraphId`
- `isEditMode`
- `canMutate`
- `canvasZoom`
- `stateDepth`
- `activityDepth`

It must emit:

- `select-state`
- `select-activity`
- `toggle-state-expansion`
- `toggle-activity-expansion`
- `layout-change`
- `container-resize`

Keep all existing drawers, validation panels, impact analysis, draft submit, and resource trees in `NetworkEditorWorkspace.vue`.

- [ ] **Step 2: Preserve test ids**

The X6 cells must expose existing `data-testid` values for core e2e compatibility:

- `network-editor-state-node-{state_node_id}`
- `network-editor-activity-node-{graph_id}`
- `network-editor-state-package-container-{state_node_id}`
- `network-editor-virtual-activity-container-{graph_id}`

---

## Chunk 2: Single Canvas Projection

### Task 3: Convert Graph Data To X6 Cells

**Files:**
- Modify: `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`

- [ ] **Step 1: Render one X6 graph**

Use one X6 `Graph` instance for all states, activities, containers, and semantic edges. Do not render separate state and activity columns.

- [ ] **Step 2: Render nodes by business role**

State nodes, state reference instances, virtual activity nodes, and atomic activity nodes must all use absolute canvas coordinates derived from existing layout metadata and fallback positioning.

- [ ] **Step 3: Render containers**

When a state package or virtual activity is expanded:

- the high-level object is represented as an X6 container/group cell
- state package containers include only state nodes/state references
- virtual activity containers include only child virtual activities/atomic activities
- boundary states for virtual activities stay outside the virtual activity container

---

## Chunk 3: MVP Interactions

### Task 4: Preview/Edit Behavior

**Files:**
- Modify: `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`

- [ ] **Step 1: Preview mode is read-only**

Disable movement, connection, resize, and mutation controls when not in edit mode. Keep selection, expansion/collapse, zoom/pan, issue location, and impact highlighting available.

- [ ] **Step 2: Edit mode queues drafts**

On node move, emit `layout-change`; the workspace must call existing layout draft helpers. On container resize, emit `container-resize`; the workspace must call existing container draft helpers. No X6 interaction calls a write API directly.

### Task 5: Expand/Collapse And Containers

**Files:**
- Modify: `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`

- [ ] **Step 1: Toggle high-level objects**

Keep existing `toggleGraphStateExpansion` and `toggleGraphActivityExpansion` as the source of truth. The X6 component only emits the intent.

- [ ] **Step 2: Container movement**

Dragging a container moves all visible child nodes together. Dragging an internal node moves only that node.

---

## Chunk 4: Verification

### Task 6: Update Tests For X6 MVP

**Files:**
- Modify: `frontend/e2e/tests/network-editor.spec.ts`

- [ ] **Step 1: Update selectors if needed**

Preserve existing assertions where possible. If X6 renders wrappers differently, update only the DOM lookup mechanics, not the user-facing behavior being asserted.

- [ ] **Step 2: Add single-canvas assertion**

Assert that the network editor canvas no longer exposes state/activity column containers and that state/activity nodes share one canvas root.

### Task 7: Run Verification

Run:

```powershell
cd frontend
npm run build
npm run test:e2e -- network-editor.spec.ts --project=chromium
```

Expected:

- build passes with only existing Vite chunk-size warning
- network editor e2e passes

If sandboxed Playwright fails with `spawn EPERM`, rerun with approved escalation and record that in STATE/TICKET.

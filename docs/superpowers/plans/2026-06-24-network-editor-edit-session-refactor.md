# Network Editor Edit Session Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:plan-execution to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the existing network editor MVP to match the latest free-board requirement: read-only preview by default, explicit edit sessions, draft changes, unified submit, and no standalone export downloads.

**Architecture:** Keep the existing V0.3 canonical database model and network-editor projection services. Add an editor-session layer in the frontend that records draft changes and applies them through existing database APIs only when the user clicks unified submit; keep graph/validate/impact/solver-precheck as read-only preview APIs.

**Tech Stack:** Vue 3, Element Plus, existing `frontend/src/api/masterData.js` API wrapper, FastAPI/SQLAlchemy network-editor endpoints, pytest and Vite build.

---

## Chunk 1: Preview/Edit Session Guard

**Files:**
- Modify: `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- Modify: `frontend/src/api/masterData.js`
- Modify: `docs/network-editor-acceptance-matrix.md`
- Modify: `docs/TICKET_041.md`

- [x] **Step 1: Add editor mode state**

Add `editorMode`, `draftChanges`, `draftSubmitting`, and computed helpers such as `isEditMode`, `draftChangeCount`, and `hasDraftChanges`.

- [x] **Step 2: Gate all mutating entry points**

Disable or guard creation, editing, deletion, binding creation/update/removal, coverage refresh, and reference mutation unless `isEditMode` is true.

- [x] **Step 3: Replace per-operation API writes with draft recording**

For frontend-created state/activity/binding/reference operations, append a `DraftChange` with operation, label, entity type, payload, and local selection metadata. Do not call mutating APIs immediately.

- [x] **Step 4: Add unified submit and cancel**

`进入编辑` snapshots the current loaded data. `取消编辑` discards draft changes and reloads committed data. `统一提交` validates, then applies draft changes in order through existing API wrappers. If any request fails, keep the draft open and show the failed change.

- [x] **Step 5: Remove standalone download affordances**

Keep `求解预检` as an on-screen database-readiness preview. Remove independent JSON and solve-template download buttons from the editor UI.

- [x] **Step 6: Verify**

Run `npm run build`. If backend contracts changed, run the focused network editor integration tests.

## Chunk 2: Requirement Evidence Update

**Files:**
- Modify: `docs/network-editor-acceptance-matrix.md`
- Modify: `docs/network-editor-user-guide.md`
- Modify: `docs/TICKET_041.md`
- Modify: `docs/STATE_V0.3.md`

- [x] **Step 1: Update matrix rows for preview/edit/unified submit**

Mark default preview mode, edit mode, draft changes, cancel edit, unified submit, and removal of standalone export downloads with current file evidence.

- [x] **Step 2: Update user guide flow**

Describe the visible buttons and mode behavior: preview, enter edit, draft count, cancel, unified submit, validation and solver precheck.

- [x] **Step 3: Update ticket/state**

Record the refactor and verification commands without changing unrelated pending roadmap items.

## Follow-up Notes

- 2026-06-24: Added a first free-board layout persistence slice on top of this plan. Node position changes are draft-only in edit mode, merge with same-node field updates, and persist through node `metadata_json._network_editor_layout` on unified submit.
- 2026-06-24: Implemented the duplicate-state reuse selector and referenced state-package `同步 / 分叉` workflow. Reuse creates `state_node_reference` draft changes; fork uses the unified-submit `state_package_fork` operation to create a branch, copy direct members, add the new/reused state, and replace the current reference usage.

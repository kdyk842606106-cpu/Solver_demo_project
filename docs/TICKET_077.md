# TICKET-077: Atomic state library objects and reference-only canvas placement
> Status: completed
> Version: V0.3
> Created: 2026-07-03
> Completed: 2026-07-03

## Scope

Implement the Network Editor atomic-state library model:

- Template-backed atomic state creation produces library `state_node` objects with
  `parent_id = null` and `level = 1`.
- Adding an atomic state to a state package creates a
  `state_node_reference` instance; package layout belongs to the reference
  metadata.
- Binary template atomic creation automatically creates the opposite target value
  as a library object only, without adding it to the canvas.
- Canvas rendering hides unreferenced atomic library objects, while state resource
  selectors can still use them.
- Network Editor commit normalizes legacy-style atomic `state_node:create` with
  `parent_id` into library state creation plus package reference creation.

## Implementation Summary

- Updated `NetworkEditorWorkspace.vue` so atomic state drawer saves route through
  library-object creation, package reference drafts, and opposite-state draft
  completion.
- Added canvas visibility filtering for unreferenced atomic library objects.
- Added backend commit normalization for atomic state creates that still arrive
  with a parent, preserving the public StateNode CRUD shape and database schema.
- Extended E2E coverage for selected-value references, hidden opposite states,
  existing opposite-state de-duplication, and draft reference submission.
- Extended backend integration assertions for normalized atomic state commit and
  same-batch draft reference resolution.

## Verification

- `.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -k network_editor -q`
  - 6 passed, 5 deselected, with existing SQLite drop-order warnings.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state reference|opposite state|atomic state library"`
  - 3 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "unified submit|draft states to atomic activities|same state dimension"`
  - 3 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state package reference|draft referenced state|nested containers"`
  - 3 passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `git diff --check` on touched files
  - only reported existing LF/CRLF warnings.

## Follow-up: Solve page target tree and Gantt state lanes

After moving new atomic states to library objects, the Solve page still built
its layered target tree from direct `parent_id` only, and layered solve goal
paths still followed the leaf state's `parent_id`. Referenced library atomic
states could therefore be missing from their package in the target selector,
and state-lane/Gantt grouping could lose the intended state package.

Fixes:

- Solve page now loads `state_node_reference` rows and projects referenced
  parentage into the layered target tree.
- Layered expansion now builds goal `source_path` from the selected target root
  through the reference-aware children graph.
- Added regression coverage for referenced library atomic states in the Solve
  target tree and for state continuity groups derived from reference paths.

Follow-up verification:

- `.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q`
  - 5 passed, with existing SQLite drop-order warnings.
- `npm.cmd run test:e2e -- solve.spec.ts --project=chromium`
  - 6 passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.

## Follow-up: Network Editor referenced atomics and transition details

Network Editor had two remaining direct-parent/direct-graph-id assumptions:
on initial graph load, a referenced atomic library body could still appear as a
top-level canvas card because the hide predicate treated `reference_parent_ids`
as enough to make the body visible; and transition detail lookup did not parse
reference graph ids such as `state_node:30:ref:901` back to their underlying
`state_node_id`.

Fixes:

- X6 visibility now hides level-1 parentless atomic library bodies even when
  they have package references, while preserving legacy directly placed atomic
  states.
- Transition state-id parsing now maps reference instance graph ids back to the
  real state id.
- Binding edge projection now prefers a visible reference instance for a bound
  state, so relay/precondition/detail views stay aligned with the canvas.
- Added E2E coverage for first-load referenced atomic projection plus populated
  realizer and precondition details.

Follow-up verification:

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "referenced atomic library states"`
  - 1 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state-transition|referenced atomic library states|reflexive precondition|new transition realizers"`
  - 13 passed.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state reference|opposite state|atomic state library|state package reference|draft referenced state|referenced atomic library states"`
  - 6 passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.

## Follow-up: Submit review 422 UX

The unified submit flow intentionally posts first with `allow_warnings=false` so
the backend can return a 422 review payload when the saved model needs
confirmation. The generic Axios interceptor surfaced that expected review
response as a raw HTTP 422 error before `NetworkEditorWorkspace` could show its
review dialog.

Fix:

- `commitNetworkEditorDraft()` now uses the existing `silentError` request option
  so Network Editor owns both the review dialog and real commit failure message.

Verification:

- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- Backend pytest was not run because the local `.venv\Scripts\python.exe` points
  at a missing Python 3.12 install and the bundled Codex Python does not include
  pytest.

## Follow-up: Iterative container-aware auto layout

Network Editor auto arrange now uses a bottom-up nested container layout path
instead of arranging one flat graph first. Each expanded container lays out only
its direct children; computed child containers then participate in the parent
layout as fixed-size boxes, and final local positions are expanded back into the
existing absolute-coordinate draft format.

Fixes:

- Added `layoutNestedContainerGraph()` with local child positions, computed
  container sizes, transient relay positions, same-level ELK edge routes, and
  diagnostics.
- Projected deep edges to the owning direct child container so cross-container
  dependencies influence the parent layer without rewriting real edge endpoints.
- Assigned state-transition relay nodes to the deepest common expanded state
  container for layout only, keeping relay positions out of unified submit.
- Preserved the current-width wrapping behavior for unconnected state-package
  children while allowing automatic layout to compact stale oversized container
  heights/widths elsewhere.
- Routed `NetworkEditorWorkspace.vue` auto arrange through the nested result and
  queued state/activity/reference positions plus `_network_editor_container`
  size drafts through the existing helper path.
- Removed unreachable legacy code after the auto-arrange early returns.

Verification:

- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "auto arrange|container|state-transition"`
  - 23 passed.

## Follow-up: High-parallel container width control

The high-parallel mechanical integration seed exposed a practical issue in the
nested layout: ELK correctly preserved the very wide parallel dependency layer,
but that produced expanded state packages wider than 22000px. Oversized
containers now get a second compacting pass that keeps DAG rank order while
wrapping rank columns into bounded horizontal segments. Saved oversized
container widths are also capped when a no-edge package falls back to manual
child wrapping.

Fixes:

- Added a 2400px compact-layout width target for oversized expanded containers.
- Kept layout units container-local: only the oversized container's direct
  children are reflowed, and parent layers still treat the result as a fixed box.
- Dropped stale ELK route vertices for compacted containers so X6 can route the
  newly wrapped geometry instead of drawing old long-row paths.
- Verified `Mechanical Integration High-Parallel Cell`: the largest expanded
  state package shrank from about 22405px to about 2496px, with inner oversized
  packages around 2400px. Screenshot:
  `output/network-editor-high-parallel-compact-auto-layout-v2.png`.

Verification:

- `node --check frontend/src/views/DataManagement/networkEditorAutoLayout.js`
  - passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "auto arrange|container|state-transition"`
  - 23 passed.

## Follow-up: 2026-07-08 Network Editor source recovery and draft UX

After a local recovery mistake temporarily replaced `NetworkEditorWorkspace.vue`
with an older 2026-07-03 backup, the 7/7+ workspace source was recovered from
Git loose object `66fdcc166ca620d63772c6efe5887bc4eb05e63f`. This restores the
nested container auto-layout integration with `networkEditorAutoLayout.js`.

Fixes:

- Reapplied grouped layout draft display so bulk position/size edits show one
  `布局调整：N 项` row instead of one row per node.
- Added grouped undo cleanup for layout and container drafts.
- Stripped UI-only `draft_kind` before unified commit payload serialization.
- Moved the submit-success reload before clearing draft state and switching to
  preview mode, preventing the preview layout from briefly reverting to stale
  pre-submit positions.
- Saved recovery candidates under `output/recovered_network_editor/`.

Verification:

- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `git diff --check` on touched frontend files
  - only reported existing LF/CRLF warnings.
- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "layout|draft|commit|edit session"`
  - 35 passed, 5 failed due to stale E2E expectations for removed direct virtual
    activity creation and the intentional grouped layout draft text.

## Follow-up: 2026-07-08 exact preview after layout submit

Users reported that arranging the Network Editor in edit mode and submitting
could still make preview mode redraw into a different layout. The remaining
cause was the submit-success graph reload: even after successful layout commit,
preview immediately rebuilt from the server projection and auto-layout fallback
paths before the freshly saved metadata was guaranteed to be reflected in the
visible graph.

Fixes:

- Pure layout-only submits no longer call `loadAll()` on success; they update
  the local revision, clear the draft-change list, switch to preview, and keep
  the already visible layout draft as the preview layout.
- Mixed submits that include layout changes preserve a submitted layout overlay
  across the reload path so the preview can still prefer the just-submitted
  positions/sizes over fallback metadata.
- Manual refresh/type changes clear the temporary submitted-layout state and
  reload from committed data.
- Draft display keeps one row per effective user action: a single-node move
  remains visible as one draft row, while batch/container/auto-arrange actions
  are grouped as one row instead of listing every internal step.
- E2E coverage now asserts that after auto-arrange submit, preview source,
  relay, and target node coordinates remain within 2 px of edit mode.

Verification:

- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "auto arrange|redraws from commit reload|cancels edit session|moves internal nodes|moves expanded containers"`
  - 9 passed.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor.spec.ts`
  - only reported existing LF/CRLF warnings.

## Out of Scope

- No database schema changes.
- No migration of historical directly parented atomic states.
- No automatic write to `MachineState` snapshots.

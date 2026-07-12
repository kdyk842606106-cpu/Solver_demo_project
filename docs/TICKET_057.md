# TICKET-057: Network Editor state-transition MVP
> Status: completed
> Version: V0.3
> Created: 2026-06-30
> Completed: 2026-06-30
> Depends on: `docs/TICKET_056.md`

## Scope

Refocus the Network Editor MVP around a state-transition knowledge graph for business process users.

The default modeling path should start from target states: users inspect an atomic target state, configure its single
realizer activity, and maintain the precondition states needed by that activity. Activity hierarchy remains a management
and filtering dimension, not the default canvas backbone.

This is a UI-projection-first MVP. It does not change database schema, solver contracts, backend commit semantics, or the
canonical network-editor API payload shapes.

## Product Decisions

- Primary user: business process/modeling user.
- Main workflow: model around states first, then configure the realizer activity and preconditions.
- Primary view label: `状态转移`.
- Default semantics: one atomic target state should normally have one realizer atomic activity, and one realizer atomic
  activity should normally output one target state.
- Realizer activity: derived from `ACTIVITY_TO_STATE` edges whose binding role is `output`; `declared_output` remains
  package/coverage explanation.
- Preconditions: shown as one business-facing precondition list. New precondition bindings default to `input`, and may
  bind states at any hierarchy level.
- State package preconditions: default to covering all currently active leaf states under the package.
- State packages: navigation containers and focus scopes by default; package targets are allowed but should show a
  warning that atomic target states are preferred.
- Activity hierarchy: left-pane filtering/classification and right-panel metadata only by default.
- Exceptions (`missing realizer`, `multiple realizers`, `multi-output realizer`) are warnings, not blockers.
- Rules: missing op rules are not generated in this MVP; they remain warning/precheck guidance.
- Draft model: continue the existing explicit edit session and unified submit flow.

## MVP Deliverables

- Add a state-transition projection on top of the existing `implementation` API view.
- Rename the visible `实现` option to `状态转移` while still sending `view_mode: "implementation"` to the backend.
- Render state cards as the default canvas focus, with compact fields:
  - target state name
  - realizer activity summary
  - precondition count
  - short relationship warning tags
- Hide activity nodes from the default state-transition canvas unless a focused/diagnostic path needs them.
- Show precondition edges only for the selected target state or selected realizer activity, with aggregation after 5
  concrete edges.
- Add right-panel inline state-transition details in this order:
  1. target state
  2. realizer activity
  3. precondition states
- Support minimal inline editing in the right panel:
  - add/select a realizer atomic activity for the selected target state
  - add/remove precondition states for that realizer activity
  - all changes enter `draftChanges` and are persisted only through unified submit
- Keep old full state/activity graph available only as a development/test switch, not as a normal user-facing view.
- Update user guide and acceptance evidence for the state-transition MVP.

## Out of Scope

- No database migration or schema refactor.
- No backend enum change for `NetworkEditorRequest.view_mode`.
- No solver behavior change.
- No automatic op-rule generation.
- No editable activity-state matrix in this MVP.
- No hard backend validation for one-to-one realizer constraints.

## Verification

- E2E coverage proves the default state-transition view is clearer than the old dense graph on the existing demo data.
- E2E coverage walks a minimal modeling flow: select/create a target state, add or select a realizer activity, add a
  precondition state, and verify the unified submit payload contains draft changes only after clicking unified submit.
- Existing network editor regression coverage for draft mode, layout, folded proxy behavior, impact/precheck, and build
  remains passing.

## Progress Notes

### 2026-06-30

Implemented the state-transition MVP:

- Visible `implementation` label is now `状态转移`; backend `view_mode` stays `implementation`.
- Default state-transition canvas renders state cards with realizer summary, precondition count, and warning badges.
- Activity nodes and dense edges are hidden by default, then shown only for the selected state/realizer diagnostic path.
- Old full graph is available only through `?networkEditorFullGraph=1` or localStorage `network-editor-full-graph=1`.
- Right panel shows selected target state, realizer activity, preconditions, and warning tags.
- Edit mode can add/select a realizer activity through an `output` binding draft without requiring an op rule.
- Edit mode can add a precondition state through an `input` binding draft; state-package preconditions default to current active leaf coverage.
- Edit mode can remove a precondition state: committed preconditions queue `activity_state_binding:delete`, while newly added precondition drafts are canceled before submit.
- User guide, acceptance matrix, and implementation plan were updated with the state-transition design and evidence.

Verified:

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state-transition"` — 1 passed, covering add/remove preconditions and realizer binding through unified submit.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium` — 20 passed.
- `npm.cmd run test:e2e -- network-editor-full-flow.spec.ts --project=chromium` — 3 passed.
- `npm.cmd run build` — passed with the existing Vite chunk-size warning.

Completion notes:

- TICKET-057 remains UI-projection-first: no database migration, backend enum change, solver behavior change, automatic rule generation, or hard backend validation for one-to-one realizer constraints.
- Warning-only one-to-one relationship checks are the accepted MVP behavior; stronger enforcement can be proposed separately if product needs it after usage feedback.

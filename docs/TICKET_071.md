# TICKET-071: Network Editor transition realizer package inheritance fix
> Status: completed - 2026-07-02
> Version: V0.3
> Created: 2026-07-02
> Depends on: `docs/TICKET_070.md`

## Scope

Fix the Network Editor state-transition workflow where creating a new
transition realizer can inherit a previously selected level-2 activity package
and appear as an automatically created activity node.

## Implementation Notes

- `新建达成活动` should create an atomic activity plus output/input bindings for
  the selected state transition.
- It must not implicitly attach the atomic activity to the currently selected
  activity package.
- When the target state can be expressed as rule effects, transition-created
  activities should create an `op_rule` draft and attach the generated
  input/output bindings to that rule so the state card does not remain in
  `缺规则`.
- Existing transition realizer bindings that already have target/precondition
  state links but lack `op_rule_id` should be repaired in the edit session by
  creating/reusing one rule draft and attaching both draft and committed
  input/output bindings to it.
- General `新建原子活动` behavior from activity-package workflows remains
  unchanged.

## Verification

- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "new transition realizers"` passed.
- Follow-up visual regression: `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state-transition"` passed.
- Follow-up rule regression: `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "new transition realizers"` passed with assertions for `op_rule:create` and generated binding `op_rule_id` references.
- Existing-binding rule repair regression: `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "reflexive precondition"` passed with assertions for `op_rule:create`, committed binding updates, and missing-rule badge removal.
- Full state-transition follow-up: `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "state-transition"` passed.
- `npm.cmd run build` passed with the existing Vite chunk-size warning.
- `git diff --check -- frontend/src/views/DataManagement/NetworkEditorWorkspace.vue frontend/e2e/tests/network-editor.spec.ts docs/TICKET_071.md docs/STATE_V0.3.md` reported only the existing LF/CRLF warnings.

## Out of Scope

- No backend API shape changes.
- No changes to general activity package atomic-reference creation.

# TICKET-100：活动编辑所属活动包

> Status: complete — 2026-10-28
> Created: 2026-10-28
> Scope: fix the Planner data-page activity editor; preserve existing uncommitted changes.

The activity dialog previously hid package selection while editing and never submitted membership changes. Show a multi-select of level-2 packages for both creation and editing, preload pending membership edits, support adding/removing/clearing memberships, and reconcile repeated edits against persisted membership IDs. Reverting must not create duplicate memberships or discard retained layouts. Reuse the existing atomic draft-commit API and mirror rebuilding; no solver or schema changes.

- [x] Dialog binding and membership reconciliation.
- [x] Browser verification for add/remove, clear, revert/reopen, and new-activity multi-package binding.
- [x] Production build and precise STATE handoff.

Verification: current Planner Chromium suite 20 passed (four new membership cases); scenario API suite 7 passed (one new real SQLite move/clear and managed-state-mirror regression); Vite production build and `git diff --check` passed. Existing package membership IDs/layouts are retained when draft changes are reverted; retained draft operations keep their order. Only unified submit persists changes. ANCHOR: no violations. No solver, schema, database, or historical snapshot changes.

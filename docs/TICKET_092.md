# TICKET-092: unified scheduling-rule selector and registered state-package continuity

> Status: completed — 2026-07-13
> Version: V0.3
> Created: 2026-07-13

## Goal

Represent scheduling rules with one multi-select dropdown in the existing Solve
optimization area and register state-package continuity as a selectable rule
that compiles to the existing state span/gap/interruption soft objectives.

## Tasks

- [x] T92-1 Register state-package continuity without a new entity or page.
- [x] T92-2 Include the rule in solve selection, snapshots, diagnostics, and persistence.
- [x] T92-3 Replace separate rule controls with one multi-select dropdown; keep required rules locked.
- [x] T92-4 Disable state-package continuity for snapshot mode with an explicit explanation.
- [x] T92-5 Add backend/frontend regression and run full verification.

## Acceptance

- Required and optional integration rules are presented in one dropdown.
- Required rules remain selected and cannot be removed.
- Optional rules can still be enabled independently.
- State-package continuity appears as a registered rule in layered and maintenance modes.
- Enabling it activates the existing state-group span, gap, and interruption costs and diagnostics.
- Snapshot mode does not submit an inapplicable state-package rule.
- Existing requests that use the legacy continuity objective switch remain compatible.

## Out of scope

- No database migration, new rule entity, new page, or strategy/version entity.
- No change to state-package membership derivation or continuity cost formulas.

## Completion evidence

- The rule-type registry now publishes `supported_modes` and an optional
  `builtin_rule`; `state_package_continuity` is a built-in optional soft rule
  for layered and maintenance solves.
- Solve uses one multi-select rule dropdown. Required rules are selected and
  locked, optional rules remain independent, and inapplicable rules are shown
  disabled with their supported-mode explanation.
- The registered Compiler reuses the existing state-group span, gap, and
  interruption terms; legacy continuity objective requests remain supported.
- Verification: backend `352 passed`; Vite production build passed with the
  existing chunk-size warning; Solve Chromium `11 passed`; full Chromium
  `83 passed`; `git diff --check` passed with the existing line-ending warning.
- MI-HP-001 PostgreSQL quality matrix passed all eight gates: crane overlap 0,
  crane shifts DAY only, pause 0, functional-test overlap 0, subsystem internal
  gap 0, subsystem interruptions 2, and all-rule makespan overhead 12.5% within
  the 15% acceptance limit.

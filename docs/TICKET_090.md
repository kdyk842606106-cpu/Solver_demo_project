# TICKET-090: MI-HP-001 integration-rule solve-quality acceptance

> Status: completed
> Version: V0.3
> Created: 2026-07-13
> Completed: 2026-07-13

## Goal

Upgrade the existing high-parallel mechanical-integration dataset `MI-HP-001`
to exercise all four integration scheduling rules, then compare solve quality
across selectable soft-rule combinations while required crane rules remain
enforced.

## Tasks

- [x] T90-1 Add responsibility, crane resource, functional-test dimension, calendars, and scheduling configuration to the repeatable seed.
- [x] T90-2 Add repeatable quality comparison tooling and automated acceptance assertions.
- [x] T90-3 Run PostgreSQL baseline/rule-combination scenarios and record makespan, concurrency, continuity, and violations.
- [x] T90-4 Run regression, audit ANCHOR compliance, and update STATE.

## Acceptance

- Required crane exclusivity and allowed-shift restrictions remain active in every scenario.
- Optional subsystem-continuity and functional-test-exclusivity rules can be enabled independently.
- The comparison reports schedule quality rather than only solve success.
- Functional-test exclusivity has an explicit enabled/disabled behavioral comparison.
- The existing 36-activity high-parallel planning path remains solvable.

## Out of scope

- No new database entity, rule type, page, or approval workflow.
- No production policy recommendation beyond evidence from this validation dataset.

## Evidence

- PostgreSQL four-scenario quality matrix: passed all eight quality gates.
- Combined-rule result: 1316-minute makespan, zero crane overlap, day-shift-only crane use,
  zero functional-test overlap, zero subsystem internal gap, two subsystem interruptions.
- Focused regression: 2 passed.
- Full backend regression: 349 passed.
- Detailed report: `docs/validation/MI_HP_001_INTEGRATION_RULE_QUALITY_20260713.md`.

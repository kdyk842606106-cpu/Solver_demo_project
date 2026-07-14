# TICKET-093: Gantt crane and shift visualization

> Status: completed
> Version: V0.3
> Created: 2026-07-14
> Completed: 2026-07-14

## Goal

Show rule-configured crane markers and segment-level shift identity directly in
the existing normal, grouped, and state-lane Gantt views without changing
Scheduler behavior or adding an entity, migration, or page.

## Tasks

- [x] T93-1 Validate and snapshot optional rule `presentation.gantt_marker` metadata.
- [x] T93-2 Edit Gantt marker text/color in the existing machine-type scheduling settings.
- [x] T93-3 Render deduplicated task markers and collapsed-group marker counts.
- [x] T93-4 Render deterministic shift strips, labels, legends, and complete tooltips from task segments.
- [x] T93-5 Add backend/frontend regression and run MI-HP-001 plus full verification.

## Acceptance

- MI_A010 and MI_A015 display a rule-configured crane marker without hard-coding their resource type in the Gantt component.
- Used shifts appear as a legend and as segment strips; adjacent shifts retain separate labels with zero pause.
- Marker and shift rendering works in normal, activity-grouped, and state-lane views.
- Collapsed activity groups show marker counts without implying that the entire group is a crane task.
- Calendar-disabled and historical results without presentation metadata retain existing behavior.

## Out of scope

- No Scheduler, calendar-continuity, rule-enforcement, entity, migration, or first-level page change.
- No version-diff Gantt contract or visualization change.

## Completion evidence

- Backend configuration validation, normalization, API round-trip, and active-rule snapshot preservation are covered; full backend regression passed `353` tests.
- Solve Chromium passed `12` tests, including marker deduplication, DAY/NIGHT/intersection shift legends, adjacent zero-pause segments, grouped aggregation, and state lanes. Full Chromium regression passed `84` tests.
- Vite production build passed with the existing large-chunk warning; `git diff --check` passed with the existing line-ending warning only.
- The PostgreSQL MI-HP-001 quality matrix passed all eight gates with unchanged scheduling behavior: crane overlap `0`, crane shifts DAY-only, pause `0`, functional-test overlap `0`, subsystem internal gap `0`, interruptions `2`, and all-rule makespan overhead `12.5%` within the `15%` limit.
- In-app MI-HP-001 layered solve completed with `36` tasks and `490m`; only `RULE_MI_A010` and `RULE_MI_A015` carried the rule-configured `吊` marker, both with `白班 (DAY_SHIFT)` segment presentation.

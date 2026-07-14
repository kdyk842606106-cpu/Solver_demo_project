# TICKET-091: night-shift crane wait and automatic independent-work pull-forward acceptance

> Status: completed
> Version: V0.3
> Created: 2026-07-13
> Completed: 2026-07-13

## Goal

Verify that a crane activity which is forbidden on the night shift waits for the
next allowed day shift while the Scheduler fills the night window with
later-listed work that has no DAG dependency on the crane. Also verify that a
true crane successor is never pulled ahead of its prerequisite.

## Tasks

- [x] T91-1 Add a realistic continuous day/night calendar acceptance scenario.
- [x] T91-2 Assert independent later-listed work is scheduled during the crane wait.
- [x] T91-3 Assert the true crane successor remains after the crane and all tasks have zero pause.
- [x] T91-4 Run focused and scheduling-rule regression and update STATE.

## Acceptance

- The solve starts at the night-shift boundary.
- The crane task starts on the next allowed day shift and never uses a night segment.
- At least one later-listed independent activity executes before the waiting crane.
- A task with an explicit crane precondition starts only after the crane finishes.
- The result is a normal initial solve; it does not misuse replan `step_role=pulled_forward`.

## Out of scope

- No change to production rule semantics, rule types, entities, pages, or MI-HP-001 process dependencies.

## Evidence

- Start: `2026-07-13T20:00:00+08:00` (`NIGHT_SHIFT_2`).
- Crane start: `2026-07-14T08:00:00+08:00`, with only a `DAY_SHIFT_1` segment.
- Two later-listed independent tasks finish before the crane starts and use night-shift segments.
- The explicit crane successor lists the crane step as a predecessor and starts after crane completion.
- Every task has zero calendar pause and retains initial-solve `step_role=normal`.
- Focused acceptance: 1 passed; scheduling-rule scenarios: 4 passed; full backend: 350 passed.

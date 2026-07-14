# TICKET-094: Make Gantt crane and shift legends explicit

> Status: completed
> Version: V0.3
> Created: 2026-07-14
> Completed: 2026-07-14

## Goal

Make the existing rule-marker and segment-shift legend unmistakable without
changing scheduling data or calendar semantics.

## Tasks

- [x] T94-1 Add an explicit Gantt legend title and separate marker/shift sections.
- [x] T94-2 Strengthen the legend border, spacing, swatches, and visual hierarchy.
- [x] T94-3 Add focused Chromium coverage and verify MI-HP-001 visually.
- [x] T94-4 Feed raw marker/shift payloads into the ECharts custom renderer and visually verify the task bars.
- [x] T94-5 Move shift text from task bars to the time-axis tick labels while retaining segment color strips.

## Out of scope

- No Scheduler, API, entity, migration, calendar, or rule-enforcement change.
- No synthetic legend entries when the plan contains no matching marker or shift metadata.

## Completion evidence

- The Gantt panel now displays an explicit `甘特图例` card with separate `作业标识` and `班次` rows.
- Existing data-driven marker and shift semantics are unchanged; empty categories remain hidden rather than fabricating legend entries.
- MI-HP-001 in-app verification displayed `吊 / Crane work exclusive within machine plan` and `白班 (DAY_SHIFT)`.
- Follow-up visual verification confirmed `RULE_MI_A010` and `RULE_MI_A015` render the orange `吊` badge inside their bars and every shift-bearing segment renders its blue top strip.
- The root cause was ECharts custom `renderItem` reading nonexistent `params.data`; the series renderer now closes over the original data array and passes the indexed raw item explicitly.
- Shift names are no longer rendered inside task bars. The time axis now appends the active shift name to each applicable tick, including the schedule-end tick; concurrent task-specific shifts are deduplicated and joined without inventing a global calendar.
- Solve Chromium passed `12/12` with one worker; Vite production build passed with the existing large-chunk warning.

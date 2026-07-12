# Planning Notes Archive

This folder contains historical planning and review notes. These files are useful
for understanding how decisions evolved, but they are not the current source of
truth.

Current project context should be read in this order:

1. `docs/ANCHOR.md`
2. `docs/STATE_V0.3.md`
3. The latest active `docs/TICKET_*.md`
4. `docs/protocols/` for implementation contracts

Some older notes still mention pre-BFS Planner behavior or single-resource
Scheduler limitations. Those statements describe the state at the time the note
was written and may be superseded by `TICKET_021`, `TICKET_022`, and
`docs/STATE_V0.3.md`.

Recent design notes:

- `2026-06-05-real-business-scaling-design.md` - real multi-subsystem
  collaboration and 5000+ activity-scale design notes covering rule-library
  governance, activity hierarchy, state maintenance, and compute-engine
  direction.
- `2026-06-05-target-business-system-gap-assessment.md` - working assessment
  document for estimating effort from the real existing activity repository
  and business system toward the target planning/solver system.

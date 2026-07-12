# TICKET-033: Layered solve preflight health summary

> Status: completed
> Version: V0.3
> Requirement source: `docs/layered_activity_state_requirements.md`
> Depends on: `docs/TICKET_026.md`, `docs/TICKET_027.md`, `docs/TICKET_031.md`

## Scope

Expose the existing layered health check as an explicit solve preflight summary
for layered and maintenance solves. TICKET-026 already provides the diagnostic
engine and TICKET-027 already calls it during layered solve; this ticket makes
the result visible and stable for API consumers and the Solve UI.

This ticket must not change Planner selection, Scheduler ordering, solve
status semantics, or health-check diagnostic logic.

## In Scope

- Add a compact `layered.preflight_health` field to successful layered and
  maintenance solve responses.
- Preserve the full `diagnostics.layered_health` payload for deeper debugging.
- The compact field should include:
  - status;
  - summary counts;
  - blocking/warning counts;
  - compact diagnostic rows suitable for UI display.
- Add Solve page display for preflight health in the layered/maintenance
  explanation tab.
- Add integration assertions proving layered and maintenance solve responses
  expose the compact preflight health field.

## Out of Scope

- No automatic blocking of solves solely because health status is `blocked`.
- No new health diagnostic codes.
- No post-import health-check execution.
- No frontend health-check workflow redesign.

## Acceptance Criteria

- [x] `/solve/layered` successful responses include `layered.preflight_health`.
- [x] `/solve/maintenance` successful responses include the same field through
      layered solve reuse.
- [x] Full health payload remains under `diagnostics.layered_health`.
- [x] Solve page shows health status, counts, and diagnostics when present.
- [x] Focused integration tests pass.
- [x] Full backend regression and frontend build pass.

## Implementation Summary

- Added `layered.preflight_health` to successful layered solve responses.
- Maintenance solve inherits the field because it delegates to layered solve.
- Kept the complete health-check payload under `diagnostics.layered_health`.
- Added a compact preflight payload with status, summary counts,
  blocking/warning counts, and UI-safe diagnostic rows.
- Solve page now shows the preflight health status, summary counts, and
  diagnostic rows in the layered/maintenance explanation tab.
- Integration tests now assert both `/solve/layered` and `/solve/maintenance`
  expose `layered.preflight_health` while preserving
  `diagnostics.layered_health`.

## Verification

- `python -m pytest tests/integration/test_layered_activity_state_api.py::test_layered_solve_consumes_scope_guards_and_schedules_level3_activities tests/integration/test_layered_activity_state_api.py::test_maintenance_solve_merges_intents_and_reuses_shared_provider -q`
  - 2 passed.
- `python -m pytest tests/integration/test_layered_activity_state_api.py -q`
  - 6 passed.
- `python -m pytest -q`
  - 309 passed.
- `npm run build`
  - passed after escalated rerun due sandbox `esbuild` `spawn EPERM`.
  - Existing Vite chunk-size warning remains.

# TICKET-081: Network Editor package-level transition aggregation
> Status: implementation_complete_verification_partial
> Version: V0.3
> Created: 2026-07-10

## Scope

Refine the frontend-only state-transition projection so folded state packages
summarize hidden atomic transitions without rendering every hidden realizer
relay and binding edge.

- Build semantic relay groups from the complete implementation graph, then
  derive the relay groups and package proxy edges visible at the current staged
  expansion depth.
- Aggregate hidden transitions by visible source state/package and visible
  target state/package.
- Keep same-package transitions as relation badges instead of self-loop edges.
- Preserve explicit state-package binding snapshot semantics and coverage
  status in relay and proxy summaries.
- Keep relay/proxy/layout artifacts frontend-only.

## Constraints

- No database schema or backend API contract changes.
- No Scheduler or RAGBuilder changes.
- State packages remain AND aggregates over their covered leaf-state snapshot.
- Package-to-package creation and proxy inspection dialogs remain out of scope.

## Verification Plan

- `npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --grep "state-transition|state package binding|folded state package|collapsed proxy"`
- `npm.cmd run build`
- `.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -k network_editor -q`
- `git diff --check`

## Implementation Result

- [x] Build complete semantic relay groups before applying the current visible
  state-package depth.
- [x] Render relays only when at least one output target is visible; otherwise
  aggregate hidden transitions into one visible package-to-package proxy.
- [x] Suppress same-package self-loops and expose their count through package
  relation badges.
- [x] Preserve explicit state-package bindings as one semantic endpoint with
  snapshot coverage labels for `complete`, `partial`, and `stale` coverage.
- [x] Keep relay, proxy, coverage, layout, and focus metadata UI-only.
- [x] Add deterministic E2E fixtures for package binding coverage, mixed package
  and atomic dependencies, package outputs, and the mechanical high-parallel
  eight-proxy scenario.

## Verification Result

- Focused projection E2E: 24 passed.
- Browser verification on `MECH_INTEGRATION_HIGH_PARALLEL`: 6 visible level-2
  packages, 8 package proxies, and 0 hidden relay nodes after expanding the
  level-1 package.
- Frontend build passed with the existing Vite chunk-size warning.
- `node --check` and `git diff --check` passed; the latter only reported the
  existing LF/CRLF warnings.
- Backend Network Editor pytest did not start because the repository `.venv`
  points to a removed Python 3.12 installation; no backend code changed.
- The complete `network-editor.spec.ts` run currently reports 46 passed and 15
  failed. The failures are outside this ticket's package-projection assertions
  and predominantly retain pre-staged expansion visibility or legacy container
  geometry expectations. They remain explicit follow-up work, so this ticket is
  not marked fully verified.

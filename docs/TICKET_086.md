# TICKET-086: Full branch review and squash integration into master
> Status: completed
> Version: V0.3
> Created: 2026-07-12
> Review completed: 2026-07-12

## Goal

Review the complete final tree of `codex/网络编辑器v2` against `master`, fix
all confirmed blocking, high-risk, and medium-risk findings, and integrate the
verified result into local `master` as one squash commit.

## Scope

- Review backend APIs/services, Planner/Scheduler, persistence/migrations,
  Network Editor frontend behavior, deployment scripts, tests, seeds, and
  documentation introduced by the branch.
- Include source, manifests, migrations, tests, seeds, tickets, and useful
  documentation artifacts.
- Exclude runtime state, release packages, temporary third-party checkouts,
  dependency caches, logs, PID files, and archive ZIP/TAR packages without
  deleting those local files.
- Preserve existing public contracts unless a confirmed review defect requires
  a backward-compatible correction.

## Quality Gates

- [x] Final inclusion/exclusion manifest is clean and reproducible.
- [x] All P0-P2 review findings are fixed with regression coverage.
- [x] Python compilation, JavaScript syntax, terminology, architecture,
      sensitive-data, conflict-marker, and cumulative diff checks pass.
- [x] Full backend pytest suite passes in a rebuilt Python 3.12 virtualenv.
- [x] PostgreSQL 15 migration, seed, and strict deployment-readiness checks pass
      against an isolated temporary database.
- [x] Frontend production build and all 78 Chromium Playwright tests pass.
- [x] Reviewed candidate is committed on the feature branch and squash-committed
      to local `master` without pushing or deleting the feature branch.
- [x] `STATE_V0.3.md` records the review, residual P3 debt, and verification.

## Known Baseline Risks To Close

- The checked-in `.venv` launcher points to a removed Python 3.12 installation.
- Two Network Editor full-flow expectations are recorded as stale.
- TICKET-081 and TICKET-082 retain partial-verification wording.
- The branch contains generated archive ZIPs and dependency-cache differences.
- The cumulative branch diff currently contains line-ending/whitespace errors.
- Vite reports a large production chunk; this is P3 and does not independently
  block integration once recorded.

## Out of Scope

- Pushing the resulting `master` commit to a remote.
- Renaming the default branch or deleting the feature branch.
- Implementing planned TICKET-064 behavior or unrelated historical debt.

## Confirmed Findings And Fixes

- P1: Network Editor graph reloads could leave a canceled debounced impact
  promise unresolved and keep the page loading indefinitely. Cancelation now
  resolves the pending promise and regression coverage exercises the full flow.
- P1: deployment scripts could classify unrelated Uvicorn/Vite processes as
  project-owned and terminate them. Process ownership now requires the resolved
  project root; stale PID handling no longer kills an unrelated live PID.
- P1: seed import on a clean PostgreSQL 15 database failed because resource
  upserts used the wrong conflict target and seed-owned `BEGIN`/`COMMIT` markers
  conflicted with loader savepoints. The conflict target now matches
  `uq_resource_machine_code`, and the loader owns transaction boundaries.
- P1: strict readiness rejected repair effects that clear
  `blockage_reason` to `none`. The enum definitions now include the clear value,
  while the UI options endpoint filters that sentinel from selectable reasons.
- P2: `/api/v1/system/status` performed synchronous inspection inside an async
  route and release metadata exposed an absolute checkout path. The route now
  uses FastAPI's thread pool and returns a stable relative metadata source.
- P2: legacy Network Editor commit payloads containing object-form state IDs
  were rejected. ID coercion again accepts `{state_node_id: ...}` without
  changing the public commit contract.
- P2: X6 container draft sizes could be ignored during focused expansion, and
  multi-root full-graph expansion lost previously expanded roots. Draft sizes
  and independent expanded roots are now preserved.
- P2: `BlockageDialog` directly owned reason loading semantics. It is now a pure
  component; `SolvePage` obtains configured reasons through `src/api/`.

## Repository Candidate

- Added `.gitattributes` and normalized the complete candidate diff so
  `git diff --check master` is clean.
- Removed tracked `frontend/node_modules` cache entries and eight release ZIPs
  from the candidate while preserving the ignored local files.
- Rebuilt `.venv` with bundled Python 3.12.13; the broken environment remains as
  the ignored timestamped backup `.venv.broken-review-20260712_192311`.
- Root package manifests, tickets, migrations, tests, seeds, design documents,
  and useful HTML/JSON/SVG/PNG/PPTX artifacts are included.

## Verification Evidence

- Backend: `326 passed` in the rebuilt virtualenv.
- PostgreSQL 15: Alembic `001 -> 009`, all SQL seeds `001 -> 011` loaded twice,
  and strict deployment readiness returned `ready`, with 0 schema and 0 data
  issues, against an isolated server on port 55432.
- Frontend: production build passed; all 78 Chromium Playwright tests passed in
  4.9 minutes using one worker.
- Static: Python compilation, cumulative JavaScript syntax, terminology,
  ANCHOR checks, conflict-marker/private-key scans, inclusion manifest, and
  cumulative whitespace checks passed.

## Residual P3 Debt

- Vite still reports a 4.6 MB minified application chunk. Code splitting remains
  follow-up work and does not block this integration.
- The test database teardown emits the existing SQLAlchemy warning for the
  `candidate_plan`/`solve_request` foreign-key cycle.

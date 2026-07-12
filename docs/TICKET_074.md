# TICKET-074: Unicode-safe state object feature keys and TEST1 data repair
> Status: completed
> Version: V0.3
> Created: 2026-07-02

## Scope

Fix the Network Editor and state target workflows so concrete state facts do
not collapse Chinese object names into the same ASCII token. Repair the local
TEST1 mechanical integration data where `模块B` and `工装B` shared one fact, and
where `管路` and `线路` shared one fact.

## Implementation Summary

- Network Editor atomic state creation now has an explicit `状态对象` field.
- Concrete feature keys are generated from `dimension_template_key + 状态对象`
  using a Unicode-safe `uXXXX` token rule while preserving existing ASCII
  keys such as `module_a`.
- State Target workspace uses the same token rule.
- Backend template-backed state validation now requires
  `metadata_json.state_object_name`, checks the exact derived concrete key, and
  rejects duplicate concrete facts.
- Network Editor exact state reuse now also checks the concrete feature key.
- Added `scripts/repair_test1_state_feature_keys.py` and ran it against the
  local TEST1 data:
  - `模块B` and `工装B` now use distinct facts.
  - `管路` and `线路` now use distinct facts.
  - TEST1 state nodes, op-rule preconditions/effects, machine-state features,
    feature definitions, and state metadata were synchronized.
  - Old collapsed keys such as `test1_dim_0001__b` and
    `test1_dim_0002__object` no longer have references.
- Re-ran TEST1/T-1 layered solve. The latest schedule contains both
  `安装模块B` and `连接线路`.

## Verification

- `.venv\Scripts\python.exe -m py_compile app\api\v1\master_data.py scripts\repair_test1_state_feature_keys.py`
  - passed.
- `.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -k "template_dimension" -q`
  - 3 passed, existing SQLite drop-order warning remains.
- `npm.cmd run build` from `frontend/`
  - passed with the existing Vite chunk-size warning.
- `npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium --grep "same state dimension|exact template state|searches existing atomic state names"` from `frontend/`
  - 3 passed.
- Direct TEST1/T-1 layered solve after repair:
  - status `done`, latest schedule makespan `150`;
  - tasks include `安装模块B` and `连接线路`.

## Out of Scope

- No solver objective changes.
- No change to the `ture`/`false` value spelling in TEST1's existing `系统上电`
  dimension.
- No migration for non-TEST1 historical data beyond the local repair script.

# TICKET-012: V0.3 前置任务 - 业务场景 Excel 导入包与端到端数据装载

> 对应版本：V0.3
> 当前状态：已完成，2026-05-29 已落地业务场景导入包
> 背景：用户需要基于真实业务场景完成一次完整端到端测试，场景包含 100+ 活动规则与若干资源，现有数据管理 CRUD 页面录入效率不足。

---

## 任务定位

本票不再只做“主数据 Excel 单文件导入”。新的目标是交付一个可支撑真实业务验收的“业务场景导入包”能力：

1. 业务人员可以用一个 `.xlsx` 文件描述完整测试场景。
2. 系统可以先 dry-run 校验，输出行级错误和 create/update 预估。
3. 系统可以 strict upsert 导入，任意错误整批回滚。
4. 导入后可以直接在求解页选择场景中的设备、起点状态、目标状态并运行端到端求解。
5. 对开发测试，允许提供同源的 seed SQL/生成脚本作为快速加载路径，但最终产品入口仍以 Excel 导入为准。

---

## 重新设计后的范围

### 必做

导入一个完整业务场景，覆盖：

1. `FeatureDefinition`：全局特征定义。
2. `MachineType`：设备/业务对象类型。
3. `Machine`：设备/业务对象实例。
4. `StateFeatureDef`：指定 machine_type 下的状态特征定义。
5. `Resource`：资源实例与容量。
6. `OpRule`：活动规则，含 `preconditions`、`effects`、`resource_reqs`。
7. `MachineState`：起点状态与目标状态。
8. `solve_case`：用于 E2E 验收的求解用例元数据。

### 保留兼容

旧版 `meta + feature_defs + resources + rules + instructions` 结构作为“主数据最小导入模式”兼容，但本次实现和验收以“业务场景模式”为主。

### 不做

- 不做 partial success。
- 不做异步导入任务队列。
- 不做 CSV 导入。
- 不在 RAGBuilder/Scheduler 中增加业务特例。
- 不通过前端页面逐条录入 100+ 活动。

---

## Excel 文件结构

必需 sheet：

1. `meta`
2. `feature_catalog`
3. `machine_type`
4. `machines`
5. `state_feature_defs`
6. `resources`
7. `rules`
8. `states`
9. `solve_cases`
10. `instructions`

可选 sheet：

1. `rule_groups`：为后续 Operation Group 能力预留。
2. `notes`：业务备注，不参与导入。

---

## Sheet 设计摘要

### meta

字段：

- `scenario_code`
- `scenario_name`
- `version`
- `mode`

约束：

- `scenario_code` 必填，作为本次导入报告中的场景标识。
- `mode` 固定为 `scenario_upsert`。

### feature_catalog

字段：

- `feature_key`
- `value_type`
- `allowed_values`
- `unit`
- `description`

用途：

- 写入全局 `feature_definition` 表。
- `allowed_values` 支持逗号分隔，导入时转为 JSON array。

### machine_type

字段：

- `code`
- `name`
- `description`

约束：

- 本阶段建议每个 Excel 只导入一个 machine_type。

### machines

字段：

- `code`
- `machine_type_code`
- `name`
- `location`

用途：

- 为 E2E 求解提供可选择的设备实例。

### state_feature_defs

字段：

- `machine_type_code`
- `feature_key`
- `feature_name`
- `value_type`
- `allowed_values`

约束：

- `feature_key` 必须存在于 `feature_catalog` 或数据库既有 `feature_definition`。
- 同一 `machine_type_code + feature_key` strict upsert。

### resources

字段：

- `code`
- `name`
- `resource_type`
- `capacity`
- `is_available`
- `meta_json`

用途：

- 为 Scheduler 多资源约束提供资源池。

### rules

字段：

- `code`
- `machine_type_code`
- `name`
- `duration_min`
- `description`
- `is_active`
- `is_repair`
- `preconditions`
- `effects`
- `resource_reqs`

DSL：

- `preconditions`：`feature_key:operator:feature_value;feature_key:operator:feature_value`
- `effects`：`feature_key:effect_type:value;feature_key:effect_type:value`
- `resource_reqs`：`resource_type:quantity:is_required;resource_type:quantity:is_required`

示例：

```text
preconditions = prep_done:eq:true;wing_ready:eq:true
effects = wing_joined:set:true
resource_reqs = technician:2:true;fixture:1:true
```

### states

字段：

- `machine_code`
- `state_code`
- `state_type`
- `label`
- `features`

DSL：

- `features`：`feature_key:value;feature_key:value`

约束：

- `state_type` 支持 `current`、`target`、`snapshot`。
- `features` 引用的 feature_key 必须属于该 machine 的 machine_type。

### solve_cases

字段：

- `case_code`
- `machine_code`
- `current_state_code`
- `target_state_code`
- `objective`
- `objectives_json`
- `constraints_json`
- `expected_min_steps`
- `expected_max_makespan_min`

用途：

- dry-run 阶段校验当前/目标状态是否可定位。
- 正式导入后返回可用于 E2E 的 `machine_id/current_state_id/target_state_id` 映射。

---

## 后端 API

### 上传并校验/导入

`POST /api/v1/imports/scenario`

请求：

- `file`: `.xlsx`
- `mode`: `scenario_upsert`
- `dry_run`: `true | false`

响应：

```json
{
  "status": "validated",
  "summary": {
    "scenario_code": "AFA_E2E_001",
    "dry_run": true,
    "error_count": 0,
    "feature_catalog_total": 32,
    "machine_types_total": 1,
    "machines_total": 1,
    "state_feature_defs_total": 32,
    "resources_total": 18,
    "rules_total": 120,
    "states_total": 2,
    "solve_cases_total": 1
  },
  "preview": {
    "rules": {"create": 100, "update": 20},
    "resources": {"create": 18, "update": 0}
  },
  "solve_cases": [
    {
      "case_code": "AFA_FULL_FLOW",
      "machine_code": "AFA-001",
      "current_state_code": "START",
      "target_state_code": "TARGET"
    }
  ],
  "errors": []
}
```

### 下载模板

`GET /api/v1/imports/scenario-template`

响应：

- `.xlsx` 模板文件。
- 包含中文 `instructions` sheet。

---

## 校验规则

基础校验：

- 所有必需 sheet 存在。
- 必填字段非空。
- 同一 sheet 的业务键唯一。
- 布尔值支持 `true/false`、`1/0`、`yes/no`、`是/否`。
- JSON 字段必须为合法 JSON。

引用校验：

- `machine_type_code` 必须能在本文件或数据库中定位。
- `machine_code` 必须能在本文件或数据库中定位。
- `feature_key` 必须能在 `feature_catalog` 或数据库中定位。
- `rules.preconditions/effects` 中的 feature_key 必须属于目标 machine_type。
- `rules.resource_reqs.resource_type` 必须能在本文件或数据库资源类型中定位。
- `solve_cases.current_state_code/target_state_code` 必须能定位到同一 machine 下的状态。

求解前置校验：

- 每条 rule 至少有一个 effect。
- 每个 solve_case 的起点/目标状态 feature_key 集合合法。
- dry-run 可选执行轻量连通性检查：至少存在规则 effect 命中目标差异。

事务语义：

- `dry_run=true` 不写数据库。
- `dry_run=false` 使用单事务。
- 任意错误整批回滚。

---

## 子任务清单

```text
[✅] A  重新冻结导入规范：业务场景 Excel 模板、DSL、校验规则、响应结构
[✅] B  后端导入服务：Excel 解析、结构化 DTO、行级错误收集
[✅] C  后端校验服务：跨 sheet/跨表引用校验、create/update 预估
[✅] D  后端落库服务：scenario_upsert 单事务导入
[✅] E  API：POST /api/v1/imports/scenario 与 GET /api/v1/imports/scenario-template
[✅] F  前端入口：DataManagement 顶部导入按钮、dry-run 结果弹窗、确认导入
[✅] G  模板交付：带 instructions 的 .xlsx 模板
[✅] H  E2E 验证：导入场景后可完成 /solve 求解，并补充 100+ rules dry-run 覆盖
[✅] I  文档回写：STATE/TICKET/协议文档同步
```

---

## 验收标准

```text
✓ 一个 .xlsx 文件可导入完整业务场景，而不需要手工逐条录入活动
✓ 支持 100+ rules 与多类型 resources 的 dry-run 校验
✓ dry-run 返回 create/update 预估和 sheet/row/field/message 错误列表
✓ 正式导入使用 strict upsert，任意错误整批回滚
✓ 导入后可以在现有求解流程中选择 machine/current_state/target_state 并完成 /solve
✓ 模板 instructions sheet 能指导业务人员独立填写
✓ 保持 API -> Service -> Persistence 分层，不把导入逻辑塞进前端或求解器
```

# 业务场景 Excel 导入设计（V0.3 / TICKET-012）

> 创建时间：2026-04-20
> 重新设计：2026-05-29
> TICKET-036 同步：2026-06-23，补齐原子活动、活动包引用、任意深度状态目标、维护意图和导入后健康检查。
> V0.3 RC 同步：2026-07-16，补齐工作日历、班次窗口、日期例外和机器日历绑定 sheets。
> 适用范围：真实业务端到端测试场景导入，支持 100+ 活动规则、资源池、起点/目标状态与求解用例。

---

## 1. 设计目标

现有数据管理页面适合少量数据维护，不适合一次性录入 100+ 活动规则。TICKET-012 重新设计后的目标是：

- 用一个 `.xlsx` 文件承载完整业务场景。
- 支持先 dry-run 校验，再 strict upsert 导入。
- 导入内容不仅包含规则/资源，还包含 E2E 所需的 machine、state、solve_case。
- 导入后可以直接使用现有 `/api/v1/solve` 流程验证完整链路。
- 保持导入逻辑独立于 Planner/Scheduler，避免在求解器中加入业务特例。

---

## 2. 模式

### 2.1 scenario_upsert

主模式，用于真实业务场景导入。

覆盖：

- `feature_definition`
- `machine_type`
- `machine`
- `state_feature_def`
- `resource`
- `op_rule`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`
- `machine_state`
- `machine_state_feature`
- `activity_node`
- `atomic_activity`
- `activity_package_atomic_ref`
- `state_node`
- `scope_guard`
- `scope_guard_precond`
- `maintenance_intent_template`
- `solve_case` 映射信息（不一定新建数据库表，第一阶段可只在响应中返回）

### 2.2 master_data_upsert

兼容旧模式，只导入：

- `state_feature_def`
- `resource`
- `op_rule`

本阶段不作为验收主路径。

---

## 3. 文件结构

必需 sheet：

| Sheet | 用途 |
|---|---|
| `meta` | 场景元信息 |
| `feature_catalog` | 全局特征定义 |
| `machine_type` | 设备/业务对象类型 |
| `machines` | 设备/业务对象实例 |
| `state_feature_defs` | 类型下的状态特征定义 |
| `resources` | 资源池 |
| `rules` | 活动规则 |
| `states` | 起点、目标、快照状态 |
| `solve_cases` | E2E 求解用例 |
| `instructions` | 中文填写说明，不参与导入 |

可选 sheet：

| Sheet | 用途 |
|---|---|
| `activity_nodes` | 一级/二级活动包；legacy 三级活动节点兼容 |
| `atomic_activities` | 可复用原子活动库 |
| `activity_package_atomic_refs` | 二级活动包到原子活动的引用 |
| `state_nodes` | 任意深度状态目标树 |
| `scope_guards` | 活动范围公共前置条件 |
| `maintenance_intents` | 维护意图模板 |
| `layered_health_checks` | 导入成功后执行的分层健康检查 |
| `rule_groups` | 预留工序组能力 |
| `notes` | 业务备注 |
| `work_calendars` | 可复用工作日历主数据 |
| `work_calendar_windows` | 周期工作窗口与班次名称 |
| `work_calendar_exceptions` | 指定日期的开放/关闭例外 |
| `machine_calendar_bindings` | 机器默认日历或状态维度日历映射 |

---

## 4. Sheet 字段

### 4.1 meta

| 字段 | 必填 | 说明 |
|---|---|---|
| `scenario_code` | 是 | 场景编码 |
| `scenario_name` | 是 | 场景名称 |
| `version` | 否 | 场景版本 |
| `mode` | 是 | 固定为 `scenario_upsert` |

约束：

- 仅允许一行有效数据。

### 4.2 feature_catalog

| 字段 | 必填 | 说明 |
|---|---|---|
| `feature_key` | 是 | 全局特征键 |
| `value_type` | 是 | `string` / `number` / `boolean` / `enum` |
| `allowed_values` | 否 | enum 可选值，逗号分隔 |
| `unit` | 否 | 单位 |
| `description` | 否 | 描述 |

Upsert 键：

- `feature_key`

### 4.3 machine_type

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 类型编码 |
| `name` | 是 | 类型名称 |
| `description` | 否 | 描述 |

Upsert 键：

- `code`

### 4.4 machines

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 设备编码 |
| `machine_type_code` | 是 | 所属类型编码 |
| `name` | 是 | 设备名称 |
| `location` | 否 | 位置 |

Upsert 键：

- `code`

### 4.5 state_feature_defs

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `feature_key` | 是 | 特征键 |
| `feature_name` | 否 | 展示名称 |
| `value_type` | 是 | `string` / `number` / `boolean` / `enum` |
| `allowed_values` | 否 | enum 可选值，逗号分隔 |

Upsert 键：

- `machine_type_code + feature_key`

### 4.6 resources

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_code` | 是 | 资源所属设备编码 |
| `code` | 是 | 资源编码 |
| `name` | 是 | 资源名称 |
| `resource_type` | 是 | 资源类型 |
| `capacity` | 是 | 正整数容量 |
| `is_available` | 否 | 默认 true |
| `meta_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_code + code`

### 4.7 rules

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 活动规则编码 |
| `machine_type_code` | 是 | 所属类型编码 |
| `name` | 是 | 活动名称 |
| `duration_min` | 是 | 正整数，分钟 |
| `description` | 否 | 描述 |
| `is_active` | 否 | 默认 true |
| `is_repair` | 否 | 默认 false |
| `preconditions` | 否 | DSL |
| `effects` | 是 | DSL，至少一项 |
| `resource_reqs` | 否 | DSL |
| `activity_node_code` | 否 | legacy 三级活动节点绑定；导入时会尽量回填原子活动 |
| `atomic_activity_code` | 否 | 推荐：绑定到 `atomic_activities.code`；不能与 `activity_node_code` 同时填写 |

Upsert 键：

- `code`

### 4.8 activity_nodes

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `code` | 是 | 活动节点编码 |
| `parent_code` | 否 | 父活动节点编码 |
| `level` | 是 | 推荐 1/2；legacy 3 会自动派生原子活动和二级包引用 |
| `name` | 是 | 名称 |
| `activity_category` | 否 | `normal` / `repair` / `maintenance` |
| `sort_order` | 否 | 排序 |
| `is_active` | 否 | 默认 true |
| `metadata_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_type_code + code`

### 4.9 atomic_activities

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `code` | 是 | 原子活动编码 |
| `name` | 是 | 名称 |
| `activity_category` | 否 | `normal` / `repair` / `maintenance` |
| `sort_order` | 否 | 排序 |
| `is_active` | 否 | 默认 true |
| `metadata_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_type_code + code`

### 4.10 activity_package_atomic_refs

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `package_code` | 是 | 二级活动包编码 |
| `atomic_activity_code` | 是 | 原子活动编码 |
| `sort_order` | 否 | 包内排序 |
| `is_active` | 否 | 默认 true |
| `metadata_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_type_code + package_code + atomic_activity_code`

### 4.11 state_nodes

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `code` | 是 | 状态节点编码 |
| `parent_code` | 否 | 父状态节点编码 |
| `level` | 是 | 正整数层级 |
| `name` | 是 | 名称 |
| `feature_key` | 原子状态必填 | 叶子状态绑定特征键 |
| `operator` | 原子状态必填 | 当前普通维护流使用 `eq` |
| `target_value` | 原子状态必填 | 目标值 |
| `state_kind` | 否 | `aggregate` / `atomic` / `external` / `manual` |
| `sort_order` | 否 | 排序 |
| `is_active` | 否 | 默认 true |
| `metadata_json` | 否 | JSON 对象 |

有子节点的状态视为聚合状态，不应绑定事实；活跃无子节点状态视为原子状态。原子状态导入会自动确保 `feature_definition` 和对应 `state_feature_def` 存在。

Upsert 键：

- `machine_type_code + code`

### 4.12 scope_guards

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `activity_node_code` | 是 | 一级或二级活动包编码 |
| `name` | 是 | Scope Guard 名称 |
| `description` | 否 | 描述 |
| `is_active` | 否 | 默认 true |
| `preconditions` | 否 | `state_node_code:operator[:expected]` DSL |
| `metadata_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_type_code + activity_node_code + name`

### 4.13 states

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_code` | 是 | 设备编码 |
| `state_code` | 是 | 文件内状态编码 |
| `state_type` | 是 | `current` / `target` / `snapshot` |
| `label` | 否 | 状态名称 |
| `features` | 是 | DSL |

Upsert 策略：

- 第一阶段按 `machine_code + state_code` 在导入过程中定位。
- 当前数据库没有 `state_code` 字段，因此正式落库时创建新的 state 快照；返回中提供 `state_code -> state_id` 映射。

### 4.14 solve_cases

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_code` | 是 | 用例编码 |
| `machine_code` | 是 | 设备编码 |
| `current_state_code` | 是 | 起点状态编码 |
| `target_state_code` | 是 | 目标状态编码 |
| `objective` | 否 | 默认 `minimize_makespan` |
| `objectives_json` | 否 | JSON array |
| `constraints_json` | 否 | JSON object |
| `expected_min_steps` | 否 | 验收辅助 |
| `expected_max_makespan_min` | 否 | 验收辅助 |

### 4.15 maintenance_intents

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `issue_type` | 是 | 维护问题类型 |
| `name` | 是 | 模板名称 |
| `scope_activity_node_code` | 是 | 维护作用域，必须为二级活动包 |
| `description` | 否 | 描述 |
| `target_state_node_codes` | 否 | 逗号或分号分隔 |
| `candidate_activity_scope_codes` | 否 | 逗号或分号分隔，默认使用 scope |
| `observed_fact_templates` | 否 | `feature:eq:value` DSL 或 JSON array |
| `desired_fact_templates` | 否 | `feature:eq:value` DSL 或 JSON array |
| `is_active` | 否 | 默认 true |
| `metadata_json` | 否 | JSON 对象 |

Upsert 键：

- `machine_type_code + issue_type`

### 4.16 layered_health_checks

| 字段 | 必填 | 说明 |
|---|---|---|
| `machine_type_code` | 是 | 类型编码 |
| `check_code` | 是 | 文件内检查编码 |
| `name` | 否 | 检查名称 |
| `target_state_node_codes` | 否 | 逗号或分号分隔 |
| `activity_scope_node_codes` | 否 | 逗号或分号分隔 |
| `include_inactive` | 否 | 默认 false |
| `description` | 否 | 描述 |

---

## 5. DSL 规范

### 5.1 通用规则

- 同一单元格多项使用 `;` 分隔。
- 单项字段使用 `:` 分隔。
- 空值表示无条目。
- 字符串值不需要加引号。

### 5.2 preconditions

格式：

```text
feature_key:operator:feature_value;feature_key:operator:feature_value
```

支持 operator：

- `eq`
- `neq`
- `gt`
- `gte`
- `lt`
- `lte`
- `in`

示例：

```text
prep_done:eq:true;pressure_bar:gte:3.5;mode:in:auto,semi
```

### 5.3 effects

格式：

```text
feature_key:effect_type:value;feature_key:effect_type:value
```

支持 effect_type：

- `set`
- `increment`
- `decrement`
- `sub`
- `reset`

示例：

```text
wing_joined:set:true;progress_pct:increment:20;cleanliness:sub:25;cleanliness:reset:100
```

`increment` / `decrement` / `sub` 的 `value` 会解析为 `delta_value`；`set` / `reset` 的 `value` 会作为目标 `new_value`。

### 5.4 resource_reqs

格式：

```text
resource_type:quantity:is_required;resource_type:quantity:is_required
```

示例：

```text
technician:2:true;fixture:1:true;inspector:1:false
```

### 5.5 state features

格式：

```text
feature_key:value;feature_key:value
```

示例：

```text
prep_done:false;wing_joined:false;delivery_ready:false
```

---

## 6. 校验

### 6.1 结构校验

- 必需 sheet 全部存在。
- 必填字段非空。
- 业务键在 sheet 内唯一。
- `duration_min`、`capacity`、`quantity` 为正整数。
- `meta_json`、`objectives_json`、`constraints_json` 为合法 JSON。

### 6.2 引用校验

- `machine_type_code` 能在文件或数据库中定位。
- `machine_code` 能在文件或数据库中定位。
- `feature_key` 能在 `feature_catalog` 或数据库 `feature_definition` 中定位。
- `state_feature_defs.feature_key` 属于目标 machine_type。
- `rules.preconditions/effects.feature_key` 属于目标 machine_type。
- `rules.resource_reqs.resource_type` 能在本文件或数据库资源类型中定位。
- `rules.atomic_activity_code` 能在 `atomic_activities` 或数据库中定位。
- `rules.activity_node_code` 与 `rules.atomic_activity_code` 不能同时填写。
- `activity_package_atomic_refs.package_code` 必须引用二级活动包。
- `activity_package_atomic_refs.atomic_activity_code` 必须引用同机型原子活动。
- `state_nodes` 聚合节点不绑定事实；原子叶子节点必须有 `feature_key/operator/target_value`。
- `scope_guards.activity_node_code` 必须引用一级或二级活动包。
- `maintenance_intents.scope_activity_node_code` 必须引用二级活动包。
- `layered_health_checks` 引用的状态节点和活动范围节点必须存在。
- `states.features.feature_key` 属于机器对应的 machine_type。
- `solve_cases` 引用的状态编码存在，且属于同一 machine。

### 6.3 求解前置校验

- 每条 rule 至少有一个 effect。
- 每个 solve_case 的当前状态和目标状态存在状态差异，或显式允许 no-op。
- 至少有一个 rule effect 命中目标状态差异。
- 多资源需求不得明显超过同类型可用资源总容量。
- 分层求解场景建议声明 `layered_health_checks`，导入成功后返回 compact 健康检查结果；dry-run 只校验声明，不执行健康检查。

---

## 7. API 契约

### 7.1 导入

`POST /api/v1/imports/scenario`

请求：

- `file`: `.xlsx`
- `mode`: `scenario_upsert`
- `dry_run`: `true | false`

响应字段：

- `status`: `validated` / `imported` / `failed`
- `summary`: 数量统计
- `preview`: create/update 预估
- `solve_cases`: 用例映射
- `maintenance_intent_templates`: 正式导入后写入的维护意图模板摘要
- `post_import_health_checks`: 正式导入后执行的分层健康检查结果，dry-run 和失败时为空
- `errors`: 错误列表

错误项格式：

```json
{
  "sheet": "rules",
  "row": 12,
  "field": "effects",
  "message": "Unknown feature_key: wing_joined"
}
```

### 7.2 模板下载

`GET /api/v1/imports/scenario-template`

响应：

- `.xlsx` 文件。

---

## 8. 前端流程

入口：

- `DataManagement` 顶部增加“下载场景模板”和“导入场景”按钮。

流程：

1. 用户选择 `.xlsx`。
2. 前端调用 dry-run。
3. 弹窗展示数量汇总、create/update 预估、错误列表、solve_cases。
4. 无错误时允许确认导入。
5. 导入成功后展示维护意图、原子活动、活动包引用和导入后健康检查结果。
6. 提示可去求解页选择对应设备和状态，或使用分层/维护模式验证。

---

## 9. 验收场景

### 成功场景

- 导入一个包含 100+ rules、多个 resource_type、2 个 states、1 个 solve_case 的 Excel。
- dry-run error_count 为 0。
- 正式导入成功。
- 调用 `/api/v1/solve` 能返回 candidate_plan 和 schedule。
- 导入包含 `activity_nodes`、`atomic_activities`、`activity_package_atomic_refs`、`state_nodes`、`maintenance_intents` 和 `layered_health_checks` 的场景。
- 正式导入后返回 `post_import_health_checks`，并可通过 `/api/v1/solve/layered` 或 `/api/v1/solve/maintenance` 使用导入数据。

### 失败场景

- rules 引用不存在 feature_key。
- rules 同时填写 `activity_node_code` 和 `atomic_activity_code`。
- 活动包引用不存在原子活动。
- 聚合状态错误绑定事实。
- resource_reqs 引用不存在 resource_type。
- states 引用不属于 machine_type 的 feature_key。
- 任一错误导致正式导入整批回滚。

---

## 10. 关联文件

- `docs/TICKET_012.md`
- `docs/STATE_V0.3.md`
- `docs/protocols/api.md`
- `app/api/v1/master_data.py`
- `app/services/scenario_import.py`
- `app/db/models.py`

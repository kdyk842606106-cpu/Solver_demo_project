# 业务场景 Excel 导入设计（V0.3 / TICKET-012）

> 创建时间：2026-04-20
> 重新设计：2026-05-29
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
| `rule_groups` | 预留工序组能力 |
| `notes` | 业务备注 |

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
| `code` | 是 | 资源编码 |
| `name` | 是 | 资源名称 |
| `resource_type` | 是 | 资源类型 |
| `capacity` | 是 | 正整数容量 |
| `is_available` | 否 | 默认 true |
| `meta_json` | 否 | JSON 对象 |

Upsert 键：

- `code`

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

Upsert 键：

- `code`

### 4.8 states

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

### 4.9 solve_cases

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
- `states.features.feature_key` 属于机器对应的 machine_type。
- `solve_cases` 引用的状态编码存在，且属于同一 machine。

### 6.3 求解前置校验

- 每条 rule 至少有一个 effect。
- 每个 solve_case 的当前状态和目标状态存在状态差异，或显式允许 no-op。
- 至少有一个 rule effect 命中目标状态差异。
- 多资源需求不得明显超过同类型可用资源总容量。

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
5. 导入成功后提示可去求解页选择对应设备和状态。

---

## 9. 验收场景

### 成功场景

- 导入一个包含 100+ rules、多个 resource_type、2 个 states、1 个 solve_case 的 Excel。
- dry-run error_count 为 0。
- 正式导入成功。
- 调用 `/api/v1/solve` 能返回 candidate_plan 和 schedule。

### 失败场景

- rules 引用不存在 feature_key。
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

# 主数据 Excel 单文件导入设计（V0.3 / TICKET-012）

> 创建时间：2026-04-20
> 适用范围：`StateFeatureDef`（按 machine_type）、`Resource`、`OpRule`
> 目标：上传一个 `.xlsx` 文件，完成严格 Upsert 导入

---

## 1. 目标与边界

### 1.1 本次目标

- 支持单文件导入三类主数据：
  - 特征定义（`StateFeatureDef`）
  - 资源（`Resource`）
  - 活动规则（`OpRule`，含 preconditions/effects/resource_reqs）
- 导入模式：`strict_upsert`
  - 已存在：更新
  - 不存在：创建
- 严格事务：任意错误整批失败，回滚不落库
- 提供 `dry_run` 预校验能力

### 1.2 本次不做

- 不导入 machine_type / machine / state
- 不导入全局 `feature_definition`（`/features`）
- 不做部分成功导入
- 不做 CSV 导入
- 不做复杂导入任务队列/异步化

---

## 2. 文件格式规范（单个 .xlsx）

必须包含以下 sheet：

1. `meta`
2. `feature_defs`
3. `resources`
4. `rules`
5. `instructions`（中文说明，仅供阅读，不参与导入）

仅支持 `.xlsx`。

---

## 3. 各 sheet 字段定义

### 3.1 `meta`

列头：

- `machine_type_code`

约束：

- 必须且仅有 1 条有效数据
- `machine_type_code` 必须在系统中存在
- 本文件中 `feature_defs`、`rules` 均归属该 machine_type

示例：

| machine_type_code |
|---|
| LASER_WELDER |

### 3.2 `feature_defs`

列头：

- `feature_key`
- `feature_name`
- `value_type`
- `allowed_values`

约束：

- `feature_key` 必填，sheet 内唯一
- `value_type` 仅允许：`string` / `number` / `boolean` / `enum`
- 当 `value_type=enum`：`allowed_values` 必填，逗号分隔
- 当 `value_type!=enum`：`allowed_values` 允许为空

业务键（strict_upsert）：

- `(machine_type_id, feature_key)`

### 3.3 `resources`

列头：

- `code`
- `name`
- `resource_type`
- `capacity`
- `is_available`

约束：

- `code` 必填，sheet 内唯一
- `capacity` 为正整数
- `is_available` 支持：`true/false`、`1/0`、`yes/no`、`是/否`

业务键（strict_upsert）：

- `code`

### 3.4 `rules`

列头：

- `code`
- `name`
- `duration_min`
- `description`
- `is_repair`
- `preconditions`
- `effects`
- `resource_reqs`

约束：

- `code` 必填，sheet 内唯一
- `duration_min` 为正整数
- `is_repair` 可解析为布尔
- `effects` 至少 1 条

业务键（strict_upsert）：

- `code`（与现有后端唯一性约束一致）

---

## 4. 单元格 DSL 规范（rules）

### 4.1 通用规则

- 同列内多项使用 `;` 分隔
- 单项字段使用 `:` 分隔
- 空值视为“无条目”

### 4.2 `preconditions`

格式：

`feature_key:operator:feature_value;feature_key:operator:feature_value`

支持 operator：`eq` / `neq` / `gt` / `gte` / `lt` / `lte` / `in`

示例：

`pressure_bar:gte:3.5;mode:eq:auto`

当 operator=`in`：

- `feature_value` 仍为字符串（如 `auto,semi`）
- 系统同时派生 `value_list=["auto","semi"]`

### 4.3 `effects`

格式：

`feature_key:effect_type:value;feature_key:effect_type:value`

支持 effect_type：`set` / `increment` / `decrement`

示例：

`temperature_c:set:180;pressure_bar:increment:0.5`

解析规则：

- `set`：`new_value=value`
- `increment/decrement`：`delta_value=number(value)`

### 4.4 `resource_reqs`

格式：

`resource_type:quantity:is_required;resource_type:quantity:is_required`

示例：

`technician:1:true;gas:1:false`

约束：

- `quantity` 为正整数
- `is_required` 可解析为布尔

---

## 5. 导入流程

### 5.1 前端流程

1. 上传 `.xlsx`
2. 触发 `dry_run=true`
3. 展示校验摘要与错误列表
4. 用户确认后触发正式导入（`dry_run=false`）
5. 成功后刷新 Rule/FeatureDef/Resource 页面数据

### 5.2 后端流程

1. 读取文件并检查 sheet 完整性
2. 解析 `meta.machine_type_code`
3. 解析并校验 `feature_defs/resources/rules`
4. 执行跨表校验（feature_key/resource_type 引用）
5. `dry_run=true` 返回预览结果
6. `dry_run=false` 执行单事务 strict_upsert

---

## 6. 事务与失败语义

- 正式导入采用单事务
- 任意一行/一列错误导致整批失败
- 失败返回结构化错误列表，不产生部分落库

---

## 7. API 契约（草案）

### 7.1 路径

- `POST /api/v1/imports/master-data`

### 7.2 请求（multipart/form-data）

- `file`：Excel 文件（.xlsx）
- `mode`：固定 `strict_upsert`
- `dry_run`：`true | false`

### 7.3 响应（示意）

```json
{
  "status": "validated",
  "summary": {
    "machine_type_code": "LASER_WELDER",
    "dry_run": true,
    "feature_defs_total": 12,
    "resources_total": 8,
    "rules_total": 15,
    "error_count": 0
  },
  "preview": {
    "feature_defs": {"create": 3, "update": 9},
    "resources": {"create": 1, "update": 7},
    "rules": {"create": 4, "update": 11}
  },
  "errors": []
}
```

---

## 8. 跨数据校验规则

- 规则中出现的 `feature_key` 必须在：
  - 本文件 `feature_defs`，或
  - DB 中该 machine_type 的已存在 `StateFeatureDef`
- 规则中出现的 `resource_type` 必须在：
  - 本文件 `resources`，或
  - DB 中已存在 `Resource.resource_type`

---

## 9. 验收标准

```text
✅ 上传一个 Excel 文件可覆盖导入 feature_defs/resources/rules 三类数据
✅ dry_run 能输出 create/update 预估与行级错误
✅ strict_upsert 生效（存在更新，不存在创建）
✅ 任意错误整批回滚，不发生部分成功
✅ instructions sheet 提供中文填写说明
```

---

## 10. 关联文档

- `docs/STATE_V0.3.md`
- `docs/TICKET_012.md`
- `docs/ANCHOR.md`

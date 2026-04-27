# TICKET-012: V0.3 前置任务 — 主数据 Excel 单文件导入（规则/特征定义/资源）

> 对应版本：V0.3
> 对应阶段：V0.3 前置可用性专项（先于 TICKET-011）
> 前置依赖：`docs/master-data-excel-import.md` 已冻结
> 导入策略：`strict_upsert`（严格事务，整批失败回滚）

---

## 本次任务范围（只做这些）

交付主数据单文件 Excel 导入能力，覆盖：

1. `StateFeatureDef`（按 machine_type）
2. `Resource`
3. `OpRule`（含 `preconditions/effects/resource_reqs`）

并满足：

- 上传一个 `.xlsx` 文件完成导入
- `dry_run` 预校验
- 正式导入采用 `strict_upsert`
- 任意错误整批回滚

---

## 子任务清单

```text
[ ] A  文档冻结：模板字段、DSL 语法、校验规则
[ ] B  后端：新增 /api/v1/imports/master-data（dry_run + strict_upsert）
[ ] C  后端：导入服务实现（Excel 解析、跨表校验、单事务落库）
[ ] D  前端：DataManagement 导入入口 + 导入弹窗（预校验/确认导入）
[ ] E  模板交付：单个 .xlsx（含 instructions 中文说明 sheet）
[ ] F  回归验证：成功导入 + 错误回滚 + 行级错误提示
[ ] G  文档回写：STATE/TICKET 状态同步
```

---

## 详细要求

### A：文档冻结

- 以 `docs/master-data-excel-import.md` 为唯一导入规范。
- 文件结构固定为：`meta`、`feature_defs`、`resources`、`rules`、`instructions`。

### B：后端 API

- 新增接口：`POST /api/v1/imports/master-data`
- 请求：`multipart/form-data`
  - `file`（.xlsx）
  - `mode`（固定 `strict_upsert`）
  - `dry_run`（`true/false`）
- 响应：返回 summary + preview + errors（行级错误）

### C：后端导入服务

- 支持 `.xlsx` 读取与 sheet 校验
- DSL 解析：
  - `preconditions`
  - `effects`
  - `resource_reqs`
- 跨表校验：
  - `feature_key` 引用合法
  - `resource_type` 引用合法
- 正式导入时单事务执行，任意异常回滚

### D：前端导入入口

- 在 `DataManagement` 顶部提供：
  - `下载模板`
  - `导入 Excel`
- 导入弹窗流程：
  1. 上传文件
  2. 预校验（dry_run）
  3. 展示预估 create/update 与错误明细
  4. 确认正式导入

### E：模板交付

- 提供静态模板文件（列头英文）。
- `instructions` sheet 提供中文填写说明与 DSL 示例。

### F：回归验证

- 成功场景：三类数据均可导入并可在页面查看结果。
- 失败场景：任一错误触发整批回滚。
- 错误提示：前端可展示 sheet/row/field/message。

### G：文档回写

- 本票子任务完成后 `[ ] -> [✅]`
- `docs/STATE_V0.3.md` 同步更新 T12 进度

---

## 验收标准

```text
✅ 单文件导入覆盖 StateFeatureDef + Resource + OpRule
✅ dry_run 输出准确校验结果与 create/update 预估
✅ strict_upsert 语义正确（存在更新，不存在创建）
✅ 任意错误整批回滚，无部分成功
✅ instructions 中文说明可独立指导业务填写
```

---

## 本次不做（明确排除）

- 不导入 machine_type / machine / state
- 不导入全局 feature_definition
- 不支持 CSV
- 不支持部分成功（partial success）
- 不做异步导入任务队列

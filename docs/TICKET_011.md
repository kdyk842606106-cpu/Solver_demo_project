# TICKET-011: V0.3 STEP 1-1 解释数据结构定义（Planner/Scheduler 统一）

> 对应版本：V0.3
> 对应 STEP：STEP 1（求解可解释性深化）
> 前置依赖：`docs/STATE_V0.3.md` 已创建
> 预估工作量：1 次对话
> 当前状态：暂缓（等待 TICKET-012 主数据导入专项完成后恢复）

---

## 本次任务范围（只做这些）

定义并落地“解释数据结构”的最小可用契约，覆盖 Planner 与 Scheduler 两段链路，确保：

1. 后端返回结构有统一、可扩展的 explain 字段
2. 现有 `/api/v1/solve` 响应保持向后兼容
3. 前端可在不重构页面前提下消费最小解释信息

**不做**：不实现完整前端解释 UI、不引入新求解策略、不修改业务规则语义。

---

## 子任务清单

```text
[ ] A  盘点当前 solve 响应与前端消费点
[ ] B  设计 explain 顶层结构与字段命名
[ ] C  在 schema 与 solve 响应中落地可选 explain 字段
[ ] D  添加最小回归验证（向后兼容 + 字段存在性）
[ ] E  更新文档（STATE/TICKET 勾选）
```

---

## 详细要求

### A：盘点现状

- 明确当前 `solve` 响应中哪些字段可复用为解释来源（如 `state_delta`、`critical_path`、任务依赖等）。
- 明确前端 `SolvePage` 目前可承载的最小解释入口（例如“解释摘要”文本/标签区）。

### B：设计 explain 结构

- 推荐结构（可调整但需一致）：

```json
{
  "explain": {
    "planner": {
      "delta_summary": [],
      "rule_matches": []
    },
    "scheduler": {
      "objective_summary": [],
      "critical_path_basis": []
    }
  }
}
```

- 要求：
  - 字段全部可选
  - 不影响现有客户端解析
  - 保持后续可扩展性

### C：后端落地

- 在 `schemas.py` 增加 explain 对应 schema（可选字段）。
- 在 `/api/v1/solve` 响应构造中写入最小 explain 内容（允许先以摘要为主）。

### D：最小验证

- 验证旧字段不受影响。
- 验证 explain 缺省与存在两种路径都能正常返回。

### E：文档同步

- 将本票已完成子任务在本文件中 `[ ] -> [✅]`。
- 在 `docs/STATE_V0.3.md` 更新对应 STEP 进度。

---

## 验收标准

```text
✅ /api/v1/solve 响应新增可选 explain 字段
✅ 未传 explain 消费逻辑时前端仍可正常使用（向后兼容）
✅ explain 字段命名与层次满足可扩展要求
✅ STATE/TICKET 状态同步更新
```

---

## 本次不做（明确排除）

- 不做完整解释可视化页面
- 不变更阻塞策略 A/B/AB 语义
- 不变更多目标求解逻辑
- 不引入 A* 搜索实现

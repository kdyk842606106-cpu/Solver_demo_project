# Solver Demo × 半导体制程调度 — 实现计划
> **For agent:** 使用 Section 4 或 Section 5 执行本计划
> **Goal:** 把用户提供的27个OPS活动表格，通过对话式AI自动写入Solver数据库，调用原生API得到排程结果，返回给人可读的结果
> **Architecture:** 用户输入 → AI解析为 op_rules + states → 调用 POST /solve → 结果审核 → 飞书返回
> **Tech Stack:** Solver Demo (FastAPI + OR-Tools CP-SAT), 飞书消息, Python 临时数据写入

## 背景

用户要在飞书里和AI对话，输入一个半导体制程装配计划（27个活动OPS，强依赖链约束），AI自动：
1. 解析表格 → 生成 op_rule 集合（27条）
2. 构建 DAG 依赖图
3. 写入 Solver 数据库（临时）
4. 调用 `POST /api/v1/solve`
5. 审核结果后通过飞书发回

**限制**：Demo 精度，人员池约束简化为单容量（演示用）。

---

## 执行前提

- 后端必须先在 Windows 上跑起来（用户手动启动）
- Docker PostgreSQL 必须可连（`solver_postgres` on 5432）

---

## 任务列表

### Task 1: 准备数据解析脚本
**文件：**
- 创建: `scripts/ops_import.py`

**Step 1:** 创建脚本文件，解析用户提供的表格，生成 op_rule 数据结构
- 27个 OPS 活动
- 每个活动包含：code, name, duration_min, preconditions (强依赖), effects (完成标记)
- 强依赖转为 op_rule_precond（通过中间"已完成"标记）

**Step 2:** 运行脚本验证能解析用户原始数据（提供测试数据）

---

### Task 2: 创建数据库写入函数
**文件：**
- 创建: `scripts/ops_import.py` 扩展

**Step 1:** 写入 `op_rule` 表（27条）
**Step 2:** 写入 `op_rule_precond` 表（强依赖关系）
**Step 3:** 写入 `op_rule_effect` 表（标记活动完成）
**Step 4:** 创建 current_state（全部 OPS pending）和 target_state（全部 OPS done）
**Step 5:** 创建 `machine_type` 和 `machine`（如果不存在，id=1）

**Step 6:** 验证数据库写入成功（查询 op_rule count = 27）

---

### Task 3: 调用 API + 获取结果
**文件：**
- 创建: `scripts/ops_query.py`

**Step 1:** 调用 `POST /api/v1/solve`，body：
```json
{
  "machine_id": 1,
  "current_state_id": <current_state_id>,
  "target_state_id": <target_state_id>,
  "objective": "minimize_makespan"
}
```

**Step 2:** 获取 `schedule.tasks` 列表

**Step 3:** 格式化为可读甘特图（活动名 / 开始时间 / 结束时间 / 资源）

---

### Task 4: 审核 + 飞书发回
**文件：**
- 修改: `scripts/ops_query.py` 添加审核逻辑

**Step 1:** 检查 makespan 是否合理（最小化工时）
**Step 2:** 检查关键路径（最长依赖链）
**Step 3:** 检查是否有资源冲突（吊装钩同时占用）
**Step 4:** 通过 `message` 工具发送飞书结果

---

### Task 5: 数据清理（可选）
**文件：**
- 创建: `scripts/ops_cleanup.py`

**Step 1:** 删除本次创建的 op_rules、states（跑完即删）

---

## 执行流程

```
用户发表格 → AI解析 → 写入DB → 调用/solve → 审核结果 → 发回飞书
```

每步完成后汇报，用户确认后再继续。

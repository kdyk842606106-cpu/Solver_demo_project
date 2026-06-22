# MS010 Scheduler 多资源约束修复 — 设计方案
> **日期**: 2026-05-16
> **作者**: OpenClaw Agent
> **关联**: MS010 机台计划报告生成过程中发现的 scheduler 资源分配缺陷
> **状态**: 待审批

---

## 1. 问题根因

### 1.1 现象

在生成 MS010 排程报告时，发现 Activity Details 中部分工序没有分配 `WORKER` 资源：

| 工序 | 应有资源需求 | scheduler 实际分配 | 缺失 |
|------|-------------|-------------------|------|
| OPS011 光源组件对准 | WORKER x4 | `[]` | ❌ WORKER |
| OPS017 顶部计量框架安装 | WORKER x4, 行吊 x1, SPACE_UP x1 | `['行吊', 'SPACE_UP']` | ❌ WORKER |
| OPS012 动态气体开关安装 | WORKER x3, SPACE_DOWN x1 | `['SPACE_DOWN']` | ❌ WORKER |
| OPS018 中框公共线缆布线 | WORKER x5, SPACE_OUT x1, SPACE_UP x1 | `['SPACE_OUT', 'SPACE_UP']` | ❌ WORKER |
| OPS007 中框真空系统前级管路安装 | WORKER x3, SPACE_OUT x1 | `['SPACE_OUT']` | ❌ WORKER |
| OPS010 光源主体对准 | WORKER x5, SPACE_LIGHT x1 | `['SPACE_LIGHT']` | ❌ WORKER |
| OPS016 机械臂1推入恢复 | WORKER x3, SPACE_OUT x1 | `['SPACE_OUT']` | ❌ WORKER |

总计 **7 个工序** 缺失 WORKER 资源分配，但 CP-SAT 排程结果是正确的（时间/顺序无误）。

### 1.2 根因分析

问题贯穿 scheduler 的 **loader → model → solver** 三层：

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   loader    │ ──▶ │    model    │ ──▶ │   solver    │
│  (数据加载)  │     │ (CP-SAT建模)│     │ (求解+分配)  │
└─────────────┘     └─────────────┘     └─────────────┘
```

#### Layer 1: loader.py — 只保留第一个资源需求

```python
# app/core/scheduler/loader.py

class StepData:
    resource_type: str      # ← 只存一个！
    resource_qty: int       # ← 只存一个！

# load_rag() 中：
for req in rule.resource_reqs:
    if req.is_required:
        resource_type = req.resource_type   # ← 取第一个就 break
        resource_qty = req.quantity
        break                               # ← 遗漏其余资源！
```

**后果**: CP-SAT 模型不知道工序还需要其他资源。

#### Layer 2: model.py — 只建模单一资源

```python
# app/core/scheduler/model.py

for res_type in resource_type_set:
    for step in rag_data.steps:
        if step.resource_type == res_type:  # ← 只匹配那个"第一个"资源
            intervals.append(tv.interval)
            demands.append(step.resource_qty)
```

**后果**: CP-SAT 的 `add_cumulative` 约束只针对单一资源类型，多资源工序的其他资源需求被忽略。

#### Layer 3: solver.py — _assign_resources 逻辑错误

```python
# app/core/scheduler/solver.py

def _assign_resources(tasks, resources):
    for task in tasks:
        pool = pools.get(task.resource_type, [])   # ← 只查那个"第一个"资源
        for res in pool:
            if _is_resource_free(...):
                task.resources.append({...})       # ← 只分配一个资源实例
                busy[res.id].append(...)
                break
```

**双重问题**:
1. 只遍历 `task.resource_type`（单一资源），不遍历全部需求
2. WORKER-POOL 是容量型资源（capacity=10），但 `_is_resource_free` 把它当作单位资源（capacity=1）检查——一旦一个任务"占用"，后续任务都分配不到

### 1.3 为什么 CP-SAT 排程结果仍正确？

因为当前 MS010 数据中：
- 第一个资源恰好都是 WORKER（按 `op_rule_resource_req` 的插入顺序）
- 所以 CP-SAT 的 `add_cumulative` 约束是在 WORKER 上
- WORKER-POOL 容量=10，最大并发需求=10，恰好满足
- 空间资源（SPACE_R/L/LIGHT/OUT/DOWN/FRONT/UP）没有容量约束被建模，但各自只有一个实例，实际也没有冲突

**排程是对的，但资源分配数据不完整。**

---

## 2. 修改范围

### 2.1 修改文件清单

| # | 文件 | 修改内容 | 复杂度 |
|---|------|---------|--------|
| 1 | `app/core/scheduler/loader.py` | `StepData` 改为多资源列表；`load_rag()` 加载全部 `resource_reqs` | 中 |
| 2 | `app/core/scheduler/model.py` | `build_model()` 对所有资源类型分别添加 `add_cumulative` | 中 |
| 3 | `app/core/scheduler/solver.py` | `_assign_resources()` 遍历全部资源需求；正确处理容量型资源 | 高 |
| 4 | `app/core/scheduler/schedule_graph.py` | 确保 `resources` 数组格式兼容（如有需要） | 低 |

### 2.2 不修改范围

- ❌ `app/api/` — API 接口层，JSON 输入输出格式不变
- ❌ `app/db/models.py` — 数据库模型正确，无需改动
- ❌ `app/db/schemas.py` — schema 不变
- ❌ 前端代码 — 只改后端数据生成
- ❌ 现有 seed SQL — 数据正确

---

## 3. 详细设计

### 3.1 loader.py — 加载全部资源需求

**当前 `StepData`**:
```python
@dataclass
class StepData:
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    duration_min: int
    resource_type: str        # ← 单一
    resource_qty: int         # ← 单一
```

**改为**:
```python
@dataclass
class StepData:
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    duration_min: int
    resource_reqs: list[dict]  # ← [{"type": "WORKER", "qty": 4}, ...]
```

**`load_rag()` 修改**:
```python
# 原：只取第一个 required resource
# 改为：收集所有 required resources
resource_reqs = []
for req in rule.resource_reqs:
    if req.is_required:
        resource_reqs.append({
            "resource_type": req.resource_type,
            "quantity": req.quantity,
        })
```

### 3.2 model.py — 多资源约束建模

**当前 `build_model()`**:
```python
for res_type in resource_type_set:
    capacity = get_resource_capacity(resources, res_type)
    for step in rag_data.steps:
        if step.resource_type == res_type:   # ← 只匹配单一
            ...
```

**改为**:
```python
# 遍历每个工序的所有资源需求
for step in rag_data.steps:
    for req in step.resource_reqs:
        res_type = req["resource_type"]
        qty = req["quantity"]
        capacity = get_resource_capacity(resources, res_type)
        if capacity <= 0:
            capacity = 1
        
        # 按资源类型分组收集 intervals
        # 然后对每个资源类型 add_cumulative
```

### 3.3 solver.py — 正确分配多资源

**当前 `_assign_resources()`**:
```python
def _assign_resources(tasks, resources):
    for task in tasks:
        if task.resource_type == "NONE":
            continue
        pool = pools.get(task.resource_type, [])
        for res in pool:
            if _is_resource_free(busy[res.id], task.start_min, task.end_min):
                task.resources.append({"resource_id": res.id, "resource_code": res.code})
                busy[res.id].append((task.start_min, task.end_min))
                break
```

**改为**:
```python
def _assign_resources(tasks, resources):
    # 按资源类型分池
    pools: dict[str, list[ResourceData]] = {}
    for r in resources:
        pools.setdefault(r.resource_type, []).append(r)
    
    # 记录每个资源实例的占用区间
    busy: dict[int, list[tuple[int, int]]] = {r.id: [] for r in resources}
    
    for task in tasks:
        # 遍历该工序的所有资源需求（而非单一 resource_type）
        for req in getattr(task, "resource_reqs", []):
            res_type = req["resource_type"]
            qty_needed = req["quantity"]
            
            if res_type == "NONE":
                continue
            
            pool = pools.get(res_type, [])
            assigned_qty = 0
            
            for res in pool:
                if res.capacity > 1:
                    # 容量型资源：允许多个并发，按"已用容量"而非"是否空闲"检查
                    used_capacity = _calc_used_capacity(
                        busy[res.id], task.start_min, task.end_min
                    )
                    if used_capacity + qty_needed <= res.capacity:
                        task.resources.append({
                            "resource_id": res.id,
                            "resource_code": res.code,
                            "resource_type": res_type,
                        })
                        busy[res.id].append((task.start_min, task.end_min, qty_needed))
                        assigned_qty += qty_needed
                        break
                else:
                    # 单位资源：传统空闲检查
                    if _is_resource_free(busy[res.id], task.start_min, task.end_min):
                        task.resources.append({
                            "resource_id": res.id,
                            "resource_code": res.code,
                            "resource_type": res_type,
                        })
                        busy[res.id].append((task.start_min, task.end_min))
                        assigned_qty += 1
                        break
```

---

## 4. 准出条件（Definition of Done）

### 4.1 功能准出

- [ ] 所有 27 个工序的 `resources` 数组包含完整资源分配（与 `resource_reqs` 一致）
- [ ] OPS011（仅 WORKER）能正确分配到 WORKER-POOL
- [ ] OPS017（WORKER+行吊+SPACE_UP）三种资源都出现在 `resources` 中
- [ ] 并发 WORKER 使用量不超过容量 10（CP-SAT 约束生效）
- [ ] 并发 SPACE_OUT 使用量不超过容量 1（如有多个任务同时需要 SPACE_OUT，应串行）

### 4.2 验证准出

- [ ] 重新运行 MS010 求解，检查返回 JSON 中每个 task 的 `resources` 与 `resource_reqs` 匹配
- [ ] 并发检查脚本：任一时刻使用 WORKER 的任务数 ≤ 10
- [ ] 并发检查脚本：任一时刻使用 SPACE_OUT 的任务数 ≤ 1
- [ ] 现有测试通过（如有 scheduler 相关测试）
- [ ] `solver_demo.db` / PostgreSQL 中的数据未受影响

### 4.3 报告准出

- [ ] HTML 报告中 Activity Details 所有工序都显示完整资源徽章
- [ ] 不再有虚线红色边框标记（表示未分配）

### 4.4 代码质量准出

- [ ] 向后兼容：API JSON 输出格式不变
- [ ] 新增代码有注释说明多资源处理逻辑
- [ ] 代码审查通过（self-review + optional peer review）

---

## 5. 风险评估与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| CP-SAT 模型复杂度增加 | 求解时间略微增加 | 资源类型数有限（MS010 只有 7 种），OR-Tools 原生支持多 cumulative 约束 |
| 向后兼容破坏 | API 消费者受影响 | `resources` 数组结构不变（仍是 `{resource_id, resource_code}` 列表），仅内容完整 |
| 容量型资源逻辑错误 | WORKER-POOL 仍分配失败 | 单独验证 WORKER-POOL（id=85, capacity=10）的分配逻辑 |
| 排程结果变化 | 与历史最优解不一致 | 当前 CP-SAT 已正确建模 WORKER 约束，修复后只是补充其他资源和分配数据，不应改变 makespan |

---

## 6. 执行建议

### 方案对比

| 方案 | 描述 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **A. 最小修复** | 只改 `_assign_resources`，让它遍历 `resource_reqs` 而非 `resource_type` | 改动小，风险低，2 小时完成 | loader/model 仍只处理单一资源，CP-SAT 约束不完整，后续扩展受限 | ★★☆ |
| **B. 完整修复** | 改 loader → model → solver 三层，支持多资源全程贯通 | 架构正确，后续支持任意多资源场景（如增加人力、借用设备） | 改动面较大，需验证各层兼容 | ★★★ |

**推荐：方案 B（完整修复）**

理由：
1. 当前数据库模型和 seed 数据已经设计为 1:N 资源需求关系
2. 只修 solver 层面是 workaround，loader/model 的数据缺失会导致 CP-SAT 约束不完整（虽然当前恰好没出问题）
3. 完整修复后，后续支持"增加人力""临时借用设备"等场景自然扩展

### 执行顺序

1. **loader.py** — 先改数据结构，确保上游数据正确
2. **model.py** — 再改 CP-SAT 建模，确保约束完整
3. **solver.py** — 最后改资源分配，确保输出正确
4. **验证** — 运行 MS010 求解，对比修复前后 JSON

---

## 7. 附录

### 7.1 当前资源定义（来自数据库）

| ID | Code | Name | Type | Capacity |
|----|------|------|------|----------|
| 85 | WORKER-POOL | 工人资源池 | WORKER | 10 |
| 4 | R1 | 行车1 | 行吊 | 1 |
| 5 | R2 | 行车2 | 行吊 | 0 (unavailable) |
| 9001 | SPACE_R | 主机台右侧维护位 | SPACE_R | 1 |
| 9002 | SPACE_L | 主机台左侧维护位 | SPACE_L | 1 |
| 9003 | SPACE_DOWN | 主机台中部-下腔内 | SPACE_DOWN | 1 |
| 9004 | SPACE_LIGHT | 光源工作位 | SPACE_LIGHT | 1 |
| 9005 | SPACE_OUT | 主机台中部-腔外 | SPACE_OUT | 1 |
| 9006 | SPACE_FRONT | 主机台前部 | SPACE_FRONT | 1 |
| 9007 | SPACE_UP | 主机台中部-上腔内 | SPACE_UP | 1 |

### 7.2 当前有问题的工序及其资源需求

| 工序 | 资源需求 (DB) | 当前 scheduler 分配 | 应有分配 |
|------|--------------|-------------------|---------|
| OPS011 | WORKER x4 | `[]` | WORKER-POOL |
| OPS017 | WORKER x4, 行吊 x1, SPACE_UP x1 | `['行吊', 'SPACE_UP']` | WORKER-POOL, R1, SPACE_UP |
| OPS012 | WORKER x3, SPACE_DOWN x1 | `['SPACE_DOWN']` | WORKER-POOL, SPACE_DOWN |
| OPS018 | WORKER x5, SPACE_OUT x1, SPACE_UP x1 | `['SPACE_OUT', 'SPACE_UP']` | WORKER-POOL, SPACE_OUT, SPACE_UP |
| OPS007 | WORKER x3, SPACE_OUT x1 | `['SPACE_OUT']` | WORKER-POOL, SPACE_OUT |
| OPS010 | WORKER x5, SPACE_LIGHT x1 | `['SPACE_LIGHT']` | WORKER-POOL, SPACE_LIGHT |
| OPS016 | WORKER x3, SPACE_OUT x1 | `['SPACE_OUT']` | WORKER-POOL, SPACE_OUT |

---

*文档生成时间: 2026-05-16 10:43 CST*
*下一步: 等待用户审批，进入 Writing Plans 阶段*

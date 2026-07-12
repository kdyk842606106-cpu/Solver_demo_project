# TICKET-010: 甘特图行标题升级为“编号 + 活动编码 + 活动名称”

> 对应问题：前端 Gantt 图当前仅展示活动编码，可读性不足
> 对应范围：Solve 结果任务显示增强（前后端联动，小范围接口补充）
> 前置依赖：TICKET-009 已完成
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

将排程 Gantt 图的行标题从当前的“活动编码”升级为：

- `步骤编号 + 活动编码 + 活动名称`

目标示例：

- `1. OP_CALIBRATE - 校准`
- `2. OP_REPAIR_HW - 硬件维修`

同时保证：

- 普通模式和对比模式的标题风格尽量一致
- tooltip 与行标题语义一致
- 任务明细表与 Gantt 图展示信息一致
- 当活动名称缺失时，自动降级为 `编号 + 活动编码`

**不做**：不改求解算法、不改阻塞处理逻辑、不重做 Gantt 图交互、不改版本 diff 核心算法。

---

## 当前现状

### 前端现状

当前 `frontend/src/components/GanttChart.vue` 中：

- 普通模式 Y 轴标题来自 `op_rule_code`
- 对比模式 Y 轴标题来自 `op_code`
- tooltip 也直接复用该标题字符串

因此当前用户看到的是：

- `OP_CALIBRATE`
- `OP_REPAIR_HW`

而不是更易读的：

- `1. OP_CALIBRATE - 校准`

### 后端现状

当前 `POST /api/v1/solve` 返回的 `schedule.tasks[]` 已包含：

- `step_order`
- `op_rule_id`
- `op_rule_code`
- `start_min` / `end_min` / `duration_min`
- `resources` / `predecessors` / `not_before` / `step_role`
- `op_rule_name`（活动名称，允许为 `null`）

### 结论

本票已完成：任务项显示名称数据已补齐，前端普通模式与对比模式展示格式已统一，并支持名称缺失降级。

---

## 子任务清单

```text
[✅] A  后端任务项补充 `op_rule_name`
[✅] B  普通模式 Gantt 行标题升级
[✅] C  对比模式标题与 tooltip 同步升级
[✅] D  任务明细表补充活动名称列
[✅] E  回归验证普通模式 / 对比模式 / 名称缺失降级
```

---

## 一、各子任务详细要求

### A：后端任务项补充 `op_rule_name`

目标：

- 让 `POST /api/v1/solve` 返回的 `schedule.tasks[]` 中带上活动名称字段
- 推荐字段名：`op_rule_name`

涉及文件：

- `app/core/scheduler/loader.py`
- `app/core/scheduler/solver.py`
- `app/api/v1/solve.py`
- `app/db/schemas.py`

实施要求：

1. `ScheduleTaskItem` / `tasks_response` 增加可选字段 `op_rule_name`
2. 名称来源必须是 `OpRule.name`，不得在前端硬编码映射
3. 保持原有 `op_rule_code` 字段不变，避免破坏兼容性
4. 若规则名称为空，允许返回 `null`

建议实现链路：

1. 在 `scheduler.loader` 的 `StepData` 中补 `op_rule_name`
2. 在 `scheduler.solver` 的 `TaskResult` 中向下传递 `op_rule_name`
3. 在 `solve.py` 构造 `tasks_response` 时写入 `op_rule_name`
4. 在 `schemas.py` 中为任务项响应模型补字段

验收标准：

- `schedule.tasks[*].op_rule_name` 可在求解接口响应中看到
- 不影响现有依赖 `op_rule_code` 的前端逻辑

---

### B：普通模式 Gantt 行标题升级

目标：

- 普通模式下，Y 轴标题从“仅活动编码”升级为“编号 + 编码 + 名称”

涉及文件：

- `frontend/src/components/GanttChart.vue`

展示规则：

1. 优先格式：`{step_order}. {op_rule_code} - {op_rule_name}`
2. 名称缺失降级：`{step_order}. {op_rule_code}`
3. 若为关键路径，保留当前关键路径标识逻辑

说明：

- 本票不改变 bar 颜色、step_role 样式、关键路径高亮方式
- 只增强标题字符串拼装逻辑

验收标准：

- 普通模式 Y 轴标题显示新格式
- 关键路径标识仍然正确

---

### C：对比模式标题与 tooltip 同步升级

目标：

- 对比模式中，标题和 tooltip 也采用同类格式，不再只显示裸 `op_code`

涉及文件：

- `frontend/src/components/GanttChart.vue`

展示规则：

1. 若 diff 数据可直接得到编号和名称，则格式为：
   - `[新增] {step_order}. {op_code} - {op_name}`
2. 若 diff 数据当前没有完整名称字段，则至少做到：
   - `[新增] {step_order}. {op_code}`
3. 若 diff 数据中没有可靠 `step_order`，允许本票阶段对比模式先使用：
   - `[新增] {op_code} - {op_name}`
   - 或 `[新增] {op_code}`
4. tooltip 文案必须与标题使用同一显示规则，避免信息不一致

约束：

- 不重构 `GET /plans/{id}/diff/{other_id}` 核心结构
- 若补名称字段成本很低，可做最小增强；否则允许先只提升普通模式，diff 模式保留降级兼容

验收标准：

- 对比模式标题和 tooltip 不再只显示单一裸编码
- 对比模式在字段缺失时能正常降级，不报错

---

### D：任务明细表补充活动名称列

目标：

- 让任务明细表与 Gantt 图使用一致的信息结构

涉及文件：

- `frontend/src/views/SolvePage/index.vue`

实施要求：

1. 在“活动编码”旁新增“活动名称”列
2. 若 `op_rule_name` 为空，显示 `—`
3. 不影响现有列：
   - 角色
   - not_before
   - 资源
   - 阻塞按钮

验收标准：

- 表格中可看到活动名称
- 表格与 Gantt 图展示信息一致

---

### E：回归验证普通模式 / 对比模式 / 名称缺失降级

目标：

- 确认本票属于展示增强，不引入接口或渲染回归

验证范围：

1. 普通模式：
   - Y 轴标题正确
   - tooltip 正确
   - 表格正确
2. 对比模式：
   - 标题正确或按设计降级正确
   - `[新增]` 标识保留
   - tooltip 正确
3. 降级场景：
   - `op_rule_name = null/空` 时，显示 `编号 + 编码`
4. 兼容性：
   - 不影响关键路径高亮
   - 不影响 step_role 颜色
   - 不影响阻塞弹窗读取 task 数据

建议验证方式：

1. 手工跑 1 个普通 solve 结果页面
2. 手工切换 1 个 diff 视图
3. 若本地有测试基础，可补最小前端回归或接口断言

验收标准：

- 普通模式和对比模式均可正常打开
- 无前端控制台错误
- 无因字段缺失导致的页面空白或 tooltip 异常

---

## 二、字段与展示格式约定

### 普通任务项建议结构

```json
{
  "step_order": 1,
  "op_rule_id": 101,
  "op_rule_code": "OP_CALIBRATE",
  "op_rule_name": "校准",
  "start_min": 0,
  "end_min": 30,
  "duration_min": 30
}
```

### 普通模式标题格式

```text
1. OP_CALIBRATE - 校准
```

### 普通模式降级格式

```text
1. OP_CALIBRATE
```

### 对比模式建议格式

若 diff 数据可提供完整字段：

```text
[新增] 2. OP_REPAIR_HW - 硬件维修
```

若 diff 数据不完整，则允许降级为：

```text
[新增] OP_REPAIR_HW
```

---

## 三、实现注意事项

### 1. 不要只在前端硬拼名称映射

活动名称必须来自后端真实规则数据，不能在前端按编码写死映射表。

### 2. 普通模式优先落地完整展示

本票的核心价值在普通 solve 结果页面，因此：

- 普通模式必须完整支持 `编号 + 编码 + 名称`
- diff 模式允许最小兼容增强，但不能拖大本票范围

### 3. 保持编码可见

本票不建议把行标题直接改成“仅名称”，必须保留 `op_rule_code`，原因：

- 便于规则库排查
- 便于与后端日志、测试、API 响应对照
- 避免名称重复时失去定位能力

### 4. 不修改求解语义

本票只能增强显示字段，不改变：

- 排程计算逻辑
- critical path 计算逻辑
- diff 算法
- blockage 流程

---

## 四、影响面分析

### 后端

小范围接口增强：

- 任务项增加 `op_rule_name`
- 不改求解过程，不改排程算法

### 前端

中小范围展示增强：

- Gantt 行标题
- tooltip
- 任务明细表

### 测试

以回归验证为主：

- 重点防止字段缺失导致前端报错
- 重点检查普通模式和 diff 模式兼容性

---

## 五、验收标准

```text
✅ 普通模式 Gantt 行标题显示“编号 + 编码 + 名称”
✅ 普通模式名称缺失时自动降级为“编号 + 编码”
✅ tooltip 同步展示增强后的标题信息
✅ 任务明细表新增活动名称列
✅ 对比模式标题与 tooltip 得到最小一致性增强
✅ 不影响关键路径、step_role、阻塞按钮、diff 模式打开
✅ 不改求解算法、不改阻塞处理逻辑
```

---

## 六、本次不做（明确排除）

| 排除项 | 原因 |
|--------|------|
| 求解算法改造 | 本票仅做展示增强 |
| Gantt 图交互重构 | 不涉及缩放、拖拽、分组等增强 |
| 阻塞流程改造 | 与本票目标无关 |
| diff API 全面重构 | 只允许最小字段增强，不做大范围改造 |
| 仅显示活动名称、隐藏编码 | 会降低问题排查和规则定位能力 |

---

## 七、建议执行顺序

1. 后端先补 `op_rule_name` 到普通 solve 响应任务项
2. 前端普通模式 Gantt 标题与 tooltip 改造
3. 任务表补活动名称列
4. 评估 diff 模式是否可低成本补名称；如不能，则做兼容降级
5. 手工回归普通模式和 diff 模式

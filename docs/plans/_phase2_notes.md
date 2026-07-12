# Phase 2: 模块交互与数据流梳理笔记

> 生成时间：2026-04-25
> 基于 V0.3 代码库完整读取
> 读取文件数：19（含后端核心、协议文档、前端组件）

---

## 一、端到端求解链路

### 1.1 完整流程图

```
POST /api/v1/solve
  │
  ├─→ [阶段1] 输入校验
  │     ├─ machine_id 存在性校验
  │     ├─ current_state_id 存在性 + 归属校验
  │     ├─ target_state_id 存在性 + 归属校验
  │     ├─ 阻塞约束解析（strategy / strategy_a / strategy_b / blocked_step_id / blocked_op_rule_id）
  │     └─ 创建 solve_request 记录，status="running"
  │     输入：SolveRequestCreate (Pydantic)
  │     输出：solve_request.id, replan_reason
  │     决策点：初次求解 vs 重排（parent_plan_id 是否非空）
  │     人工介入点：无（纯校验）
  │
  ├─→ [阶段2] Planner.build_rag()
  │     ├─ load_state(current_state_id) → dict[str, str]
  │     ├─ 应用 current_state_override（策略B时注入 blockage_reason）
  │     ├─ load_state(target_state_id) → dict[str, str]
  │     ├─ is_goal() 检查（已在目标状态则返回 no_solution）
  │     ├─ compute_state_delta() → {(feature_key): (current_val, target_val)}
  │     ├─ 加载 machine_type_id → 加载 feature_defs → 加载 active rules
  │     ├─ 为每个 delta 匹配候选工序（find_ops_for_delta）
  │     │   数字类型特征走 plan_exact_numeric_feature() 链式规划
  │     ├─ 优先选择 precondition 已满足的候选；否则选最短 duration
  │     ├─ 去重（同一工序可修复多个 delta）
  │     ├─ 策略B时：若 include_repair=true，额外加载 is_repair=True 且 precondition 已满足的工序
  │     ├─ 递归补齐前置依赖（worklist 循环，max_ops=50 安全上限）
  │     │   对每个 precondition：
  │     │     ├─ 当前状态已满足 → 跳过
  │     │     ├─ 在 needed_ops 中找 provider → 建边
  │     │     └─ 未找到 → 在全量规则中找 intermediate → 加入 worklist → 建边
  │     ├─ 合并 numeric plan 的链式步骤（带 predecessor_instance_ids）
  │     ├─ has_cycle() DFS 环检测
  │     └─ → 返回 RAG(nodes + edges)
  │     输入：current_state_id, target_state_id, current_state_override, include_repair
  │     输出：PlanResult(status, rag, error_message)
  │     关键决策点：
  │       - 多候选时选"precondition已满足"还是"最短duration"
  │       - 中间工序选择策略（sat vs shortest）
  │     人工介入点：
  │       ★ 规则库维护（op_rule / precond / effect / resource_req 的完整性和正确性）
  │       ★ 策略B时 blockage_reason 的取值必须匹配某条维修序列的 precondition
  │
  ├─→ [阶段3] 持久化候选计划
  │     ├─ save_candidate_plan(rag, solve_request_id)
  │     │   创建 candidate_plan（version 递增，parent_plan_id, replan_reason）
  │     │   批量创建 candidate_plan_step（step_order = RAGNode.id, predecessor_ids）
  │     └─ → 返回 plan_id
  │     输入：RAG, solve_request_id, version, parent_plan_id, replan_reason
  │     输出：candidate_plan.id
  │     人工介入点：无
  │
  ├─→ [阶段4] 应用策略A约束（not_before）
  │     ├─ 若 strategy ∈ (A, AB)：
  │     │   解析 blocked_step（优先 blocked_step_id，回退 blocked_op_rule_id）
  │     │   写入 blocked_step.not_before = strategy_a_offset
  │     ├─ 创建 blockage_event 记录
  │     └─ flush()
  │     输入：plan_id, blocked_step_id/op_rule_id, strategy_a_offset
  │     输出：new_blocked_step_id, blockage_event.id
  │     关键决策点：
  │       - 当同个 op_rule 出现多次时，blocked_step_id 必须精确指定（否则抛 AMBIGUOUS_BLOCKED_STEP）
  │     人工介入点：
  │       ★ 计划师手动选择被阻塞步骤和 not_before 时间
  │
  ├─→ [阶段5] Scheduler.solve_schedule()
  │     ├─ load_rag(plan_id) → RagData(steps[], edges[])
  │     ├─ load_resources(resource_types) → ResourceData[]
  │     ├─ build_model() —— 构建 CP-SAT 模型：
  │     │   ├─ 每个任务 → start / end / interval IntVar
  │     │   ├─ horizon = sum(duration) + max_not_before
  │     │   ├─ precedence 约束（edges → start_j >= end_i）
  │     │   ├─ cumulative 容量约束（按 resource_type 分组）
  │     │   ├─ makespan = max(end_i)
  │     │   ├─ not_before 约束（start >= not_before）
  │     │   └─ 目标函数：ObjectiveRegistry.apply_all()（默认 minimize_makespan）
  │     ├─ CpSolver.Solve()，max_time_in_seconds=30.0
  │     ├─ 提取结果 → TaskResult[]（含 start_min, end_min, duration_min, predecessors）
  │     ├─ _assign_resources() —— 贪心分配首个空闲资源实例
  │     ├─ _detect_actual_parallel() —— 时间区间重叠检测
  │     └─ → 返回 ScheduleResultData
  │     输入：candidate_plan_id, objectives, max_time_seconds=30
  │     输出：ScheduleResultData(status, makespan, tasks, parallel_groups, solver_stats, error_message)
  │     关键决策点：
  │       - 求解时间上限（30秒硬编码）
  │       - 资源容量不足时回退到 1（容错策略）
  │       - 资源分配贪心策略（首个空闲，非最优）
  │     人工介入点：
  │       ★ 资源池配置（resource 表的 capacity / is_available）
  │       ★ 求解超时阈值调整（需改代码）
  │
  ├─→ [阶段6] 持久化排程结果
  │     ├─ save_schedule_result() → schedule_result 记录
  │     ├─ compute_step_role_diff(plan_id, parent_plan_id) —— 对比父计划标注步骤角色
  │     │   写入 step_role ∈ {normal, repair, pulled_forward, delayed}
  │     └─ flush()
  │     输入：ScheduleResultData, solve_request_id, plan_id
  │     输出：schedule_result.id
  │     人工介入点：无
  │
  ├─→ [阶段7] 响应组装
  │     ├─ 查询 plan_steps（含 not_before, step_role）
 │     ├─ 组装 tasks_response（含 step_id, op_rule_id, code, name, timing, resources, not_before, step_role）
  │     ├─ 计算 critical_path（从 makespan 终点反向回溯 tight edges）
  │     ├─ 组装 state_delta（当前→目标特征变化列表）
  │     ├─ 更新 solve_request.status="done", solved_at
  │     └─ commit()
  │     输出：SolveResponse（含 solve_request_id, status, candidate_plan_id, state_delta, critical_path, schedule）
  │
  └─→ 返回 HTTP 200（无论成功失败，失败时 status="failed" + error_code）
```

### 1.2 各阶段数据结构

| 阶段 | 输入结构 | 输出结构 | 持久化表 |
|------|---------|---------|---------|
| 输入校验 | `SolveRequestCreate` (Pydantic) | `solve_request` ORM 对象 | `solve_request` |
| Planner | `current_state_id`, `target_state_id`, `current_state_override` | `PlanResult` (dataclass: status, rag, error_message) | 无（纯内存） |
| 持久化计划 | `RAG` (nodes + edges) | `candidate_plan.id` | `candidate_plan`, `candidate_plan_step` |
| 策略A约束 | `strategy_a.not_before_offset`, `blocked_step_id` | `new_blocked_step_id` | `candidate_plan_step.not_before`, `blockage_event` |
| Scheduler | `candidate_plan_id`, `objectives` | `ScheduleResultData` (status, makespan, tasks[], parallel_groups[]) | 无（纯内存） |
| 持久化结果 | `ScheduleResultData` | `schedule_result.id` | `schedule_result` |
| 响应组装 | 多个 ORM 查询结果 | `dict` (未使用 Pydantic response_model) | 无 |

### 1.3 人工介入点清单

| 位置 | 介入内容 | 当前实现 | 自动化潜力 |
|------|---------|---------|-----------|
| **规则库维护** | 定义 op_rule / precond / effect / resource_req | 通过 DataManagement 页面 CRUD | 中（规则模板化、导入导出） |
| **策略A：not_before 时间** | 计划师预估离线修复时长，手动输入 | BlockageDialog 表单输入 | 高（可基于历史数据推荐） |
| **策略B：blockage_reason 选择** | 选择阻塞原因以匹配维修序列 | BlockageDialog 下拉框（从 feature_definition 动态读取） | 中（可基于故障模式库推荐） |
| **策略B：维修序列规则编写** | 预定义 OP_REPAIR_* 的 precond/effect | 规则库中 is_repair=TRUE 的规则 | 低（需领域知识） |
| **资源池配置** | resource 的 capacity / is_available | DataManagement 页面配置 | 中（可对接外部系统同步） |
| **求解超时阈值** | max_time_seconds 硬编码 30 秒 | 代码常量 | 高（应暴露为配置参数） |
| **状态快照维护** | machine_state / machine_state_feature | DataManagement 页面配置 | 中（可对接 IoT 自动采集） |
| **阻塞标记触发** | 计划师在甘特图上点击"标记阻塞" | 手动触发 | 高（可基于时间窗口/资源冲突自动检测） |

---

## 二、模块间接口契约

### 2.1 核心表清单（实际 16 张表）

> 注：任务文档列出 15 张，实际 ORM 定义有 16 张（多了 `feature_definition` 全局特征定义表）

| 序号 | 表名 | 职责 | 关联模块 |
|------|------|------|---------|
| 1 | `machine_type` | 机台类型定义（CNC、铣床等） | 全局 |
| 2 | `machine` | 机台实例，关联 machine_type | 全局 |
| 3 | `state_feature_def` | 某机台类型的状态维度定义（温度等级、清洁度等） | Planner, 数据管理 |
| 4 | `machine_state` | 机台状态快照（current/target/snapshot） | Planner, API, 前端 |
| 5 | `machine_state_feature` | 状态快照的具体特征键值对 | Planner |
| 6 | `op_rule` | 工序规则主表（含 duration, is_active, is_repair） | Planner, 数据管理 |
| 7 | `op_rule_precond` | 工序前置条件（feature_key, operator, feature_value） | Planner |
| 8 | `op_rule_effect` | 工序执行效果（feature_key, new_value, effect_type） | Planner |
| 9 | `op_rule_resource_req` | 工序资源需求（resource_type, quantity, is_required） | Scheduler |
| 10 | `resource` | 资源实例（人员、工具等，含 capacity, is_available） | Scheduler, 数据管理 |
| 11 | `feature_definition` | **全局特征类型定义**（feature_key, value_type, allowed_values） | 前端下拉框动态读取（如 blockage_reason） |
| 12 | `solve_request` | 求解请求记录（含状态流转 running→done/failed） | API, 查询 |
| 13 | `candidate_plan` | 候选方案（RAG 落库，含 version / parent_plan_id / replan_reason） | Planner, Scheduler, 查询 |
| 14 | `candidate_plan_step` | 候选方案步骤（step_order, op_rule_id, predecessor_ids, not_before, step_role） | Planner, Scheduler |
| 15 | `schedule_result` | 排程结果（makespan, solver_status, tasks JSONB） | Scheduler, API 查询 |
| 16 | `blockage_event` | 阻塞事件记录（strategy, not_before_offset, blockage_reason） | API, 查询 |

### 2.2 实体关系图（文本版 ASCII）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              机台与状态层                                  │
│                                                                          │
│  machine_type ──┬──► machine ──┬──► machine_state ──► machine_state_feature
│       │         │       │       │        │                              │
│       │         │       │       │        └── state_feature_def ◄────────┘
│       │         │       │       │
│       │         │       │       └── solve_request ◄──────┐
│       │         │       │                                │
│       └─────────┴───────┴────────────────────────────────┘
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                              工序规则层                                    │
│                                                                          │
│  machine_type ──► op_rule ──┬──► op_rule_precond                         │
│       │                     ├──► op_rule_effect                            │
│       │                     └──► op_rule_resource_req                      │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                              资源层                                        │
│                                                                          │
│  resource (独立表，通过 resource_type 与 op_rule_resource_req 关联)         │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                              求解与结果层                                  │
│                                                                          │
│  solve_request ──┬──► candidate_plan ──┬──► candidate_plan_step          │
│       │          │           │          │                                │
│       │          │           │          └──► blockage_event              │
│       │          │           │                                             │
│       │          │           └──► schedule_result                         │
│       │          │                                                        │
│       └──────────┴────────────────────────────────────────────────────────┘
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                              全局特征定义                                  │
│                                                                          │
│  feature_definition (独立表，无 FK，被前端动态读取用于下拉框)              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 数据流方向

```
┌──────────────────────────────────────────────────────────────┐
│                     规则库（数据库）                            │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│  │ machine_type│    │ state_feature│    │ op_rule         │  │
│  │ machine     │    │ _def         │    │ op_rule_precond │  │
│  │ machine_    │───►│ machine_     │───►│ op_rule_effect  │  │
│  │  state      │    │ state_feature│    │ op_rule_resource│  │
│  └─────────────┘    └──────────────┘    │ _req            │  │
│                                         └─────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Planner (build_rag)                                      │ │
│  │  输入：current_state_id + target_state_id                 │ │
│  │  输出：RAG (nodes + edges)                               │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  持久化层                                                 │ │
│  │  candidate_plan + candidate_plan_step                     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Scheduler (solve_schedule)                               │ │
│  │  输入：candidate_plan_id                                  │ │
│  │  输出：ScheduleResultData (makespan, tasks[], parallel)    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  持久化层                                                 │ │
│  │  schedule_result + blockage_event                         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  API 响应层                                               │ │
│  │  POST /solve → 同步返回 SolveResponse                     │ │
│  │  GET /solve-requests/{id} → 查询完整历史                  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  前端                                                     │ │
│  │  SolvePage → GanttChart / BlockageDialog / VersionHistory│ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 "规则库是数据驱动核心"如何减少代码修改

| 扩展场景 | 操作方式 | 是否修改代码 |
|---------|---------|-----------|
| **新增工序** | `op_rule` INSERT + `op_rule_precond`/`op_rule_effect`/`op_rule_resource_req` INSERT | ❌ 否 |
| **新增状态特征维度** | `state_feature_def` INSERT + 在状态中填入对应 `machine_state_feature` | ❌ 否 |
| **新增资源类型/实例** | `resource` INSERT | ❌ 否 |
| **新增机台类型** | `machine_type` INSERT + 完整规则集 INSERT | ❌ 否 |
| **新增维修序列** | `op_rule` INSERT（is_repair=TRUE）+ 预cond/effect 定义 | ❌ 否 |
| **调整工序时长** | `op_rule.duration_min` UPDATE | ❌ 否 |
| **调整资源容量** | `resource.capacity` UPDATE | ❌ 否 |
| **调整特征允许值** | `state_feature_def.allowed_values` UPDATE | ❌ 否 |
| **数字特征链式规划** | `feature_def.value_type="number"` → 自动路由到 numeric planner | ❌ 否 |

**仍需修改代码的场景：**
- 新增阻塞处理策略（当前只有 A/B/AB，如需策略 C 需改 solve.py）
- 新增目标函数类型（当前仅 minimize_makespan，ObjectiveRegistry 需扩展）
- 修改求解超时阈值（硬编码 30 秒）
- 修改 max_ops 安全上限（硬编码 50）
- 修改资源分配策略（当前贪心 MVP）
- 新增 effect_type（当前 set/increment/decrement）

---

## 三、前端交互流程

### 3.1 前端目录结构

```
frontend/src/
├── main.js                    # Vue3 应用入口，ElementPlus 配置
├── App.vue                    # 根布局：侧边栏导航（数据管理 / 求解）
│
├── api/
│   ├── index.js               # axios 实例 + 拦截器（error_code → 中文消息）
│   ├── masterData.js          # 主数据 API（machines, states, feature defs, rules...）
│   ├── solve.js               # 求解 API（postSolve, getPlanVersions, getPlanDiff, getSolveRequest）
│   └── system.js              # 健康检查
│
├── components/
│   ├── GanttChart.vue         # ECharts 自定义系列甘特图
│   │                          #   - 支持普通模式 + 对比模式
│   │                          #   - step_role 颜色标注（normal/repair/pulled_forward/delayed）
│   │                          #   - 关键路径边框高亮
│   └── BlockageDialog.vue     # 阻塞标记弹窗（策略 A/B/AB 选择 + 参数填写）
│
├── utils/
│   └── (errorCodes 等工具函数)
│
└── views/
    ├── DataManagement/        # 数据管理页面（7 个子页面）
    │   ├── index.vue          #   路由容器
    │   ├── MachineTypePage.vue
    │   ├── MachinePage.vue
    │   ├── StatePage.vue
    │   ├── FeatureDefPage.vue
    │   ├── RulePage.vue        #   工序规则 CRUD（含 precond/effect/resource 聚合编辑）
    │   └── ResourcePage.vue
    │
    └── SolvePage/             # 求解主页面
        ├── index.vue          #   求解表单 + 结果展示 + 版本历史（14.8 KB，核心页面）
        └── VersionHistory.vue #   版本时间线（支持对比 / 查看）
```

### 3.2 用户操作链路

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: 选择机台                                               │
│  ├─ 前端: el-select 下拉框（loadMachines）                       │
│  └─ 自动触发: onMachineChange() → 加载该机台 states               │
│                                                                 │
│  Step 2: 选择起点状态 & 目标状态（自动预填充）                    │
│  ├─ 当前状态: auto-select 第一个 state_type="current"             │
│  └─ 目标状态: auto-select 第一个 state_type="target"              │
│                                                                 │
│  Step 3: 点击"开始求解"                                          │
│  ├─ 校验: machine_id / current_state_id / target_state_id 非空    │
│  ├─ 校验: current ≠ target                                       │
│  ├─ API 调用: POST /solve（ objectives: [{minimize_makespan}] ）  │
│  └─ 等待: solving 状态 + loading 动画                              │
│                                                                 │
│  Step 4: 查看结果                                                │
│  ├─ 指标卡片: makespan（总工期）                                   │
│  ├─ 状态变化标签: state_delta（feature: from → to）               │
│  ├─ 关键路径标签: critical_path（★ 标记）                        │
│  ├─ 甘特图: GanttChart（ECharts custom series）                   │
│  ├─ 任务明细表: el-table（含步骤/编码/名称/时间/角色/not_before/资源/操作）
│  └─ 并行组: parallel_groups 标签展示                              │
│                                                                 │
│  Step 5（可选）: 标记阻塞                                        │
│  ├─ 入口: 任务表右侧"标记阻塞"按钮 或 甘特图（未实现直接点击）       │
│  ├─ 弹窗: BlockageDialog.vue                                     │
│  │   ├─ 策略选择: A（延时）/ B（维修）/ AB（两者）                 │
│  │   ├─ 策略A: not_before_offset（最早可执行时间，分钟）           │
│  │   ├─ 策略B: blockage_reason（从 feature_definition 动态读取）   │
│  │   └─ 备注 + 创建人                                              │
│  ├─ 提交: POST /solve（parent_plan_id = 当前 plan_id）             │
│  │        + blockage_constraints 参数                              │
│  └─ 结果: 新版本计划生成，版本号递增                               │
│                                                                 │
│  Step 6（可选）: 版本对比                                         │
│  ├─ 版本历史面板: VersionHistory.vue（el-timeline）                │
│  ├─ 操作: "与当前对比" 或 "查看"                                   │
│  └─ 对比视图: diffMode=true → GanttChart 并排展示基准 vs 新计划      │
│              基准计划用半透明灰色，新计划用 step_role 颜色           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 可自动化空间

| 当前人工步骤 | 自动化方案 | 难度 | 优先级 |
|-------------|-----------|------|--------|
| **状态选择预填充** | 已部分自动化（选 first current/target），可优化为智能推荐最近使用 | 低 | 低 |
| **阻塞标记触发** | 自动检测资源冲突 / 时间窗口超限，主动提示计划师 | 中 | 高 |
| **策略A: not_before 时间** | 基于历史阻塞修复时长数据，推荐默认值 | 中 | 中 |
| **策略B: blockage_reason 选择** | 基于故障模式库 + 当前状态特征，智能推荐 | 中 | 中 |
| **策略推荐（A/B/AB）** | 基于阻塞类型、资源池状态、工期敏感度，推荐最优策略 | 高 | 中 |
| **状态快照维护** | 对接 IoT / SCADA 系统自动采集机台状态 | 中 | 高 |
| **规则库质量检查** | 自动检测 unreachable rules / missing effects / 环 | 中 | 中 |
| **求解参数调优** | 基于问题规模自动调整 max_time_seconds / max_ops | 低 | 低 |
| **目标状态推荐** | 基于历史求解记录和机台类型，推荐常用目标状态 | 低 | 低 |

---

## 四、关键发现

### 发现1: step_order 语义不精确，Scheduler 依赖 predecessor_ids 建约束
- `RAGNode.id` 直接作为 `step_order`，是节点创建顺序（1-indexed），**不是拓扑排序结果**
- Scheduler 正确性依赖于 `predecessor_ids` 数组，而非 step_order 的数值顺序
- 当前无 bug，但如果未来需要在 step_order 上施加数值语义（如"步骤 3 必须在步骤 5 之前"），会出问题

### 发现2: 资源"容量建模"与"实例回填"不完全等价
- CP-SAT cumulative 约束按 `resource_type` 容量建模
- 但 `_assign_resources()` 是**贪心 MVP**：按时间顺序，给每个任务分配第一个空闲资源实例
- 如果 `resource_qty > 1`，cumulative 会正确约束，但实例分配仍只写一个具体资源到 `tasks_response`
- 资源不足时返回空列表（降级模式），不会导致求解失败

### 发现3: 效果可交换性并行过滤层缺失（与 Phase 1 发现一致）
- Planner 的 `find_parallel_groups(rag)` 仅基于"相同 predecessor 集合"分组
- **未检查 effect 冲突**：两个无前驱的步骤如果都修改同一 feature，可能被误判为可并行
- 当前对外暴露的 `parallel_groups` 来自 Scheduler 的时间重叠检测（`_detect_actual_parallel`），是正确的
- 但 Planner 阶段的并行机会分析存在理论缺陷

### 发现4: 目标模型语义未对齐（state_id vs 条件表达式）
- 前端和 API 使用 `target_state_id`（具体状态快照）
- 但业务上真正的"目标"应是条件表达式（如 `temperature_level = "hot"`），而非某个特定 snapshot
- 当前系统中：不同 machine_state 记录可能表示相同语义状态（重复快照），导致计划师困惑
- 建议：目标状态应支持"条件表达式模式"，而非强制选择 snapshot

### 发现5: 异常处理采用"200 OK + 结构化错误"模式，但 Schema 未绑定
- `POST /solve` 对所有失败路径返回 HTTP 200，payload 中 `status="failed"` + `error_code`
- 这一设计避免了前端处理 HTTP 错误码，但牺牲了标准 REST 语义
- `SolveResponse` Pydantic Schema 已定义，但路由未声明 `response_model`，返回的是手写 dict
- 风险：Schema 与实际返回结构可能漂移（如 `error_message` vs `detail`）

### 发现6: `max_ops = 50` 安全上限是硬编码的隐性约束
- 在 `build_rag()` 的 worklist 循环中，`max_ops = 50` 用于防止异常规则导致无限扩张
- 对于复杂机台类型（如航空发动机装配，可能有 100+ 步骤），这个上限会成为瓶颈
- 当前没有日志或告警通知用户"因安全上限截断"，而是静默处理（循环终止后进入环检测）

### 发现7: `FeatureDefinition` 是全局表，与 `StateFeatureDef` 职责部分重叠
- `StateFeatureDef`：按 `machine_type_id` 分组的特征定义（机台类型维度）
- `FeatureDefinition`：全局特征定义（系统维度），无 FK 关联，被前端动态读取 blockage_reason 等
- 两个表维护同一概念（特征的定义），存在数据一致性风险
- 建议：合并或明确分工（StateFeatureDef 管业务特征，FeatureDefinition 管系统级元特征如 blockage_reason）

### 发现8: 策略B的维修序列匹配依赖 `is_repair` 标记 + precondition 满足
- `build_rag()` 中 `include_repair=True` 时，遍历所有 `is_repair=True` 的规则
- 仅当 `check_preconditions(current_state, rule.preconditions)` 为 True 时才加入
- 这意味着：**维修序列不会通过 delta 匹配引入**（因为 target_state 通常不包含 blockage_reason）
- 而是通过"当前状态已满足 precondition"的旁路逻辑引入，这是一个特殊 case
- 风险：如果维修序列的 precondition 不止 blockage_reason 一条，需要全部满足才会被引入

### 发现9: `blockage_reason` 的合法值来源分散
- 前端 BlockageDialog 从 `feature_definition` 表的 `allowed_values` 读取下拉选项
- 后端策略B从 `op_rule_precond.feature_value` 匹配维修序列
- 两处数据源不同，可能导致：前端显示的可选值，后端没有对应的维修序列（或反之）
- 当前未做交叉校验

### 发现10: `compute_step_role_diff` 在 solve.py 末尾调用，但逻辑在外部模块
- `from app.core.solver.step_role import compute_step_role_diff` 在 solve.py 中导入
- 它在 solve_schedule 完成后、响应组装前执行
- 我没有读取其源码，但协议文档说明它通过与父计划 diff 计算 step_role
- 这一后置处理是前端甘特图颜色标注和对比视图的数据基础

---

## 五、自审查清单

- [x] 端到端流程图完整（从 POST /solve 到响应）
- [x] 每个阶段标注了数据结构（输入/输出/持久化表）
- [x] 关键决策点已标注（候选选择策略、中间工序选择、求解超时、资源回退等）
- [x] 人工介入点已识别（规则库维护、阻塞策略选择、资源池配置等）
- [x] 16 张核心表已列出（含 FeatureDefinition）
- [x] 实体关系图已绘制（ASCII 分层图）
- [x] 数据流方向已绘制（规则库 → Planner → Scheduler → 前端）
- [x] "规则库驱动减少代码修改"已论证（含正反两面）
- [x] 前端目录结构已列出（含文件职责）
- [x] 用户操作链路已绘制（6 步链路）
- [x] 可自动化空间已标注（9 项，含难度和优先级）
- [x] 关键发现已记录（10 条，涵盖语义、架构、数据一致性）

---

## 六、读取文件清单

| 路径 | 用途 | 读取行数 |
|------|------|---------|
| `app/api/v1/solve.py` | API 入口，求解主流程 | 全文（~290行） |
| `app/core/planner/search.py` | RAG 构建核心 | 全文（~350行） |
| `app/core/scheduler/solver.py` | CP-SAT 排程 | 全文（~290行） |
| `app/core/scheduler/model.py` | CP-SAT 模型构建 | 全文（~140行） |
| `docs/protocols/planner.md` | Planner 协议文档 | 全文 |
| `docs/protocols/scheduler.md` | Scheduler 协议文档 | 全文 |
| `app/db/models.py` | ORM 模型（全部16张表） | 全文（~570行） |
| `app/db/schemas.py` | Pydantic Schema | 全文（~640行） |
| `docs/protocols/api.md` | API 契约 | 全文 |
| `docs/protocols/db.md` | 数据库协议 | 全文 |
| `docs/v0.2-spec.md` | V0.2 阻塞处理规范 | 全文 |
| `frontend/src/App.vue` | 前端根布局 | 全文 |
| `frontend/src/main.js` | 前端入口 | 全文 |
| `frontend/src/views/SolvePage/index.vue` | 求解主页面 | 全文（~260行） |
| `frontend/src/views/SolvePage/VersionHistory.vue` | 版本历史组件 | 全文 |
| `frontend/src/components/GanttChart.vue` | 甘特图组件 | 全文（~220行） |
| `frontend/src/components/BlockageDialog.vue` | 阻塞弹窗 | 全文（~170行） |
| `frontend/src/api/solve.js` | 求解 API 客户端 | 全文 |
| `frontend/src/api/index.js` | axios 配置 | 全文 |

---

## 七、遗漏与疑问

1. **`compute_step_role_diff` 具体实现未读取**：只看到了调用点，未读取 `app/core/solver/step_role.py` 源码，但协议文档已说明其通过与父计划 diff 计算角色。

2. **`app/core/planner/numeric.py` 未读取**：数字特征链式规划（`plan_exact_numeric_feature`）的内部逻辑未完全展开，仅知其为独立路由的分支。

3. **`app/core/solver/objectives.py` 未读取**：ObjectiveRegistry 的注册机制和多目标叠加逻辑未完全展开，当前仅知默认是 minimize_makespan。

4. **前端 `DataManagement` 页面未深入读取**：只读取了目录结构和 App.vue 中的引用，未读取各子页面的实现细节（但对本 Phase 目标非必要）。

5. **版本链查询接口未读取后端实现**：`getPlanVersions` / `getPlanDiff` 的后端路由实现未读取（但前端已展示其契约）。

6. **数据库 migration 文件未检查**：虽然 ORM 模型已读取完整，但 migration 历史可能揭示 schema 演化信息。

7. **`blockage_event.blocked_step_id` 允许 NULL**：models.py 中定义为 `Optional[int]`，但 v0.2-spec 的 SQL 定义写的是 `NOT NULL`。代码实现更灵活（允许记录无具体步骤的阻塞事件），但文档与实现不一致。

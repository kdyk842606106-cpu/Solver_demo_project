# TICKET-097：状态/活动本体—引用模型统一与单一状态转移视图

> Status: completed (2026-07-28)
> Version: V0.3
> Created: 2026-07-28
> Updated: 2026-07-28

## Goal

在不重做现有主数据表和求解链路的前提下，把状态、活动和网络编辑器收敛为一致的 MVP 语义：

- 状态包通过 `StateNodeReference` 引用原子状态；
- 活动包通过 `ActivityPackageAtomicRef` 引用原子活动；
- 原子状态和原子活动是可复用本体，包内成员、排序、启用和布局属于引用；
- `ActivityStateBinding` 与 `OpRule` 绑定原子活动本体，不绑定某个画布引用实例；
- 删除引用只解除成员关系，不能级联删除本体；
- 名称、编码和布局变化不改变本体、引用或绑定身份；
- Network Editor 只保留一个完整状态转移视图，直接呈现“输入状态 → 原子活动 → 输出状态”；
- 求解预检保留为校验动作和结果面板，不再作为独立画布视图；
- 日落“虚拟活动”产品概念，`ActivityNode(level 1/2)` 只按“活动包”解释。

## Locked MVP semantics

1. 本票据复用现有 `StateNode`、`StateNodeReference`、`ActivityNode`、`AtomicActivity`、`ActivityPackageAtomicRef` 和 `ActivityStateBinding`，不新建同义业务表。
2. `StateNode.parent_id` 和 `ActivityNode.parent_id` 继续承载包到包的主层级；原子成员不能再通过 `parent_id` 挂包。
3. 原子状态必须是库对象，`parent_id IS NULL`；加入状态包必须创建 `StateNodeReference`。
4. 原子活动没有包所有权；加入活动包必须创建 `ActivityPackageAtomicRef`。
5. 引用和语义边端点不可原地替换。把引用改到另一本体，或改变活动—状态绑定的端点/角色，按“删除旧关系 + 创建新关系”处理。
6. 当前 MVP 以数据库主键作为稳定身份。修改 `name` 或 `code` 不改变本体 ID、引用 ID、绑定和 canonical 图 ID。
7. 包内排序、启用、别名、画布位置和容器上下文信息保存在引用；本体只保存脱离包后仍成立的业务定义。
8. 原子活动规则及输入/输出绑定属于 `AtomicActivity` 本体。状态转移视图可把边投影到当前可见引用实例，但持久化端点仍是 canonical 本体。
9. 活动包只负责复用组织、分类、筛选和展示，不作为可执行状态转移节点，不产生“包 → 状态”的伪语义边，也不再承载任何求解约束。
10. Scope Guard 随活动包求解语义一并日落：停止新增和编辑，停止通过包路径向原子活动继承前置条件，停止进入新的有效模型和求解。
11. `ActivityNode(level 1/2)` 在代码和数据库兼容期内继续存在，但业务名称统一为“活动包”，禁止继续称为或创建“虚拟活动”。
12. 旧虚拟活动状态绑定角色（包括 `context_input`、`declared_output`）停止新增、停止编辑、停止进入网络图和求解模型；历史记录只读保留用于审计，不自动转换成原子活动输入/输出。
13. 旧 `ActivityNode(level=3)` 只读兼容，不再作为新增活动或 Network Editor 创建目标。
14. 真正影响执行的公共准入条件必须落实为原子状态到原子活动的 `ActivityStateBinding(input)`；管理包的移动、重命名、分组和层级变化不得改变求解结果。
15. 当前 PostgreSQL 审计确认 `scope_guard=0`、`scope_guard_precond=0`，且两个序列均从未调用；本票据不执行任何 Scope Guard 数据库迁移或数据转换。
16. 发布前必须再次执行 Scope Guard 零数据断言；若任一部署环境出现非零记录，立即停止发布并另开数据决策，不在本票据内自动取并集或转换。
17. 历史求解继续使用当次保存的有效模型和必要快照；当前数据库没有 Scope Guard 历史影响记录。
18. 求解候选直接读取 active `AtomicActivity`、规则和输入/输出绑定，不读取活动包层级或 `ActivityPackageAtomicRef.is_active`。如用户通过活动包筛选求解范围，界面必须先解析并提交明确的 canonical 原子活动 ID 集合。

## Single-view contract

Network Editor 只有一个业务画布：`state_transition`。

- 画布完整显示状态包、状态引用实例、原子活动引用实例以及 canonical 输入/输出绑定；
- 每条有效转移必须可读为“输入状态 → 原子活动 → 输出状态”；
- 活动包仅作为资源树分组、筛选和管理上下文，不进入转移主链，也不提供求解前置条件；
- 同一原子状态或原子活动被多个包引用时，画布可显示多个引用实例，同时保留相同 `canonical_id`；
- 日落纲要视图、求解视图、虚拟活动聚焦画布和视图切换器；
- 旧 `outline`、`implementation`、`solver_ready` 等 `view_mode` 请求在兼容窗口内统一归一化为 `state_transition`，不再返回不同图投影；兼容期结束后删除参数；
- solver precheck、health check 和影响分析读取同一 canonical 有效模型，以按钮、侧栏或结果面板呈现，不生成第二张图。

## Tasks

- [x] T97-0 冻结本计划，盘点现有数据、旧 `view_mode` 调用、历史活动包绑定和回归基线。
- [x] T97-1 统一原子状态、状态包、活动包和 legacy 活动判定入口，吸收 TICKET-064 的分散判定技术债。
- [x] T97-2 增加 Alembic 014：把直接挂包的原子状态转为成员引用，并收紧引用/绑定删除约束；尚未对当前开发库执行升级。
- [x] T97-3 收敛 CRUD 与统一提交：关系端点不可变、本体删除受保护、改名不改身份。
- [x] T97-4 收敛全部写路径；禁止新增已日落活动层级、活动包状态绑定、Scope Guard 和 `ActivityNode(level=3)`。
- [x] T97-5 将 Network Editor 收敛为唯一完整状态转移投影，活动引用为独立实例并保留 canonical 端点。
- [x] T97-6 删除旧业务视图入口、视图切换器和活动包专属交互；求解预检改为单一画布上的校验动作。
- [x] T97-7 固化 Scope Guard 零数据门禁，删除包路径前置条件继承，并完成 layered expansion、health check、solver precheck、Scheduler loader 和历史回放回归。
- [x] T97-8 完成 PostgreSQL 迁移演练、专项/全量自动化、业务验收、文档与 STATE 回写。

## Implementation evidence

已完成：

- 新增统一语义 helper、canonical/display graph ID parser；
- 新增 014 migration，且 migration 文件不访问 Scope Guard 表；
- 新增只读数据审计及 Scope Guard 零数据发布门禁；
- CRUD、统一提交、场景导入和删除保护已按冻结语义收口；
- Network Editor 固定为 `state_transition`，旧参数只返回归一化诊断；
- 预检与正式求解共用有效模型解析器；
- `SolveRequest.overrides` 保存模型版本、摘要及 `effective-model/v1` 快照；
- Scheduler 不再从活动包引用推断隐式主分组；
- 用户指南、验收矩阵、API/DB 协议和分层需求已同步。
- 当前项目库只读审计确认：`scope_guard=0`、`scope_guard_precond=0`；59 个原子状态仍需由 014 从直接 `parent_id` 成员关系转换为状态引用；重复/跨机型/自引用异常均为 0；历史包级绑定为 `context_input=3`、`declared_output=6`。
- PostgreSQL 迁移演练通过：对 `.postgres-data` 的一致物理副本执行 013 → 014；新增 59 条状态引用，迁移后 `atomic_state_with_parent=0`，重复引用、跨机型引用和自引用均为 0，五个关键本体外键均为 `RESTRICT`。
- Scope Guard 迁移零影响：迁移前后两张表均为 0、两个序列状态不变、Schema 指纹不变；014 不访问 Scope Guard 表，`scope_guard_migration_executed=false`。
- 迁移后历史包级绑定仍为 `context_input=3`、`declared_output=6`，只读审计可见且未进入当前图或求解。
- 修复迁移验收发现的 canonical/display ID 偏差：图校验按 canonical 端点去重，solver precheck 的活动范围和阻塞状态直接来自统一有效模型；无启用规则由有效模型健康检查阻塞。
- 真实迁移副本业务验收通过：Network Editor 图接口返回 `state_transition`；求解预检为 `ready`，canonical 活动范围为 `[111,112,113,114]`；正式求解生成 4 步、makespan 40，预检、求解和持久快照模型版本均为 `sha256:97dbdf1ea120ebd2a2c169b9c179767e82c09332d07fdc8da7143e8d28d3d452`。
- 历史求解证据通过：候选计划 90 的 `SolveRequest.overrides` 保存 `effective-model/v1`，包含 4 个目标事实、4 个 canonical 原子活动、4 条有效规则和明确的 `atomic_activity_scope_ids`。
- 可恢复性验证通过：停止验收副本后重新启动原始库，原库仍为 `013_plan_adjustment`、59 个直接父关系、4 条原有状态引用、Scope Guard 0/0；原库随后恢复为停止状态，临时副本已删除，当前开发库未被升级。
- 自动化通过：后端 `399 passed`；Network Editor Chromium `62 passed`；Vite production build 通过；术语检查通过（17 files scanned）；数据库验收后的 Scope Guard 零数据门禁、body/reference 审计和固定求解场景均通过。

## Phase gates

每个阶段必须同时满足：

- 本阶段新增单元/集成测试通过；
- 既有 Network Editor、layered solve 和场景导入聚焦回归通过；
- 数据完整性查询无新增异常；
- API 和图协议保持明确兼容窗口；
- 不能用人工说明、跳过测试或 mock-only 结果替代真实 PostgreSQL 与真实浏览器证据。

完整开发步骤、测试矩阵、业务场景和准入/准出规则见：

`docs/superpowers/plans/2026-07-28-state-activity-body-reference-unification.md`

## Out of scope

- 机台实例 + 机台类型基线的版本仓库实现。
- 内容寻址对象库、提交对象、Merkle Tree、分支合并和回写基线。
- 新增 `entity_key/relation_key` 跨数据库稳定标识；当前先以数据库主键冻结身份语义。
- 解决同一原子活动被多个活动包引用时的 Scheduler 连续性归属策略。
- 维护意图模板继续开发；该能力已按产品决策废弃。
- 把包到包主层级全面改造成 DAG 引用。
- 一次性物理删除旧表、旧字段、legacy `ActivityNode(level=3)` 或历史虚拟活动审计数据。

## Acceptance summary

- 新建原子状态或原子活动时，本体只保存一次，加入两个包只产生两个引用。
- 两个引用实例可独立排序、启停和摆放，不污染本体或另一引用。
- 修改本体名称/编码后，本体 ID、引用 ID、规则、绑定和 canonical 图 ID 不变。
- 修改引用或绑定端点/语义角色时，旧关系被删除并创建新关系，不复用旧关系 ID。
- 移除一个引用后，本体、其他引用、规则和绑定仍存在；在用本体删除返回结构化冲突。
- Network Editor 只显示完整状态转移视图，不再出现纲要/求解视图切换和虚拟活动专属交互。
- 每条活动绑定在画布上可读为输入状态、原子活动、输出状态；活动包不伪装成活动节点或状态转移边。
- 同一 canonical 原子活动的多个引用可显示为多个画布实例，求解预检和最终计划不会重复生成任务。
- 历史 `context_input`、`declared_output` 绑定不再参与图投影和求解，且没有被自动误转为原子活动绑定。
- 新建/编辑 Scope Guard 的入口关闭，活动包层级或成员变化不再改变求解模型。
- 求解请求使用 canonical 原子活动范围；活动包筛选只是一种界面选取方式，不作为求解器输入。
- Scope Guard 两张表在发布前仍为零；本票据未执行相关数据库迁移或数据转换。
- 历史求解快照仍可重放；状态包目标展开、健康检查、覆盖快照和场景导入无非预期回退。

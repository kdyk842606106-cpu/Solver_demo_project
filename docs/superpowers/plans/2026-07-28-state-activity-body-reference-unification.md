# 状态/活动本体—引用模型统一与单一状态转移视图：开发与验收计划

> **Status:** Completed
> **Ticket:** TICKET-097
> **Version:** V0.3
> **Created:** 2026-07-28
> **Updated:** 2026-07-28
> **Implementation rule:** 已在可恢复的 PostgreSQL 物理副本完成 013 → 014 演练、迁移后只读审计、API 预检和固定业务求解验收；当前开发库保持 013，未执行 Scope Guard 迁移。

## 0. 2026-07-28 实施快照

- Scope Guard 决策：当前项目库 `scope_guard=0`、`scope_guard_precond=0`，本任务未执行、也不计划执行 Scope Guard 数据迁移。
- 迁移前 body/reference 审计：59 个原子状态仍以 `parent_id` 直接挂包；重复引用、跨机型引用和自引用均为 0；历史包级绑定为 `context_input=3`、`declared_output=6`。
- 014 migration、统一语义 helper、CRUD/导入保护、单一状态转移画布、有效模型解析与求解快照、Scheduler canonical 化均已实现。
- 自动化证据：后端 `399 passed`；Network Editor Chromium `62 passed`；Vite production build 通过；术语检查 `17 files scanned`。
- PostgreSQL 副本验收：013 → 014 成功；新增 59 条状态引用，`atomic_state_with_parent=0`，重复/跨机型/自引用异常均为 0，关键外键均为 `RESTRICT`。
- Scope Guard 前后均为 0/0、序列与 Schema 指纹不变，014 未访问 Scope Guard；历史 `context_input=3`、`declared_output=6` 保持只读。
- 迁移副本 Network Editor、统一有效模型预检和固定 layered solve 均通过；预检与 4 步求解共享模型版本，makespan 为 40，`effective-model/v1` 快照已持久化。
- 原始库恢复验证仍为 013、59 个直接父关系和 4 条原有引用；当前开发库未升级，临时验收副本已删除。
- 下文阶段清单保留为原始执行分解；最终完成状态与证据以本快照和 `docs/TICKET_097.md` 为准。

## 1. 目标与结果

本计划把当前已经部分存在的“本体 + 引用”能力收敛为统一、可验证的 MVP 契约。

最终业务视图：

```text
状态包 ── StateNodeReference ──> 原子状态本体
活动包 ── ActivityPackageAtomicRef ──> 原子活动本体
原子活动本体 ── ActivityStateBinding(input/output) ──> 状态本体
原子活动本体 ── OpRule ──> 可执行规则
```

核心结果：

- 本体只保存一次，可被多个包复用；
- 包只维护成员引用，不复制、不拥有原子本体；
- 本体、成员引用、语义绑定拥有不同且稳定的身份；
- 包内排序、启用、布局和上下文展示信息由引用拥有；
- 删除引用不会删除本体；
- 改名不会改变身份；
- Network Editor 只保留完整状态转移视图，网络图显示引用实例，求解器读取 canonical 本体；
- 纲要视图和求解视图日落；求解预检保留为同一画布上的校验动作与结果面板；
- “虚拟活动”产品概念日落，`ActivityNode(level 1/2)` 只表示活动包；
- Scope Guard 日落，活动包成为纯管理结构；真实准入条件显式转换为原子活动 `input` 状态绑定；
- 历史数据可迁移，旧接口有明确兼容窗口。

## 2. 当前实现与主要差距

### 2.1 已有能力

当前数据库已经具备主要骨架：

| 业务概念 | 当前模型 |
|---|---|
| 状态包 / 状态本体 | `StateNode` |
| 状态包成员引用 | `StateNodeReference` |
| 活动包 | `ActivityNode(level 1/2)` |
| 原子活动本体 | `AtomicActivity` |
| 活动包成员引用 | `ActivityPackageAtomicRef` |
| 原子活动—状态语义边 | `ActivityStateBinding` |
| 原子活动可执行规则 | `OpRule.atomic_activity_id` |

Network Editor 已经支持状态引用实例的独立 `reference_id` 和引用自有布局；活动包引用也有独立持久化表和 `reference_id`，但图投影仍会把同一本体的多个活动引用聚合成一个 `atomic_activity:{id}` 节点。

### 2.2 P0 差距

1. **原子状态仍可能直接挂包。**
   `StateNode.parent_id`、创建/更新 Schema 和部分旧写路径仍允许原子状态通过父子关系进入状态包。

2. **活动引用实例在图投影中被合并。**
   同一原子活动有多个 `ActivityPackageAtomicRef` 时，后端通常只返回一个 canonical 图节点，并把多个引用塞入 `reference_ids`；布局和包上下文会选择一个 `primary_ref`，不能完整表达每个引用实例。

3. **引用端点语义不一致。**
   `StateNodeReference` 更新不能换端点，但 `ActivityPackageAtomicRefUpdate` 仍允许修改 `atomic_activity_id`。这会让同一引用 ID 突然代表另一条成员关系。

4. **本体删除保护不足。**
   当前原子活动删除流程会主动删除包引用和规则；部分外键还使用 `CASCADE` 或 `SET NULL`。状态本体删除也可能通过级联清除引用或绑定，不符合“移除引用不删除本体、本体在用不能删除”的知识图谱语义。

5. **原子状态判定分散。**
   `state_kind`、`feature_key + target_value`、是否有子节点和前端 `is_leaf` 并存，TICKET-064 尚未统一。

6. **技术文档仍有旧层级表述。**
   ORM 注释和部分 Schema 仍写“一级/二级聚合、三级叶子”“additional display parent”，与当前产品术语不一致。

7. **Network Editor 存在多套业务图投影。**
   纲要、实现/聚焦和求解就绪等模式会让同一份主数据出现不同节点/边口径，用户无法确定哪一张图才是可编辑、可求解的有效模型。

8. **旧“虚拟活动”语义仍渗透到界面和绑定。**
   `ActivityNode(level 1/2)` 同时被当作活动包和虚拟活动，历史 `context_input`、`declared_output` 状态绑定、聚焦画布及覆盖统计会把组织容器误解为可执行活动。

## 3. 冻结的 MVP 语义

### 3.1 包层级与原子成员

本票据不把所有包层级改造成 DAG，保留现有主层级：

| 关系 | MVP 持久化方式 | 说明 |
|---|---|---|
| 状态包 → 子状态包 | 现有 `StateNode.parent_id` 主层级；已有共享包引用继续兼容 | 本票据不全面改造包到包层级 |
| 状态包 → 原子状态 | 只能使用 `StateNodeReference` | 原子状态 `parent_id` 必须为空 |
| 活动包 → 子活动包 | `ActivityNode.parent_id` | 只表达管理分解 |
| 活动包 → 原子活动 | 只能使用 `ActivityPackageAtomicRef` | 原子活动没有包所有权 |

### 3.2 本体身份

MVP 不新增跨数据库身份字段，冻结以下规则：

- 状态本体身份：`StateNode.id`；
- 原子活动本体身份：`AtomicActivity.id`；
- 状态成员关系身份：`StateNodeReference.id`；
- 活动成员关系身份：`ActivityPackageAtomicRef.id`；
- 活动—状态语义关系身份：`ActivityStateBinding.id`。

`name` 和 `code` 是可修改业务属性，不是数据库内部身份。修改它们后：

- 数据库主键不变；
- 引用主键不变；
- `OpRule` 和 `ActivityStateBinding` 关系不变；历史 Scope Guard 记录在日落迁移前保持原身份；
- canonical 图 ID 不变；
- Network Editor revision 应变化，以便编辑冲突检测生效。

跨机台实例、跨数据库和内容寻址版本中的稳定 `entity_key/relation_key` 留给版本仓库票据处理。

### 3.3 引用身份

引用表示一条确定的成员关系：

```text
reference_id = package_id + body_id 这条关系的稳定身份
```

规则：

- 引用 ID 创建后，起点包和终点本体不可原地变更；
- 改换本体或改换包按“删除旧引用 + 新建引用”处理；
- 排序、启用、包内别名、布局和其他包内元数据可以更新；
- 同一包对同一本体只能有一个引用；
- 同一本体可以在多个包中各有一个引用。

`ActivityStateBinding` 同样是一条有身份的语义关系。以下字段定义关系语义，创建后不可原地替换：

- `atomic_activity_id` 或 legacy `activity_node_id`；
- `state_node_id`；
- `binding_role`。

需要改变活动端点、状态端点或输入/输出角色时，统一提交必须显式删除旧绑定并创建新绑定。覆盖范围、启用状态和关系 metadata 可以在原绑定上更新。

### 3.4 本体与引用字段边界

| 内容 | 本体 | 引用 |
|---|---:|---:|
| 名称、编码、说明 | 是 | 否 |
| 状态事实、活动能力、类别 | 是 | 否 |
| 原子活动规则、资源需求 | 是 | 否 |
| 原子活动输入/输出绑定 | 是 | 否 |
| 所在包 | 否 | 是 |
| 包内排序 | 否 | 是 |
| 包内启用 | 否 | 是 |
| 包内显示别名/说明 | 否 | 是，可选 metadata |
| 画布位置和包内布局 | 否 | 是 |

如果某项信息离开包之后仍然成立，它属于本体；只有进入某个包后才成立的信息属于引用。

### 3.5 绑定与图端点

`ActivityStateBinding` 继续绑定本体：

```text
AtomicActivity.id -> StateNode.id
```

画布可以把边显示到当前引用实例，但必须同时保留 canonical 端点：

```json
{
  "source_id": "atomic_activity:42:ref:700",
  "canonical_source_id": "atomic_activity:42",
  "target_id": "state_node:51:ref:901",
  "canonical_target_id": "state_node:51"
}
```

持久化、校验、影响分析和求解都使用 canonical ID；引用图 ID 只表达当前视图中的一次出现。

### 3.6 删除语义

| 用户动作 | 系统行为 |
|---|---|
| 从包中移除 | 删除引用，保留本体、其他引用、规则和绑定 |
| 停用包内成员 | 更新引用 `is_active=false`，不停用本体 |
| 停用本体 | 更新本体 `is_active=false`，所有引用仍保留但默认视图不参与求解 |
| 删除未使用本体 | 仅在无引用、无绑定、无规则、无历史计划使用时允许 |
| 删除在用本体 | 返回结构化 409，列出引用类型和数量，不执行级联删除 |

包删除可以删除“该包作为父端”的成员引用，但不能删除被引用的原子本体。

### 3.7 Scope Guard 日落与零数据门禁

活动包冻结为纯管理结构，因此挂在活动包上的 Scope Guard 不再拥有求解语义：

- 停止新增、编辑、导入和复制 Scope Guard；
- layered expansion、health、solver precheck、layered solve 和 Scheduler 不再通过 package path 继承 Scope Guard；
- 活动包移动、改名、重新分组、层级调整和引用增减不得改变原子活动有效前置条件；
- 求解候选直接读取 active `AtomicActivity`、`OpRule` 和输入/输出绑定，不读取活动包层级或活动包引用启停；
- 真正影响执行的公共准入条件必须显式落为“原子状态 → 原子活动”的 `ActivityStateBinding(input)`；
- 历史求解读取保存时的有效模型版本和必要快照，不用当前 Scope Guard 表重新解释。

2026-07-28 对当前项目 PostgreSQL 的只读审计结果：

- `scope_guard=0`、`scope_guard_precond=0`；
- 两个自增序列均为 `last_value=1, is_called=false`；
- PostgreSQL 表统计的 insert/update/delete 均为 0；
- 现有求解请求、候选计划、计划步骤、排程结果和全部 JSONB 列没有 Scope Guard 痕迹。

因此本票据明确不执行 Scope Guard 数据库迁移，也不开发 Guard → `input` 绑定转换脚本。发布前只重复零数据断言；若其他部署环境出现非零记录，停止发布并另开数据决策。本票据仍不解决同一原子活动多包复用时的 Scheduler 连续性归属策略，也不得通过隐式“主引用”恢复包级求解语义。

### 3.8 单一状态转移视图与虚拟活动日落

Network Editor 只保留一个业务画布，协议名称冻结为 `state_transition`：

- 完整呈现状态包/状态引用、原子活动引用及 `input/output` 绑定；
- 每条有效转移在画布上可读为“输入状态 → 原子活动 → 输出状态”；
- 活动包只承担资源组织、复用入口、分类、筛选和展示，不是可执行节点，不创建包到状态的语义边，也不提供求解前置条件；
- 同一 canonical 本体可以因多个包引用显示为多个画布实例，但持久化、校验、影响分析和求解仍使用 canonical ID；
- 纲要、实现/聚焦、求解就绪和全图调试不得作为用户可切换的第二业务画布；
- solver precheck、health check 和影响分析作为按钮、侧栏或结果面板消费同一份 canonical 有效模型。

“虚拟活动”不再是领域对象：

- `ActivityNode(level 1/2)` 在数据库和代码兼容期只解释为活动包；
- 禁止新增或编辑包级状态绑定，包括 `context_input`、`declared_output`；
- 历史包级绑定只读保留用于审计，默认不进入图投影、有效模型和求解；
- 不把历史包级绑定自动转换成原子活动 `input/output`，因为两者语义不等价；
- 虚拟活动聚焦画布、实现覆盖率、声明输出和上下文输入等专属 UI 一并移除；
- `ActivityNode(level=3)` 继续只读兼容且禁止新增。

## 4. 目标图协议

图协议只服务于一张完整状态转移画布。资源树或筛选器可改变当前可见范围，但不能切换节点/边的业务语义。

### 4.1 状态引用实例

保持当前主要形态：

```json
{
  "id": "state_node:51:ref:901",
  "state_node_id": 51,
  "canonical_id": "state_node:51",
  "reference_id": 901,
  "reference_ids": [901],
  "parent_id": 10,
  "parent_graph_id": "state_node:10",
  "is_reference_instance": true,
  "metadata_json": {
    "_network_editor_layout": {"x": 320, "y": 180}
  }
}
```

### 4.2 活动引用实例

从当前聚合形态改为与状态一致：

```json
{
  "id": "atomic_activity:42:ref:700",
  "atomic_activity_id": 42,
  "canonical_id": "atomic_activity:42",
  "reference_id": 700,
  "reference_ids": [700],
  "parent_id": 20,
  "parent_graph_id": "activity_node:20",
  "is_reference_instance": true,
  "metadata_json": {
    "_network_editor_layout": {"x": 640, "y": 220}
  },
  "atomic_metadata_json": {
    "responsible_subsystem": "TRANSFER"
  }
}
```

同一原子活动在两个包中出现时返回两个引用实例。无包引用的原子活动保留 canonical library 节点：

```text
atomic_activity:42
```

它默认只出现在资源库或未布置列表，不在某个包容器中伪装成引用，也不构成第二画布视图。

### 4.3 完整状态转移投影

对每个可见的原子活动引用，画布按 canonical 绑定投影状态转移：

```text
state reference/canonical ── input ──> atomic activity reference
atomic activity reference ── output ──> state reference/canonical
```

投影规则：

- 优先命中当前可见的状态/活动引用实例，同时返回 canonical 端点；
- 包层级和成员引用是资源组织关系，可用容器、资源树或辅助连线表达，但不能混入 `input/output` 语义边；
- 活动缺少输入或输出时仍显示节点，并由结构校验标记问题，不通过隐藏节点制造“完整”假象；
- 同一 canonical 活动显示多个引用时，每个实例可显示相同 canonical 绑定，但有效模型和求解计数只计算一次；
- 图响应必须明确 `view_mode: "state_transition"`，不得随请求参数改变节点/边语义。

### 4.4 向后兼容

- 新增 `canonical_id` 和 `is_reference_instance` 为向后兼容字段；
- 保留 `atomic_activity_id`、`reference_id`、`reference_ids`；
- 前端在兼容窗口内同时识别旧 `atomic_activity:{id}` 和新 `atomic_activity:{id}:ref:{ref_id}`；
- 旧 `outline`、`implementation`、`solver_ready` 等 `view_mode` 在一个发布窗口内统一归一化为 `state_transition`，只返回相同投影并记录弃用诊断；
- 新前端不再发送 `view_mode` 切换请求；兼容窗口结束后删除旧枚举和参数；
- 求解预检、校验和影响分析不得依赖展示图 ID 直接解析业务主键，必须先 canonicalize；
- 历史 `context_input`、`declared_output` 响应字段在兼容窗口内可只读返回审计摘要，但不得生成图边或进入求解；
- 兼容窗口结束前，旧响应夹具和旧 API 消费方必须有回归。

## 5. 分阶段开发流程

## Phase 0：规格冻结与基线盘点

**目标：** 在改代码前证明当前数据和行为边界已知。

**涉及文件：**

- `docs/TICKET_097.md`
- 本计划
- 新增只读数据审计脚本，建议：`scripts/audit_body_reference_model.py`
- 新增或扩展测试夹具，不改生产行为

**步骤：**

- [ ] P0-1 统计每个机型的状态本体、原子状态、状态包、状态引用、活动包、原子活动、活动引用和绑定数量。
- [ ] P0-2 列出所有非聚合状态且 `parent_id IS NOT NULL` 的历史直接成员。
- [ ] P0-3 检查重复引用对、跨机型引用、孤儿引用、引用环和引用 metadata 布局冲突。
- [ ] P0-4 列出所有 `ActivityNode(level=3)`、仍绑定 `op_rule.activity_node_id` 的 legacy 数据及其计划使用情况。
- [ ] P0-5 盘点 `ActivityNode(level 1/2)` 上的 `context_input`、`declared_output` 等历史包级绑定，记录数量、使用方和历史计划引用，禁止直接删除或自动转换。
- [ ] P0-6 为同一原子活动被两个活动包引用、同一状态被两个状态包引用建立固定测试夹具。
- [ ] P0-7 盘点前后端全部 `view_mode`、纲要/实现/求解就绪切换、虚拟活动聚焦和专属统计调用点。
- [ ] P0-8 记录当前 Network Editor、layered solve、场景导入、全量后端和 Chromium 基线。
- [x] P0-9 盘点全部 Scope Guard 和历史痕迹；当前库两表为零、序列未调用、历史 JSONB 无命中，因此不执行相关数据库迁移。
- [ ] P0-10 增加发布前 Scope Guard 零数据断言测试；非零时返回阻塞诊断，不自动转换。
- [ ] P0-11 评审并冻结本文第 3、4 节。

**准出门禁：**

- 数据盘点报告可重复运行；
- 未知跨机型引用、孤儿引用或环必须先修复或形成明确阻塞项；
- 测试基线有实际通过数量和执行日期；
- 不允许在数据形态未知时直接执行迁移。

## Phase 1：统一领域判定与身份工具

**目标：** 吸收 TICKET-064，消除后端和前端对原子状态、活动包及 legacy 活动的分散判断。

**建议文件：**

- 新增：`app/core/modeling/semantics.py`
- 修改：`app/services/layered_expansion.py`
- 修改：`app/services/layered_health.py`
- 修改：`app/services/network_editor.py`
- 修改：`app/api/v1/master_data.py`
- 修改：相关前端投影 helper
- 新增：`tests/unit/test_modeling_semantics.py`

**步骤：**

- [ ] P1-1 定义唯一判定函数：`is_state_package()`、`is_atomic_state()`、`is_activity_package()`、`is_legacy_executable_activity()`；不得继续新增 `is_virtual_activity_*` 领域命名。
- [ ] P1-2 原子状态以明确业务语义为准，不再分别使用 `is_leaf`、无子节点或单独 `feature_key` 判断。
- [ ] P1-3 集中定义 canonical/display 图 ID 的生成与解析，禁止在多个调用点手写字符串切分。
- [ ] P1-4 所有 API、展开、健康检查、网络图、覆盖快照和前端投影改用统一 helper。
- [ ] P1-5 对历史缺少 `state_kind` 但具备有效事实的数据提供只读兼容判定，并产生审计 warning。
- [ ] P1-6 集中定义唯一用户画布常量 `state_transition`；旧视图枚举只能存在于兼容适配层。

**准出门禁：**

- 新增单元测试覆盖 aggregate、atomic、external/manual、legacy childless package 和脏数据；
- 现有 layered expansion/health/network editor 回归结果不变；
- TICKET-064 的分散判定命中扫描归零或只剩明确 legacy 兼容点。

## Phase 2：数据库迁移与约束收紧

**目标：** 把原子状态成员统一成引用，并阻止数据库级危险级联。

**涉及文件：**

- 新增：`migrations/versions/014_body_reference_unification.py`
- 修改：`app/db/models.py`
- 修改：`app/db/schemas.py`
- 新增：迁移专项测试

**迁移顺序：**

1. 迁移前执行 Phase 0 审计并保存报告。
2. 找出 `state_kind != 'aggregate' AND parent_id IS NOT NULL` 的状态。
3. 对每条记录：
   - 若 `(state_node_id, parent_state_node_id)` 引用不存在，创建 `StateNodeReference`；
   - 复制该状态原来的 `sort_order`、`is_active`；
   - `_network_editor_layout` 等包内布局优先写到新引用 metadata；
   - 若引用已存在，保留已有引用 metadata，不覆盖用户已维护布局。
4. 将这些原子状态的 `parent_id` 置空。
5. 增加约束：非 `aggregate` 状态不得拥有 `parent_id`。
6. 调整外键删除策略：
   - 被引用状态本体删除使用 `RESTRICT`；
   - 被绑定状态本体删除使用 `RESTRICT`；
   - 被引用原子活动删除使用 `RESTRICT`；
   - 被绑定或被规则使用的原子活动删除不得级联或静默 `SET NULL`；
   - 删除包时允许删除以该包为父端的成员引用，但不删除成员本体。
7. 保留包到包主层级，不迁移所有 aggregate `parent_id`。
8. 历史包级活动—状态绑定不自动删除、不转成原子绑定；迁移审计给出 `context_input`、`declared_output` 数量，应用层禁止新增并从有效模型中排除。
9. Scope Guard 表和前置条件表本阶段不物理删除、不迁移；应用层关闭写入和求解读取，发布审计要求两表持续为零。

**降级策略：**

约束和外键可以通过 Alembic downgrade 恢复；引用化后的数据不做自动反向折叠，因为一个本体可能已有多个引用，自动选择一个 `parent_id` 会丢失语义。数据级回滚必须使用迁移前 PostgreSQL 备份。

**准出门禁：**

- PostgreSQL 从 013 升级到 014 成功；
- 重复执行审计后，直接挂包的原子状态数量为 0；
- 引用数量与迁移输入对应，无重复对；
- 所有原状态的状态包可见性、布局和 active 状态保持；
- downgrade 约束演练成功，数据回滚流程用备份完成一次演练；
- SQLite 测试环境与 PostgreSQL 行为差异被显式记录。
- 历史包级绑定数量在迁移前后相同，并有明确只读审计报告。
- Scope Guard 两表为零，且本次 migration 没有包含任何 Scope Guard DDL/DML。

## Phase 3：API、Service 与统一提交收敛

**目标：** 所有写入口遵守同一成员引用和删除规则。

**建议文件：**

- 新增：`app/services/body_reference.py`
- 修改：`app/api/v1/master_data.py`
- 修改：`app/db/schemas.py`
- 修改：Network Editor commit change handler
- 修改：`frontend/src/api/masterData.js`
- 修改：`tests/integration/test_master_data_api.py`

**步骤：**

- [ ] P3-1 原子状态创建 API 拒绝新的非空 `parent_id`；需要加入包时由调用方同事务创建本体和引用。
- [ ] P3-2 Network Editor 的 body + ref 草稿继续支持 `_draft_ref`，但统一走共享 Service。
- [ ] P3-3 `ActivityPackageAtomicRefUpdate` 不再允许修改 `atomic_activity_id`；旧客户端尝试改端点返回 `RELATION_ENDPOINT_IMMUTABLE`。
- [ ] P3-4 状态引用和活动引用更新只允许排序、启用和 metadata。
- [ ] P3-5 `ActivityStateBinding` 更新只允许覆盖范围、启用和 metadata；端点或角色变化转换为 delete + create。
- [ ] P3-6 本体删除前统一检查引用、规则、绑定、Scope Guard、计划步骤和其他持久化使用方。
- [ ] P3-7 在用本体删除返回 409，响应包含引用类型和计数；前端提示“先移除引用/停用本体”。
- [ ] P3-8 移除引用接口只删除关系，不触碰本体。
- [ ] P3-9 改名/改码继续使用原记录 UPDATE；禁止通过“删旧建新”实现重命名。
- [ ] P3-10 所有跨机型成员引用和绑定继续返回 422。
- [ ] P3-11 revision 指纹同时覆盖本体字段和引用字段；改名、引用布局变化都应更新 revision。
- [ ] P3-12 禁止为活动包创建/更新 `context_input`、`declared_output` 等包级状态绑定，返回 `ACTIVITY_PACKAGE_BINDING_SUNSET`。
- [ ] P3-13 图查询和有效模型解析默认过滤历史包级绑定；审计接口可只读查询但不能回写。
- [ ] P3-14 Scope Guard create/update/copy 接口关闭并返回 `SCOPE_GUARD_SUNSET`；历史查询仅在审计接口保留。
- [ ] P3-15 原子活动输入绑定成为唯一运行时准入条件来源；禁止在普通 CRUD 中通过包 ID 隐式补充条件。
- [ ] P3-16 求解/展开请求新增 canonical `atomic_activity_scope_ids`；空集合表示全部 active 原子活动。
- [ ] P3-17 旧 `activity_scope_node_ids` 在一个兼容窗口内仅作为边界适配：解析成去重的 canonical 原子活动 ID 后立即丢弃包路径，并返回弃用诊断。

**建议错误码：**

| 错误码 | 场景 |
|---|---|
| `ATOMIC_STATE_PARENT_FORBIDDEN` | 新原子状态试图直接设置 `parent_id` |
| `RELATION_ENDPOINT_IMMUTABLE` | 更新引用或绑定时试图改变端点/语义角色 |
| `BODY_IN_USE` | 删除仍被引用/绑定/规则/计划使用的本体 |
| `REFERENCE_CROSS_MACHINE_TYPE` | 包与本体不属于同一机型 |
| `LEGACY_EXECUTABLE_CREATE_FORBIDDEN` | 新建 `ActivityNode(level=3)` |
| `ACTIVITY_PACKAGE_BINDING_SUNSET` | 新建或编辑历史虚拟活动的包级状态绑定 |
| `SCOPE_GUARD_SUNSET` | 新建、编辑、复制或导入 Scope Guard |

**准出门禁：**

- API 专项覆盖 create/update/delete/rename/ref move；
- 统一提交任一失败整批回滚；
- 本体删除无任何隐式级联；
- 旧合法请求保持兼容，旧端点改绑请求得到明确错误；
- 新增或编辑虚拟活动、包级绑定和 Scope Guard 的所有 API 路径均被关闭。

## Phase 4：全部写路径统一

**目标：** 避免主 API 已收敛，但导入、种子或旧页面继续写回旧结构。

**涉及文件：**

- `app/services/scenario_import.py`
- `frontend/src/views/DataManagement/StateTargetWorkspace.vue`
- `frontend/src/views/DataManagement/ActivityCapabilityWorkspace.vue`
- `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- `seeds/*.sql`
- 场景模板与导入文档

**步骤：**

- [ ] P4-1 State Target 新建原子状态时始终先创建库本体，再创建包成员引用。
- [ ] P4-2 Activity Capability 新建原子活动时始终创建 `AtomicActivity`，挂包时创建 `ActivityPackageAtomicRef`。
- [ ] P4-3 Network Editor 草稿中的原子状态和原子活动包归属统一为引用 create，不再给本体写 parent/package metadata。
- [ ] P4-4 场景 Excel 导入把原子状态的包归属翻译成 `state_node_reference`；已有旧列只作为兼容输入。
- [ ] P4-5 场景导入和种子禁止新增 `ActivityNode(level=3)`；legacy 输入仍可读取并给出迁移 warning。
- [ ] P4-6 清点所有测试夹具和 seed，新增数据全部使用引用模型。
- [ ] P4-7 旧 payload normalizer 只做兼容转换并记录诊断，不继续向数据库写旧形态。
- [ ] P4-8 场景导入、种子和旧页面禁止创建“虚拟活动”或包级状态绑定；历史输入只记录弃用诊断，不导入为有效转移。
- [ ] P4-9 场景导入和种子禁止新增 Scope Guard；新工艺条件必须写为原子活动 `input` 绑定。

**准出门禁：**

- 新建数据经 API、Network Editor、State Target、Activity Capability、Excel 导入和 seed 六条路径后形态一致；
- 导入失败整批回滚；
- 重复导入不产生重复本体或重复引用；
- 旧场景文件仍能读取并显示迁移提示；其中 Scope Guard 只进入审计/人工决策报告，不直接写入当前有效模型。

## Phase 5：Network Editor 唯一完整状态转移投影

**目标：** 只生成一套完整状态转移图；活动引用实例达到与状态引用实例相同的可读性和独立布局能力。

**涉及文件：**

- `app/services/network_editor.py`
- `app/db/schemas.py`
- `tests/integration/test_master_data_api.py`
- Network Editor 前端投影 helper

**步骤：**

- [ ] P5-1 增加 `_atomic_reference_graph_id(atomic_id, ref_id)` 和统一 parser。
- [ ] P5-2 每个 active `ActivityPackageAtomicRef` 投影为一个独立图节点。
- [ ] P5-3 引用节点的 `metadata_json` 只来自引用；本体 metadata 通过 `atomic_metadata_json` 单独返回。
- [ ] P5-4 无引用本体保留 canonical library node，但不伪造 parent。
- [ ] P5-5 状态和活动节点统一返回 `canonical_id`、`reference_id`、`is_reference_instance`。
- [ ] P5-6 绑定边连接当前可见引用实例，同时保留 canonical source/target；不再依赖虚拟活动或活动包聚焦语义。
- [ ] P5-7 影响分析、问题定位、选中态和局部展开先 canonicalize，再访问业务数据。
- [ ] P5-8 图响应固定为 `view_mode: "state_transition"`，完整返回输入状态、原子活动、输出状态及其绑定。
- [ ] P5-9 revision 包含引用布局和引用启用状态，保证并发编辑冲突可检测。
- [ ] P5-10 旧 `outline`、`implementation`、`solver_ready` 请求在兼容层归一化为同一 `state_transition` 投影并记录弃用诊断。
- [ ] P5-11 历史包级 `context_input`、`declared_output` 绑定不生成节点或边；活动包仅作为资源组织上下文。
- [ ] P5-12 求解预检直接 canonicalize 这套有效模型并去重，不生成或缓存第二套“求解图”。
- [ ] P5-13 Scope Guard 不生成图边、继承边或隐藏前置条件；转换后的原子活动 `input` 绑定按普通状态转移边展示。

**准出门禁：**

- 同一原子活动在两个包中返回两个不同 display graph ID；
- 两个节点具有相同 `canonical_id` 和不同 `reference_id`；
- 拖动或停用一个引用只改变该引用；
- 语义边在画布命中正确实例，后台绑定 ID 和 canonical 端点不变；
- 每条有效转移可读为“输入状态 → 原子活动 → 输出状态”；
- 任意旧视图参数得到相同节点/边语义，不再存在第二套业务投影；
- 求解预检和 impact 统计不会把同一本体重复计数。

## Phase 6：前端单一画布与交互统一

**目标：** 用户只在完整状态转移画布中工作，并能明确区分“编辑本体”“移除引用”“停用引用”“停用本体”。

**涉及文件：**

- `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`
- `frontend/src/views/DataManagement/ActivityCapabilityWorkspace.vue`
- `frontend/src/views/DataManagement/StateTargetWorkspace.vue`
- `frontend/e2e/tests/network-editor.spec.ts`
- `frontend/e2e/tests/network-editor-full-flow.spec.ts`

**步骤：**

- [ ] P6-1 活动资源树按引用实例显示原子活动，可同时出现在多个活动包下。
- [ ] P6-2 X6 使用 display graph ID 作为 cell ID，使用 canonical ID 做业务选择和绑定。
- [ ] P6-3 两个活动引用实例独立保存位置和包内显示信息。
- [ ] P6-4 引用实例右键动作明确为“编辑原子活动本体 / 从当前活动包移除 / 在当前包停用”。
- [ ] P6-5 本体库动作明确为“编辑本体 / 停用本体 / 删除未使用本体”。
- [ ] P6-6 改名后所有引用实例显示新名称，但坐标、引用 ID 和草稿选择不丢失。
- [ ] P6-7 删除纲要、实现/聚焦、求解视图的页签/切换器及相关路由状态，只保留状态转移画布。
- [ ] P6-8 前端仍兼容旧 canonical-only activity graph fixtures，兼容期结束后再清理。
- [ ] P6-9 删除“虚拟活动”创建、编辑、聚焦、声明输出、上下文输入和实现覆盖率等专属入口与文案。
- [ ] P6-10 求解预检保留为状态转移画布工具栏动作，结果在侧栏/面板展示并定位到同一画布节点，不切换画布。
- [ ] P6-11 统一提交预检区分结构错误、删除冲突和求解有效性问题。
- [ ] P6-12 活动包只出现在资源树、筛选器和管理上下文中，不渲染为可执行转移节点。
- [ ] P6-13 删除 Scope Guard 创建/编辑入口；历史 Guard 只在迁移审计报告中查看，不能从 Network Editor 恢复为包级约束。
- [ ] P6-14 用户按活动包筛选候选时，前端明确展示解析出的原子活动集合，并向预检/求解提交 canonical `atomic_activity_scope_ids`，不提交包路径作为求解语义。

**准出门禁：**

- 浏览器自动化覆盖双包活动引用、双包状态引用、独立拖动、改名、移除引用、删除保护；
- 取消编辑恢复已提交引用布局；
- 统一提交只有一次写库请求；
- 预览模式不能产生引用或删除草稿；
- 页面不再用“删除活动”混淆“移除活动包引用”；
- 页面无业务视图切换器，无纲要/求解/虚拟活动/Scope Guard 编辑入口；
- 求解预检完成前后始终停留在同一状态转移画布。

## Phase 7：求解与知识图谱读取回归

**目标：** 引用实例增强不能改变 canonical 求解模型。

**涉及文件：**

- `app/services/layered_expansion.py`
- `app/services/layered_health.py`
- `app/services/layered_solve.py`
- `app/core/scheduler/loader.py`
- `app/services/network_editor.py`
- 对应 unit/integration tests

**步骤：**

- [ ] P7-1 状态包成员展开统一读取 `StateNodeReference`，迁移前后 goal facts 一致。
- [ ] P7-2 原子活动候选按 canonical `AtomicActivity`/`OpRule` 识别，不按画布实例重复。
- [ ] P7-3 明确测试空原子活动 scope、显式 `atomic_activity_scope_ids` 和旧包 scope 兼容解析三条路径。
- [ ] P7-4 删除 Scope Guard package path 的 effective preconditions 合并；有效规则只读取原子活动自身规则和 `input` 绑定。
- [ ] P7-5 同一原子活动有多个活动引用时，有效前置条件必须完全相同，不读取任一“主引用”或包路径。
- [ ] P7-6 Scheduler task、活动分组、状态连续性分组和解释字段不使用 display graph ID 作为业务身份。
- [ ] P7-7 健康检查对同一本体多引用不误报重复 provider；真正多个不同本体 provider 仍正常提示。
- [ ] P7-8 历史计划回放继续读取保存时的规则和状态快照，不依赖当前引用布局。
- [ ] P7-9 求解预检与 layered solve 使用同一个 canonical 有效模型解析入口，不读取 `view_mode` 分支或历史包级状态绑定。
- [ ] P7-10 对历史 `context_input`、`declared_output` 建立负向回归：可审计但不产生候选、事实或计划步骤。
- [ ] P7-11 对历史 Scope Guard 建立负向回归：当前求解不读取；对已安全转换项，只由新建的原子活动 `input` 绑定产生前置条件。
- [ ] P7-12 删除仅由 Scope Guard 继承产生的 `SELF_DEPENDENCY` 检查分支；普通原子状态—活动循环仍由 canonical 图健康检查负责。
- [ ] P7-13 默认候选从 active `AtomicActivity` 库直接产生，不以是否有活动包引用或引用 `is_active` 决定是否可求解。

**准出门禁：**

- 同一原子活动引用两次不会在单次计划中无故生成两个相同 canonical 任务；
- 活动包移动、换父级或增删引用不会改变候选活动的 effective preconditions；
- Scope Guard 表存在与否不会改变当前求解；安全转换后的输入绑定能产生等价前置条件；
- layered expansion、health、solver precheck、layered solve 和 Scheduler loader 专项全部通过；
- 求解侧不存在依赖纲要图、求解图、虚拟活动投影或 Scope Guard 包路径的读取分支；
- 迁移前后的固定业务场景得到相同目标事实、候选规则集合和计划结果，允许仅展示路径 metadata 变化。

## Phase 8：文档、术语与兼容收口

**涉及文件：**

- `docs/ANCHOR.md`（仅在需要锁定永久术语时修改）
- `docs/状态活动网络图编辑器_需求设计文档.md`
- `docs/layered_activity_state_requirements.md`
- `docs/network-editor-user-guide.md`
- `docs/network-editor-acceptance-matrix.md`
- `docs/protocols/db.md`
- `docs/protocols/api.md`
- `docs/STATE_V0.3.md`
- `scripts/check_terminology.py`

**步骤：**

- [ ] P8-1 ORM/Schema 注释从“additional display parent”改为“状态包成员引用”。
- [ ] P8-2 文档明确包到包主层级与包到原子成员引用的边界。
- [ ] P8-3 用户说明加入改名、移除引用、停用本体和删除保护。
- [ ] P8-4 验收矩阵增加活动引用实例独立布局和 canonical 求解去重证据。
- [ ] P8-5 协议文档记录 display/canonical graph ID 与兼容窗口。
- [ ] P8-6 STATE 记录迁移、验证结果、遗留 legacy 数量和后续票据。
- [ ] P8-7 术语守护阻止“虚拟活动”“活动包包含/拥有原子活动”“引用删除即删除本体”等错误文案回流；仅允许在迁移/日落说明中出现旧术语。
- [ ] P8-8 用户说明和验收矩阵只描述完整状态转移视图；求解预检明确为动作/面板，不再描述为视图。
- [ ] P8-9 协议标注旧 `view_mode` 归一化窗口、删除版本以及包级状态绑定的只读审计策略。
- [ ] P8-10 文档明确活动包是纯管理结构，Scope Guard 已日落，工艺准入条件只能通过原子状态—原子活动 `input` 绑定表达。
- [ ] P8-11 STATE 记录 Scope Guard 分类数量、安全转换映射、人工决策清单和历史回放证据。

## 6. 测试与验收矩阵

### 6.1 单元测试

| 编号 | 场景 | 预期 |
|---|---|---|
| UT-01 | 原子状态判定 | 所有后端入口得到一致结果 |
| UT-02 | 状态包判定 | aggregate 包与历史脏数据有稳定诊断 |
| UT-03 | graph ID parser | canonical/ref/draft ID 可双向解析 |
| UT-04 | 引用端点更新 | 换端点被拒绝 |
| UT-05 | 绑定端点/角色更新 | 转换为删除旧关系并创建新关系 |
| UT-06 | 删除依赖收集 | 返回引用、规则、绑定、计划使用计数 |
| UT-07 | revision 指纹 | 本体改名或引用布局变化会更新 revision |
| UT-08 | 旧 `view_mode` 归一化 | 全部得到 `state_transition`，节点/边语义一致 |
| UT-09 | 包级绑定过滤 | `context_input`、`declared_output` 不进入有效模型 |
| UT-10 | Scope Guard 零数据门禁 | 两表为零时通过，非零时阻止发布且不写库 |

### 6.2 API / Service 集成测试

| 编号 | 场景 | 预期 |
|---|---|---|
| IT-01 | 创建原子状态并加入两个状态包 | 一条本体、两条引用 |
| IT-02 | 创建原子活动并加入两个活动包 | 一条本体、两条引用 |
| IT-03 | 重复加入同一包 | 409，不产生重复引用 |
| IT-04 | 跨机型引用 | 422 |
| IT-05 | 改名/改码 | 本体 ID、引用 ID、绑定 ID 不变 |
| IT-06 | 移除一个引用 | 本体和其他引用仍存在 |
| IT-07 | 删除在用本体 | 409，无级联删除 |
| IT-08 | 删除未使用本体 | 204 |
| IT-09 | 统一提交 body + ref + binding | 同事务成功 |
| IT-10 | 统一提交中任一步失败 | 全部回滚 |
| IT-11 | revision 冲突 | 409，草稿可保留 |
| IT-12 | 场景重复导入 | 不重复本体或引用 |
| IT-13 | 修改绑定端点或角色 | 旧绑定删除，新绑定使用新 ID |
| IT-14 | 新建/编辑包级状态绑定 | 返回 `ACTIVITY_PACKAGE_BINDING_SUNSET` |
| IT-15 | 旧视图参数请求图 | 返回同一状态转移投影并包含弃用诊断 |
| IT-16 | 新建/编辑/导入 Scope Guard | 返回 `SCOPE_GUARD_SUNSET` |
| IT-18 | 旧活动包 scope 请求 | 兼容层解析为 canonical 原子活动集合并返回弃用诊断 |

### 6.3 图投影测试

| 编号 | 场景 | 预期 |
|---|---|---|
| GP-01 | 状态双包引用 | 两个 display ID，一个 canonical ID |
| GP-02 | 活动双包引用 | 两个 display ID，一个 canonical ID |
| GP-03 | 引用独立布局 | metadata 分别来自两条引用 |
| GP-04 | 绑定边端点投影 | display 端点正确，canonical 端点不变 |
| GP-05 | 完整状态转移 | 每个有效活动可读为输入状态 → 原子活动 → 输出状态 |
| GP-06 | 影响分析 | 选择任一引用得到同一本体业务影响和当前包上下文 |
| GP-07 | include_inactive | 可审计停用引用，默认求解过滤 |
| GP-08 | 单一视图协议 | 仅返回 `state_transition`，无替代投影 |
| GP-09 | 虚拟活动历史数据 | 包级状态绑定不投影为图边 |
| GP-10 | 历史 Scope Guard | 不投影为边；转换后的 `input` 绑定正常显示 |

### 6.4 求解回归

| 编号 | 场景 | 预期 |
|---|---|---|
| SV-01 | 引用化状态包目标 | goal facts 与迁移前一致 |
| SV-02 | 双包原子活动 | 不重复计划同一 canonical 活动 |
| SV-03 | 显式原子活动 scope | 只读取提交的 canonical 原子活动 ID |
| SV-04 | 空活动 scope | 维持当前默认全部原子活动行为 |
| SV-05 | Scope Guard 日落 | 当前有效模型不读取包路径 Guard |
| SV-06 | 状态覆盖快照 | complete/partial/stale 结果一致 |
| SV-07 | 历史计划回放 | 当前改名/布局不影响历史模型重放 |
| SV-08 | 预检与正式求解模型 | canonical 活动、状态、绑定集合一致 |
| SV-09 | 历史包级绑定 | 不产生事实、候选或计划步骤 |
| SV-10 | Scope Guard 空表 | 不产生任何隐藏 effective preconditions |
| SV-12 | 活动包重组/引用启停 | canonical 候选及有效前置条件不变 |

### 6.5 浏览器验收

| 编号 | 操作 | 预期 |
|---|---|---|
| E2E-01 | 将同一状态引用到两个状态包 | 两个引用节点独立显示 |
| E2E-02 | 将同一活动引用到两个活动包 | 两个引用节点独立显示 |
| E2E-03 | 分别拖动两个引用 | 互不影响 |
| E2E-04 | 修改本体名称 | 两个引用同步显示新名称，位置不变 |
| E2E-05 | 从一个包移除引用 | 另一包引用和本体仍存在 |
| E2E-06 | 删除仍在用本体 | 显示依赖冲突，无数据丢失 |
| E2E-07 | 取消编辑 | 所有未提交引用和布局恢复 |
| E2E-08 | 统一提交 | body/ref/binding 一次提交并正确刷新 |
| E2E-09 | 求解预检 | canonical 计数不因引用数量膨胀 |
| E2E-10 | 打开 Network Editor | 只存在完整状态转移画布，无业务视图切换器 |
| E2E-11 | 执行求解预检 | 结果面板打开，画布不切换且问题可定位 |
| E2E-12 | 搜索旧产品入口 | 无虚拟活动创建/编辑/聚焦和包级状态绑定入口 |
| E2E-13 | 搜索 Scope Guard 入口 | 无创建/编辑入口，历史数据仅在审计报告可见 |

## 7. 业务验收流程

### 7.1 验收环境准备

1. 从可恢复备份创建独立 PostgreSQL 验收库。
2. 将数据库迁移到当前 013 head，加载固定 Network Editor 与 layered solve 场景。
3. 保存迁移前审计报告、关键表行数和固定求解响应摘要。
4. 运行后端、前端 build 和 Chromium 基线，确认环境本身可用。
5. 升级到 014，再运行迁移后审计。

### 7.2 UAT-01：状态本体复用

1. 创建原子状态“模块 A 已安装”。
2. 分别引用到“结构安装完成”和“整机集成完成”两个状态包。
3. 在两个包中设置不同位置和排序。
4. 修改本体名称为“模块 A 安装完成”。
5. 从第一个包移除引用。

**验收结果：**

- 数据库始终只有一个状态本体；
- 两个引用 ID 不同；
- 改名后两个引用同步显示新名称；
- 布局和引用 ID 不变；
- 移除一个引用后另一个引用、绑定和本体仍存在。

### 7.3 UAT-02：原子活动复用

1. 创建原子活动“安装模块 A”并绑定输入/输出状态和规则。
2. 引用到“结构安装”和“总装实现”两个活动包。
3. 在完整状态转移画布中摆放两个活动引用实例。
4. 通过资源树筛选两个活动包，分别检查同一 canonical 输入/输出边；画布类型始终不变。
5. 执行 solver precheck 和 layered solve。

**验收结果：**

- 数据库只有一个 `AtomicActivity`、一套 canonical 规则和绑定；
- 有两个活动包引用和两个画布实例；
- 两个实例的边显示到当前包内节点，但 canonical 端点相同；
- 全程只有完整状态转移视图，求解预检在结果面板展示；
- 求解预检和最终计划不因两个引用重复生成相同任务。

### 7.4 UAT-03：身份与改名

1. 记录本体 ID、引用 ID、绑定 ID、规则 ID 和 graph canonical ID。
2. 修改本体名称和编码。
3. 刷新页面并重新进入编辑。

**验收结果：**

- 所有记录 ID 和引用关系不变；
- Network Editor revision 已变化；
- 新会话显示新名称/编码；
- 历史计划快照仍可重放。

### 7.5 UAT-04：安全删除

1. 尝试删除仍有两个引用、规则和绑定的原子活动。
2. 逐个移除包引用，但保留规则和绑定，再次删除。
3. 停用规则并移除绑定，再检查历史计划使用。
4. 仅在所有依赖清除且无历史使用时删除。

**验收结果：**

- 前三步均得到明确依赖冲突；
- 任一步失败后引用、规则、绑定数量不变；
- 页面提供移除引用或停用本体的正确建议；
- 真正未使用本体才能删除。

### 7.6 UAT-05：历史数据迁移

1. 准备一个原子状态通过 `parent_id` 直接挂包且带布局的 013 数据库。
2. 升级到 014。
3. 打开相同状态包和 Network Editor。
4. 执行相同 layered solve。

**验收结果：**

- 原子状态 `parent_id` 为空；
- 新增一条对应 `StateNodeReference`；
- 原布局、排序、启用和包内可见性保持；
- 目标事实、候选规则和求解结果与迁移前基线一致。

### 7.7 UAT-06：Scope Guard 日落与零数据门禁

1. 执行发布审计，确认 `scope_guard`、`scope_guard_precond` 和历史痕迹均为零。
2. 调整活动包父级、移动引用并重新执行 expansion、health、solver precheck 和 solve。
3. 尝试新增、编辑或导入 Scope Guard。
4. 在隔离测试事务中构造非零门禁输入，确认发布审计阻塞且不修改数据。

**验收结果：**

- 本票据没有执行 Scope Guard DDL/DML 或输入绑定转换；
- 活动包结构和成员变化不改变 effective preconditions 或求解结果；
- 当前求解不读取 Scope Guard；
- Scope Guard 新增、编辑和导入均被明确拒绝；
- 发布门禁在非零时停止且不做自动迁移；
- 历史求解仍使用当次模型版本和快照完成重放。

### 7.8 UAT-07：单一视图与虚拟活动日落

1. 打开 Network Editor，检查工具栏、页签、路由状态和资源树。
2. 加载包含输入状态、原子活动、输出状态、活动包以及历史 `context_input`/`declared_output` 的固定场景。
3. 分别使用旧 `outline`、`implementation`、`solver_ready` 参数调用图接口。
4. 在画布执行求解预检并定位一个结构问题。
5. 尝试新建虚拟活动或为活动包新增包级状态绑定。

**验收结果：**

- 页面只存在完整状态转移画布，不存在纲要/求解视图切换器；
- 三个旧参数均得到同一 `state_transition` 节点/边集合和明确弃用诊断；
- 活动包不作为可执行转移节点，历史包级绑定不显示为状态转移边；
- 求解预检结果在同一画布的面板中展示并可定位节点；
- 虚拟活动和包级状态绑定写入被明确拒绝，历史记录仍可通过审计接口只读查询。

## 8. 自动化执行顺序

实施完成后按以下顺序运行，任一步失败都停止进入下一门禁：

```powershell
# 1. 语法与术语
.venv\Scripts\python.exe -m py_compile <本票据修改的 Python 文件>
.venv\Scripts\python.exe scripts\check_terminology.py

# 2. 单元测试
.venv\Scripts\python.exe -m pytest tests\unit\test_modeling_semantics.py -q --basetemp .pytest-tmp\t97-unit

# 3. 聚焦集成
.venv\Scripts\python.exe -m pytest tests\integration\test_master_data_api.py -q --basetemp .pytest-tmp\t97-master-data
.venv\Scripts\python.exe -m pytest tests\integration\test_state_group_continuity.py -q --basetemp .pytest-tmp\t97-layered
.venv\Scripts\python.exe -m pytest tests\integration\test_scenario_import_api.py -q --basetemp .pytest-tmp\t97-import

# 4. 前端
Set-Location frontend
npm.cmd run build
npm.cmd run test:e2e -- e2e/tests/network-editor.spec.ts --project=chromium
npm.cmd run test:e2e -- e2e/tests/network-editor-full-flow.spec.ts --project=chromium

# 5. 全量
Set-Location ..
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp\t97-full

# 6. 变更检查
git diff --check
```

迁移必须额外在真实 PostgreSQL 执行：

```powershell
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe current
.venv\Scripts\python.exe scripts\audit_body_reference_model.py
```

审计脚本必须显示 Scope Guard 两表为零。测试通过数量不得低于实施前 Phase 0 基线；如测试总数因新增用例增加，应记录新增数量和完整结果。

## 9. 数据完整性准出条件

发布前审计必须满足：

- 非 aggregate 状态 `parent_id IS NOT NULL`：0；
- 同一包—本体重复引用：0；
- 跨机型状态引用：0；
- 跨机型活动引用：0；
- 孤儿状态引用：0；
- 孤儿活动引用：0；
- 引用端点原地变更能力：关闭；
- 绑定端点或语义角色原地变更能力：关闭；
- 仍被引用/绑定/规则/计划使用但可被直接删除的本体：0；
- 求解有效模型中重复 canonical 原子活动：0；
- 网络图引用节点缺少 `canonical_id`：0；
- 引用布局错误写入本体 metadata：0；
- 用户可切换业务图投影数量：1（`state_transition`）；
- 新增活动包级 `context_input`/`declared_output` 写入口：0；
- 历史包级状态绑定进入图投影或求解模型的数量：0；
- Scope Guard 新增/编辑/导入写入口：0；
- 历史 Scope Guard 进入当前图投影或求解模型的数量：0；
- 求解核心读取活动包层级、活动包引用或 Scope Guard 的入口：0。

## 10. 发布与回滚流程

### 发布前

1. 冻结主数据写入窗口。
2. 完成 PostgreSQL 全量备份并验证可恢复。
3. 保存 Phase 0 审计报告和迁移前关键计数。
4. 先在副本库执行 013 → 014 升级、应用启动和完整验收。
5. 对比迁移前后固定 solve 摘要。

### 发布

1. 应用 014 migration。
2. 立即执行数据完整性审计。
3. 启动后端和前端。
4. 执行 UAT-01、UAT-02、UAT-05、UAT-06、UAT-07 最小烟雾验收。
5. 解除写入窗口。

### 回滚触发条件

- 迁移后存在原子状态直接 `parent_id`；
- 引用数量不符合迁移输入；
- Network Editor 无法加载或引用布局丢失；
- 状态转移图缺失有效输入/输出绑定，或重新出现多业务视图分支；
- 求解有效模型出现重复 canonical 活动；
- 历史包级状态绑定进入图投影或求解；
- 历史 Scope Guard 继续通过包路径进入求解，或歧义 Guard 被自动合并；
- 固定 layered solve 的事实或计划结果发生未解释变化；
- 删除保护仍可造成级联数据丢失。

### 回滚动作

1. 立即停止主数据写入。
2. 回退应用版本。
3. 对约束/外键问题可执行 Alembic downgrade。
4. 涉及引用化数据逆转时，不自动把多引用折叠回 `parent_id`，直接恢复迁移前数据库备份。
5. 重新运行 Phase 0 审计确认恢复完成。

## 11. 验收证据包

TICKET 完成时必须在票据或 STATE 中记录：

- 013 → 014 PostgreSQL migration 输出和 current head；
- 迁移前后审计报告；
- 数据完整性全部准出结果；
- 单元、聚焦集成、全量后端、Vite build、Chromium 测试数量；
- UAT-01 至 UAT-07 的结果摘要；
- 固定 layered solve 迁移前后对比；
- `git diff --check` 和术语检查结果；
- 剩余 legacy `ActivityNode(level=3)` 数量；
- 剩余历史 `context_input`、`declared_output` 数量及其未参与图/求解的证据；
- 旧 `view_mode` 调用数量、兼容诊断和计划删除版本；
- Scope Guard 两表和历史痕迹为零、且本票据未执行相关数据库迁移的证据；
- 多包 Scheduler 连续性归属未改动的明确说明；
- 后续版本仓库/稳定跨版本身份票据的链接。

## 12. Definition of Done

只有同时满足以下条件，TICKET-097 才能标记完成：

1. 所有新增原子状态和原子活动只通过引用加入包；
2. 历史直接挂包的原子状态已安全迁移；
3. 状态引用与活动引用都拥有独立图实例和布局；
4. 图展示端点与 canonical 求解端点明确分离；
5. 引用端点不可原地修改；
6. 活动—状态绑定改变端点或角色时使用新的关系 ID；
7. 移除引用不删除本体；
8. 在用本体不能删除，且无级联数据丢失；
9. 改名/改码不改变身份；
10. Network Editor 只有完整状态转移视图，旧视图参数不再产生不同投影；
11. 求解预检是同一画布上的动作/面板，与正式求解读取同一 canonical 有效模型；
12. “虚拟活动”及其创建、聚焦、包级状态绑定和专属统计入口已日落；
13. 历史包级绑定只读可审计，但不进入图投影、有效模型或求解；
14. Scope Guard 写入口和包路径求解继承已关闭，历史数据仅用于审计；
15. Scope Guard 两表保持为零，本票据未执行相关数据库迁移或转换；
16. 求解候选和范围使用 canonical 原子活动，活动包只作为界面管理/筛选入口；
17. 活动包结构、层级、成员和引用启停调整不改变 canonical 有效模型；
18. layered expansion、health、solver precheck、Scheduler 和历史回放通过新的语义回归；
19. 自动化、真实 PostgreSQL、真实 Chromium 和业务 UAT 全部通过；
20. 用户说明、协议、验收矩阵、STATE 和 TICKET 已同步；
21. 所有遗留项都有明确后续票据，不以隐藏兼容分支留在主流程中。

# 机台知识库与版本变更管理前端 MVP：开发与验收计划

> Status: Planned
> Scope: MVP v1
> Date: 2026-07-28
> Ticket: [TICKET-098](../../TICKET_098.md)
> Design authority: [前端设计基线](../../机台知识库与版本变更管理_前端设计基线.md)
> API and data authority: [后端设计基线](../../机台知识库与版本变更管理_后端设计基线.md)
> Backend execution plan: [后端开发与验收计划](./2026-07-28-machine-knowledge-backend-mvp.md)
> Integration plan: [前后端贯通与发布计划](./2026-07-28-machine-knowledge-integration-mvp.md)

---

## 0. 计划定位

本文档把冻结的前端设计基线拆成可编码、可测试、可分阶段验收的 F0–F9 实施任务。

本文档负责：

- 当前前端差距和保留边界；
- 页面、路由、共享状态、草稿和组件改造；
- API 在前端的封装位置与调用时机；
- 版本历史、差异、回写、升级和重放交互；
- 前端测试、性能、兼容与切换准备。

本文档不重新定义：

- Manifest、Revision、内容哈希和稳定身份；
- Change、Diff、Merge 和依赖闭包的后端语义；
- 后端数据库结构和事务；
- `effective-model/v2` 的权威字段；
- 生产 `off → shadow → enforced` 的最终切换授权。

本计划只描述实现顺序。执行每个阶段前，必须确认对应后端能力或 mock 契约已经达到[前后端贯通计划](./2026-07-28-machine-knowledge-integration-mvp.md)的准入条件。

---

## 1. 当前实现基线与核心差距

### 1.1 当前仓库事实

当前前端：

- Vue 3 + Element Plus + AntV X6 + ECharts；
- `App.vue` 使用本地 `currentView` 在“数据管理/求解”间切换，没有 Vue Router；
- `DataManagement/index.vue` 使用八个实体或工具页签组织界面；
- 每个数据管理子页面自行加载机台类型或机台实例，自行调用旧 CRUD；
- `NetworkEditorWorkspace.vue` 已有 `preview/edit` 和一次性提交草稿，但草稿只属于该组件；
- Network Editor 当前提交到旧 `/machine-types/{id}/network-editor/commit`；
- `StateTargetWorkspace`、`ActivityCapabilityWorkspace`、资源、日历等页面仍有各自直接写库路径；
- `SolvePage/index.vue` 直接按当前机台投影读取状态、活动和规则；
- 求解页仍包含已废弃的维护意图模式和维护意图模板读取；
- API 统一经过 `frontend/src/api/`，已有集中错误拦截；
- 前端没有独立单元测试脚本，主要使用 Playwright；
- `network-editor.spec.ts` 体积较大，覆盖当前图编辑回归；
- 当前应用没有跨页面共享草稿、Revision 缓存、知识版本时间线、回写或升级界面。

### 1.2 目标差距

| 领域 | 当前状态 | MVP 目标 |
|---|---|---|
| 主导航 | 数据管理 / 求解 | 机台知识库 / 求解 |
| 二级导航 | 按实体拆成多个页签 | 基础配置 / 模型构建 / 版本管理 |
| 范围选择 | 各子页重复选择 | 顶部共享范围栏只选一次 |
| 数据读取 | 当前规范化投影 | 指定不可变 Revision 的完整模型 |
| 编辑 | 子页面直接写库 | 跨页面共享本地草稿 |
| 提交 | 多个旧 CRUD/Editor commit | Validate + Knowledge Commit |
| 并发 | Network Editor 私有 revision | 全工作区 `expected_head_revision_id` |
| 历史 | 无知识版本 UI | 时间线、详情、差异、引用、只读查看 |
| 回写/升级 | 无 | 三方合并向导 |
| 求解 | 当前投影和旧 v1 | 正式实例 Revision + v2 |
| 重放 | 无完整入口 | 历史知识与运行时快照重放 |
| 废弃概念 | 维护意图仍可见 | 全部移出现行 UI |

### 1.3 改造原则

1. 不一次性重写 Network Editor 的画布和布局算法。
2. 先把范围、模型和草稿所有权上移，再替换写接口。
3. 现有表单优先改成“受控组件”，保留其字段校验和显示能力。
4. 所有新写操作先生成统一 `KnowledgeChange`，组件不得直接调用知识写 API。
5. 正式模型与草稿叠加只在前端选择器和画布显示层完成；求解永远不读草稿。
6. 前端不实现三方合并算法，只展示后端给出的合并结果、依赖和冲突。
7. `shadow` 期间可以开放只读知识工作区；写能力以服务端返回的能力状态为准。

---

## 2. 冻结前端技术决策

### 2.1 路由

引入 Vue Router 4，替换 `App.vue` 的本地视图切换。

固定路由：

```text
/knowledge
  ?stage=configuration|model|versions
  &scope=baseline|instance
  &machine_type_id=...
  &machine_id=...
  &revision_id=...

/solve
  ?machine_id=...
  &revision_id=...
  &solve_request_id=...
```

规则：

- `/` 重定向到 `/knowledge?stage=configuration`；
- 非法 `stage` 归一化为 `configuration`；
- 实例范围缺少 `machine_id` 时停留在实例空状态，不猜测；
- 历史 `revision_id` 与当前头不同则进入 `historical_readonly`；
- URL 更新不得触发无草稿保护绕过；
- 浏览器前进/后退必须经过相同切换守卫。

### 2.2 共享状态

MVP 不引入 Pinia。使用一个工作区级 `reactive` store，通过 `provide/inject` 暴露。

理由：

- 知识状态只在 `/knowledge` 子树中共享；
- 当前项目没有全局状态库；
- 保持依赖和迁移成本最小；
- 纯草稿内核单独实现，避免 Vue 响应式逻辑与业务合并逻辑耦合。

工作区状态至少包含：

```js
{
  lifecycle: 'loading|ready|error',
  editorState: 'preview|editing|validating|submitting|conflict|historical_readonly',
  stage: 'configuration|model|versions',
  scopeKind: 'baseline|instance',
  machineTypeId: null,
  machineId: null,
  head: null,
  viewedRevisionId: null,
  model: null,
  graph: null,
  validation: null,
  draft: null,
  capabilities: null,
  lastError: null
}
```

### 2.3 草稿格式

前端草稿直接使用后端 Commit 的 `changes` 语义，不再维护第二套长期 wire shape：

```js
{
  schemaVersion: 'knowledge-draft/v1',
  scopeKind: 'baseline',
  scopeId: '123',
  baseRevisionId: 'uuid',
  createdAt: 'ISO-8601',
  updatedAt: 'ISO-8601',
  changes: [
    {
      operation: 'upsert',
      identity_kind: 'entity',
      identity_key: 'uuid',
      object_kind: 'atomic_state',
      content: {
        semantic: {},
        presentation: {}
      }
    }
  ]
}
```

约束：

- 新对象和新关系在创建草稿时立即用 `crypto.randomUUID()` 分配身份；
- 改名继续使用原 `identity_key`；
- 关系端点或角色变化转换成 delete + upsert；
- 同身份连续 upsert 合并成最后内容；
- 新建后又删除且未提交的对象可以从草稿中抵消；
- 已存在对象删除后不得被无提示的后续表单保存恢复；
- 布局变化写入 `presentation`，默认不参与实例回写选择；
- 草稿内核不计算三方合并。

### 2.4 草稿存储

使用 `sessionStorage`，键格式：

```text
knowledge-draft:v1:{scope_kind}:{scope_id}:{base_revision_id}
```

初始化范围尚未创建时：

```text
knowledge-draft:v1:pending:{client_scope_uuid}
```

规则：

- 只在相同基础 Revision 恢复；
- 头版本变化后将草稿标记为冲突，不自动套到新头；
- 提交成功或明确放弃后清除；
- 序列化失败或超出浏览器容量时阻止继续编辑并提示导出草稿摘要；
- 不把草稿写入 URL；
- 不使用 `localStorage`，避免跨浏览器会话长期滞留。

### 2.5 缓存

- 当前头版本：每次进入范围或显式刷新重新读取；
- 不可变模型、图和验证摘要：按 `revision_id` 缓存；
- 历史列表和 diff：按完整查询参数缓存当前会话结果；
- Commit、回写或升级成功后清除相关 scope head/history/diff 缓存；
- 请求必须带序号或 AbortController，旧响应不得覆盖新范围。

### 2.6 前端能力门禁

前端只读取后端系统状态提供的知识仓库能力：

```js
{
  mode: 'off|shadow|enforced',
  read_enabled: true,
  write_enabled: false,
  solve_v2_authoritative: false,
  bootstrap_status: 'not_started|ready|blocked'
}
```

界面规则：

| 能力 | 界面行为 |
|---|---|
| `read_enabled=false` | 不进入知识工作区，保留兼容入口 |
| 只读 | 可浏览版本和 shadow 数据，隐藏编辑/回写/升级 |
| `write_enabled=true` | 开放 Knowledge Commit 和变更向导 |
| `solve_v2_authoritative=true` | 求解页只允许正式实例 Revision |

不得仅凭前端构建变量绕过后端能力门禁。

---

## 3. 目标目录与组件边界

### 3.1 新增目录

```text
frontend/src/
├─ router/
│  └─ index.js
├─ api/
│  └─ knowledge.js
├─ knowledge/
│  ├─ knowledgeDraft.js
│  ├─ knowledgeDraftStorage.js
│  ├─ knowledgeModelOverlay.js
│  ├─ knowledgeRoute.js
│  ├─ knowledgeCache.js
│  └─ knowledgeKinds.js
├─ composables/
│  └─ useKnowledgeWorkspace.js
├─ views/
│  └─ Knowledge/
│     ├─ index.vue
│     ├─ KnowledgeConfigurationPage.vue
│     ├─ KnowledgeModelPage.vue
│     ├─ KnowledgeVersionsPage.vue
│     ├─ components/
│     │  ├─ KnowledgeScopeBar.vue
│     │  ├─ KnowledgeStageNav.vue
│     │  ├─ KnowledgeDraftSummary.vue
│     │  ├─ KnowledgeValidationPanel.vue
│     │  ├─ RevisionStatusBadge.vue
│     │  ├─ RevisionTimeline.vue
│     │  ├─ RevisionDiffWorkspace.vue
│     │  ├─ HistoricalRevisionViewer.vue
│     │  ├─ WritebackWizard.vue
│     │  ├─ UpgradeWizard.vue
│     │  └─ KnowledgeConflictResolver.vue
│     └─ sections/
│        ├─ MachineInfoSection.vue
│        ├─ StateDimensionSection.vue
│        ├─ ResourceConfigurationSection.vue
│        ├─ CalendarConfigurationSection.vue
│        ├─ StateModelingSection.vue
│        ├─ ActivityModelingSection.vue
│        └─ CommitReviewSection.vue
└─ views/SolvePage/
   └─ SolveReplayDrawer.vue
```

### 3.2 现有文件改造

| 文件 | 改造 |
|---|---|
| `frontend/src/main.js` | 安装 Router |
| `frontend/src/App.vue` | 路由导航、系统能力状态、移除本地 `currentView` |
| `frontend/src/views/DataManagement/index.vue` | 兼容窗口保留，enforced 后不再作为知识写入口 |
| `MachineTypePage.vue` | 抽取为受控机台类型表单/列表能力 |
| `MachinePage.vue` | 抽取实例表单，不直接切换知识范围 |
| `BusinessStateDimensionPage.vue` | 改为接收模型和发出 Change |
| `ResourcePage.vue` | 区分基线资源类型与实例机器资源 |
| `WorkCalendarPage.vue` | 分离日历库修订与知识中的日历引用 |
| `StateTargetWorkspace.vue` | 复用状态建模表单；不再把运行时目标快照混入知识 |
| `ActivityCapabilityWorkspace.vue` | 复用活动包、原子活动和规则表单；停止直接写库 |
| `NetworkEditorWorkspace.vue` | 接收共享范围/模型/草稿，移除私有选择器和私有提交 |
| `ValidationWorkspace.vue` | 收敛为统一验证面板 |
| `SolvePage/index.vue` | 加载实例头、显式 Revision、v2 状态和重放入口 |
| `frontend/src/api/masterData.js` | 保留兼容读取和运行时 API；新知识写入移到 `knowledge.js` |
| `frontend/src/api/solve.js` | 增加 Revision 求解与 replay API |
| `frontend/src/utils/errorCodes.js` | 加入全部知识错误码 |

### 3.3 不得发生

- 组件内直接导入 Axios；
- 每个子页面重新加载机台类型、实例和当前 Revision；
- Network Editor 保留第二套知识草稿；
- 版本管理页直接修改模型字段；
- 前端根据自增数据库 ID 推导稳定身份；
- 前端自行补齐回写依赖或执行三方合并；
- 前端把活动包转换成求解节点；
- 重新出现 Scope Guard、维护意图、虚拟活动或多图视图切换器。

---

## 4. API 封装

### 4.1 `frontend/src/api/knowledge.js`

封装：

```text
createBaselineScope
createInstanceScope
getKnowledgeHead
getKnowledgeRevision
getKnowledgeModel
getKnowledgeGraph
getKnowledgeValidation
getKnowledgeHistory
getKnowledgeReferences
validateKnowledgeChanges
commitKnowledgeChanges
getKnowledgeDiff
previewWriteback
getWriteback
resolveWriteback
confirmWriteback
cancelWriteback
previewUpgrade
getUpgrade
resolveUpgrade
confirmUpgrade
cancelUpgrade
```

要求：

- 方法名使用业务能力，不暴露存储表名；
- GET 分页参数原样传后端；
- Validate/Commit 接收同一命令构造器；
- Commit、Preview、Confirm 默认使用 `silentError: true`，由工作流组件展示可操作错误；
- 不在 API 模块生成或重用幂等键；幂等键由发起工作流持有；
- 响应只做最小归一化，不在 API 层推导 merge 结果。

### 4.2 `frontend/src/api/solve.js`

新增：

```text
getSolveReplayInput
replaySolveRequest
```

现有求解方法增加：

- `instance_revision_id`；
- 允许后端返回 baseline/instance Revision；
- `effective_model_schema_version`；
- `effective_model_hash`；
- 可重放状态摘要。

### 4.3 系统状态

`frontend/src/api/system.js` 增加 `getSystemStatus()`，应用启动和用户刷新时读取知识能力。

健康检查继续只显示服务存活；是否可写知识版本不得由 `/health` 推导。

### 4.4 错误码映射

必须加入后端设计基线全部错误码，并提供工作流动作：

| 错误码 | 前端处理 |
|---|---|
| `KNOWLEDGE_REVISION_NOT_FOUND` | 关闭失效的历史视图，保留当前范围并返回头版本 |
| `KNOWLEDGE_SCOPE_NOT_FOUND` | 清除失效的范围 query，返回范围空状态重新选择 |
| `KNOWLEDGE_MODE_DISABLED` | 回到兼容入口或显示只读不可用 |
| `KNOWLEDGE_WRITE_REQUIRES_VERSION_COMMIT` | 跳到知识工作区检查提交 |
| `KNOWLEDGE_HEAD_CONFLICT` | 进入 conflict，保留草稿并加载新头 |
| `KNOWLEDGE_IDENTITY_CONFLICT` | 定位对应对象，提示重新检查身份/归属 |
| `KNOWLEDGE_IDEMPOTENCY_KEY_REUSED` | 停止自动重试，生成新的用户动作 |
| `KNOWLEDGE_CHANGE_REQUEST_STALE` | 禁用确认，要求重新预览 |
| `KNOWLEDGE_MERGE_CONFLICT_UNRESOLVED` | 返回冲突步骤 |
| `KNOWLEDGE_REVISION_SOLVER_BLOCKED` | 禁用求解并展示验证摘要 |
| `KNOWLEDGE_STRUCTURE_INVALID` | 定位结构错误，禁止提交 |
| `KNOWLEDGE_SOLVER_REVIEW_REQUIRED` | 显示明确确认项 |
| `KNOWLEDGE_DEPENDENCY_INCOMPLETE` | 展示后端缺失依赖原因，不自行猜测 |
| `KNOWLEDGE_NO_CHANGES` | 保留预览，提示没有有效变化 |
| `KNOWLEDGE_REPLAY_INPUT_INCOMPLETE` | 允许查看历史输入，禁用重跑 |
| `KNOWLEDGE_INTEGRITY_FAILURE` | 进入不可继续状态并提示联系管理员 |

---

## 5. 分阶段实施总览

| 阶段 | 目标 | 依赖 | 主要交付 |
|---|---|---|---|
| F0 | 基础工程与测试基线 | T98 冻结 | Router、单测、错误码、能力读取 |
| F1 | 只读知识工作区 | 后端 B4 或契约 mock | 三阶段壳、范围栏、Revision 读取 |
| F2 | 共享草稿内核 | F1 | 草稿、叠加、恢复、切换保护 |
| F3 | 基础配置接入 | F2、后端 B5 契约 | 四配置区块只产生 Change |
| F4 | 模型构建接入 | F2、后端 B5 契约 | 状态、活动、单一转移图 |
| F5 | 验证、提交与冲突 | F3、F4、后端 B5 | Check/Commit、状态机、恢复 |
| F6 | 版本历史和差异 | 后端 B6 | 时间线、比较、引用、历史恢复 |
| F7 | 回写与升级 | 后端 B7 | 两个向导和冲突解决 |
| F8 | 求解与历史重放 | 后端 B8 | Revision 求解、v2、replay |
| F9 | 性能、兼容和发布门禁 | F0–F8、后端 B9 | 大数据、全回归、切换准备 |

---

## 6. F0：基础工程与测试基线

### 6.1 任务

1. 新增 Vue Router 4 和路由文件。
2. 保留 `/knowledge` 与 `/solve` 两个主路由。
3. 增加 Vitest 和前端纯逻辑单元测试脚本。
4. 增加 `getSystemStatus()` 和知识能力模型。
5. 补齐 16 个知识错误码的中文映射。
6. 建立 `knowledgeKinds.js`，集中保存对象/关系 kind 的用户显示名。
7. 建立知识 API mock fixture builder，避免每个 E2E 文件复制 wire shape。
8. 固定 `data-testid` 命名：

```text
knowledge-scope-*
knowledge-stage-*
knowledge-draft-*
knowledge-commit-*
revision-*
writeback-*
upgrade-*
solve-replay-*
```

### 6.2 测试

- 路由 query 解析和归一化；
- 错误码全覆盖；
- 系统状态 off/shadow/enforced 显示；
- `/`、`/knowledge`、`/solve` 导航；
- 现有 Solve 和 Network Editor E2E 在兼容入口仍可运行。

### 6.3 门禁

- `npm run build` 通过；
- 新增 `npm run test:unit` 通过；
- 现有 Playwright 测试未因 Router 引入而失去入口；
- 默认后端 off 时不误开放新知识写入口。

---

## 7. F1：只读知识工作区和共享范围

### 7.1 页面壳

新增 `Knowledge/index.vue`：

- 顶部固定 `KnowledgeScopeBar`；
- 下方固定三个二级页面；
- 只挂载当前 stage；
- scope/model/draft 由同一 workspace store 提供；
- 加载失败保留原范围。

### 7.2 范围栏

实现：

- 基线/实例切换；
- 机台类型选择；
- 实例选择；
- 当前版本；
- 冻结基线；
- 主线最新；
- 可求解状态；
- 草稿数；
- 可用升级提示；
- 历史只读状态。

范围列表继续使用现有只读 `machine-types` 和 `machines` 投影接口；选中后所有知识内容必须从 Revision API 读取。

### 7.3 读取顺序

```text
选择范围
→ get head
→ 确定 viewed_revision_id
→ 并行读取 model / validation
→ 进入转移关系步骤时按需读取 graph
→ 更新 URL
```

不能在每次步骤切换时重新读取相同 Revision。

### 7.4 空状态

覆盖：

- 无机台类型；
- 无实例；
- 尚无首版本；
- scope 不存在；
- Revision 不存在；
- 知识模式禁用；
- bootstrap 未完成；
- 历史 Revision 只读。

### 7.5 测试

- 基线和实例各一次范围选择；
- 实例显示冻结/最新版本；
- 页面切换不重复加载相同模型；
- 请求竞态时旧响应不覆盖新范围；
- URL 刷新恢复范围和 stage；
- 历史 Revision 只读；
- 三个且只有三个二级页面。

---

## 8. F2：共享草稿内核

### 8.1 纯逻辑模块

`knowledgeDraft.js` 实现：

```text
createDraft
appendChange
replaceChange
removeChange
compactChanges
discardDraft
summarizeDraft
isDraftCompatibleWithHead
buildValidateCommand
buildCommitCommand
```

`knowledgeModelOverlay.js` 实现：

- 把草稿叠加到正式模型供表单和选择器显示；
- 保持实体和关系身份；
- 删除项从正常列表移除，但在变化摘要中保留；
- 不生成后端未定义的对象；
- 不进行依赖闭包或 merge。

### 8.2 编辑状态机

由 workspace store 统一管理：

```text
preview
→ editing
→ validating
→ submitting
→ preview
```

冲突：

```text
submitting
→ conflict
→ 查看新头
→ 重新应用或放弃
```

历史：

```text
historical_readonly
→ create restoration draft
→ editing
```

### 8.3 切换保护

以下动作统一经过同一守卫：

- 切换机台类型；
- 切换机台实例；
- 基线/实例模式切换；
- 浏览器前进/后退；
- 从知识库进入求解；
- 打开历史 Revision。

有草稿时只允许：

- 返回编辑；
- 明确放弃；
- 完成提交。

MVP 不提供“临时保存后切换”。

### 8.4 幂等键生命周期

- 用户每次点击“提交版本”开始一个提交意图；
- 首次发送前生成 `idempotency_key`；
- 网络超时或未知结果重试必须复用；
- 用户修改草稿后生成新的提交意图和新键；
- `KNOWLEDGE_IDEMPOTENCY_KEY_REUSED` 不自动重试。

### 8.5 测试

- upsert 合并；
- create + delete 抵消；
- rename 保留身份；
- relation endpoint change 转换成 delete + upsert；
- sessionStorage 保存和恢复；
- base head 不一致进入 conflict；
- 页面刷新不丢草稿；
- 成功提交和明确放弃清理；
- API 失败不清理；
- 幂等键重试保持。

---

## 9. F3：基础配置接入共享草稿

### 9.1 页面结构

`KnowledgeConfigurationPage.vue` 固定四个区块：

```text
机台信息
→ 状态维度
→ 资源配置
→ 工作日历
```

使用步骤条或纵向锚点，不新增二级路由。

### 9.2 机台信息

基线：

- 编辑机台类型字段；
- 字段变化发出 `machine_type` upsert；
- 改名保持 `entity_key`。

实例：

- 编辑具体机台信息；
- 所属机台类型和冻结基线只读；
- 变化发出 `machine_instance` upsert。

### 9.3 状态维度

- 由 Revision model 加载；
- 选择器禁止硬编码 `feature_key`；
- 实例新增或覆盖写入实例草稿；
- 不调用旧 `createFeatureDef/updateFeatureDef/deleteFeatureDef`。

### 9.4 资源

基线模式：

- 资源类型和规则可引用分类；
- 默认排程配置。

实例模式：

- 具体机器资源、容量、启用状态；
- 与基线资源需求的匹配提示；
- 只写实例草稿。

禁止把实例资源写入共享机台类型投影。

### 9.5 工作日历

分开处理：

- 日历库自身 Revision：继续使用现有日历 API；
- 范围引用哪个日历 Revision：生成知识 Change。

界面必须清楚显示“编辑日历内容”和“机台采用哪个日历版本”的区别。

### 9.6 Excel 导入

流程：

```text
选择文件
→ dry-run
→ 返回规范化 knowledge changes
→ 显示新增/修改/删除/错误
→ 合并进当前共享草稿
→ 前往检查提交
```

前端在知识写模式下不得调用旧 `dry_run=false` 直接落库。

### 9.7 创建范围

首个机台类型：

- 使用 pending draft；
- 检查通过后调用 `createBaselineScope`；
- 成功返回 B-000001 并切入正式 scope。

首个实例：

- 选择机台类型和冻结基线；
- 默认最新可求解基线；
- 结构无效基线禁止选择；
- 提交调用 `createInstanceScope`；
- 成功返回 I-000001。

### 9.8 测试

- 四区块顺序；
- 基线/实例字段差异；
- 动态状态维度；
- 实例资源不污染基线；
- 日历库修改不自动移动机台知识版本；
- 日历引用修改进入草稿；
- Excel 只生成草稿；
- 首个范围失败无半成品；
- 无首版本状态不能求解。

---

## 10. F4：模型构建和单一状态转移图

### 10.1 页面结构

`KnowledgeModelPage.vue` 固定：

```text
状态建模
→ 活动建模
→ 转移关系
→ 检查提交
```

步骤切换不提交，不重新选择范围。

### 10.2 状态建模

`StateModelingSection.vue` 维护：

- 状态包；
- 原子状态本体；
- 状态包成员引用；
- 状态维度、运算符和值；
- 引用别名、排序、启用和布局。

删除在用本体时，把后端引用详情转换成用户可操作的冲突列表。

### 10.3 活动建模

`ActivityModelingSection.vue` 维护：

- 一级/二级活动包；
- 原子活动；
- 活动包原子活动引用；
- 原子活动规则；
- precondition/effect；
- 时长和资源需求；
- 责任子系统。

不得显示：

- Scope Guard；
- 维护意图；
- 虚拟活动；
- `ActivityNode(level=3)` 新建或编辑。

### 10.4 Network Editor 所有权迁移

按以下顺序改造，避免一次性重写：

1. 抽离现有草稿序列化、ID 解析和布局批次纯函数。
2. 增加受控 props：

```text
scope
revisionModel
revisionGraph
draftChanges
editorState
readonly
```

3. 增加事件：

```text
append-change
remove-change
replace-change
request-validation
open-model-step
```

4. 移除组件内机台类型选择器。
5. 移除组件内 `startEditSession/cancelEditSession/submitDraftChanges` 所有权。
6. 移除对旧 graph/commit API 的直接调用。
7. 保留 X6 渲染、选择、拖动、展开、布局和定位能力。
8. 让画布只渲染后端 Revision graph + 前端草稿 overlay。

### 10.5 关系编辑

- input/output 端点读取 canonical 身份；
- 修改端点在草稿层变为删除旧关系 + 创建新关系；
- 同一 canonical 本体的多个引用实例可以独立布局；
- 图上投影引用不改变持久化关系端点；
- 活动包不显示为求解转移节点。

### 10.6 大图

- 左侧树使用 Element Plus 虚拟树；
- 默认按状态根、活动范围和展开深度加载；
- 首屏最多 500 个图元素；
- 预计超过 1,000 时不实例化全量 X6 cell，显示缩小范围动作；
- 筛选状态不写入草稿；
- 自动布局继续有请求序号和过期结果保护。

### 10.7 测试

现有 Network Editor 回归必须保留，并新增：

- 无私有范围选择器；
- 无私有提交按钮；
- 外部草稿跨步骤仍存在；
- 状态/活动改名身份不变；
- 删除引用不删除本体；
- 端点变化 delete + add；
- 活动包不进入主链；
- 只存在 `state_transition`；
- 无 Scope Guard、维护意图、虚拟活动；
- 500/1,000 元素边界；
- 同一 canonical 的多引用布局隔离。

---

## 11. F5：检查、提交、冲突和恢复

### 11.1 检查提交

`CommitReviewSection.vue` 显示：

- 基础版本；
- 对象新增/修改/删除；
- 关系新增/删除；
- 资源和日历变化；
- 纯布局变化；
- 后端规范化或系统补充项；
- 结构、健康、求解准备三个层级。

### 11.2 Validate

```text
editing
→ validating
→ POST validate
→ 显示结果
→ editing 或可提交
```

规则：

- 每次草稿变化使上次验证结果过期；
- Validate 不移动版本；
- 结构错误禁止提交；
- 求解阻断必须显示明确确认；
- no-op 禁止进入提交。

### 11.3 Commit

请求：

```js
{
  expected_head_revision_id,
  idempotency_key,
  message,
  allow_solver_blockers,
  changes
}
```

成功后：

1. 更新 head 和 viewed Revision；
2. 清理草稿；
3. 清理相关缓存；
4. 返回 preview；
5. 显示新业务版本号；
6. 允许前往版本管理。

失败：

- 网络、超时、500：草稿保留；
- head conflict：进入 conflict；
- structure invalid：返回问题定位；
- solver review required：保持提交弹窗；
- no changes：不清理。

### 11.4 并发冲突

界面提供：

- 当前草稿基础版本；
- 服务端最新头；
- 两者变化摘要；
- “重新应用到最新版本”；
- “放弃草稿”。

不提供强制覆盖。

重新应用应调用后端验证/合并能力；前端不能在字段层自制三方合并。

### 11.5 历史恢复

```text
打开历史只读模型
→ 以此版本恢复
→ 计算历史到当前头的恢复 changes
→ 进入共享草稿
→ Validate
→ Commit 新 Revision
```

恢复不得移动 Ref 到旧 Revision。

### 11.6 测试

- validate 不写版本；
- 草稿修改使验证过期；
- 结构错误阻断；
- solver blocker 明确确认；
- 成功提交清草稿；
- 所有失败保留草稿；
- 超时重试复用幂等键；
- head conflict 无强制覆盖；
- 历史恢复产生新 Revision。

---

## 12. F6：版本管理

### 12.1 时间线

`RevisionTimeline.vue`：

- 默认 50 条；
- 游标分页；
- 显示业务版本号、时间、说明、可求解状态；
- 当前头明确标记；
- 实例显示冻结基线；
- 不以 UUID/Hash 作为主标签。

### 12.2 版本详情和引用

显示：

- 父版本；
- 变化数量；
- 验证摘要；
- 实例冻结基线；
- 使用该 Revision 的实例和 SolveRequest；
- 技术详情折叠区。

### 12.3 差异

`RevisionDiffWorkspace.vue`：

- from/to 选择；
- 对象/关系/布局分类；
- add/modify/delete 筛选；
- 顶层字段；
- 关系端点摘要；
- 大列表虚拟滚动；
- layout 默认关闭；
- 分页游标。

颜色只作为辅助，必须同时有文字和图标。

### 12.4 历史模型

`HistoricalRevisionViewer.vue`：

- 持续只读横幅；
- 复用配置和模型组件的 readonly 模式；
- 不出现保存或原地编辑；
- 可以比较、查看引用、创建恢复草稿。

### 12.5 测试

- 50 条分页；
- 任意同范围版本比较；
- 实例头与冻结基线比较；
- 改名显示 modify；
- 关系端点显示 delete/add；
- layout 默认排除；
- 历史只读；
- Revision 缓存按 ID；
- 引用列表分页。

---

## 13. F7：部分回写和实例升级

### 13.1 回写向导

固定步骤：

```text
选择变化
→ 查看依赖
→ 处理冲突
→ 验证
→ 填写原因并确认
→ 结果
```

要求：

- 只在实例当前头显示入口；
- 初始比较为冻结基线到实例头；
- layout 默认不选；
- 自动依赖有原因说明且不可取消；
- 选择变化变化后重新 preview；
- Preview 的 `request_id` 和幂等键保留到结束；
- 冲突解决只提交用户选择，不在前端改写 merge 算法；
- Confirm 前显示当前基线主线；
- stale 后禁用确认并要求重开。

结果必须说明：

- 新基线版本；
- 原实例未改变；
- 原冻结基线未改变；
- 可以继续实例升级。

### 13.2 升级向导

固定步骤：

```text
选择目标基线
→ 查看基线与实例变化
→ 自动合并预览
→ 处理冲突
→ 验证
→ 确认
→ 结果
```

要求：

- 默认目标为主线最新；
- 暂不可求解目标有强警告；
- 未解决冲突禁用确认；
- 失败或取消保持实例头和冻结基线；
- 成功后刷新 scope head、模型、验证和版本历史。

### 13.3 冲突组件

`KnowledgeConflictResolver.vue` 显示：

- Base；
- 当前目标侧；
- 来源侧；
- 冲突字段；
- 可选 ours/theirs/manual；
- 删除/修改冲突的明确文本。

嵌套 JSON 和数组在 MVP 中作为整体字段显示，不能伪装成逐元素安全合并。

### 13.4 测试

- 依赖自动补齐；
- 必要依赖不可取消；
- 无冲突直接 ready；
- 同字段冲突；
- delete/modify；
- manual resolution；
- 未解决禁止确认；
- stale；
- 重复 confirm 返回同一结果；
- 回写不改实例；
- 升级更新冻结基线；
- 中途失败无 UI 假成功。

---

## 14. F8：求解、有效模型和历史重放

### 14.1 求解入口

求解页选择具体机台后：

```text
读取 instance head
→ 显示实例版本和冻结基线
→ 检查可求解状态
→ 加载当前/目标状态等运行时输入
→ 显式提交 instance_revision_id
```

有知识草稿时：

- 可以离开知识页前明确放弃；
- 不允许“用草稿求解”；
- 求解页不读取 `sessionStorage` 草稿。

### 14.2 结果显示

求解结果增加：

- 实例业务版本；
- 冻结基线业务版本；
- `effective-model/v2`；
- 有效模型 Hash 的短显示；
- 技术详情中的完整 Revision/Hash；
- 可重放状态。

预检和正式求解 hash 不一致时显示完整性错误，不能继续把结果标记为可信。

### 14.3 历史重放

`SolveReplayDrawer.vue`：

1. 读取 replay input；
2. 显示当次基线、实例版本；
3. 显示当前状态、目标状态、临时条件和日历摘要；
4. 允许只读打开当次知识模型；
5. 输入完整时允许重跑；
6. 显示原结果与新结果的版本、状态、步数和 makespan；
7. 输入不足时禁用重跑，但保留查看。

### 14.4 日落维护意图

从现行求解界面移除：

- `maintenance` 模式切换；
- 维护意图模板选择；
- 维护意图结果面板；
- `getMaintenanceIntentTemplates` 和 `postMaintenanceSolve` 的现行 UI 调用。

既有阻塞策略 A/B 和计划调整能力按自身契约保留，不与“维护意图模板”混同。

### 14.5 测试

- 求解显式携带实例 Revision；
- blocked Revision 禁止求解；
- 草稿不进入求解；
- 基线更新不改变冻结实例；
- 实例升级后读取新 Revision；
- precheck/solve hash 一致；
- replay 不偷用当前头；
- replay input 不足；
- 旧 v1 历史记录只读兼容；
- 计划调整继承原知识 Revision；
- 维护意图不再出现。

---

## 15. F9：性能、兼容和发布准备

### 15.1 性能目标

| 场景 | 目标 |
|---|---|
| 10,000 条完整模型首次解析 | 不阻塞主线程超过可接受交互阈值；必要时分片 |
| 版本历史首屏 | 50 条 |
| diff 列表 | 10,000 项使用虚拟滚动和分页 |
| 图首屏 | ≤ 500 元素 |
| 图全量阈值 | > 1,000 时阻止直接绘制 |
| 相同 Revision 页面切换 | 不重复请求 model/validation |
| 范围快速切换 | 旧请求不覆盖新结果 |
| 草稿恢复 | 与草稿项数量线性，提供超大草稿提示 |

性能验收必须记录测试数据规模、浏览器版本、机器配置和测量方法。

### 15.2 兼容入口

| 后端状态 | 前端入口 |
|---|---|
| off | 旧 DataManagement 继续工作，新知识写 UI 不开放 |
| shadow 只读 | 旧写入口仍为业务入口；新知识页面只读对比 |
| staging write ready | 测试用户可执行完整新工作流 |
| enforced | 新知识工作区为唯一知识写入口；旧写控件隐藏 |

前端隐藏旧入口不是安全边界；后端 enforced guard 必须同时生效。

### 15.3 浏览器矩阵

至少：

- Chromium 主流程全量；
- Firefox 覆盖范围切换、草稿恢复、版本 diff 和提交；
- WebKit 覆盖导航、表单和只读版本查看；
- 真实浏览器 + 真实 PostgreSQL 跑完整主验收。

### 15.4 可用性

- 颜色差异同时有文本；
- 键盘可到达范围栏、步骤、差异列表和向导按钮；
- 提交、回写和升级二次确认说明结果；
- 加载和错误状态不造成页面跳动；
- 技术 UUID/Hash 默认收起；
- 中文错误说明包含下一步动作。

---

## 16. 前端测试矩阵

| 层级 | 文件建议 | 覆盖 |
|---|---|---|
| 纯逻辑 | `frontend/src/knowledge/*.spec.js` | 草稿、路由、overlay、缓存 |
| 工作区组件 | `frontend/src/views/Knowledge/**/*.spec.js` | 状态机、范围栏、差异和向导 |
| Mock E2E | `frontend/e2e/tests/knowledge-workspace.spec.ts` | 基础配置、模型、提交 |
| Mock E2E | `frontend/e2e/tests/knowledge-versions.spec.ts` | 历史、diff、恢复 |
| Mock E2E | `frontend/e2e/tests/knowledge-change-management.spec.ts` | 回写、升级、冲突 |
| Mock E2E | `frontend/e2e/tests/knowledge-solve-replay.spec.ts` | Revision 求解和重放 |
| 兼容回归 | 现有 `network-editor*.spec.ts`、`solve.spec.ts` | T97 与旧求解能力 |
| 真实 E2E | `frontend/e2e/tests/knowledge-real-api.spec.ts` | PostgreSQL 端到端 |

每个 mock 场景必须有至少一个真实 API 验收对应项，不能以 mock-only 作为完成证据。

---

## 17. 验证命令

计划执行时按实际依赖命令调整，但至少保留：

```powershell
Set-Location frontend
npm.cmd run test:unit
npm.cmd run build
npm.cmd run test:e2e -- knowledge-workspace.spec.ts --project=chromium
npm.cmd run test:e2e -- knowledge-versions.spec.ts --project=chromium
npm.cmd run test:e2e -- knowledge-change-management.spec.ts --project=chromium
npm.cmd run test:e2e -- knowledge-solve-replay.spec.ts --project=chromium
npm.cmd run test:e2e -- network-editor.spec.ts --project=chromium
npm.cmd run test:e2e -- solve.spec.ts --project=chromium
```

真实 API 场景必须由贯通计划提供独立命令和数据库准备流程。

---

## 18. 阶段提交策略

推荐按阶段提交，禁止把导航、所有表单、Network Editor 和版本管理一次性混为一个无法审查的提交。

建议提交边界：

```text
F0 router/test/capability foundation
F1 read-only workspace and scope
F2 shared draft kernel
F3 configuration adapters
F4 model-building adapters
F5 validate/commit/conflict
F6 revision history/diff
F7 writeback/upgrade
F8 solve/replay
F9 performance/cutover preparation
```

每个提交：

- 只包含本阶段必要文件；
- 有对应自动化证据；
- 不修改尚未到阶段的后端契约；
- 不提前删除兼容入口；
- 更新 TICKET-098 子任务证据。

---

## 19. 设计基线追踪矩阵

| 前端设计基线 | 实施阶段 |
|---|---|
| 三个二级页面 | F0–F1 |
| 共享范围栏 | F1 |
| 基础配置四区块 | F3 |
| 模型构建四步骤 | F4–F5 |
| 完整状态转移图 | F4 |
| 统一编辑状态机 | F2、F5 |
| 草稿恢复和切换保护 | F2 |
| 版本时间线、详情、比较 | F6 |
| 历史只读和恢复 | F5–F6 |
| 部分回写 | F7 |
| 实例升级 | F7 |
| 正式 Revision 求解 | F8 |
| 历史重放 | F8 |
| 页面状态和错误反馈 | F0–F8 |
| 大树、diff 和图性能 | F4、F6、F9 |

---

## 20. 前端最终完成审计

- [ ] 顶部主导航只有“机台知识库”和“求解”。
- [ ] 机台知识库只有三个二级页面。
- [ ] 路由可恢复 stage、scope 和只读 Revision。
- [ ] 范围选择不在子页面重复。
- [ ] 基础配置和模型构建共享同一草稿。
- [ ] 所有知识编辑只生成 `KnowledgeChange`。
- [ ] 所有正式写入通过知识 Commit 或范围创建。
- [ ] API 失败、超时和并发不清空草稿。
- [ ] 改名不改变身份，关系端点变化为 delete + add。
- [ ] Network Editor 只有 `state_transition`。
- [ ] 活动包不作为求解节点。
- [ ] Scope Guard、维护意图和虚拟活动不出现在现行 UI。
- [ ] 历史版本只读，恢复创建新 Revision。
- [ ] 回写和升级均处理依赖、冲突、stale 和幂等。
- [ ] 求解不读取草稿，并显式绑定实例 Revision。
- [ ] 预检与求解有效模型 Hash 一致。
- [ ] replay 使用历史 Revision 和历史运行时快照。
- [ ] 16 个知识错误码都有中文说明和可操作动作。
- [ ] 大树、差异和图满足性能基线。
- [ ] Mock E2E、真实 API E2E、现有 Network Editor 和 Solve 回归全部通过。
- [ ] enforced 前旧写 UI 已隐藏且后端 guard 已生效。

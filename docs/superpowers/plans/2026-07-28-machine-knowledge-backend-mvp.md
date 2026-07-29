# 机台知识库与版本变更管理后端 MVP：开发与验收计划

> **Status:** Planned
> **Target ticket:** [TICKET-098](../../TICKET_098.md)（MVP scope frozen，implementation not started）
> **Version:** V0.3
> **Created:** 2026-07-28
> **Source of truth:** [后端设计基线](../../机台知识库与版本变更管理_后端设计基线.md)
> **Related frontend baseline:** [前端设计基线](../../机台知识库与版本变更管理_前端设计基线.md)

## 0. 计划定位

本计划把已冻结的后端设计基线拆成可以逐阶段开发、验证和回滚的工程任务。计划完成的含义不是“表已创建”或“API 能返回版本号”，而是：

- 机台类型基线和机台实例都拥有不可变知识版本；
- 相同内容只保存一次，未变化对象继续引用旧内容；
- 对象、关系、版本和 Manifest 身份稳定；
- 实例完整 Manifest 可以脱离冻结基线独立恢复；
- 提交、差异、依赖闭包、部分回写和实例升级均可通过正式 API 完成；
- 预检和求解从同一个 `effective-model/v2` 解析器读取指定实例版本；
- 历史求解保存知识版本和必要快照，可以查看并在条件完整时重放；
- `off → shadow → enforced` 切换可验证、可审计；
- Scope Guard、维护意图、虚拟活动和活动包求解语义不进入新仓库。

本计划只涉及后端、数据库、脚本、协议和后端测试。前端页面重组与交互实现不在本计划内。

## 1. 当前实现基线与差距

### 1.1 当前仓库事实

- 当前 Alembic 迁移头为 `014_body_reference_unification`，上游为 `013_plan_adjustment`。
- `MachineType` 持有状态、活动、规则和绑定等机台类型数据。
- `Machine` 持有具体资源、默认日历和状态维度日历映射。
- Network Editor 的 `commit` 仍直接修改规范化表，并用实时内容摘要作为编辑冲突 revision。
- `app/services/effective_model.py` 当前生成 `effective-model/v1`，直接从当前机台类型投影读取数据。
- Network Editor 求解预检与 layered solve 已共享 `resolve_effective_model()`，这是升级到 v2 的现有接缝。
- `SolveRequest.overrides` 已保存 v1 的版本、摘要和快照，但没有正式知识 Revision 外键。
- 当前 SQLite 内存测试覆盖常规 API；TICKET-097 的真实 PostgreSQL 验收通过物理副本、审计脚本和固定求解完成。
- 工作区存在大量 TICKET-097 相关未提交改动；实施时必须保留这些改动，不得重置或覆盖。

### 1.2 主要差距

| 设计基线要求 | 当前状态 | 缺口 |
|---|---|---|
| 稳定 `entity_key/relation_key` | 主要使用整数主键 | 缺 UUID 身份与旧 ID 映射 |
| 内容寻址 | 无内容对象库 | 缺 canonical JSON、SHA-256 和去重 |
| 完整 Manifest | 无 | 缺不可变完整清单 |
| Revision/Ref | 无 | 缺线性历史、主线和实例头 |
| 实例完整模型 | 类型数据实时共享 | 实例不能独立修改状态、活动和规则 |
| 正式 Commit | Network Editor 直接改表 | 缺期望头、幂等、完整验证和原子 Ref 移动 |
| Diff/Merge | 无 | 缺字段差异、关系差异和三方合并 |
| 回写/升级 | 无 | 缺变化请求、冲突和确认事务 |
| `effective-model/v2` | 当前为 v1 | 缺按实例 Revision 解析 |
| 重放 | v1 快照在 overrides | 缺正式 Revision 字段和重放 API |
| 切换 | 无知识仓库模式 | 缺 off/shadow/enforced 和发布门禁 |

## 2. 冻结实施边界

### 2.1 必须实现

- 设计基线定义的 8 张 `knowledge_*` 表；
- 现有投影表的 UUID 映射字段；
- SolveRequest 的知识版本与有效模型字段；
- Canonical JSON、Content Object、Manifest、Revision 和 Ref；
- RevisionStore 全部冻结接口；
- 基线/实例首版本原子创建；
- 历史数据 `dry-run/apply/verify` 初始化；
- Validate、Commit、History、Diff、References API；
- Writeback 和 Upgrade API；
- `effective-model/v2`、求解持久化和 replay API；
- `off/shadow/enforced` 模式、系统状态和发布门禁；
- 单元、SQLite 集成、真实 PostgreSQL、固定求解和 1 万条性能验证。

### 2.2 明确不实现

- 命名分支、任意 checkout、rebase 或 cherry-pick；
- Merkle Tree；
- 垃圾回收和物理删除历史对象；
- 权限、审批、多租户；
- 自动升级实例；
- 自动把实例回写结果再次升级到来源实例；
- 数组元素级或语义相似度合并；
- Scope Guard 迁移；
- 维护意图继续开发；
- 虚拟活动恢复；
- 将实例专属状态/活动写回共享机台类型投影；
- 前端页面和交互。

### 2.3 不可破坏的现有契约

- API → Service → Domain → Persistence 分层；
- RuleEvaluator 仍是前置和效果计算唯一入口；
- Network Editor 只有 `state_transition`；
- 活动包只管理和引用原子活动；
- 原子本体、成员引用和语义关系身份相互独立；
- 现有 `effective-model/v1` 历史记录继续可读；
- 知识版本和 `PlanFamily/CandidatePlan` 计划版本完全独立；
- 默认 `KNOWLEDGE_REPOSITORY_MODE=off` 时现有行为不变。

## 3. Canonical Object Kind 注册表

实施前先冻结 Canonical Model 的粒度。所有 Kind 通过注册表声明编码器、解码器、依赖和投影策略，禁止在提交、差异或合并主流程中堆积大段 `if/elif`。

### 3.1 实体 Kind

| `object_kind` | 当前投影 | 范围 | 说明 |
|---|---|---|---|
| `machine_type` | `MachineType` | baseline | 机台类型基本配置和 scheduling config |
| `machine_instance` | `Machine` | instance | 具体机台基本配置 |
| `state_dimension` | `StateFeatureDef` | baseline/instance | 实例新增或覆盖只存在实例 Manifest |
| `state_package` | `StateNode(state_kind=aggregate)` | baseline/instance | 包本体 |
| `atomic_state` | `StateNode(state_kind!=aggregate)` | baseline/instance | 原子状态本体 |
| `activity_package` | `ActivityNode(level 1/2)` | baseline/instance | 纯管理包 |
| `atomic_activity` | `AtomicActivity` | baseline/instance | 可执行能力本体 |
| `op_rule` | `OpRule` | baseline/instance | 规则主信息 |
| `resource_type` | 由类型内 resource type code 合成 | baseline/instance | 无独立旧表，改名按删除/新增 |
| `machine_resource` | `Resource` | instance | 具体资源 |
| `calendar_policy` | `Machine`、`WorkCalendarRevision`、维度映射合成 | baseline/instance | 固化日历修订快照，不把当前指针当历史输入 |

补充身份规则：

- `resource_type` 使用 `resource-type/<scope-root-entity-key>/<normalized-code>` 生成确定性 UUID，编码变化按删除旧实体、新增新实体处理；
- `calendar_policy` 每个业务范围只有一个确定性实体身份，日历修订、时区、窗口、例外和映射变化只改变内容；
- `WorkCalendar` 和 `WorkCalendarRevision` 在 MVP 中仍是外部可复用日历库，不扩展第三种 `global` 知识范围；知识版本通过 `calendar_policy` 固化所引用修订的 code、revision_no、checksum 和必要快照。

### 3.2 关系 Kind

| `object_kind` | 当前投影 | 身份策略 |
|---|---|---|
| `state_package_parent` | `StateNode.parent_id` | 由 kind + 两端 entity key 生成确定性 UUID |
| `state_package_member` | `StateNodeReference` | 行级 `relation_key` |
| `state_dimension_template` | `StateFeatureDef.dimension_template_id` | 由 kind + 两端 key 生成 |
| `activity_package_parent` | `ActivityNode.parent_id` | 由 kind + 两端 key 生成 |
| `activity_package_member` | `ActivityPackageAtomicRef` | 行级 `relation_key` |
| `atomic_activity_rule` | `OpRule.atomic_activity_id` | 由 kind + 两端 key 生成 |
| `rule_precondition` | `OpRulePrecond` | 行级 `relation_key` |
| `rule_effect` | `OpRuleEffect` | 行级 `relation_key` |
| `rule_resource_requirement` | `OpRuleResourceReq` | 行级 `relation_key` |
| `activity_state_input` | `ActivityStateBinding(input)` | 行级 `relation_key` |
| `activity_state_output` | `ActivityStateBinding(output)` | 行级 `relation_key` |
| `machine_dimension_calendar` | `MachineStateDimensionCalendar` | 行级 `relation_key`，内容引用 calendar policy 快照 |

### 3.3 明确排除

- `MachineState` 和 `MachineStateFeature`：运行时快照；
- `ScopeGuard` 和 `ScopeGuardPrecond`：废弃且零数据门禁；
- `MaintenanceIntentTemplate`：废弃兼容数据；
- `ActivityNode(level=3)`：只读 legacy；
- `ActivityStateBinding(context_input/declared_output)`：只读审计；
- CandidatePlan、ScheduleResult 和 PlanAdjustment：计划域。

## 4. 目标代码结构

### 4.1 纯领域层

新增 `app/core/knowledge/`：

```text
types.py          枚举、不可变 dataclass 和命令结果
registry.py       Object Kind 注册表
canonical.py      canonical-json/v1
manifest.py       Manifest 构建、哈希和完整性
diff.py           身份和顶层字段差异
dependencies.py   最小依赖闭包
merge.py          三方合并和冲突
errors.py         与 FastAPI 无关的稳定领域错误
```

领域层不得导入 SQLAlchemy Session、FastAPI 或现有 API Schema。

### 4.2 服务与持久化编排

新增 `app/services/knowledge/`：

```text
revision_store.py       RevisionStore SQLAlchemy 实现
snapshot_builder.py     旧投影 ↔ Canonical Model 编解码
projection.py           正式头版本到兼容表的投影
validation.py           结构、健康、求解准备编排
commands.py             范围创建、validate、commit
changes.py              diff、回写和升级请求编排
references.py           实例和求解引用查询
cutover.py              off/shadow/enforced 与审计
```

现有 `app/services/effective_model.py` 保留为统一入口，内部增加 v1/v2 provider，不新建第二个求解主流程。

### 4.3 API 和 Schema

- 新增 `app/api/v1/knowledge.py`；
- 在 `app/main.py` 注册 router；
- 在 `app/db/schemas.py` 增加知识 API Schema；
- 增加统一 `KnowledgeError` 异常处理；
- 既有组件和路由不得直接访问 Manifest 表。

### 4.4 数据与运维

- `migrations/versions/015_knowledge_repository.py`
- `scripts/bootstrap_knowledge_repository.py`
- `scripts/audit_knowledge_repository.py`
- `scripts/benchmark_knowledge_repository.py`
- `app/services/system_status.py` 增加知识仓库模式和完整性状态。

## 5. 分阶段实施总览

| 阶段 | 结果 | 是否改变现有业务行为 |
|---|---|---|
| B0 | TICKET、差距和对象注册表冻结 | 否 |
| B1 | 纯领域 Canonical/Manifest/Diff/Merge | 否 |
| B2 | Alembic 015、ORM、Schema | 默认否 |
| B3 | Snapshot Builder、初始化和审计 | 否 |
| B4 | RevisionStore 只读能力和查询 API | off 模式否 |
| B5 | Validate、Commit、范围创建和投影 | off 模式否 |
| B6 | Diff、依赖闭包和版本引用 | off 模式否 |
| B7 | 部分回写和实例升级 | off 模式否 |
| B8 | effective-model/v2、求解保存和重放 | shadow 不改变响应 |
| B9 | 切换门禁、全量回归和 PostgreSQL 验收 | 由配置决定 |

每个阶段必须通过本阶段门禁后才能进入下一阶段，不能先接求解再补版本完整性。

## 6. B0：执行前冻结与测试基线

### 6.1 任务

- [x] 已创建并冻结 `docs/TICKET_098.md`，引用两份设计基线和前端、后端、贯通计划。
- [ ] 在 TICKET 中冻结本计划的 Object Kind 注册表。
- [ ] 记录当前后端全量测试数量和命令。
- [ ] 记录当前数据库迁移头、Scope Guard 0/0、body/reference 审计结果。
- [ ] 记录固定业务实例、预检模型版本、求解步数和 makespan。
- [ ] 对当前 PostgreSQL 数据目录创建一致物理副本或逻辑备份。
- [ ] 明确本票据不修改前端，不将生产配置切到 enforced。

### 6.2 门禁

- TICKET-098 状态为 approved；
- 014 在 PostgreSQL 副本可成功应用；
- `scripts/check_scope_guard_zero.py` 通过；
- `scripts/audit_body_reference_model.py` 通过；
- 当前后端全量测试绿；
- 固定业务求解证据已保存。

## 7. B1：纯领域基础

### 7.1 Canonical JSON

先写 `tests/unit/test_knowledge_canonical.py`，再实现：

- UTF-8 和 Unicode NFC；
- 对象键稳定排序；
- Decimal 无指数规范字符串；
- UTC 微秒时间；
- 显式 null；
- 禁止 NaN/Infinity；
- schema 声明为集合的数组按稳定键排序；
- 普通数组保持顺序；
- `semantic/presentation` 分区；
- SHA-256 `sha256:<64 hex>`。

必须断言：

- 字段插入顺序不改变哈希；
- Unicode 等价字符串哈希相同；
- Decimal/时间跨序列化稳定；
- presentation 变化会改变内容哈希，但可在 Diff 中单独分类；
- 数据库 ID、created_at、updated_at 不进入内容。

### 7.2 Manifest

先写 `tests/unit/test_knowledge_manifest.py`，再实现：

- `KnowledgeEntry`；
- 完整 Manifest 构建；
- `(identity_kind, identity_key, object_kind, content_hash)` 排序；
- Manifest Hash；
- Entry 数量；
- 重复身份拒绝；
- 悬空内容哈希拒绝；
- 完整性重算。

### 7.3 Diff、依赖和 Merge

先写：

- `tests/unit/test_knowledge_diff.py`
- `tests/unit/test_knowledge_dependencies.py`
- `tests/unit/test_knowledge_merge.py`

覆盖：

- add/modify/delete；
- semantic 与 presentation 分类；
- 顶层字段选择；
- 不同字段自动合并；
- 同字段不同值冲突；
- delete/modify、add/add 冲突；
- 关系端点变化的 delete + add；
- 新关系端点、规则、资源类型和引用闭包；
- 删除对象缺少必要关系删除时阻断。

### 7.4 B1 门禁

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\unit\test_knowledge_canonical.py `
  tests\unit\test_knowledge_manifest.py `
  tests\unit\test_knowledge_diff.py `
  tests\unit\test_knowledge_dependencies.py `
  tests\unit\test_knowledge_merge.py `
  -q --basetemp .pytest-tmp\t98-b1
```

- 纯领域测试全部通过；
- `app/core/knowledge/` 不导入 FastAPI 或 SQLAlchemy Session；
- Object Kind 主流程没有类型分发大段 `if/elif`。

## 8. B2：Alembic 015、ORM 和 Schema

### 8.1 015 新表

严格按后端设计基线新增：

1. `knowledge_identity`
2. `knowledge_content_object`
3. `knowledge_manifest`
4. `knowledge_manifest_entry`
5. `knowledge_revision`
6. `knowledge_ref`
7. `knowledge_change_request`
8. `knowledge_change_item`

约束必须通过数据库而不只靠 Pydantic：

- 内容哈希格式；
- Revision 范围与冻结基线条件；
- scope/revision_no 唯一；
- scope/idempotency_key 唯一；
- Ref kind 与 scope kind；
- 所有历史引用使用 RESTRICT；
- Change Item 主键和变化类型；
- Manifest Hash 全局唯一。

### 8.2 投影身份字段

015 对现有投影表增加 nullable + unique 的 UUID 映射列：

#### `entity_key`

- `machine_type`
- `machine`
- `state_feature_def`
- `resource`
- `activity_node`
- `atomic_activity`
- `state_node`
- `op_rule`

#### `relation_key`

- `state_node_reference`
- `activity_package_atomic_ref`
- `activity_state_binding`
- `op_rule_precond`
- `op_rule_effect`
- `op_rule_resource_req`
- `machine_state_dimension_calendar`

这些列在 off/shadow 兼容期允许为空，原因是旧 SQL 种子和旧写接口仍可能运行。进入 enforced 前，发布门禁必须断言所有进入知识版本的投影行已分配稳定键。

新知识 Commit 创建的投影行必须始终带键。迁移不依赖 PostgreSQL 扩展生成 UUID。

### 8.3 SolveRequest 字段

015 增加 nullable 字段，兼容旧记录：

- `knowledge_baseline_revision_id UUID`
- `knowledge_instance_revision_id UUID`
- `effective_model_schema_version VARCHAR(32)`
- `effective_model_hash VARCHAR(71)`
- `effective_model_summary JSONB`
- `effective_model_snapshot JSONB`

两个知识 Revision 字段使用 RESTRICT 外键并建立查询索引。

### 8.4 ORM 和 Schema

- 在 `app/db/models.py` 增加知识 ORM 和投影身份列；
- 在 `app/db/schemas.py` 增加领域无关的 API 请求/响应 Schema；
- Pydantic 与 ORM 严格分离；
- 更新 SQLite 类型兼容层；
- `SolveRequestDetailResponse` 增加可选知识版本和有效模型摘要；
- 不删除 `overrides` 中的 v1 兼容数据。

### 8.5 迁移约束

- 015 upgrade 只建结构，不自动建立 B1/I1；
- 不读取或写入 Scope Guard；
- 不自动回填旧 SolveRequest；
- downgrade 只允许在尚未运行 bootstrap、没有知识 Revision 的环境执行；
- 生产环境一旦存在 Revision，禁止通过 downgrade 删除历史。

### 8.6 B2 测试

- `tests/unit/test_knowledge_models.py`
- `tests/unit/test_knowledge_schemas.py`
- 迁移空库 upgrade/downgrade/upgrade；
- 013 → 014 → 015 副本升级；
- 外键、唯一约束、RESTRICT 和 nullable 兼容断言。

### 8.7 B2 门禁

- ORM metadata 与 PostgreSQL 015 一致；
- SQLite 全量建表通过；
- 原有 SQL 种子在 nullable 映射列下仍可加载；
- 014 数据升级 015 不改变旧业务行数量；
- Scope Guard 表、序列和行数不变。

## 9. B3：Snapshot Builder、初始化和审计

### 9.1 Projection Codec 注册

为第 3 节每个 Object Kind 实现：

- 旧 ORM → Canonical Envelope；
- Canonical Entry → 兼容投影；
- 依赖提取；
- 稳定身份读取；
- semantic/presentation 字段白名单；
- legacy 排除规则。

Codec 必须显式列字段，禁止对 ORM `__dict__` 全量序列化。

### 9.2 稳定键分配

历史行使用固定命名空间 UUIDv5：

```text
solver-legacy/<table>/<legacy-id>
```

合成关系使用：

```text
solver-relation/<relation-kind>/<source-entity-key>/<target-entity-key>
```

规则：

- 已有非空键不得重写；
- 重跑产生相同结果；
- 行级关系写回 `relation_key`；
- 合成关系只存在 Manifest，不要求创建旧投影行；
- 所有身份同步写入 `knowledge_identity`。

### 9.3 初始化

`scripts/bootstrap_knowledge_repository.py` 支持：

```text
--mode dry-run
--mode apply
--mode verify
--machine-type-id <optional>
--machine-id <optional>
--json
```

#### Dry-run

- 检查 014；
- 检查 Scope Guard 0/0；
- 检查 body/reference；
- 列出将分配的身份；
- 计算 Content Object 数量和去重率；
- 计算 B1/I1 Manifest Hash；
- 检查悬空关系和跨机台引用；
- 不写数据库。

#### Apply

- 对每个机台类型创建 `B-000001`；
- 对每个实例创建 `I-000001`；
- I1 复用 B1 的身份和内容对象；
- I1 追加实例配置、资源和日历快照；
- I1 的冻结基线指向对应 B1；
- 创建 `baseline_main`、`instance_head`；
- 不为旧 SolveRequest 伪造 Revision。

#### Verify

- 重算全部 Content/Manifest Hash；
- 检查 Entry 数量和唯一性；
- 检查 Ref 范围；
- 检查实例 Manifest 可独立加载；
- 检查相同基线内容复用率；
- 对比基线头兼容投影；
- 对比实例配置投影；
- 输出废弃数据排除统计。

### 9.4 实例与投影边界

这是实施中的硬边界：

- 基线头可以投影到现有机台类型级表；
- 实例基本信息、Resource 和 Calendar Mapping 可以投影到实例级表；
- 实例专属状态、活动、规则和关系只存在实例 Manifest；
- 任何实例提交不得修改共享 `StateNode/AtomicActivity/OpRule` 类型投影；
- enforced 求解必须读取实例 Manifest，不能回退到机台类型表解释实例变化。

### 9.5 审计脚本

`scripts/audit_knowledge_repository.py` 至少报告：

- identity/content/manifest/revision/ref 数量；
- Content Object 复用率；
- Manifest Hash 重算错误；
- 悬空 Entry；
- 范围错误 Ref；
- nullable 投影身份数量；
- 无头范围；
- 实例冻结基线错误；
- 被排除的 legacy/Scope Guard/维护意图数量；
- SolveRequest Revision 引用完整性。

### 9.6 B3 门禁

- dry-run 重复执行结果相同；
- apply 重复执行不产生第二套 B1/I1；
- verify 为 ready；
- 每个实例可独立加载；
- 原有投影内容未被意外修改；
- 原始数据库恢复验证通过。

## 10. B4：RevisionStore 只读能力和查询 API

### 10.1 RevisionStore 只读

实现：

- `load_revision`
- `get_entry`
- `verify`
- 按 Revision 加载完整 KnowledgeModel；
- Content Object 批量加载；
- 不可变 Revision 缓存；
- 缓存键只使用 `revision_id`；
- 完整性错误抛出 `KNOWLEDGE_INTEGRITY_FAILURE`。

### 10.2 查询 API

新增：

- `GET /api/v1/knowledge/scopes/{scope_kind}/{scope_id}/head`
- `GET /api/v1/knowledge/revisions/{revision_id}`
- `GET /api/v1/knowledge/revisions/{revision_id}/model`
- `GET /api/v1/knowledge/revisions/{revision_id}/graph`
- `GET /api/v1/knowledge/revisions/{revision_id}/validation`
- `GET /api/v1/knowledge/scopes/{scope_kind}/{scope_id}/history`
- `GET /api/v1/knowledge/revisions/{revision_id}/references`

History 和 References 使用游标分页，不返回无界集合。

Graph 只返回 `state_transition`。历史 Revision 图为只读，不调用当前表重新投影。

### 10.3 模式行为

| 模式 | 只读知识 API |
|---|---|
| off | 返回 `KNOWLEDGE_MODE_DISABLED`，运维 verify 除外 |
| shadow | 可读，用于对比，不改变旧 API |
| enforced | 正式读路径 |

### 10.4 B4 测试

- `tests/integration/test_knowledge_read_api.py`
- 头版本、历史、指定 Revision、模型和图；
- 旧版本在头移动后仍可读；
- 不存在 Revision；
- Manifest 损坏；
- 分页稳定；
- `state_transition` 唯一图模式；
- Scope Guard、维护意图、虚拟活动不出现在返回中。

## 11. B5：Validate、Commit、范围创建和兼容投影

### 11.1 Validate

`POST /knowledge/scopes/{kind}/{id}/validate`：

- 接收与 Commit 相同的 Change；
- 不写 Content、Manifest、Revision 或 Ref；
- 返回规范化变化、结构问题、求解阻断和提醒；
- 结构、健康和求解准备共享正式提交验证器。

### 11.2 Commit

按后端基线固定顺序实现：

1. 锁 Ref；
2. 检查期望头；
3. 检查幂等键；
4. 加载完整头 Manifest；
5. 校验身份和范围；
6. 应用 Change；
7. 内容去重；
8. 生成完整 Manifest；
9. 结构验证；
10. 健康和求解准备；
11. 创建 Revision；
12. 移动 Ref；
13. 更新允许的兼容投影；
14. 同一事务提交。

### 11.3 原子创建范围

新增：

- `POST /api/v1/knowledge/baseline-scopes`
- `POST /api/v1/knowledge/instance-scopes`

范围锚点、首 Manifest、首 Revision 和 Ref 必须同事务创建。失败不得留下无首版本的 MachineType 或 Machine。

### 11.4 幂等和 No-op

- 相同范围、相同幂等键、相同请求返回原结果；
- 相同幂等键、不同请求返回冲突；
- Manifest Hash 未变化返回 `KNOWLEDGE_NO_CHANGES`；
- 并发头变化返回 `KNOWLEDGE_HEAD_CONFLICT`；
- 不提供 force overwrite。

### 11.5 投影

#### 基线

当前基线头投影到：

- MachineType；
- StateFeatureDef；
- StateNode/StateNodeReference；
- ActivityNode/AtomicActivity/ActivityPackageAtomicRef；
- OpRule 及其子表；
- ActivityStateBinding；
- 基线允许的配置字段。

#### 实例

只投影：

- Machine；
- Resource；
- MachineStateDimensionCalendar；
- 默认工作日历和实例配置。

实例专属类型模型不投影到共享类型表。

### 11.6 旧写接口

新增统一守卫 `ensure_legacy_knowledge_write_allowed()`：

- off/shadow：旧写接口行为保持；
- enforced：所有会改变知识版本内容的旧写接口返回 `KNOWLEDGE_WRITE_REQUIRES_VERSION_COMMIT`；
- MachineState 等运行时接口继续允许；
- 工作日历库可以继续创建不可变日历修订，但机台所引用修订的变化必须走知识 Commit；
- 场景导入在 enforced 下必须先转换为知识 Change，再 Commit；
- 不在 enforced 下执行“先改旧表、再补 Revision”。

### 11.7 B5 测试

- `tests/integration/test_knowledge_commit_api.py`
- 首版本原子创建；
- 正常提交；
- no-op；
- 结构错误整体回滚；
- blocked 版本确认；
- 幂等重复；
- 幂等请求不一致；
- 两个并发会话只允许一个移动头；
- 基线投影；
- 实例专属模型不污染基线投影；
- 旧接口 mode guard；
- 导入在 enforced 下走 Commit。

## 12. B6：Diff、依赖闭包和版本引用

### 12.1 Diff API

实现：

```text
GET /api/v1/knowledge/diff
```

参数：

- from/to Revision；
- `include_presentation`；
- object kind filter；
- change kind filter；
- cursor/limit。

响应：

- add/modify/delete 总数；
- semantic/presentation 分类；
- 顶层字段差异；
- 关系端点摘要；
- 分页游标。

### 12.2 Dependency Closure

服务必须补齐：

- 新关系两端；
- 状态维度；
- 原子活动规则；
- 规则资源类型；
- 包成员两端；
- 删除对象所需关系删除。

缺少可安全补齐的删除时返回 `KNOWLEDGE_DEPENDENCY_INCOMPLETE`，不得额外删除目标基线数据。

### 12.3 References

按 Revision 查询：

- 冻结该基线的实例；
- 使用该 Revision 的 SolveRequest；
- 作为变更请求 Base/Ours/Theirs 的引用。

禁止物理删除任何仍被引用的 Revision。

### 12.4 B6 测试

- `tests/integration/test_knowledge_diff_api.py`
- `tests/integration/test_knowledge_references_api.py`
- 大结果分页；
- 字段选择；
- layout 默认排除；
- 改名不变身份；
- 关系端点 delete/add；
- 依赖原因；
- 引用统计。

## 13. B7：部分回写和实例升级

### 13.1 Change Request 状态机

```text
draft
→ conflict | ready
→ confirmed

draft/conflict/ready
→ cancelled

draft/conflict/ready
→ stale
```

Confirmed/Cancelled/Stale 为终态。

### 13.2 Writeback

三方输入：

```text
Base   = 实例当前冻结基线
Ours   = 基线主线当前版本
Theirs = 实例头选定变化
```

实现：

- preview；
- 自动依赖；
- 持久化变化项和冲突；
- resolve；
- 完整结果验证；
- confirm 时重锁基线头；
- 创建新基线 Revision；
- 原实例头和冻结基线保持不变。

Writeback confirm 的 reason 必填。

### 13.3 Upgrade

三方输入：

```text
Base   = 实例冻结基线
Ours   = 实例当前头
Theirs = 目标基线
```

实现：

- 目标基线归属校验；
- preview/resolve；
- 结果完整性和求解准备；
- confirm 时重锁实例头；
- 创建新实例 Revision；
- 新 Revision pin 目标基线；
- 原历史不变。

### 13.4 API

- `/knowledge/writebacks/preview`
- `/knowledge/writebacks/{id}`
- `/knowledge/writebacks/{id}/resolve`
- `/knowledge/writebacks/{id}/confirm`
- `/knowledge/writebacks/{id}/cancel`
- `/knowledge/upgrades/preview`
- `/knowledge/upgrades/{id}`
- `/knowledge/upgrades/{id}/resolve`
- `/knowledge/upgrades/{id}/confirm`
- `/knowledge/upgrades/{id}/cancel`

### 13.5 B7 测试

- `tests/integration/test_knowledge_writeback_api.py`
- `tests/integration/test_knowledge_upgrade_api.py`
- 无冲突自动合并；
- 同字段冲突；
- delete/modify；
- manual resolution；
- 未解决冲突禁止确认；
- stale；
- idempotent confirm；
- 回写不改变实例；
- 升级改变冻结基线并保留实例变化；
- blocked 结果确认；
- 事务失败无半成品。

## 14. B8：effective-model/v2、求解保存和重放

### 14.1 Resolver 重构

保留 `app/services/effective_model.py` 为唯一入口，拆成 provider：

```text
LegacyProjectionProvider → effective-model/v1
RevisionProvider         → effective-model/v2
```

正式 v2 输入：

- machine_id；
- instance Revision，默认 instance_head；
- canonical 原子活动范围；
- 目标状态范围；
- 当前状态和临时条件。

正式 v2 输出严格按后端基线，包括：

- baseline Revision；
- instance Revision；
- schema version；
- hash；
- summary；
- replay snapshot；
- expansion；
- health。

### 14.2 预检边界

- 实例求解预检和正式 solve 使用同一 RevisionProvider；
- 基线编辑只运行结构、模型健康和能力准备检查；
- 需要具体资源、日历和运行时状态的“求解预检”必须选择实例；
- Network Editor 不创建第二张 solver-ready 图。

### 14.3 模式行为

| 模式 | 求解行为 |
|---|---|
| off | 只使用 v1 |
| shadow | 同时生成 v1/v2，保存对比诊断，业务结果仍使用 v1 |
| enforced | 只允许正式实例 Revision 的 v2 |

Shadow 对比至少包含：

- 目标事实数；
- canonical 原子活动集合；
- 有效规则集合；
- blocking 数；
- 有效模型 Hash；
- 固定场景求解步序和 makespan。

### 14.4 SolveRequest

新求解写入专用列，同时在兼容窗口继续写 `overrides`：

- baseline/instance Revision；
- `effective-model/v2`；
- hash、summary、snapshot；
- 运行时快照；
- 日历快照。

计划调整创建子 SolveRequest 时必须继承原知识 Revision 和有效模型快照，不得改用当前 instance_head。

### 14.5 Replay API

- `GET /solve-requests/{id}/replay-input`
- `POST /solve-requests/{id}/replay`

Replay：

- 使用原知识 Revision；
- 使用原运行时快照；
- 不读取当前头替代；
- 输入不完整返回 `KNOWLEDGE_REPLAY_INPUT_INCOMPLETE`；
- 旧 v1 记录使用原兼容读取器；
- 返回原结果和新结果的可比较标识。

### 14.6 B8 测试

- `tests/integration/test_knowledge_effective_model.py`
- `tests/integration/test_knowledge_replay_api.py`
- 预检和 solve v2 hash 一致；
- 基线更新不改变冻结实例求解；
- 实例升级后求解使用新 Revision；
- blocked Revision 禁止求解；
- plan adjustment 继承原 Revision；
- v1 旧记录可读；
- replay 不偷用当前头；
- calendar snapshot 稳定。

## 15. B9：切换、发布门禁和回滚

### 15.1 配置

新增：

```text
KNOWLEDGE_REPOSITORY_MODE=off|shadow|enforced
```

默认 `off`。非法值启动失败，不静默回退。

系统状态返回：

- 当前 mode；
- 当前 Alembic；
- 是否已 bootstrap；
- 空身份数量；
- Manifest 完整性问题；
- 无头范围；
- shadow 差异摘要；
- enforced 准备状态。

### 15.2 off

- 旧读写和 v1 求解不变；
- 允许迁移和 dry-run；
- 正式知识 API 除运维审计外禁用。

### 15.3 shadow

- 完成 bootstrap；
- 开放知识只读 API；
- 新 v2 与 v1 同时解析并比较；
- 不改变业务求解响应；
- 知识写 API不对普通用户开放；
- Shadow 期间如旧主数据继续写入，必须重新运行受影响范围同步并记录新 shadow Revision；
- 最终切换前安排短维护窗口冻结旧主数据写入，执行最终同步和 verify。

### 15.4 enforced

前置条件：

- 015 已应用；
- Bootstrap/Verify ready；
- 所有版本化投影键非空；
- Scope Guard 0/0；
- 固定场景 v1/v2 结果符合接受的对比基线；
- 新知识写 API 全部通过；
- 前端已经切换到知识 Commit；
- 旧版本化写 API 已受 guard 保护；
- PostgreSQL 备份完成。

行为：

- RevisionStore 为知识权威；
- effective-model/v2 为求解权威；
- 旧知识写接口拒绝；
- 运行时状态接口继续允许；
- 不允许用旧表覆盖实例专属模型。

### 15.5 回滚

#### Schema 阶段

- 未 bootstrap 时可 downgrade 015；
- 已有 Revision 后不得 downgrade 删除历史；
- Schema 兼容问题优先回滚应用版本并保留 015 表。

#### off/shadow

- 可将 mode 改回 off；
- 旧路径仍为权威；
- 保留知识表供诊断。

#### enforced

- 在产生任何知识专属写入前，可以回退到 shadow/off；
- 一旦实例存在无法投影到旧类型表的专属知识，不能回退到 pre-knowledge 应用作为业务权威；
- 此后只允许回滚到上一版“仍能读取 RevisionStore”的应用；
- 禁止通过导出实例内容覆盖共享类型表来伪造回滚。

## 16. 测试矩阵

| 能力 | 单元 | SQLite API | PostgreSQL | 固定求解 |
|---|---:|---:|---:|---:|
| Canonical/Hash | 必须 | - | 重算 | - |
| Manifest/去重 | 必须 | 必须 | 必须 | - |
| Revision/Ref | 必须 | 必须 | 并发/锁 | - |
| 初始化 | 辅助 | - | 必须 | 必须 |
| Commit/投影 | 必须 | 必须 | 原子事务 | - |
| Diff/Closure | 必须 | 必须 | 分页 | - |
| Merge | 必须 | 必须 | stale/锁 | - |
| Writeback/Upgrade | 必须 | 必须 | 必须 | 可求解 |
| effective-model/v2 | 必须 | 必须 | 必须 | 必须 |
| Replay | 必须 | 必须 | 必须 | 必须 |
| Cutover | 必须 | mode API | 发布门禁 | shadow 对比 |

SQLite 测试不能替代 PostgreSQL 行锁、JSONB、约束和迁移证据。

### 16.1 稳定错误码实施归属

| `error_code` | 首次实现阶段 | 必测场景 |
|---|---|---|
| `KNOWLEDGE_REVISION_NOT_FOUND` | B4 | 读取不存在 Revision |
| `KNOWLEDGE_SCOPE_NOT_FOUND` | B4/B5 | 读取或提交不存在范围 |
| `KNOWLEDGE_MODE_DISABLED` | B4/B9 | off 下调用知识业务 API |
| `KNOWLEDGE_WRITE_REQUIRES_VERSION_COMMIT` | B5/B9 | enforced 下调用旧知识写接口 |
| `KNOWLEDGE_HEAD_CONFLICT` | B5 | 并发头变化 |
| `KNOWLEDGE_IDENTITY_CONFLICT` | B5 | UUID 重用或范围错误 |
| `KNOWLEDGE_IDEMPOTENCY_KEY_REUSED` | B5/B7 | 同键不同请求 |
| `KNOWLEDGE_CHANGE_REQUEST_STALE` | B7 | confirm 前目标头变化 |
| `KNOWLEDGE_MERGE_CONFLICT_UNRESOLVED` | B7 | 未解决冲突确认 |
| `KNOWLEDGE_REVISION_SOLVER_BLOCKED` | B8 | blocked Revision 求解 |
| `KNOWLEDGE_STRUCTURE_INVALID` | B5/B7 | 结构错误提交或合并 |
| `KNOWLEDGE_SOLVER_REVIEW_REQUIRED` | B5/B7 | 阻断未明确确认 |
| `KNOWLEDGE_DEPENDENCY_INCOMPLETE` | B6/B7 | 删除依赖无法安全补齐 |
| `KNOWLEDGE_NO_CHANGES` | B5 | Manifest Hash 未变化 |
| `KNOWLEDGE_REPLAY_INPUT_INCOMPLETE` | B8 | 历史运行时输入不足 |
| `KNOWLEDGE_INTEGRITY_FAILURE` | B4/B9 | Hash、Entry 或 Ref 完整性失败 |

## 17. 验证命令

### 17.1 静态与专项

```powershell
.venv\Scripts\python.exe -m compileall -q `
  app\core\knowledge `
  app\services\knowledge `
  app\services\effective_model.py `
  app\api\v1\knowledge.py `
  app\db\models.py `
  app\db\schemas.py
```

```powershell
.venv\Scripts\python.exe -m pytest tests\unit `
  -q -k knowledge --basetemp .pytest-tmp\t98-unit
```

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\integration\test_knowledge_read_api.py `
  tests\integration\test_knowledge_commit_api.py `
  tests\integration\test_knowledge_diff_api.py `
  tests\integration\test_knowledge_writeback_api.py `
  tests\integration\test_knowledge_upgrade_api.py `
  tests\integration\test_knowledge_effective_model.py `
  tests\integration\test_knowledge_replay_api.py `
  -q --basetemp .pytest-tmp\t98-integration
```

### 17.2 相关回归

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\integration\test_master_data_api.py `
  tests\integration\test_scenario_import_api.py `
  tests\integration\test_state_group_continuity.py `
  tests\integration\test_plan_adjustment_api.py `
  tests\integration\test_work_calendar_api.py `
  -q --basetemp .pytest-tmp\t98-related
```

### 17.3 全量

```powershell
.venv\Scripts\python.exe -m pytest -q `
  --basetemp .pytest-tmp\t98-full
```

不允许用 `pytest.skip` 逃逸 PostgreSQL、求解或迁移失败。

### 17.4 PostgreSQL 副本

```powershell
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe current
.venv\Scripts\python.exe scripts\check_scope_guard_zero.py
.venv\Scripts\python.exe scripts\audit_body_reference_model.py
.venv\Scripts\python.exe scripts\bootstrap_knowledge_repository.py --mode dry-run --json
.venv\Scripts\python.exe scripts\bootstrap_knowledge_repository.py --mode apply --json
.venv\Scripts\python.exe scripts\bootstrap_knowledge_repository.py --mode verify --json
.venv\Scripts\python.exe scripts\audit_knowledge_repository.py --strict --json
.venv\Scripts\python.exe scripts\check_deploy_readiness.py --strict-data --json
```

随后执行固定 Network Editor graph、实例预检、正式求解、SolveRequest 快照和 replay 验收。

### 17.5 性能

```powershell
.venv\Scripts\python.exe scripts\benchmark_knowledge_repository.py `
  --entries 10000 `
  --revisions 100 `
  --json
```

报告必须包含：

- CPU、内存、数据库版本；
- 冷/热缓存；
- Revision load；
- Manifest verify；
- Diff；
- Merge；
- API 序列化；
- 是否满足 1 万 Diff 目标。

## 18. 阶段验收与提交策略

每个阶段独立形成可审查提交，建议顺序：

1. `knowledge-domain-foundation`
2. `knowledge-schema-015`
3. `knowledge-bootstrap`
4. `knowledge-read-store-api`
5. `knowledge-commit-projection`
6. `knowledge-diff-dependencies`
7. `knowledge-writeback-upgrade`
8. `knowledge-effective-model-v2-replay`
9. `knowledge-cutover-verification`

禁止把 015、Commit、求解切换和回写全部堆在一个不可审查提交中。

## 19. 设计基线追踪矩阵

| 后端设计基线章节 | 实施阶段 | 主要证据 |
|---|---|---|
| 2 领域模型 | B0/B3/B5 | 首 B/I、完整实例、Ref |
| 3 内容边界 | B3/B8 | Codec 排除统计、v2 snapshot |
| 4 稳定身份 | B1/B2/B3 | UUID、改名、端点变化测试 |
| 5 规范内容 | B1 | canonical 单元测试 |
| 6 Manifest/Revision | B1/B2/B4/B5 | Hash、去重、历史读取 |
| 7 数据库设计 | B2 | 015 PostgreSQL 验收 |
| 8 RevisionStore | B4/B5/B6 | Store 接口测试 |
| 9 提交协议 | B5 | 并发、幂等、回滚 |
| 10 差异和依赖 | B1/B6 | Diff/Closure 测试 |
| 11 三方合并 | B1/B7 | 冲突矩阵 |
| 12 部分回写 | B7 | 基线新增、实例不变 |
| 13 实例升级 | B7 | 新实例 Revision 和 pin |
| 14 有效模型 | B8 | 预检/solve v2 hash |
| 15 求解重放 | B8 | replay API 和旧 v1 |
| 16 API | B4-B8 | OpenAPI/API 集成测试 |
| 17 错误码 | B4-B8 | 错误响应断言 |
| 18 幂等并发 | B5/B7 | PostgreSQL 行锁测试 |
| 19 初始化迁移 | B2/B3 | dry/apply/verify |
| 20 切换 | B9 | mode/status/release gate |
| 21 测试性能 | 全阶段 | 专项、全量、PG、benchmark |

## 20. 最终完成审计

只有以下证据全部存在，TICKET-098 后端任务才能标记完成：

- [ ] 015 在空库和 014 真实副本成功；
- [ ] 两份设计基线中的后端要求均有代码和测试对应；
- [ ] 所有 Object Kind Codec 已注册并经过往返验证；
- [ ] 首 B/I 初始化可重跑且实例可独立恢复；
- [ ] 内容去重和未变化引用复用有数据库证据；
- [ ] Commit 并发、幂等、No-op、阻断和事务回滚通过；
- [ ] Diff、依赖闭包和关系端点变化通过；
- [ ] Writeback 不改变原实例；
- [ ] Upgrade 保留实例变化并更新冻结基线；
- [ ] effective-model/v2 预检、solve、持久快照 Hash 一致；
- [ ] 历史 v1 可读，v2 可重放；
- [ ] off 模式原行为回归通过；
- [ ] shadow 对比有报告且不改变业务响应；
- [ ] enforced 在 API 测试环境通过全部写保护和求解门禁；
- [ ] Scope Guard 仍为 0/0 且未迁移；
- [ ] 活动包不进入求解；
- [ ] 后端全量测试 0 失败、0 跳过；
- [ ] PostgreSQL 固定业务验收通过；
- [ ] 1 万条性能报告满足设计目标；若目标需调整，必须先通过显式产品/架构决策更新后端设计基线；
- [ ] 原数据库恢复验证通过；
- [ ] TICKET 和 STATE 回写实际结果、命令和证据。

后端代码完成并不自动授权生产切换到 enforced。生产切换仍要求前端完成知识 Commit 工作流并通过联合验收。

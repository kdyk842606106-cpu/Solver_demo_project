# 机台知识库与版本变更管理 MVP：前后端贯通与发布计划

> Status: Planned
> Scope: MVP v1
> Date: 2026-07-28
> Ticket: [TICKET-098](../../TICKET_098.md)
> Frontend authority: [前端设计基线](../../机台知识库与版本变更管理_前端设计基线.md)
> Backend authority: [后端设计基线](../../机台知识库与版本变更管理_后端设计基线.md)
> Frontend plan: [前端开发与验收计划](./2026-07-28-machine-knowledge-frontend-mvp.md)
> Backend plan: [后端开发与验收计划](./2026-07-28-machine-knowledge-backend-mvp.md)

---

## 0. 计划定位

本文档定义前端和后端如何从独立开发进入真实贯通、业务验收和安全切换。

本文档解决：

- 前后端阶段依赖；
- 需要在编码前冻结的请求/响应契约；
- mock 与真实 API 的一致性；
- 共享测试数据和端到端业务场景；
- `off → shadow → enforced` 的联合门禁；
- 前端、后端、数据库和求解链路的回滚边界；
- 完成证据和责任归属。

本文档不授权：

- 立即执行 Alembic 015；
- 修改当前开发 PostgreSQL；
- 将生产环境切换为 `shadow` 或 `enforced`；
- 删除任何历史数据或 legacy 表；
- 在后端未 ready 时用前端逻辑替代 RevisionStore、依赖闭包或三方合并。

---

## 1. 联调总原则

1. 后端设计基线是 wire shape、错误码、版本和合并语义的权威。
2. 前端可以在后端阶段完成前使用契约 mock，但 mock-only 不算完成。
3. 每个用户写操作必须有一个明确后端事务边界。
4. 前端草稿不是后端 Revision，后端 Revision 也不是求解运行时快照。
5. 前端不读取 Manifest Entry 自行拼装权威模型。
6. 后端不为不同页面提供多套同义提交接口。
7. 预检和正式求解必须使用相同的 `effective-model/v2` 解析入口。
8. `shadow` 只证明一致性，不自动授权业务切换。
9. `enforced` 必须在前端新写入口、后端 guard 和最终同步同时 ready 后进行。
10. 一旦产生不能投影回旧表的实例专属知识，不允许回退到旧系统作为权威。

---

## 2. 阶段依赖总图

```text
后端 B0-B3：领域、015、初始化
        │
        ├────────── 前端 F0：路由、测试、能力门禁
        ▼
后端 B4：只读 Revision API
        │
        └────────── 前端 F1：只读知识工作区
                       │
                       ▼
                    I2 shadow 读取验收

后端 B5：范围创建、Validate、Commit
        │
        └────────── 前端 F2-F5：共享草稿、配置、模型、提交
                       │
                       ▼
                    I3 写入与并发验收

后端 B6：Diff、Dependency、References
        │
        └────────── 前端 F6：版本管理
                       │
                       ▼
                    I4 历史与差异验收

后端 B7：Writeback、Upgrade
        │
        └────────── 前端 F7：变更向导
                       │
                       ▼
                    I5 合并验收

后端 B8：effective-model/v2、Replay
        │
        └────────── 前端 F8：Revision 求解和重放
                       │
                       ▼
                    I6 求解一致性验收

后端 B9 + 前端 F9
        │
        ▼
I7 shadow 门禁、enforced 切换与回滚演练
```

阶段逐项映射：

| 后端阶段 | 前端阶段 | 联调阶段 |
|---|---|---|
| B0、B1、B2、B3 | F0 | I0、I1 |
| B4 | F1 | I2 |
| B5 | F2、F3、F4、F5 | I3 |
| B6 | F6 | I4 |
| B7 | F7 | I5 |
| B8 | F8 | I6 |
| B9 | F9 | I7 |

---

## 3. 交付责任矩阵

| 能力 | 后端负责 | 前端负责 | 联调共同证明 |
|---|---|---|---|
| 业务范围 | 原子创建、头 Ref、归属 | 选择器、创建向导 | 无无首版本半成品 |
| Revision 读取 | 不可变模型/图/验证 | 缓存、只读展示 | 头移动后旧版本仍一致 |
| 草稿 | Validate/Commit 输入语义 | 本地持有、叠加、恢复 | 草稿不被求解读取 |
| 提交 | 并发、幂等、事务、投影 | 状态机、说明、错误动作 | 失败无部分写入 |
| 差异 | 权威 diff、分页 | 分类、筛选、虚拟滚动 | 改名与关系端点语义一致 |
| 依赖 | 最小闭包和原因 | 展示并锁定必要项 | 不缺依赖、不额外选业务内容 |
| Merge | 三方合并、冲突、验证 | 解决冲突交互 | 同一三方输入结果一致 |
| 回写 | 创建新基线、实例不变 | 选择与确认向导 | 原实例头/冻结基线未变 |
| 升级 | 创建新实例、更新 pin | 目标选择和冲突向导 | 失败无半成品 |
| 求解 | v2 解析、快照、重放 | 运行时输入、版本提示 | precheck/solve hash 一致 |
| 切换 | mode、guard、审计 | 能力门禁、双入口兼容 | 无绕过知识 Commit 的写入 |

---

## 4. I0：API 契约冻结

I0 必须在前端 F1 和后端 B4 大规模编码前完成。

### 4.1 契约来源

使用 FastAPI OpenAPI 作为机器可检查契约，但不在 MVP 引入自动生成前端客户端。

新增或维护：

```text
tests/contract/test_knowledge_openapi.py
frontend/e2e/fixtures/knowledge-api.ts
scripts/check_knowledge_contract.py
```

职责：

- 后端测试确认路径、方法、必填字段和响应模型存在；
- 前端 fixture builder 只生成契约允许字段；
- 检查脚本对关键 JSON 示例和 OpenAPI 做字段存在性校验；
- 禁止测试 mock 长期拥有真实 API 不存在的便利字段。

### 4.2 通用错误 Envelope

所有知识 API 统一返回：

```json
{
  "error_code": "KNOWLEDGE_HEAD_CONFLICT",
  "message": "当前版本已更新",
  "details": {},
  "current_head_revision_id": "uuid-or-null"
}
```

联调要求：

- 不再把知识错误只放在字符串 `detail`；
- Axios 拦截器兼容旧 API 的嵌套错误，但新知识 API 测试必须断言顶层结构；
- 422 Pydantic 参数错误与领域 `KNOWLEDGE_STRUCTURE_INVALID` 可区分；
- 任何响应不得包含 SQL、堆栈或服务器路径。

### 4.3 范围创建

在后端 Schema 中冻结请求：

```json
{
  "idempotency_key": "uuid",
  "message": "创建首个机台类型基线",
  "allow_solver_blockers": false,
  "scope": {
    "entity_key": "uuid",
    "code": "MT-A",
    "name": "A 型机台",
    "description": ""
  },
  "frozen_baseline_revision_id": null,
  "changes": []
}
```

规则：

- baseline 创建的 `frozen_baseline_revision_id` 必须为空；
- instance 创建必须填写所属 machine type 和冻结基线；
- scope 锚点、首 Manifest、首 Revision 和 Ref 同事务；
- 返回真实 `scope_id`、业务版本号和 Revision；
- 前端 pending scope UUID 不作为后端 `scope_id`。

### 4.4 Head 响应

冻结最小结构：

```json
{
  "scope": {
    "scope_kind": "instance",
    "scope_id": "123",
    "machine_type_id": 10,
    "machine_id": 123
  },
  "head_revision": {
    "revision_id": "uuid",
    "revision_no": 8,
    "display_version": "I-000008",
    "solver_status": "ready"
  },
  "frozen_baseline_revision": {
    "revision_id": "uuid",
    "display_version": "B-000021"
  },
  "baseline_head_revision": {
    "revision_id": "uuid",
    "display_version": "B-000024"
  },
  "has_upgrade": true
}
```

基线范围的 frozen/baseline head 可为空或按 Schema 明确定义，不允许同一字段有多个类型。

### 4.5 Model 响应

冻结业务模型外壳：

```json
{
  "schema_version": "knowledge-model/v1",
  "revision": {},
  "entities": [],
  "relations": [],
  "configuration": {},
  "summary": {}
}
```

每个 entity/relation 至少有：

```text
identity_kind
identity_key
object_kind
content.semantic
content.presentation
```

前端不得依赖 Manifest Entry 的数据库行 ID。

### 4.6 Graph 响应

```json
{
  "view_mode": "state_transition",
  "revision_id": "uuid",
  "nodes": [],
  "edges": [],
  "summary": {
    "node_count": 0,
    "edge_count": 0,
    "truncated": false
  }
}
```

如果预计超过 1,000 个元素，后端应返回可筛选摘要或明确 `truncated`，前端不得假设一次拿到无界图。

### 4.7 Validate/Commit

请求：

```json
{
  "expected_head_revision_id": "uuid",
  "idempotency_key": "uuid",
  "message": "增加真空联调状态转移",
  "allow_solver_blockers": false,
  "changes": []
}
```

Validate：

- 接受相同 shape；
- `message` 可按 Schema 允许为空，但前端检查提交时仍要求；
- 不创建任何持久对象。

响应至少包含：

```text
normalized_changes
summary
structure_issues
health_issues
solver_issues
solver_status
can_commit
```

Commit 响应至少包含：

```text
revision
display_version
manifest_hash
validation
applied_change_count
current_head_revision
```

### 4.8 Diff

查询：

```text
from_revision_id
to_revision_id
include_presentation
object_kind
change_kind
cursor
limit
```

响应：

```json
{
  "summary": {
    "added": 0,
    "modified": 0,
    "deleted": 0
  },
  "items": [],
  "next_cursor": null,
  "truncated": false
}
```

每项必须携带足够的用户解释字段：

```text
identity_kind
identity_key
object_kind
change_kind
display_label
field_changes
relation_endpoint_summary
presentation_only
```

### 4.9 Writeback/Upgrade

Preview 请求共同字段：

```text
idempotency_key
source_revision_id
target_revision_id
selected_items
include_presentation
```

响应共同字段：

```text
request_id
status
base_revision
ours_revision
theirs_revision
selected_items
required_dependencies
conflicts
validation
result_summary
```

Resolve：

```json
{
  "resolutions": [
    {
      "identity_key": "uuid",
      "field": "semantic.duration_min",
      "choice": "ours|theirs|manual",
      "manual_value": null
    }
  ]
}
```

Confirm：

- 回写 `reason` 必填；
- 升级确认字段按后端 Schema 固定；
- 重复 confirm 返回原结果；
- stale 使用稳定错误码。

### 4.10 System status 握手

在既有 `/api/v1/system/status` 增加：

```json
{
  "knowledge_repository": {
    "mode": "shadow",
    "read_enabled": true,
    "write_enabled": false,
    "solve_v2_authoritative": false,
    "bootstrap_status": "ready",
    "identity_missing_count": 0,
    "manifest_issue_count": 0,
    "headless_scope_count": 0,
    "shadow_mismatch_count": 0,
    "enforced_ready": false
  }
}
```

前端不得从 Alembic 版本字符串自行推断能力。

### 4.11 I0 门禁

- OpenAPI 契约测试通过；
- 前端 fixture 与示例字段一致；
- 16 个错误码全部可构造和显示；
- 所有公开后端写操作有前端入口或明确标记为内部/运维；
- 没有 Scope Guard、维护意图、虚拟活动或命名分支字段。

---

## 5. I1：数据库、初始化和 off 模式联合基线

### 5.1 环境

使用当前 PostgreSQL 物理一致副本：

```text
013
→ 014_body_reference_unification
→ 015_knowledge_repository
```

不得直接以当前开发数据库做首次迁移验收。

### 5.2 后端动作

1. 应用 014 和 015；
2. `bootstrap dry-run`；
3. 核对稳定身份和排除项；
4. `bootstrap apply`；
5. `bootstrap verify`；
6. 确认 off 模式旧行为不变。

### 5.3 前端动作

- 系统状态显示知识模式 off；
- 不开放新知识写入口；
- 现有 DataManagement 和 v1 求解继续回归；
- 新路由直接访问时给出可理解的不可用状态；
- 不因 015 存在而误判断 ready。

### 5.4 数据断言

- Scope Guard 仍为 0/0；
- 维护意图和 legacy 虚拟活动不进入知识对象；
- T97 状态/活动引用审计仍通过；
- 每个机台类型有一个首基线；
- 每个机台实例有一个首实例 Revision 和冻结基线；
- 重复内容对象确实去重；
- 实例专属模型不投影覆盖共享类型表；
- 旧求解记录不被修改。

### 5.5 I1 门禁

- 迁移、bootstrap 和 verify 可重复；
- 原数据库恢复方式演练通过；
- off 模式 399+ 后端基线及前端现有回归无非预期变化；
- 新知识 API 在 off 下按设计禁用。

---

## 6. I2：shadow 只读贯通

### 6.1 目标

证明同一现有投影可以生成稳定 Revision，并由新前端按指定 Revision 正确读取，而不改变业务写入和求解权威。

### 6.2 流程

```text
后端 mode=shadow
→ 前端读取 system status
→ 打开只读知识工作区
→ 选择基线/实例
→ 读取 head/model/validation
→ 按需读取 graph/history/references
→ 与旧页面和旧图结果对比
```

### 6.3 联合断言

- 范围栏显示正确业务版本；
- 实例冻结基线和主线最新正确；
- Revision model 不包含运行时状态快照；
- graph 只有 `state_transition`；
- 同一 canonical 本体的多引用身份正确；
- 活动包不进入求解主链；
- 历史 Revision 在头移动后仍读取原内容；
- 相同 Revision 页面切换不重复取数；
- 旧写接口变化后，受影响范围重新同步生成新的 shadow Revision。

### 6.4 Shadow 差异

后端记录，前端技术状态可查看：

- 对象数；
- 关系数；
- canonical 原子活动集合；
- 规则集合；
- validation blocking 数；
- graph 节点/边数；
- Manifest 完整性。

不一致必须有稳定 issue code 和可定位范围。

### 6.5 I2 门禁

- B4 + F1 全部通过；
- 至少一个基线和一个实例真实读取；
- 历史只读真实浏览器通过；
- 只读页面不发知识写请求；
- shadow mismatch 为 0 或全部有经批准的解释记录。

---

## 7. I3：共享草稿、Validate、Commit 和范围创建

### 7.1 首个基线

端到端场景：

```text
新建机台类型
→ pending 草稿
→ 基本信息
→ 状态维度
→ 资源类型/日历引用
→ 状态包/原子状态
→ 活动包/原子活动/规则
→ input/output
→ validate
→ create baseline scope
→ B-000001
```

断言：

- scope、Revision、Ref 和投影同事务；
- 浏览器只发一次范围创建；
- 失败不留下空机台类型；
- 重试使用同幂等键返回同 Revision。

### 7.2 首个实例

```text
选择机台类型
→ 选择可求解基线
→ 配置具体机台、资源、日历
→ 按需新增实例模型变化
→ validate
→ create instance scope
→ I-000001
```

断言：

- 实例模型逻辑完整；
- 冻结基线记录正确；
- 实例专属状态/活动只存在实例 Manifest；
- 基线投影未被覆盖。

### 7.3 日常修改

在基础配置和模型构建之间编辑：

- 改名；
- 新增状态；
- 将状态引用到两个状态包；
- 新增原子活动和规则；
- 新增 input/output；
- 修改具体机器资源；
- 修改日历 Revision 引用；
- 调整布局。

一次 Commit 创建一个新 Revision。

### 7.4 并发

使用两个真实浏览器上下文：

1. A、B 都基于同一头进入编辑；
2. A 提交成功；
3. B 提交得到 `KNOWLEDGE_HEAD_CONFLICT`；
4. B 草稿仍存在；
5. B 查看新头并重新应用；
6. B 成功创建下一 Revision。

不得出现：

- force overwrite；
- B 草稿被清空；
- 投影与 Ref 不一致；
- 重复 Revision 号。

### 7.5 Excel

- dry-run 返回知识 Change；
- 前端加入当前草稿；
- 未 Commit 前数据库不变化；
- Commit 失败草稿仍在；
- enforced 下前端不调用旧直接导入。

### 7.6 I3 门禁

- B5 + F2–F5 全部通过；
- 首范围、日常提交、no-op、solver blocker、并发和幂等真实验证；
- Commit 后 Revision/Manifest/Ref/投影一致；
- T97 Network Editor 回归继续通过；
- 草稿不进入 solve 请求。

---

## 8. I4：历史、差异、引用和恢复

### 8.1 差异场景

构造连续三个版本：

```text
V1 原始对象和关系
V2 对象改名 + 新增对象 + 布局变化
V3 关系端点变化 + 删除对象
```

联合断言：

- 改名是 modify，同 `identity_key`；
- 关系端点是 delete old + add new；
- layout 默认不显示；
- 打开 layout 后归类为 presentation；
- 分页稳定且没有重复/漏项；
- 前端总数与后端 summary 一致。

### 8.2 引用

Revision 引用页显示：

- 冻结该基线的实例；
- 使用该 Revision 的 SolveRequest；
- 使用它作为 Base/Ours/Theirs 的变更请求。

头移动不改变历史引用。

### 8.3 历史恢复

恢复草稿生成方式：

1. 加载当前头模型；
2. 加载历史模型；
3. 使用权威 diff 确定身份集合；
4. 历史存在的身份写入历史完整内容 upsert；
5. 仅当前存在的身份写 delete；
6. 以当前头为基础进入本地草稿；
7. Validate；
8. Commit 新 Revision。

前端不得移动 Ref 到历史 Revision。

### 8.4 I4 门禁

- B6 + F6 通过；
- 10,000 diff 项分页和虚拟滚动通过；
- 历史模型与原 Revision Hash 一致；
- 恢复后生成新头，旧 Revision 未改变；
- 引用列表真实数据正确。

---

## 9. I5：部分回写和实例升级

### 9.1 共享三方测试数据

建立：

```text
Base B-000001
Baseline Main B-000002
Instance I-000002
```

包含：

- 只在基线变化的字段；
- 只在实例变化的字段；
- 两边结果相同的字段；
- 同字段不同修改；
- 删除/修改冲突；
- 新关系和必要端点；
- 关系端点变化；
- layout-only 变化；
- 原子活动引用的规则/资源依赖。

### 9.2 回写

验证：

- Base = 冻结基线；
- Ours = 基线当前主线；
- Theirs = 实例选定变化；
- 前端选择项与后端 request item 一致；
- 自动依赖有原因；
- layout 默认未选；
- 冲突解决后完整模型重新验证；
- confirm 创建新基线；
- 实例头和冻结基线不变。

### 9.3 升级

验证：

- Base = 实例冻结基线；
- Ours = 实例当前头；
- Theirs = 目标基线；
- 合并保留实例本地变化；
- confirm 创建新实例 Revision；
- 新实例 pin 目标基线；
- 旧实例 Revision 不变。

### 9.4 Stale 和幂等

两个关键测试：

1. Preview 后目标头变化，confirm 返回 stale，页面要求重新预览。
2. Confirm 响应丢失后重试，返回同一 Revision，不创建第二个版本。

### 9.5 事务故障注入

分别在以下点注入失败：

- 合并结果验证后；
- Content 写入后；
- Revision 创建后；
- Ref 移动前；
- 投影更新时。

断言：

- 数据库事务整体回滚；
- 前端不显示成功；
- request 状态可诊断；
- 原头保持。

### 9.6 I5 门禁

- B7 + F7 通过；
- 无冲突、字段冲突、delete/modify、manual、stale、幂等都真实通过；
- 必要依赖闭合；
- 回写不改实例；
- 升级原子更新实例头和冻结基线；
- 失败无半成品。

---

## 10. I6：effective-model/v2、正式求解和重放

### 10.1 Shadow 对比

在相同机台、当前状态、目标状态、活动范围、日历和临时条件下同时解析 v1/v2：

```text
目标事实数
canonical 原子活动集合
有效规则集合
blocking 数
步序
makespan
有效模型 Hash
```

差异必须分类：

- 预期语义变化；
- 数据初始化问题；
- 投影 codec 问题；
- resolver 问题；
- 求解非确定性或配置问题。

未经批准的差异不得进入 enforced。

### 10.2 正式求解

前端显式发送：

```text
machine_id
instance_revision_id
current_state_id / current state snapshot
target_state_id / target scope
canonical atomic activity scope
temporary availability
schedule_start_at
calendar context
```

后端保存：

- baseline Revision；
- instance Revision；
- v2 schema；
- effective model hash/summary/snapshot；
- 当前/目标/临时条件；
- 日历快照。

联合断言：

- precheck 和 solve 使用同一 instance Revision；
- precheck 和 solve hash 一致；
- 求解结果页面显示正确业务版本；
- 更新基线主线不改变未升级实例结果；
- 实例升级后新求解使用新 Revision。

### 10.3 计划调整

从已求解计划创建调整：

- 子 SolveRequest 继承原知识 Revision；
- 继承原有效模型和日历快照；
- 不读取当前 instance head 替换；
- 计划调整行为回归保持。

### 10.4 重放

测试：

1. 完整 v2 记录可重放；
2. 当前实例头已移动；
3. 当前基线头已移动；
4. 当前工作日历已有新 Revision；
5. 重放仍使用历史知识和历史运行时输入；
6. 原结果与新结果可比较；
7. 输入缺失返回 `KNOWLEDGE_REPLAY_INPUT_INCOMPLETE`；
8. 旧 v1 记录保持只读兼容。

### 10.5 日落检查

真实页面和 API 流量均不得出现：

- 维护意图模板读取；
- 维护意图求解；
- Scope Guard；
- 虚拟活动；
- Network Editor solver-ready 第二张图。

阻塞策略 A/B 和计划调整按独立业务契约验证。

### 10.6 I6 门禁

- B8 + F8 通过；
- 固定场景 v1/v2 shadow 对比达到接受基线；
- precheck/solve hash 一致；
- 冻结实例稳定；
- upgrade 后版本切换正确；
- plan adjustment 继承历史知识；
- replay 不偷用当前头；
- 旧 v1 记录可读。

---

## 11. I7：联合发布、切换和回滚

### 11.1 发布前状态

必须部署同一套支持双模式的前后端：

- 后端支持 off/shadow/enforced；
- 前端按 system status 自动选择兼容、只读或正式工作区；
- 旧知识写 API 已有 enforced guard；
- 新知识写 API 已完整；
- 应用版本即使回滚也能读取 RevisionStore。

### 11.2 off 发布

顺序：

1. 备份；
2. 发布支持 015 的应用；
3. 应用 014/015；
4. 保持 mode=off；
5. 验证旧业务；
6. dry-run。

退出条件：

- 旧 UI、旧求解无回归；
- Schema、身份、Manifest 审计可运行。

### 11.3 shadow 发布

顺序：

1. bootstrap apply/verify；
2. mode=shadow；
3. 开放前端只读知识工作区；
4. 持续记录 v1/v2；
5. 旧主数据发生写入时同步受影响范围；
6. 每日或每批次审计 mismatch。

退出条件：

- 所有业务范围有头；
- 身份缺失为 0；
- Manifest 完整性问题为 0；
- Scope Guard 0/0；
- 固定场景差异达到接受基线；
- 真实浏览器读路径稳定。

### 11.4 写入预演

在隔离环境或授权测试范围：

- 开放 `write_enabled`；
- 执行 I3–I6 全流程；
- 生成知识专属实例变化；
- 验证 enforced guard；
- 演练支持 RevisionStore 的应用版本回滚；
- 禁止把实例变化覆盖进共享类型表。

### 11.5 最终切换窗口

```text
进入短维护窗口
→ 冻结旧知识写入口
→ 最终同步受影响范围
→ bootstrap verify
→ v1/v2 固定场景复核
→ PostgreSQL 备份
→ mode=enforced
→ 前端读取新能力并启用知识工作区
→ 冒烟验收
→ 结束维护窗口
```

后端 mode 切换和前端能力刷新必须在同一维护窗口验证。

### 11.6 Enforced 冒烟

至少完成：

- 打开一个基线和一个实例；
- 创建一个无求解阻断的新版本；
- 历史比较；
- 一次实例升级预览并取消；
- 一次正式实例求解；
- 读取 replay input；
- 旧知识写接口返回 guard；
- MachineState 等运行时接口仍可写。

### 11.7 回滚矩阵

| 状态 | 允许回滚 | 禁止 |
|---|---|---|
| 015 未 bootstrap | 应用回滚；必要时按迁移规则 downgrade | 未核对目标就删除数据目录 |
| off | 回旧应用；保留 015 表 | 把未验证知识表当权威 |
| shadow | mode 回 off；旧投影仍权威 | 删除 shadow Revision 以隐藏差异 |
| enforced 尚无专属写 | 可回 shadow/off，需确认无专属内容 | 仅切前端而不切后端 guard |
| enforced 已有专属写 | 回到上一版支持 RevisionStore 的应用；可进入只读维护 | 回 pre-knowledge 应用作为业务权威 |

### 11.8 前端故障降级

- 新知识页面渲染故障但后端正常：进入只读维护页，不开放旧写。
- diff/图大数据故障：允许列表筛选和分页，不跳过版本语义。
- 回写/升级 UI 故障：禁止 confirm，不使用手工 API 临时绕过。
- 求解 UI 故障：历史数据不受影响；不得切回 v1 替代 enforced v2。

### 11.9 I7 门禁

- B9 + F9 通过；
- I0–I6 全部完成；
- 备份和恢复演练通过；
- 真实 PostgreSQL、真实浏览器、固定求解场景通过；
- 系统状态 `enforced_ready=true`；
- 旧写 guard 与新前端同时 ready；
- 获得单独生产切换确认。

---

## 12. 联调测试数据

### 12.1 最小业务数据集

至少包含：

- 1 个机台类型；
- 2 个实例；
- 2 个状态维度；
- 2 层状态包；
- 同一原子状态被两个包引用；
- 2 层活动包；
- 同一原子活动被两个包引用；
- 4 个原子活动；
- input/output 关系；
- 至少一个多资源需求；
- 默认日历和维度日历；
- 一个实例专属状态/活动变化。

### 12.2 冲突数据集

覆盖：

- rename；
- 不同字段并行修改；
- 同字段不同修改；
- delete/modify；
- relation endpoint change；
- layout-only；
- 缺失依赖；
- stale target head。

### 12.3 性能数据集

- 10,000 Manifest Entry；
- 10,000 diff item；
- 500 元素 graph；
- 1,001 元素 graph；
- 至少 200 个 Revision 历史；
- 至少 100 个 Revision 引用。

### 12.4 求解数据集

复用 T97 真实验收场景，并增加：

- 基线更新但实例未升级；
- 实例升级；
- v2 replay；
- plan adjustment 继承；
- 日历 Revision 后续变化。

---

## 13. 自动化执行层级

### 13.1 后端

```text
unit
→ SQLite integration 仅用于快速反馈
→ PostgreSQL integration
→ migration/bootstrap copy gate
→ solver fixed scenarios
```

涉及事务、约束、锁、迁移和性能的结论必须来自 PostgreSQL。

### 13.2 前端

```text
Vitest pure logic
→ component tests
→ Playwright contract mocks
→ Playwright real API
→ cross-browser focused
```

### 13.3 联合流水线

建议新增独立流水线：

```text
knowledge-contract
knowledge-postgres
knowledge-frontend-mock
knowledge-real-e2e
knowledge-solver-shadow
knowledge-performance
```

不得把所有联合验收塞进一个无法定位失败原因的单任务。

---

## 14. 联调可观测性

### 14.1 后端日志

知识写请求记录：

```text
request_id
idempotency_key
scope_kind
scope_id
expected_head
result_revision
change_count
duration_ms
status
error_code
```

不得记录完整知识内容、SQL、用户敏感字段或堆栈到普通响应。

### 14.2 前端诊断

技术详情可显示：

- 当前 mode；
- scope；
- head/viewed Revision；
- base Revision；
- request ID；
- error code；
- effective model schema/hash。

默认用户界面仍使用业务版本号和中文说明。

### 14.3 审计

每次阶段验收保存：

- 应用 commit；
- Alembic head；
- mode；
- bootstrap verify 摘要；
- 数据集版本；
- 浏览器和数据库版本；
- 测试结果；
- 固定求解 hash、步序和 makespan。

---

## 15. 公开写操作与前端入口审计

| 后端写操作 | 前端入口 | 其他用途 |
|---|---|---|
| create baseline scope | 新建机台类型向导 | 无 |
| create instance scope | 新建机台实例向导 | 无 |
| validate | 检查提交、恢复、向导验证 | 可内部复用 |
| commit | 检查提交 | 无直接实体按钮 |
| writeback preview | 回写向导 | 无 |
| writeback resolve | 回写冲突步骤 | 无 |
| writeback confirm | 回写最终确认 | 无 |
| writeback cancel | 回写向导取消 | 无 |
| upgrade preview | 升级向导 | 无 |
| upgrade resolve | 升级冲突步骤 | 无 |
| upgrade confirm | 升级最终确认 | 无 |
| upgrade cancel | 升级向导取消 | 无 |
| solve replay | 求解历史重放 | 无 |
| bootstrap apply | 无普通前端入口 | 仅运维 |
| verify | 系统状态只读摘要 | 脚本/运维 |

任何新增公开写 API 必须先更新本表和 TICKET-098。

---

## 16. 端到端业务验收清单

### 16.1 创建和建模

- [ ] 从空环境创建 B-000001。
- [ ] 从可求解基线创建 I-000001。
- [ ] 同一状态/活动本体多包复用。
- [ ] 基础配置和模型构建跨页保留草稿。
- [ ] Excel 只生成草稿。
- [ ] Network Editor 只有完整状态转移图。

### 16.2 版本

- [ ] Commit 产生不可变新 Revision。
- [ ] no-op 不产生 Revision。
- [ ] 幂等重试返回同 Revision。
- [ ] 并发冲突保留草稿。
- [ ] 历史版本只读。
- [ ] 历史恢复创建新头。
- [ ] 改名与关系端点 diff 正确。

### 16.3 变更治理

- [ ] 回写依赖闭合。
- [ ] 回写冲突可解决。
- [ ] 回写后实例不变。
- [ ] 升级保留实例变化。
- [ ] 升级更新冻结基线。
- [ ] stale 和事务失败无半成品。

### 16.4 求解

- [ ] 求解绑定正式实例 Revision。
- [ ] 草稿不进入求解。
- [ ] precheck/solve hash 一致。
- [ ] 基线主线更新不改变冻结实例。
- [ ] 实例升级后使用新 Revision。
- [ ] 计划调整继承原知识快照。
- [ ] 历史重放不读取当前头。

### 16.5 日落和边界

- [ ] Scope Guard 不进入知识/图/求解。
- [ ] 维护意图不出现在现行 UI 或求解流量。
- [ ] 虚拟活动不出现。
- [ ] 活动包不参与求解。
- [ ] 运行时状态和临时条件不进入知识 Revision。
- [ ] 实例专属模型不覆盖共享类型表。

---

## 17. 阶段证据模板

每个 I 阶段完成时在 TICKET-098 或 STATE 中记录：

```text
阶段：
应用 commit：
数据库来源与 Alembic：
KNOWLEDGE_REPOSITORY_MODE：
测试数据集：
后端测试：
前端单元/组件测试：
Mock E2E：
真实 API E2E：
PostgreSQL 审计：
求解对比：
性能：
已知限制：
回滚验证：
ANCHOR 检查：
```

未填写真实 API、PostgreSQL 或浏览器证据的适用阶段不得标记完成。

---

## 18. 最终完成条件

TICKET-098 只有在以下全部满足后才能关闭：

- [ ] B0–B9 全部完成。
- [ ] F0–F9 全部完成。
- [ ] I0–I7 全部完成。
- [ ] 两份设计基线和三份实施计划术语一致。
- [ ] API 契约、错误码和前端 fixture 一致。
- [ ] 所有公开写操作有入口或明确内部归属。
- [ ] 真实 PostgreSQL 014→015、bootstrap 和 verify 通过。
- [ ] 真实浏览器完成创建、提交、版本、回写、升级、求解和重放。
- [ ] 10,000 Entry、10,000 diff 和大图性能通过。
- [ ] shadow v1/v2 对比达到接受基线。
- [ ] enforced guard 证明旧知识写接口不可绕过。
- [ ] enforced 回滚路径在知识专属写入前后分别演练。
- [ ] Scope Guard 仍为 0/0，且没有相关迁移。
- [ ] 维护意图、虚拟活动和命名分支不在现行产品中。
- [ ] 活动包只管理原子活动引用，不参与求解。
- [ ] 预检、正式求解和 replay 使用可证明的历史知识版本。
- [ ] STATE 和 TICKET-098 回写完成。
- [ ] 生产切换另行获得明确授权。

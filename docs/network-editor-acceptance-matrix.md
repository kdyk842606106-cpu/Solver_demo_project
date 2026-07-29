# 网络编辑器 TICKET-097 验收矩阵

> 版本：V0.3
> 更新：2026-07-28
> 唯一业务画布：`state_transition`

## 1. 数据语义

| 编号 | 场景 | 验收结果 | 自动化证据 |
|---|---|---|---|
| DM-01 | 创建原子状态并加入状态包 | 原子状态 `parent_id=NULL`，成员关系保存为 `StateNodeReference` | `test_master_data_api.py` |
| DM-02 | 同一状态加入两个状态包 | 一个状态本体、两个引用 ID、两份引用 metadata | 图投影集成测试 |
| DM-03 | 创建原子活动并加入活动包 | 本体保存为 `AtomicActivity`，成员关系保存为 `ActivityPackageAtomicRef` | `test_master_data_api.py` |
| DM-04 | 同一活动加入两个活动包 | 一个活动本体、两个引用 ID、两份独立布局 | 图投影及 Chromium |
| DM-05 | 重复引用 | 同一包—本体唯一约束返回 409，不新增记录 | 主数据 API 测试 |
| DM-06 | 跨设备类型引用 | 返回 `REFERENCE_CROSS_MACHINE_TYPE` | 主数据 API 测试 |
| DM-07 | 改名或改码 | 本体、引用、绑定及规则 ID 均不变，revision 变化 | 主数据 API 测试 |
| DM-08 | 改换引用端点 | 更新被拒绝；必须删除旧引用并新建 | Schema/API 测试 |

## 2. 删除安全

| 编号 | 操作 | 验收结果 |
|---|---|---|
| DEL-01 | 从包移除成员 | 只删除引用，本体、规则、绑定和其他引用保留 |
| DEL-02 | 停用包内成员 | 只更新引用 `is_active=false` |
| DEL-03 | 删除有引用的本体 | 409 `BODY_IN_USE`，返回依赖类型和数量 |
| DEL-04 | 删除有绑定或规则的活动本体 | 409，不级联、不静默置空 |
| DEL-05 | 删除历史计划使用的本体 | 409，历史计划仍可重放 |
| DEL-06 | 删除未使用本体 | 204，其他实体不受影响 |
| DEL-07 | 删除包 | 可删除该包作为父端的成员引用，不删除被引用本体 |

## 3. 单一状态转移图

| 编号 | 场景 | 验收结果 |
|---|---|---|
| GP-01 | 默认打开 Network Editor | `view_mode=state_transition`，无业务视图切换器 |
| GP-02 | 请求旧 `outline` | 返回相同投影和 `LEGACY_VIEW_MODE_NORMALIZED` |
| GP-03 | 请求旧 `implementation` | 返回相同投影和弃用诊断 |
| GP-04 | 请求旧 `solver_ready` | 返回相同投影和弃用诊断 |
| GP-05 | 状态双包引用 | 两个 display ID，共用一个 canonical ID |
| GP-06 | 活动双包引用 | 两个 display ID，共用一个 canonical ID |
| GP-07 | 分别拖动两个引用 | 仅各自引用 metadata 变化 |
| GP-08 | 输入/输出边投影 | display 端点命中当前引用，canonical 端点不变 |
| GP-09 | 活动包 | 只在资源树和筛选器出现，不作为可执行转移节点 |
| GP-10 | 历史包级绑定 | 可审计，但不生成图边 |
| GP-11 | 求解预检 | 在同一画布结果面板显示，不切换投影 |

## 4. 统一提交

| 编号 | 场景 | 验收结果 |
|---|---|---|
| TX-01 | 新建本体、引用和绑定 | 同一事务全部写入 |
| TX-02 | 任一草稿非法 | 整批回滚，数据库无部分写入 |
| TX-03 | revision 冲突 | 409，草稿保留，提示重新加载 |
| TX-04 | 修改绑定端点或角色 | 删除旧绑定并创建新绑定，使用新关系 ID |
| TX-05 | 取消编辑 | 未提交本体、引用、绑定和布局全部恢复 |
| TX-06 | 引用布局提交 | 写入引用 metadata，不污染本体 metadata |

## 5. 有效模型与求解

| 编号 | 场景 | 验收结果 |
|---|---|---|
| SV-01 | 求解预检与正式求解 | 调用同一有效模型解析器 |
| SV-02 | 活动包筛选 | 边界层解析为明确的 canonical 原子活动 ID |
| SV-03 | 空活动范围 | 使用设备类型下全部启用原子活动 |
| SV-04 | 同一活动被多包引用 | 候选和计划步骤按 canonical ID 去重 |
| SV-05 | 调整活动包父级 | 候选、规则和有效前置条件不变 |
| SV-06 | 调整引用启停 | 不改变 canonical 有效模型 |
| SV-07 | 历史包级绑定 | 不生成事实、候选或计划步骤 |
| SV-08 | 保存求解请求 | 保存模型版本、摘要和 `effective-model/v1` 快照 |
| SV-09 | 当前模型后来变化 | 历史求解从保存快照读取，仍可重放 |
| SV-10 | Scheduler loader | 不选择“第一条活动包引用”作为隐式主分组 |

## 6. Scope Guard 日落门禁

| 编号 | 场景 | 验收结果 |
|---|---|---|
| SG-01 | 发布前只读检查 | `scope_guard=0` 且 `scope_guard_precond=0` |
| SG-02 | 新建、编辑或删除接口 | 返回 410 `SCOPE_GUARD_SUNSET` |
| SG-03 | 场景导入包含数据行 | 校验失败，不写数据库、不自动转换 |
| SG-04 | expansion/health/precheck/solve | 均不读取 Scope Guard 或活动包路径 |
| SG-05 | 非零部署环境 | 发布门禁失败并停止，不执行自动迁移 |
| SG-06 | 本票据数据库迁移 | 014 不包含 Scope Guard DDL/DML |

历史表保留只读审计。真实工艺准入条件必须表达为原子活动 `input` 状态绑定。

## 7. 已日落入口

| 编号 | 入口 | 验收结果 |
|---|---|---|
| SUN-01 | 多业务视图选择器 | 不存在 |
| SUN-02 | 活动包聚焦画布 | 不存在 |
| SUN-03 | 活动包级状态绑定 | 新建/编辑返回 `ACTIVITY_PACKAGE_BINDING_SUNSET` |
| SUN-04 | 活动包在 Network Editor 新建/编辑 | 不存在；统一到活动能力页面 |
| SUN-05 | `ActivityNode(level=3)` 新建 | 被拒绝，只读兼容 |
| SUN-06 | 包级实现覆盖率及声明输出统计 | 不再出现在用户界面 |

## 8. 数据库迁移 013 → 014

| 编号 | 检查 | 通过标准 |
|---|---|---|
| MIG-01 | 迁移前备份 | 可恢复备份已验证 |
| MIG-02 | 历史原子状态直接挂包 | 转换为引用，`parent_id` 置空 |
| MIG-03 | 排序、启用和布局 | 迁移到新引用；已有引用 metadata 不覆盖 |
| MIG-04 | 非 aggregate `parent_id` 约束 | 迁移后数量为 0 |
| MIG-05 | 本体外键 | 被引用、绑定或规则使用时为 `RESTRICT` |
| MIG-06 | 包侧引用外键 | 删除包可清理成员关系，但不删除本体 |
| MIG-07 | Scope Guard | 不读、不写、不迁移 |
| MIG-08 | 降级 | 只恢复约束/外键，不把多引用自动折叠回单一父级 |

迁移必须先在独立 PostgreSQL 副本执行。未取得明确授权时，不在当前开发库运行升级。

## 9. 自动化门禁

发布证据至少包含：

1. `scripts/check_scope_guard_zero.py`；
2. `scripts/audit_body_reference_model.py`；
3. 语义 helper 单元测试；
4. 主数据、分层求解、场景导入聚焦集成测试；
5. 全量后端测试；
6. Vite production build；
7. Chromium Network Editor 与完整业务流测试；
8. 真实 PostgreSQL 013 → 014 升级、current head 和迁移后审计；
9. `scripts/check_terminology.py`；
10. `git diff --check`。

任何一项未通过时，TICKET-097 不得标记完成。当前开发库若仍停留 013，应明确记录为“代码完成、数据库发布验收待执行”，不得伪报完成。

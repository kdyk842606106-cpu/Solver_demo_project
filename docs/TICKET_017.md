# TICKET-017: V0.3 数值型重复步骤与阻塞重排兼容性修复

> 状态：已完成 — 2026-04-21
> 对应版本：V0.3
> 对应阶段：数值型状态规划与阻塞能力交叉验证
> 前置依赖：`docs/TICKET_016.md` 已完成
> 预估工作量：1-2 次对话
> 当前状态：已完成

---

## 本次任务范围（只做这些）

验证并修复“阻塞能力”与当前 numeric Phase 1 实现的交叉兼容性，覆盖：

1. numeric 重复步骤场景下 Strategy A / AB 的阻塞定位歧义
2. numeric 重复步骤场景下 step_role diff 的错配问题
3. numeric + blockage 的交叉回归测试补齐
4. 在不破坏现有 enum / numeric 初始求解链路前提下完成最小修复
5. 文档回写：STATE/TICKET 状态同步

---

## 子任务清单

```text
[✅] A  补充交叉场景测试：numeric repeated steps + blockage A/AB
[✅] B  修复 Strategy A/AB 的 blocked step 定位歧义
[✅] C  修复 step_role diff 对重复 op_rule_id 的错配
[✅] D  验证 numeric + Strategy B / mixed 场景保持兼容
[✅] E  运行相关测试并修复问题
[✅] F  文档回写：STATE/TICKET 状态同步
```

---

## 验收标准

```text
✅ numeric 重复步骤在 Strategy A/AB 下可稳定定位到具体步骤实例
✅ 重复 op_rule_id 的 step_role diff 不再依赖单一 op_rule_id 映射
✅ enum 场景与 numeric 初始求解场景回归不退化
✅ numeric + blockage 交叉测试至少覆盖 A、B、AB 三类场景
```


---

## 本次不做（明确排除）

- 不引入新的数值目标 API
- 不重构 Scheduler 核心建模
- 不新增大规模解释字段
- 不改 `target_state` 语义
- 不扩展 `primary_feature` 主方案

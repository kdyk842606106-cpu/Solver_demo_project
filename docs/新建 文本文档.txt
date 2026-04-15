---
# STEP 2 准出审视报告
## 总体结论：有条件通过（1 项阻塞 + 2 项必须修复）
功能实现层面 STEP 2 的 9 个子任务全部完成，ANCHOR 硬性约束无违反，STATE 文档悬挂问题 #1-#3 均已解决。但测试层面存在 **1 项阻塞级问题** 和 **2 项必须修复的代码缺陷**，不满足 TICKET-005 定义的验收门禁。
---
一、通过项（22/25 检查点）
功能子任务（9/9 ✅）
子任务	状态	关键证据
2-1 OperatorRegistry + 7 Operator	✅	operators.py 装饰器注册，无 if/elif，数值自动 float() 转换
2-2 EffectRegistry + 3 Effect	✅	effects.py 装饰器注册，值计算纯函数
2-3 RuleEvaluator	✅	rule_evaluator.py 统一入口，dict(state) 浅拷贝保证不可变
2-4 RAGBuilder 升级	✅	search.py:212-213 调用 RuleEvaluator，has_cycle() DFS 三色检测，max_ops=50
2-5 ObjectiveRegistry	✅	objectives.py 装饰器注册，空数组兜底 minimize_makespan
2-6a Scheduler not_before	✅	model.py:110-112 注入 start >= not_before 约束
2-6b Scheduler objectives 数组	✅	model.py:121-124 通过 ObjectiveRegistry.apply_all 支持
2-7a 阻塞处理编排	✅	solve.py:82-195 策略 A/B/AB 完整编排
2-7b step_role 计算	✅	step_role.py:129-146 4 种角色，求解后 diff 计算
ANCHOR 合规（6/6 ✅）
约束	状态
约束1: RuleEvaluator 统一入口	✅
约束2: 零侵入扩展	✅
约束3: 状态不可变	✅
约束4: 阻塞不侵入 RAGBuilder	✅
约束8: step_role 后置 diff	✅
约束13: 注册表装饰器模式	✅
STATE 悬挂问题（3/3 已解决）
问题	状态	证据
#1 solver.py 阻塞 event loop	✅	solver.py:118 — asyncio.to_thread(solver.solve, ...)
#2 search.py 硬编码 ==	✅	search.py:212-213 — evaluator.evaluate_precondition()
#3 领域层直接 commit	✅	search.py 和 solver.py 均改为 flush()，commit 由 API 层控制
TICKET-005 D1-D7 修复（7/7 ✅）
缺陷	状态
D1 test_objectives.py	✅
D2 pulled_forward/delayed 测试	✅
D3 策略 AB >= 2 测试	✅
D4 step_role 非 repair=normal	✅
D5 solve.py try/except	✅
D6 solver/init.py	✅
D7 objectives.py 无未使用 import	✅
---
二、不通过项（3 项）
阻塞级：Q3 违规 — pytest.skip 逃逸 infeasible（17 处）
文件: tests/integration/test_blockage_strategies.py
具体位置: 行 193, 235, 306, 362, 483, 518, 550, 590, 622, 669, 691, 734, 749, 764, 782 等共 17 处
问题: 几乎所有集成测试都包含如下模式：
if sched_result.status == "infeasible":
    pytest.skip(f"Scheduler returned infeasible: ...")
违反条款: TICKET-005 验收门禁 Q3 明确规定：
> "集成测试中不允许用 pytest.skip 逃逸 scheduler infeasible（测试数据必须保证 feasible）"
同时违反 G1："0 失败、0 跳过"。如果种子数据/资源配置有问题导致 scheduler 返回 infeasible，所有这些测试将静默跳过而非报错，测试形同虚设。
修复建议: 
1. 确保种子数据中资源配置（Resource 容量、is_required）能保证所有测试场景 feasible
2. 将所有 pytest.skip(...) 替换为断言：
assert sched_result.status in ("optimal", "feasible"), \
    f"Expected feasible schedule, got {sched_result.status}: {sched_result.error_message}"
3. 对 build_rag 返回 no_solution 的也同样处理（行 381, 394, 749, 764）
---
必须修复：TestStrategyAB 类重复定义
文件: tests/integration/test_blockage_strategies.py:316 和 :435
问题: 同一文件中定义了两个 class TestStrategyAB。Python 类重定义行为导致：
- 第一个 TestStrategyAB（行 316-364，1 个测试）被完全覆盖，是死代码
- 只有第二个 TestStrategyAB（行 435-563，2 个测试）会被 pytest 收集执行
虽然第二个类的测试断言更强，但第一个类的存在是明确的代码错误，会误导审阅者以为有 3 个 AB 测试实际只有 2 个。
修复建议: 删除第一个 TestStrategyAB 类（行 316-364），或将其重命名为 TestStrategyABBasic 以保留。
---
必须修复：search.py 死导入
文件: app/core/planner/search.py:29
from app.core.planner.executor import effects_satisfy_precondition  # 未使用
effects_satisfy_precondition 被导入但在 search.py 中从未调用。这是一个遗留死导入，类似于 TICKET-005 D7 修复的 objectives.py 死导入，应当一并清理。
---
三、建议改进项（非阻塞）
#	严重度	问题
1	中	model.py ↔ objectives.py 循环依赖，靠延迟导入 workaround
2	中	parent_steps_by_rule dict 覆盖——同 op_rule_id 多步骤时只保留最后一个
3	低	RuleEvaluator() 在循环内每次 precond 新建实例
4	低	apply_effects() 多余的初始 dict(state) 拷贝
5	低	solve.py 遗留单 objective 枚举校验与新 objectives 数组并存
6	信息	BlockageEvent.blocked_step_id 可能为 None（步骤匹配失败时）
---
四、测试数量核验
类别	要求
Operator 单元测试	>= 7
Effect 单元测试	>= 3
RuleEvaluator 单元测试	>= 3
Objective 单元测试	>= 5
step_role 测试（4 种角色）	4 种
策略 A 集成测试	>= 2
策略 B 集成测试	>= 2
策略 AB 集成测试	>= 2
循环检测测试	>= 1
数值比较测试	>= 2
---
五、准出判定
结论：不通过 — 需修复 3 项后重新审视
必须修复的 3 项清单：
1. 阻塞 移除全部 17 处 pytest.skip infeasible 逃逸，替换为 assert 失败，确保种子数据保证 feasible
2. 必须 修复 TestStrategyAB 重复类定义（删除或重命名第一个）
3. 必须 清理 search.py:29 死导入 effects_satisfy_precondition
预估修复工作量：1 个 TICKET，1 次对话可完成。
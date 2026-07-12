# TICKET-019: 启动脚本统一收敛与模式分流

> 对应版本：V0.3
> 对应阶段：开发机启动脚本收敛
> 前置依赖：`docs/TICKET_018.md` 已完成
> 预估工作量：1 次对话
> 当前状态：已完成

---

## 本次任务范围（只做这些）

将现有 Windows 启动入口统一收敛到同一套 PowerShell 启动逻辑，覆盖：

1. `start.bat` 继续保留 Docker 模式，但委托同一 launcher
2. `start.local.bat` 迁移到共享 launcher
3. `start.intranet.bat` 继续复用共享 launcher
4. 共享 launcher 支持模式分流，不改业务逻辑
5. 文档回写：STATE/TICKET 状态同步

---

## 子任务清单

```text
 [✅] A  为 launcher 增加 mode 参数与分支
 [✅] B  让 start.bat / start.local.bat 统一调用 launcher
 [✅] C  保持 intranet / local / docker 三种入口兼容
 [✅] D  运行启动脚本相关检查并修复问题
 [✅] E  文档回写：STATE/TICKET 状态同步
```

---

## 验收标准

```text
✅ start.bat / start.local.bat / start.intranet.bat 都指向同一套 launcher
✅ Docker / local / intranet 三种模式行为可区分
✅ 不影响现有后端/前端启动逻辑
✅ 不引入业务 API 变更
```

---

## 本次不做（明确排除）

- 不改数据库 schema
- 不改前端业务页面
- 不引入新的依赖管理方案
- 不改 seed 内容

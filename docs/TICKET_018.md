# TICKET-018: 内网开发机一键启动架构

> 对应版本：V0.3
> 对应阶段：开发机部署体验增强
> 前置依赖：`docs/TICKET_017.md` 已完成
> 预估工作量：1 次对话
> 当前状态：已完成

---

## 本次任务范围（只做这些）

为公司内网开发机提供一键启动前后端的轻量扩展架构，覆盖：

1. Python 依赖使用公网 `pip install` 正常安装
2. npm 使用公司内网镜像进行安装
3. PostgreSQL 复用既有环境，不引入 Docker / request / 外部下载式数据加载
4. 首次环境准备与日常启动拆分为 bootstrap / launch 两阶段
5. 提供 `start.intranet.bat` 一键入口
6. 更新 README 使用说明

---

## 子任务清单

```text
[✅] A  设计并落地 bootstrap / launch 两阶段脚本
[✅] B  新增 start.intranet.bat 一键入口
[✅] C  固定项目级 npm registry 使用方式
[✅] D  复用现有 PostgreSQL 与迁移/seed 流程
[✅] E  更新 README 使用说明
[✅] F  文档回写：STATE/TICKET 状态同步
```

---

## 验收标准

```text
✅ 开发机可通过一次启动流程拉起后端与前端
✅ 不依赖 Docker
✅ 不需要 request/HTTP 方式加载数据
✅ npm 按公司内网镜像安装
✅ PostgreSQL 复用既有环境
```

---

## 本次不做（明确排除）

- 不做 PostgreSQL 自动安装
- 不做离线 wheel / npm bundle
- 不做生产部署编排
- 不改业务 API 逻辑
